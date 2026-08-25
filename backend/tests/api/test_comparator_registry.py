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


# --------------------------------------------------------------------------- M13 integration


def test_the_cost_bridge_reconciles_to_the_budget_impact(session: Session) -> None:
    """M13 section 5.4. The bridge adds no arithmetic — it re-expresses what
    M7 already computed, so it must not diverge from it by so much as a
    rounding step.

    Reconciled in both directions: the bridge equals M7's net cost per
    switch, and multiplying it by addressable population and uptake
    reproduces that year's budget impact.
    """
    import uuid as _uuid

    from biet_api.models.scenario import Scenario
    from biet_api.services.calculation_service import CalculationService

    scenario = Scenario(
        scenario_id=_uuid.uuid4(), name=f"{PREFIX} bridge", indication_id=OBESITY,
        asset_name="Wegovy", launch_year=2028, horizon_years=3,
        reporting_currency="USD", country_codes=["USA"],
    )
    response, _, _ = CalculationService(session).calculate(scenario)

    country = response.countries[0]
    bridge = country.cost_bridge
    assert bridge is not None

    for year in country.years:
        assert bridge.net_cost_per_switch == pytest.approx(
            year.net_cost_per_switch, rel=1e-9,
        ), "the bridge is year-invariant and must equal every year's figure"

        switchers = year.addressable * year.uptake
        assert bridge.net_cost_per_switch * switchers == pytest.approx(
            year.budget_impact, rel=1e-6,
        ), "bridge x addressable x uptake must reproduce the year's budget impact"


def test_adverse_event_costs_reach_the_therapy_cost_stack(session: Session) -> None:
    """Two therapies differing in adverse-event profile must produce
    different costs — otherwise the whole module is decorative."""
    import uuid as _uuid

    from biet_api.models.scenario import Scenario
    from biet_api.services.calculation_service import CalculationService

    scenario = Scenario(
        scenario_id=_uuid.uuid4(), name=f"{PREFIX} ae", indication_id=OBESITY,
        asset_name="Wegovy", launch_year=2028, horizon_years=3,
        reporting_currency="USD", country_codes=["USA"],
    )
    response, _, _ = CalculationService(session).calculate(scenario)
    bridge = response.countries[0].cost_bridge
    assert bridge is not None

    ae_term = next(t for t in bridge.terms if t.component == "ae")
    assert ae_term.new_therapy > 0, "seeded STEP 1 incidences should price above zero"
    assert ae_term.displaced > 0, "the comparators carry profiles too"


def test_an_asymmetric_profile_is_warned_about(session: Session) -> None:
    """Orlistat and no-pharmacotherapy carry no profile while the incretins
    do. Costing the ones without at zero biases the comparison in their
    favour, and the run must say so rather than look clean."""
    import uuid as _uuid

    from biet_api.models.scenario import Scenario
    from biet_api.services.calculation_service import CalculationService

    scenario = Scenario(
        scenario_id=_uuid.uuid4(), name=f"{PREFIX} asym", indication_id=OBESITY,
        asset_name="Wegovy", launch_year=2028, horizon_years=3,
        reporting_currency="USD", country_codes=["USA"],
    )
    response, _, _ = CalculationService(session).calculate(scenario)
    codes = {w.code for w in response.warnings}
    assert "AE_PROFILE_ASYMMETRIC" in codes
    assert "AE_COST_DERIVED" in codes


# --------------------------------------------------------------------------- M14 integration


def _register_entrant(
    service: ComparatorRegistryService, *, share: float = 0.20, completion_year: int = 2027,
) -> int:
    """A Phase III entrant, by default expected to arrive *after* launch.

    Completion 2027 plus the 1.5-year regulatory lag against a 2028 launch
    puts approval in 2029 — launch-relative year 2. A 2026 completion would
    put it on the market before the asset even launches, which makes it an
    incumbent rather than an entrant.
    """
    from datetime import date as _date

    asset = service.register(_intake(
        name=f"{PREFIX}-ENTRANT",
        competitor_class="pipeline",
        max_clinical_stage="PHASE_3",
        sponsor="Test Sponsor",
        primary_completion=_date(completion_year, 6, 1),
        assumed_terminal_pct=share,
    ))
    return asset.asset_id


def _calculate(session: Session, *, project: bool):
    import uuid as _uuid

    from biet_api.models.scenario import Scenario
    from biet_api.services.calculation_service import CalculationService

    scenario = Scenario(
        scenario_id=_uuid.uuid4(), name=f"{PREFIX} landscape", indication_id=OBESITY,
        asset_name="Wegovy", launch_year=2028, horizon_years=3,
        reporting_currency="USD", country_codes=["USA"],
    )
    response, engine_input, _ = CalculationService(session).calculate(
        scenario, project_landscape=project,
    )
    return response, engine_input


def test_an_unapproved_therapy_stays_out_of_the_current_market(
    service: ComparatorRegistryService, session: Session,
) -> None:
    """The defect this test exists for: promotion writes a `drugs` row, and
    everything in `drugs` for the indication is otherwise treated as
    marketed. A Phase III asset holding a full incumbent share asserts it is
    on sale today."""
    asset_id = _register_entrant(service)
    service.promote(asset_id, PromotionRequest(regimen=_regimen(), prices=[_price()]))
    session.flush()

    response, engine_input = _calculate(session, project=False)
    names = {t.name for t in engine_input.countries[0].therapies}
    assert f"{PREFIX}-ENTRANT" not in names
    assert "PIPELINE_ENTRANT_EXCLUDED" in {w.code for w in response.warnings}


def test_projection_admits_the_entrant_only_from_its_entry_year(
    service: ComparatorRegistryService, session: Session,
) -> None:
    asset_id = _register_entrant(service)
    promoted = service.promote(
        asset_id, PromotionRequest(regimen=_regimen(), prices=[_price()]),
    )
    session.flush()

    _, engine_input = _calculate(session, project=True)
    shares = engine_input.countries[0].baseline_shares
    assert promoted.drug_id in shares

    vector = shares[promoted.drug_id or 0]
    assert vector[0] == pytest.approx(0.0), "not yet approved in year 1"
    assert vector[-1] > 0.0, "on the market by the end of the horizon"
    assert vector == tuple(sorted(vector)), "a ramp, not a step in and out"


def test_projection_changes_the_world_without(
    service: ComparatorRegistryService, session: Session,
) -> None:
    """If admitting a competitor into the baseline left the answer alone, the
    module would be decorative."""
    asset_id = _register_entrant(service)
    service.promote(asset_id, PromotionRequest(regimen=_regimen(), prices=[_price()]))
    session.flush()

    current, _ = _calculate(session, project=False)
    launch, _ = _calculate(session, project=True)

    assert current.countries[0].years[-1].cost_without != pytest.approx(
        launch.countries[0].years[-1].cost_without,
    )
    assert "PIPELINE_ENTRANT_MODELLED" in {w.code for w in launch.warnings}


def test_an_unpromoted_entrant_is_skipped_by_name_not_silently(
    service: ComparatorRegistryService, session: Session,
) -> None:
    """M12's guard, in the one place it is genuinely reachable."""
    _register_entrant(service)
    session.flush()

    response, _ = _calculate(session, project=True)
    skipped = [w for w in response.warnings if w.code == "PIPELINE_ENTRANT_SKIPPED"]
    assert skipped
    assert f"{PREFIX}-ENTRANT" in skipped[0].message
    assert "not promoted" in skipped[0].message


def test_an_entrant_without_a_plateau_share_is_skipped(
    service: ComparatorRegistryService, session: Session,
) -> None:
    """Nothing in the public record supplies one, and this module will not
    invent it."""
    from datetime import date as _date

    asset = service.register(_intake(
        name=f"{PREFIX}-NOSHARE", competitor_class="pipeline",
        max_clinical_stage="PHASE_3", primary_completion=_date(2026, 6, 1),
    ))
    service.promote(asset.asset_id, PromotionRequest(regimen=_regimen(), prices=[_price()]))
    session.flush()

    response, _ = _calculate(session, project=True)
    skipped = [w for w in response.warnings if w.code == "PIPELINE_ENTRANT_SKIPPED"]
    assert any("plateau share" in w.message for w in skipped)


# --------------------------------------------------------------------------- M15 integration


def test_evidence_gaps_rank_differently_from_the_tornado(session: Session) -> None:
    """M15's whole justification. If the ranking always matched the swing
    ordering, the module would be a relabelled tornado.

    On the seeded data, adult share has the second-largest swing and a tier-B
    World Bank source, while treatment rate is derived and tier C — so the
    evidence ranking moves adult share down and treatment rate up.
    """
    import uuid as _uuid

    from biet_api.models.scenario import Scenario
    from biet_api.services.evidence_gap_service import EvidenceGapService

    scenario = Scenario(
        scenario_id=_uuid.uuid4(), name=f"{PREFIX} gaps", indication_id=OBESITY,
        asset_name="Wegovy", launch_year=2028, horizon_years=3,
        reporting_currency="USD", country_codes=["USA"],
    )
    report, currency = EvidenceGapService(session).rank(scenario)

    assert currency == "USD"
    assert report.gaps, "the seeded scenario has swept parameters"

    by_swing = sorted(report.gaps, key=lambda g: -g.swing.amount)
    by_priority = list(report.gaps)
    assert [g.parameter_path for g in by_swing] != [
        g.parameter_path for g in by_priority
    ], "evidence weakness must reorder the tornado, not reproduce it"


def test_every_gap_states_its_source_and_carries_a_band(session: Session) -> None:
    import uuid as _uuid

    from biet_api.models.scenario import Scenario
    from biet_api.services.evidence_gap_service import EvidenceGapService

    scenario = Scenario(
        scenario_id=_uuid.uuid4(), name=f"{PREFIX} gaps2", indication_id=OBESITY,
        asset_name="Wegovy", launch_year=2028, horizon_years=3,
        reporting_currency="USD", country_codes=["USA"],
    )
    report, _ = EvidenceGapService(session).rank(scenario)

    for gap in report.gaps:
        assert gap.source.strip(), "a reader needs to know what the value rests on"
        assert 0.0 <= gap.influence <= 1.0
        assert 0.0 <= gap.priority_score <= 1.0


def test_a_published_prevalence_does_not_top_the_research_list(session: Session) -> None:
    """WHO prevalence is tier A. It moves the answer, and it is not what an
    analyst should go and re-derive."""
    import uuid as _uuid

    from biet_api.models.scenario import Scenario
    from biet_api.services.evidence_gap_service import EvidenceGapService

    scenario = Scenario(
        scenario_id=_uuid.uuid4(), name=f"{PREFIX} gaps3", indication_id=OBESITY,
        asset_name="Wegovy", launch_year=2028, horizon_years=3,
        reporting_currency="USD", country_codes=["USA"],
    )
    report, _ = EvidenceGapService(session).rank(scenario)
    assert report.gaps[0].parameter_path != "epidemiology.prevalence"
