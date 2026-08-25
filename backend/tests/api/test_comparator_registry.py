"""Comparator registry — M12 section 10.

Against a real database, like the other integration tests: the interesting
behaviour is transactional (promotion is atomic, re-promotion updates in
place, the guard reads what was actually written), and none of that can be
observed against a fake.

Every test cleans up after itself through `registered`, so a failing run does
not leave rows behind that the next one trips over.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from biet_api.dal import session_factory
from biet_api.exceptions import (
    ComparatorNotPricedError,
    ConflictError,
    EntityNotFoundError,
    ValidationError,
)
from biet_api.schemas.comparator import (
    AssetIntake,
    MarketApprovalIn,
    PriceIn,
    PromotionRequest,
    RegimenIn,
)
from biet_api.services.comparator_registry_service import ComparatorRegistryService


def _database_available() -> bool:
    try:
        with session_factory() as probe:
            probe.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(),
    reason="needs the local PostgreSQL instance (see STATUS.md section 5.1)",
)

#: Distinct enough that the cleanup below cannot match a seeded row.
PREFIX = "M12TEST"
OBESITY = 1
DIABETES = 2


def _intake(name: str = f"{PREFIX}-DRUG", **over: object) -> AssetIntake:
    base: dict[str, object] = {
        "source_id": f"CHEMBL_{name}",
        "asset_name": name,
        "indication_id": OBESITY,
        "target_symbol": "GLP1R",
        "max_clinical_stage": "APPROVAL",
        "competitor_class": "direct",
        "relevance": 0.9,
        "rationale": "registered by a test",
        "source": "open_targets",
    }
    base.update(over)
    return AssetIntake(**base)  # type: ignore[arg-type]


def _regimen(source: str = "label") -> RegimenIn:
    return RegimenIn(
        dose_amount=2.4, dose_unit="mg", units_per_admin=1, admins_per_year=52,
        wastage_pct=0.0, persistence_12m=0.65, source=source, confidence_tier="B",
    )


def _price(country: str = "USA", currency: str = "USD", amount: float = 1349.0) -> PriceIn:
    return PriceIn(
        country_code=country, price_local=amount, currency_code=currency,
        price_basis="list", source="test", confidence_tier="B",
    )


def _purge(session: Session) -> None:
    session.execute(text(
        "DELETE FROM comparator_approvals WHERE asset_id IN "
        "(SELECT asset_id FROM comparator_assets WHERE asset_name LIKE :p)"
    ), {"p": f"{PREFIX}%"})
    session.execute(text(
        "DELETE FROM comparator_assets WHERE asset_name LIKE :p"), {"p": f"{PREFIX}%"})
    for table in ("drug_prices", "drug_regimens"):
        session.execute(text(
            f"DELETE FROM {table} WHERE drug_id IN "
            "(SELECT drug_id FROM drugs WHERE drug_name LIKE :p)"
        ), {"p": f"{PREFIX}%"})
    session.execute(text("DELETE FROM drugs WHERE drug_name LIKE :p"), {"p": f"{PREFIX}%"})
    session.commit()


@pytest.fixture
def session() -> Iterator[Session]:
    with session_factory() as s:
        _purge(s)
        try:
            yield s
        finally:
            s.rollback()
            _purge(s)


@pytest.fixture
def service(session: Session) -> ComparatorRegistryService:
    return ComparatorRegistryService(session)


# --------------------------------------------------------------------------- registration


def test_registering_the_same_molecule_twice_returns_one_record(
    service: ComparatorRegistryService,
) -> None:
    """Running discovery twice is ordinary, not a conflict."""
    first = service.register(_intake())
    second = service.register(_intake())
    assert second.asset_id == first.asset_id


def test_the_same_molecule_in_two_indications_is_two_records(
    service: ComparatorRegistryService,
) -> None:
    """Line of therapy, comparator set and relevance all differ between
    indications, so they are different records (M12 section 5.2)."""
    obesity = service.register(_intake())
    diabetes = service.register(_intake(indication_id=DIABETES))
    assert obesity.asset_id != diabetes.asset_id


def test_re_registration_fills_gaps_without_erasing_what_is_there(
    service: ComparatorRegistryService,
) -> None:
    service.register(_intake(brand_name="Original"))
    merged = service.register(_intake(brand_name="Replacement", manufacturer="Acme"))
    assert merged.brand_name == "Original", "a curated value is not overwritten"
    assert merged.manufacturer == "Acme", "but a gap is filled"


def test_registering_against_an_unknown_indication_is_rejected(
    service: ComparatorRegistryService,
) -> None:
    with pytest.raises(ValidationError):
        service.register(_intake(indication_id=9999))


def test_registration_links_a_molecule_this_system_already_prices(
    service: ComparatorRegistryService,
) -> None:
    """Semaglutide is seeded. Registering it should arrive already usable
    rather than needing a price entered that exists two tables away."""
    asset = service.register(_intake(name=f"{PREFIX}-X", asset_name="semaglutide"))
    assert asset.drug_id is not None
    assert asset.is_promoted


# --------------------------------------------------------------------------- promotion gaps


def test_an_unpromoted_asset_names_both_gaps(service: ComparatorRegistryService) -> None:
    asset = service.register(_intake())
    assert set(asset.missing_for_promotion) == {"regimen", "price"}


def test_gaps_are_named_per_market(service: ComparatorRegistryService) -> None:
    """"Needs a German price" is actionable; "not ready" is not
    (M12 section 5.4)."""
    asset = service.register(_intake(approvals=[
        MarketApprovalIn(country_code="USA", source="FDA"),
        MarketApprovalIn(country_code="DEU", source="EMA"),
    ]))
    promoted = service.promote(
        asset.asset_id, PromotionRequest(regimen=_regimen(), prices=[_price("USA")]),
    )
    assert promoted.missing_for_promotion == ["price:DEU"]


# --------------------------------------------------------------------------- promotion


def test_promotion_makes_the_asset_usable(service: ComparatorRegistryService) -> None:
    asset = service.register(_intake())
    promoted = service.promote(
        asset.asset_id, PromotionRequest(regimen=_regimen(), prices=[_price()]),
    )
    assert promoted.is_promoted
    assert promoted.drug_id is not None
    assert promoted.missing_for_promotion == []


def test_promotion_is_atomic_when_a_price_is_rejected(
    service: ComparatorRegistryService, session: Session,
) -> None:
    """A comparator with a regimen and no price is not usable, so a failing
    price must leave no `drugs` row behind (M12 section 5.3)."""
    asset = service.register(_intake())
    session.flush()

    with pytest.raises(ConflictError):
        service.promote(asset.asset_id, PromotionRequest(
            regimen=_regimen(), prices=[_price(currency="EUR")],
        ))

    session.rollback()
    remaining = session.execute(
        text("SELECT count(*) FROM drugs WHERE drug_name LIKE :p"), {"p": f"{PREFIX}%"},
    ).scalar()
    assert remaining == 0


def test_a_price_in_the_wrong_currency_for_its_market_is_refused(
    service: ComparatorRegistryService,
) -> None:
    """A euro price filed against the USA would compute a plausible, wrong
    annual cost — the failure mode this system exists to prevent."""
    asset = service.register(_intake())
    with pytest.raises(ConflictError) as exc:
        service.promote(asset.asset_id, PromotionRequest(
            regimen=_regimen(), prices=[_price(currency="EUR")],
        ))
    assert "USD" in str(exc.value)


def test_an_estimated_net_price_must_state_its_gross_to_net_ratio(
    service: ComparatorRegistryService,
) -> None:
    asset = service.register(_intake())
    price = _price().model_copy(update={"price_basis": "estimated_net"})
    with pytest.raises(ValidationError):
        service.promote(
            asset.asset_id, PromotionRequest(regimen=_regimen(), prices=[price]),
        )


def test_an_unknown_market_is_refused(service: ComparatorRegistryService) -> None:
    asset = service.register(_intake())
    with pytest.raises(ValidationError):
        service.promote(asset.asset_id, PromotionRequest(
            regimen=_regimen(), prices=[_price(country="ZZZ")],
        ))


def test_re_promotion_updates_in_place_rather_than_duplicating(
    service: ComparatorRegistryService,
) -> None:
    """`uq_drugs_name` would reject a duplicate anyway; failing on a unique
    constraint is not an acceptable way to express a business rule."""
    asset = service.register(_intake())
    first = service.promote(
        asset.asset_id, PromotionRequest(regimen=_regimen(), prices=[_price()]),
    )
    second = service.promote(
        asset.asset_id,
        PromotionRequest(regimen=_regimen("label v2"), prices=[_price(amount=1500.0)]),
    )
    assert second.drug_id == first.drug_id
    assert len(service._assets.list_prices(second.drug_id or 0)) == 1


def test_promoting_an_unknown_asset_is_a_not_found(
    service: ComparatorRegistryService,
) -> None:
    with pytest.raises(EntityNotFoundError):
        service.promote(999_999, PromotionRequest(regimen=_regimen(), prices=[_price()]))


# --------------------------------------------------------------------------- the guard


def test_the_guard_raises_for_an_unpromoted_comparator_and_names_it(
    service: ComparatorRegistryService,
) -> None:
    """Dropping it instead would mean its cost is never subtracted from the
    world-without, overstating budget impact by exactly the cost of the care
    the new therapy displaces (M12 section 5.6)."""
    asset = service.register(_intake())
    with pytest.raises(ComparatorNotPricedError) as exc:
        service.require_promoted([asset.asset_id])
    assert f"{PREFIX}-DRUG" in str(exc.value)


def test_the_guard_passes_once_promoted(service: ComparatorRegistryService) -> None:
    asset = service.register(_intake())
    service.promote(asset.asset_id, PromotionRequest(regimen=_regimen(), prices=[_price()]))
    service.require_promoted([asset.asset_id])


def test_the_guard_reports_an_asset_that_does_not_exist_at_all(
    service: ComparatorRegistryService,
) -> None:
    """A missing asset and an unpriced one are different problems and must
    not share a message."""
    with pytest.raises(EntityNotFoundError):
        service.require_promoted([999_999])


def test_the_guard_accepts_an_empty_list(service: ComparatorRegistryService) -> None:
    """A scenario with no discovered comparators is ordinary."""
    service.require_promoted([])


# --------------------------------------------------------------------------- listing


def test_listing_is_scoped_to_an_indication_and_ranked(
    service: ComparatorRegistryService,
) -> None:
    service.register(_intake(name=f"{PREFIX}-LOW", relevance=0.3))
    service.register(_intake(name=f"{PREFIX}-HIGH", relevance=0.95))
    service.register(_intake(name=f"{PREFIX}-OTHER", indication_id=DIABETES))

    listed = [a for a in service.list_assets(OBESITY) if a.asset_name.startswith(PREFIX)]
    assert [a.asset_name for a in listed] == [f"{PREFIX}-HIGH", f"{PREFIX}-LOW"]


def test_listing_filters_by_competitor_class(service: ComparatorRegistryService) -> None:
    service.register(_intake(name=f"{PREFIX}-D", competitor_class="direct"))
    service.register(_intake(name=f"{PREFIX}-T", competitor_class="therapeutic"))

    listed = [
        a for a in service.list_assets(OBESITY, competitor_class="therapeutic")
        if a.asset_name.startswith(PREFIX)
    ]
    assert [a.asset_name for a in listed] == [f"{PREFIX}-T"]
