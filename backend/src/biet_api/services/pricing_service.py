"""The editable price grid.

Only three of ten markets carry an observed price for the obesity class, and
the other seven derive theirs from a US list price that sits far above European
reality. An analyst who knows their own market has better information than this
model does, and a price grid that will not accept it is telling them otherwise.

Two rules keep that editability from corrupting the evidence base:

**An edit is a scenario override, never a write to reference data.** The
observed German price and one analyst's working assumption about the Japanese
one are different claims. Overwriting `drug_prices` would merge them, and the
next scenario would inherit an assumption as though it were a citation.

**A derived price is labelled as derived, before and after the edit.** The grid
pre-fills the model's own working figure rather than an empty cell, so the
analyst can see what they are disagreeing with — but `is_observed` stays false
until a real source replaces it.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from biet_engine.constants import (
    PPP_DEFAULT_ELASTICITY,
    PPP_PRICE_FLOOR,
    REFERENCE_MARKET,
    PriceBasis,
)
from biet_engine.cost import derive_ppp_price
from biet_engine.fx import convert
from biet_engine.models import Money

from ..models.reference import Drug, DrugPrice
from ..repositories.reference import ReferenceRepository
from ..schemas.pricing import DrugPriceRead, PriceEdit

#: The override path a price edit writes to. Declared here as a format string
#: rather than concatenated at each call site: a path outside the closed
#: vocabulary is discarded silently at validation, which is precisely the
#: failure the vocabulary exists to prevent.
PRICE_PATH = "therapy.{drug_id}.price_local"

DERIVED_SOURCE = (
    "No observed price in this market. Derived from the {reference} figure by "
    "purchasing-power parity at the model's default elasticity — a modelling "
    "assumption, not a national price. Replace it with a real figure if you have "
    "one; the edit is recorded as your override rather than as a citation."
)

UNPRICED_SOURCE = (
    "No price in any market this could be derived from, so no figure is offered. "
    "Enter one to include this therapy in the comparison."
)


class PricingService:
    """The whole price matrix an analyst can see and edit."""

    def __init__(self, session: Session) -> None:
        self._reference = ReferenceRepository(session)

    def grid(
        self, indication_id: int, country_codes: Sequence[str],
    ) -> list[DrugPriceRead]:
        """Every therapy x market cell, observed or derived.

        Returns the cells with *no* observed price as well, carrying the
        derivation the engine would use. Those are the cells worth an analyst's
        attention first, and an empty row would hide them rather than surface
        them.
        """
        drugs = list(self._reference.list_drugs_with_regimens(indication_id))
        drug_ids = [d.drug_id for d in drugs]
        prices = self._reference.load_prices(list(country_codes), drug_ids)
        reference_prices = self._reference.load_prices([REFERENCE_MARKET], drug_ids)
        fx_rates, _ = self._reference.load_fx_snapshot()

        countries = {
            str(c.country_code): c
            for c in self._reference.list_countries(list(country_codes))
        }
        gdp = self._gdp_by_country(
            [*country_codes, REFERENCE_MARKET],
        )

        rows: list[DrugPriceRead] = []
        for drug in drugs:
            for code in country_codes:
                country = countries.get(code)
                if country is None:
                    continue
                rows.append(self._cell(
                    drug, code, str(country.currency_code),
                    prices.get((drug.drug_id, code)),
                    reference_prices.get((drug.drug_id, REFERENCE_MARKET)),
                    gdp, fx_rates,
                ))
        return rows

    def _cell(
        self,
        drug: Drug,
        country_code: str,
        currency: str,
        observed: DrugPrice | None,
        reference: DrugPrice | None,
        gdp: dict[str, float],
        fx_rates: dict[str, float],
    ) -> DrugPriceRead:
        annual_factor = self._annual_factor(drug)
        path = PRICE_PATH.format(drug_id=drug.drug_id)

        if observed is not None:
            unit = float(observed.price_local)
            return DrugPriceRead(
                drug_id=drug.drug_id,
                drug_name=drug.drug_name,
                is_new_asset=not drug.is_comparator,
                country_code=country_code,
                currency_code=str(observed.currency_code),
                unit_price=unit,
                annual_cost=unit * annual_factor,
                price_basis=str(observed.price_basis),
                is_observed=observed.price_basis != PriceBasis.PPP_DERIVED,
                confidence_tier=str(observed.confidence_tier),
                source=observed.source,
                source_url=observed.source_url,
                vintage_year=(
                    observed.effective_date.year
                    if observed.effective_date else None
                ),
                parameter_path=path,
            )

        derived = self._derive(reference, country_code, currency, gdp, fx_rates)
        if derived is None:
            return DrugPriceRead(
                drug_id=drug.drug_id,
                drug_name=drug.drug_name,
                is_new_asset=not drug.is_comparator,
                country_code=country_code,
                currency_code=currency,
                unit_price=0.0,
                annual_cost=0.0,
                price_basis=str(PriceBasis.PPP_DERIVED),
                is_observed=False,
                confidence_tier="D",
                source=UNPRICED_SOURCE,
                parameter_path=path,
            )

        return DrugPriceRead(
            drug_id=drug.drug_id,
            drug_name=drug.drug_name,
            is_new_asset=not drug.is_comparator,
            country_code=country_code,
            currency_code=currency,
            unit_price=derived,
            annual_cost=derived * annual_factor,
            price_basis=str(PriceBasis.PPP_DERIVED),
            is_observed=False,
            confidence_tier="C",
            source=DERIVED_SOURCE.format(reference=REFERENCE_MARKET),
            parameter_path=path,
        )

    @staticmethod
    def _annual_factor(drug: Drug) -> float:
        """Units consumed per year, including wastage.

        The multiplier that turns a unit price into the annual cost an analyst
        recognises. Taken from the therapy's own regimen rather than assumed:
        a "monthly" GLP-1 package is 28 days, so a year is thirteen packages
        and not twelve — the 8.3% discrepancy that catches every reconciliation
        against a spreadsheet built the other way.
        """
        regimen = drug.regimens[0] if drug.regimens else None
        if regimen is None:
            return 0.0
        return (
            float(regimen.units_per_admin)
            * float(regimen.admins_per_year)
            * (1.0 + float(regimen.wastage_pct or 0))
        )

    def _gdp_by_country(self, codes: Sequence[str]) -> dict[str, float]:
        economics = self._reference.load_economics(list(set(codes)))
        return {
            country: value.value
            for (path, country), value in economics.items()
            if path == "economics.gdp_pc_ppp" and country is not None
        }

    @staticmethod
    def _derive(
        reference: DrugPrice | None,
        country_code: str,
        currency: str,
        gdp: dict[str, float],
        fx_rates: dict[str, float],
    ) -> float | None:
        """The purchasing-power figure the engine itself would use.

        Runs in USD and converts back, exactly as M5 does — the formula is
        defined on USD-normalised values, and scaling a local-currency figure
        by a PPP ratio would apply the exchange rate twice.
        """
        target = gdp.get(country_code)
        anchor = gdp.get(REFERENCE_MARKET)
        if reference is None or target is None or not anchor:
            return None

        reference_usd = convert(
            Money(
                amount=float(reference.price_local),
                currency=str(reference.currency_code),
            ),
            "USD", fx_rates,
        )
        derived_usd = derive_ppp_price(
            reference_usd.amount, target, anchor,
            PPP_DEFAULT_ELASTICITY, PPP_PRICE_FLOOR,
        )
        return convert(
            Money(amount=derived_usd, currency="USD"), currency, fx_rates,
        ).amount

    # ----------------------------------------------------------------- edits

    def to_overrides(
        self, indication_id: int, edits: Sequence[PriceEdit],
    ) -> list[dict[str, object]]:
        """Price edits, as scenario overrides.

        An edit supplied as an annual cost is divided back through the
        therapy's own regimen rather than stored as-is, because the engine's
        cost formula multiplies a *unit* price by units per administration.
        Storing an annual figure in a unit-price field would inflate every cost
        in the model by the annual factor — roughly fifty-fold for a weekly
        injectable — while looking like a perfectly ordinary number.
        """
        drugs = {
            d.drug_id: d
            for d in self._reference.list_drugs_with_regimens(indication_id)
        }
        overrides: list[dict[str, object]] = []
        for edit in edits:
            drug = drugs.get(edit.drug_id)
            if drug is None:
                continue

            unit = edit.unit_price
            if unit is None and edit.annual_cost is not None:
                factor = self._annual_factor(drug)
                if factor <= 0:
                    continue
                unit = edit.annual_cost / factor
            if unit is None or unit <= 0:
                continue

            overrides.append({
                "country_code": edit.country_code,
                "parameter_path": PRICE_PATH.format(drug_id=edit.drug_id),
                "value": unit,
                "note": edit.note or (
                    f"Analyst-supplied price for {drug.drug_name} in "
                    f"{edit.country_code}."
                ),
            })
        return overrides
