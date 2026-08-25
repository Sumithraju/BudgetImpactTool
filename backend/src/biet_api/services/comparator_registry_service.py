"""Comparator registry and promotion — M12.

The hinge between discovery and calculation. M11 returns molecules; M5 needs
prices, regimens and persistence; no public target database carries any of the
three, and no further retrieval will produce them — a net price is not a public
fact. This is where a retrieved molecule and a curated commercial record become
one row, and promotion is the explicit act that makes that row usable.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.orm import Session

from ..constants.domain import PriceBasis
from ..exceptions import (
    ComparatorNotPricedError,
    ConflictError,
    EntityNotFoundError,
    ValidationError,
)
from ..models.comparator import ComparatorApproval, ComparatorAsset
from ..models.reference import Country, Drug, DrugPrice, DrugRegimen, Indication
from ..repositories.comparator_asset import ComparatorAssetRepository
from ..schemas.comparator import (
    AssetIntake,
    MarketApprovalRead,
    PriceIn,
    PromotionRequest,
    RegimenIn,
    RegisteredAsset,
)

log = logging.getLogger("biet.comparator.registry")


class ComparatorRegistryService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._assets = ComparatorAssetRepository(session)

    # ----------------------------------------------------------------- reads

    def list_assets(
        self, indication_id: int, *, competitor_class: str | None = None,
    ) -> list[RegisteredAsset]:
        assets = self._assets.list_for_indication(
            indication_id, competitor_class=competitor_class,
        )
        return [self._read(a) for a in assets]

    def require(self, asset_id: int) -> ComparatorAsset:
        asset = self._assets.get(asset_id)
        if asset is None:
            raise EntityNotFoundError(f"no comparator asset {asset_id}", asset_id=asset_id)
        return asset

    def read(self, asset_id: int) -> RegisteredAsset:
        return self._read(self.require(asset_id))

    # ----------------------------------------------------------------- writes

    def register(self, intake: AssetIntake) -> RegisteredAsset:
        """Record an asset, or return the record that already exists.

        Idempotent on `(source_id, indication_id)`. Registering twice is the
        ordinary consequence of running discovery twice, not a conflict, so
        it returns the existing record rather than raising.
        """
        if self._session.get(Indication, intake.indication_id) is None:
            raise ValidationError(
                f"no indication {intake.indication_id}", indication_id=intake.indication_id,
            )

        existing = self._assets.get_by_natural_key(intake.source_id, intake.indication_id)
        if existing is not None:
            self._merge_curated(existing, intake)
            self._session.flush()
            return self._read(existing)

        asset = ComparatorAsset(
            source_id=intake.source_id,
            asset_name=intake.asset_name,
            indication_id=intake.indication_id,
            target_symbol=intake.target_symbol,
            target_id=intake.target_id,
            mechanism_of_action=intake.mechanism_of_action,
            action_type=intake.action_type,
            pathway_ids=list(intake.pathway_ids),
            drug_type=intake.drug_type,
            max_clinical_stage=intake.max_clinical_stage,
            competitor_class=intake.competitor_class.value,
            relevance=intake.relevance,
            rationale=intake.rationale,
            brand_name=intake.brand_name,
            manufacturer=intake.manufacturer,
            route=intake.route,
            line_of_therapy=(
                intake.line_of_therapy.value if intake.line_of_therapy else None
            ),
            sponsor=intake.sponsor,
            primary_completion=intake.primary_completion,
            expected_entry_year=intake.expected_entry_year,
            assumed_terminal_pct=(
                Decimal(str(intake.assumed_terminal_pct))
                if intake.assumed_terminal_pct is not None else None
            ),
            is_new_asset=intake.is_new_asset,
            source=intake.source,
            source_url=intake.source_url,
            confidence_tier=intake.confidence_tier,
        )
        # A molecule this system already prices is usable the moment it is
        # registered — that link is what `seeded_drug_id` was telling the user
        # about at discovery, made durable.
        matched = self._assets.get_drug_by_name(intake.asset_name)
        if matched is not None:
            asset.drug_id = matched.drug_id

        self._assets.add(asset)
        self._apply_approvals(asset, intake)
        self._session.flush()
        return self._read(asset)

    def promote(self, asset_id: int, request: PromotionRequest) -> RegisteredAsset:
        """Attach a regimen and prices; make the asset usable by M5.

        One transaction or none. A comparator with a regimen and no price is
        not usable, and a half-promoted asset that *looks* promoted is worse
        than one that plainly is not (M12 section 5.3).
        """
        asset = self.require(asset_id)
        self._validate_markets(request.prices)

        drug = self._drug_for(asset, request)
        self._session.flush()          # assign drug_id before the children reference it

        self._replace_regimen(drug, request.regimen)
        self._replace_prices(drug, request.prices)

        asset.drug_id = drug.drug_id
        self._session.flush()
        return self._read(asset)

    # ----------------------------------------------------------------- the guard

    def require_promoted(self, asset_ids: Sequence[int]) -> None:
        """Raise unless every named comparator can enter a calculation.

        Called at scenario build. Dropping an unpromoted comparator instead
        would mean its cost is never subtracted from the world-without, and
        budget impact is overstated by exactly the cost of the care the new
        therapy displaces (M12 section 5.6).
        """
        assets = self._assets.list_by_ids(asset_ids)
        found = {a.asset_id for a in assets}
        missing = [i for i in asset_ids if i not in found]
        if missing:
            raise EntityNotFoundError(
                f"no comparator asset {missing[0]}", asset_ids=list(missing),
            )

        unpriced = [a for a in assets if not a.is_promoted]
        if unpriced:
            names = ", ".join(sorted(a.asset_name for a in unpriced))
            raise ComparatorNotPricedError(
                f"{names} has no price or regimen and cannot enter a calculation. "
                "Discovery yields a molecule, not a cost — promote it first.",
                asset_ids=[a.asset_id for a in unpriced],
                asset_names=sorted(a.asset_name for a in unpriced),
            )

    # ----------------------------------------------------------------- internals

    def _drug_for(self, asset: ComparatorAsset, request: PromotionRequest) -> Drug:
        """The `drugs` row this asset promotes into.

        Re-promotion updates in place; a name collision links to the existing
        row. Both exist so that promotion never depends on a unique
        constraint to express a rule.
        """
        if asset.drug_id is not None:
            drug = self._session.get(Drug, asset.drug_id)
            if drug is not None:
                return drug

        existing = self._assets.get_drug_by_name(asset.asset_name)
        if existing is not None:
            return existing

        drug = Drug(
            drug_name=asset.asset_name,
            generic_name=asset.asset_name.lower(),
            company=request.company or asset.manufacturer,
            drug_class=request.drug_class or asset.mechanism_of_action,
            route=asset.route,
            indication_id=asset.indication_id,
            is_comparator=not asset.is_new_asset,
        )
        self._session.add(drug)
        return drug

    def _replace_regimen(self, drug: Drug, regimen: RegimenIn) -> None:
        existing = self._assets.get_regimen(drug.drug_id)
        if existing is not None:
            self._session.delete(existing)
            self._session.flush()

        self._session.add(DrugRegimen(
            drug_id=drug.drug_id,
            dose_amount=Decimal(str(regimen.dose_amount)),
            dose_unit=regimen.dose_unit,
            units_per_admin=Decimal(str(regimen.units_per_admin)),
            admins_per_year=Decimal(str(regimen.admins_per_year)),
            wastage_pct=Decimal(str(regimen.wastage_pct)),
            persistence_12m=Decimal(str(regimen.persistence_12m)),
            source=regimen.source,
            confidence_tier=regimen.confidence_tier,
        ))

    def _replace_prices(self, drug: Drug, prices: Sequence[PriceIn]) -> None:
        for existing in self._assets.list_prices(drug.drug_id):
            self._session.delete(existing)
        self._session.flush()

        for price in prices:
            # The schema constraint says a stated net price must say what
            # assumption produced it. Checked here too, so the message names
            # the market rather than arriving as a constraint violation.
            if (
                price.price_basis == PriceBasis.ESTIMATED_NET
                and price.gross_to_net_pct is None
            ):
                raise ValidationError(
                    f"{price.country_code}: an estimated net price must state the "
                    "gross-to-net ratio that produced it",
                    country_code=price.country_code,
                )
            self._session.add(DrugPrice(
                drug_id=drug.drug_id,
                country_code=price.country_code,
                price_local=Decimal(str(price.price_local)),
                currency_code=price.currency_code,
                price_basis=price.price_basis,
                gross_to_net_pct=(
                    Decimal(str(price.gross_to_net_pct))
                    if price.gross_to_net_pct is not None else None
                ),
                effective_date=price.effective_date,
                source=price.source,
                source_url=price.source_url,
                confidence_tier=price.confidence_tier,
            ))

    def _validate_markets(self, prices: Sequence[PriceIn]) -> None:
        for price in prices:
            country = self._session.get(Country, price.country_code)
            if country is None:
                raise ValidationError(
                    f"no market {price.country_code}", country_code=price.country_code,
                )
            if country.currency_code != price.currency_code:
                # Money carries a currency, and the currency must be the
                # market's — a euro price filed against Japan would compute
                # a plausible, wrong annual cost.
                raise ConflictError(
                    f"{price.country_code} settles in {country.currency_code}, "
                    f"not {price.currency_code}",
                    country_code=price.country_code,
                    expected=country.currency_code,
                    supplied=price.currency_code,
                )

    def _apply_approvals(self, asset: ComparatorAsset, intake: AssetIntake) -> None:
        for approval in intake.approvals:
            if self._session.get(Country, approval.country_code) is None:
                raise ValidationError(
                    f"no market {approval.country_code}",
                    country_code=approval.country_code,
                )
            asset.approvals.append(ComparatorApproval(
                country_code=approval.country_code,
                approval_year=approval.approval_year,
                is_reimbursed=approval.is_reimbursed,
                source=approval.source,
                confidence_tier=approval.confidence_tier,
            ))

    @staticmethod
    def _merge_curated(asset: ComparatorAsset, intake: AssetIntake) -> None:
        """Fill gaps from a re-registration; never erase what is there.

        A curated value does not silently overwrite a retrieved one, and a
        retrieved value does not overwrite a curated one either — the same
        rule as M1's scenario overrides, applied to reference data
        (M12 section 5.2).
        """
        asset.brand_name = asset.brand_name or intake.brand_name
        asset.manufacturer = asset.manufacturer or intake.manufacturer
        asset.route = asset.route or intake.route
        asset.line_of_therapy = asset.line_of_therapy or (
            intake.line_of_therapy.value if intake.line_of_therapy else None
        )
        asset.sponsor = asset.sponsor or intake.sponsor
        asset.primary_completion = asset.primary_completion or intake.primary_completion
        if not asset.pathway_ids and intake.pathway_ids:
            asset.pathway_ids = list(intake.pathway_ids)

    def _read(self, asset: ComparatorAsset) -> RegisteredAsset:
        return RegisteredAsset(
            asset_id=asset.asset_id,
            source_id=asset.source_id,
            asset_name=asset.asset_name,
            indication_id=asset.indication_id,
            target_symbol=asset.target_symbol,
            mechanism_of_action=asset.mechanism_of_action,
            action_type=asset.action_type,
            pathway_ids=list(asset.pathway_ids or []),
            max_clinical_stage=asset.max_clinical_stage,
            competitor_class=asset.competitor_class,
            relevance=float(asset.relevance),
            rationale=asset.rationale,
            brand_name=asset.brand_name,
            manufacturer=asset.manufacturer,
            line_of_therapy=asset.line_of_therapy,
            sponsor=asset.sponsor,
            expected_entry_year=asset.expected_entry_year,
            is_new_asset=asset.is_new_asset,
            drug_id=asset.drug_id,
            is_promoted=asset.is_promoted,
            missing_for_promotion=self._gaps(asset),
            source=asset.source,
            confidence_tier=asset.confidence_tier,
            approvals=[
                MarketApprovalRead.model_validate(a) for a in asset.approvals
            ],
        )

    def _gaps(self, asset: ComparatorAsset) -> list[str]:
        """What still stands between this asset and a calculation.

        Named per market rather than reported as one boolean, so the
        interface can say "needs a German price" rather than "not ready"
        (M12 section 5.4).
        """
        if asset.drug_id is None:
            return ["regimen", "price"]

        gaps: list[str] = []
        if self._assets.get_regimen(asset.drug_id) is None:
            gaps.append("regimen")

        priced = self._assets.priced_markets(asset.drug_id)
        approved = {a.country_code for a in asset.approvals}
        # Only markets the asset is actually approved in are expected to have
        # a price. Demanding one everywhere would flag a US-only therapy as
        # incomplete for nine markets it will never be sold in.
        gaps.extend(f"price:{code}" for code in sorted(approved - priced))
        if not priced:
            gaps.append("price")
        return gaps
