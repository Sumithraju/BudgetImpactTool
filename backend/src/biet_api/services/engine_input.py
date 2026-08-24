"""Assembling `EngineInput` — M1's central job.

This is the seam between the database and the engine. Everything above it
deals in ORM rows and overrides; everything below deals in frozen,
fully-resolved values with provenance. `EngineInput` has no optional fields
and no defaults, so anything unresolved must fail *here*, loudly, rather
than reaching a calculation that would produce a plausible wrong number.

Queries happen once, in the repository, before resolution begins — M1
section 5.2's rule that one query per parameter per market is a defect.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy.orm import Session

from biet_engine.constants import (
    PPP_DEFAULT_ELASTICITY,
    PPP_PRICE_FLOOR,
    REFERENCE_MARKET,
    CriterionType,
    PriceBasis,
    UptakeCurve,
)
from biet_engine.cost import derive_ppp_price
from biet_engine.exceptions import UnpricedReferenceError
from biet_engine.fx import convert
from biet_engine.models import (
    ConfidenceTier,
    CountryInput,
    Criterion,
    EngineInput,
    FunnelRates,
    Money,
    Provenance,
    Regimen,
    ResolutionLevel,
    Substitution,
    TherapyInput,
    UptakeInput,
    Valued,
    Warning_,
)

from ..models.reference import Drug, DrugPrice, EligibilityCriterion
from ..models.scenario import Scenario
from ..repositories.reference import ReferenceRepository
from .resolution import (
    ReferenceValue,
    ResolutionContext,
    ResolutionKey,
    ResolutionService,
    UnresolvedParameterError,
)

#: Defaults for values M1's override vocabulary exposes but no reference
#: table seeds. Uptake is scenario-level rather than market-level (M4
#: section 7), so it has no row to resolve against; these are the
#: ARCHITECTURE.md Appendix B figures used when the scenario doesn't say.
DEFAULT_UPTAKE_YEAR_1 = 0.05
DEFAULT_UPTAKE_TERMINAL = 0.15

#: Costs M5 accepts but M0 does not seed. Zero is the honest default: a
#: stated zero is visible in the cost breakdown, whereas an invented
#: administration cost would silently move the budget impact.
_ZERO_COST = 0.0


class EngineInputBuilder:
    """Builds one scenario's `EngineInput` from persisted state."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._reference = ReferenceRepository(session)

    def build(self, scenario: Scenario) -> tuple[EngineInput, tuple[Warning_, ...]]:
        """Resolve every value this scenario needs and freeze it.

        Returns:
            The engine input, and the warnings resolution accumulated along
            the way (stale vintages, projected values, tier-D inputs). The
            warnings travel with the result rather than blocking it.

        Raises:
            UnresolvedParameterError: a required value has no entry at any
                resolution level.
        """
        codes = list(scenario.country_codes)
        context = self._load_context(scenario, codes)
        resolver = ResolutionService(context)

        drugs = self._reference.list_drugs_with_regimens(scenario.indication_id)
        prices = self._reference.load_prices(codes, [d.drug_id for d in drugs])
        criteria_rows = self._reference.list_criteria(scenario.indication_id)
        fx_rates, fx_date = self._reference.load_fx_snapshot()
        if fx_date is None:
            raise UnresolvedParameterError("fx_rates", None)

        countries = tuple(
            self._build_country(
                code, resolver, drugs, prices, criteria_rows,
                scenario.horizon_years, fx_rates,
            )
            for code in codes
        )

        return (
            EngineInput(
                scenario_id=scenario.scenario_id,
                indication_id=scenario.indication_id,
                launch_year=scenario.launch_year,
                horizon_years=scenario.horizon_years,
                reporting_currency=scenario.reporting_currency,
                fx_rates=fx_rates,
                fx_snapshot_date=fx_date,
                uptake=self._build_uptake(resolver, scenario.horizon_years),
                countries=countries,
            ),
            resolver.warnings,
        )

    # ----------------------------------------------------------------- context

    def _load_context(self, scenario: Scenario, codes: Sequence[str]) -> ResolutionContext:
        country_defaults: dict[ResolutionKey, ReferenceValue] = {}
        country_defaults.update(self._reference.load_economics(codes))
        country_defaults.update(self._reference.load_adult_share(codes))
        country_defaults.update(
            self._reference.load_prevalence(codes, scenario.indication_id)
        )

        funnel_country, funnel_global = self._reference.load_funnel_defaults(
            codes, scenario.indication_id
        )
        country_defaults.update(funnel_country)

        return ResolutionContext(
            scenario_overrides=self._overrides_to_reference_values(scenario),
            country_defaults=country_defaults,
            global_defaults=funnel_global,
            launch_year=scenario.launch_year,
        )

    def _overrides_to_reference_values(
        self, scenario: Scenario,
    ) -> dict[ResolutionKey, ReferenceValue]:
        """Scenario overrides, keyed for resolution.

        `ScenarioOverride.value` is JSONB and may hold a bool, string or
        list as well as a number — `uptake.curve` and
        `criteria.<code>.enabled` are not floats. Non-numeric values are
        carried through `note` rather than `value`, since `ReferenceValue`
        is numeric by contract; the consumers that need them
        (`_build_uptake`, `_build_country`) read them back from there.
        """
        resolved: dict[ResolutionKey, ReferenceValue] = {}
        for override in scenario.overrides:
            raw = override.value
            numeric = float(raw) if isinstance(raw, (int, float)) and not isinstance(
                raw, bool
            ) else 0.0
            resolved[(override.parameter_path, override.country_code)] = ReferenceValue(
                value=numeric,
                source="scenario override",
                confidence_tier=ConfidenceTier.C,
                note=override.note if isinstance(raw, (int, float)) else json.dumps(raw),
            )
        return resolved

    # ----------------------------------------------------------------- per market

    def _build_country(
        self,
        code: str,
        resolver: ResolutionService,
        drugs: Sequence[Drug],
        prices: dict[tuple[int, str], DrugPrice],
        criteria_rows: Sequence[EligibilityCriterion],
        horizon_years: int,
        fx_rates: dict[str, float],
    ) -> CountryInput:
        country = next(
            (c for c in self._reference.list_countries([code])), None
        )
        if country is None:
            raise UnresolvedParameterError("countries.country_code", code)

        priced = tuple(
            self._build_therapy(
                drug, code, country.currency_code, prices, resolver, fx_rates,
            )
            for drug in drugs
        )
        if len(priced) < 2:
            # One priced therapy cannot make a two-world comparison: there is
            # either no new asset or nothing for it to displace.
            raise UnresolvedParameterError("therapy.price_local", code)

        # The new asset is the first non-comparator therapy where one exists,
        # else the first. M1 does not let a scenario name its asset's drug_id
        # explicitly (`asset_name` is free text), so this is the closest
        # defensible reading of the persisted state.
        new_therapy = next((t for t in priced if t.is_new), priced[0])
        # `CountryInput.therapies` excludes the new asset by contract — it is
        # the world-without set that new_therapy displaces.
        therapies = tuple(t for t in priced if t.drug_id != new_therapy.drug_id)

        return CountryInput(
            country_code=code,
            currency=country.currency_code,
            population_total=resolver.resolve("economics.population_total", code),
            adult_share=self._resolve_optional(resolver, "countries.adult_share", code),
            population_growth=self._zero_growth(),
            prevalence=resolver.resolve("epidemiology.prevalence", code),
            health_exp_pc=self._resolve_optional(
                resolver, "economics.health_exp_pc_usd", code
            ),
            gdp_pc_ppp=resolver.resolve("economics.gdp_pc_ppp", code),
            funnel=FunnelRates(
                diagnosis_rate=resolver.resolve("funnel.diagnosis_rate", code),
                treatment_rate=resolver.resolve("funnel.treatment_rate", code),
                access_rate=resolver.resolve("funnel.access_rate", code),
            ),
            criteria=self._build_criteria(criteria_rows, resolver, code),
            therapies=therapies,
            new_therapy=new_therapy,
            baseline_shares=self._build_baseline_shares(therapies, horizon_years),
            substitution=self._build_substitution(resolver, therapies),
        )

    @staticmethod
    def _resolve_optional(
        resolver: ResolutionService, path: str, code: str,
    ) -> Valued | None:
        """`adult_share` and `health_exp_pc` are nullable on `CountryInput`.

        M2 section 5.1 requires the *unresolved* state to reach the engine so
        it can raise there rather than have this layer default it to 1.0 —
        so an absent value becomes None here, not a substitute figure.
        """
        try:
            return resolver.resolve(path, code)
        except UnresolvedParameterError:
            return None

    @staticmethod
    def _zero_growth() -> Valued:
        """Population growth is not seeded per market (M2 section 12 leaves
        a per-market World Bank series as an open question), so it is a
        stated zero rather than an invented rate — flat population across the
        horizon, visible as such in the assumption register."""
        return Valued(
            value=0.0,
            provenance=Provenance(
                source="assumed flat population across the horizon",
                confidence_tier=ConfidenceTier.C,
                resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
            ),
        )

    def _build_criteria(
        self,
        rows: Sequence[EligibilityCriterion],
        resolver: ResolutionService,
        code: str,
    ) -> tuple[Criterion, ...]:
        """The criterion stack for one market.

        A criterion resolves through the override chain like anything else;
        absent an override it falls back to its own seeded `default_factor`,
        which is the library value rather than a substitute.

        Every criterion is enabled. `criteria.<code>.enabled` is in M1's
        override vocabulary, but its value is a bool while `ReferenceValue`
        is numeric by contract, so honouring an explicit toggle needs the
        non-numeric path `_overrides_to_reference_values` stashes in `note` —
        wired up when the API exposes criterion selection.

        Enabling *every* seeded criterion is not a valid default: M3 section
        5.4 declares some pairs correlated (BMI >= 35 and established
        cardiovascular disease overlap clinically), and combining both in
        strict mode — the documented default for API calls — raises. So a
        criterion is enabled unless it is correlated with one already
        enabled; ties break by `criterion_id`, which makes the default stack
        deterministic and conflict-free rather than dependent on row order.

        The skipped half of a correlated pair stays in the returned tuple
        with `enabled=False`, so the interface can present it as an available
        choice the scenario has not taken rather than hide it.
        """
        criteria = []
        enabled_codes: set[str] = set()
        correlated_with_enabled: set[str] = set()
        for row in rows:
            criterion_code = row.criterion_code
            factor_path = f"criteria.{criterion_code}.factor"
            try:
                factor = resolver.resolve(factor_path, code)
            except UnresolvedParameterError:
                factor = Valued(
                    value=float(row.default_factor),
                    low=_opt_float(row.factor_low),
                    high=_opt_float(row.factor_high),
                    provenance=Provenance(
                        source=row.source,
                        confidence_tier=ConfidenceTier(row.confidence_tier),
                        resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
                    ),
                )
            correlations = tuple(row.correlated_with or ())
            enabled = criterion_code not in correlated_with_enabled
            if enabled:
                enabled_codes.add(criterion_code)
                correlated_with_enabled.update(correlations)

            criteria.append(
                Criterion(
                    code=criterion_code,
                    label=row.criterion_label,
                    type=CriterionType(row.criterion_type),
                    factor=factor,
                    enabled=enabled,
                    correlated_with=correlations,
                )
            )
        return tuple(criteria)

    def _build_therapy(
        self,
        drug: Drug,
        code: str,
        country_currency: str,
        prices: dict[tuple[int, str], DrugPrice],
        resolver: ResolutionService,
        fx_rates: dict[str, float],
    ) -> TherapyInput:
        regimen_row = drug.regimens[0] if drug.regimens else None
        if regimen_row is None:
            raise UnresolvedParameterError(f"therapy.{drug.drug_id}.regimen", code)

        price = prices.get((drug.drug_id, code))
        if price is not None:
            unit_price = Money(
                amount=float(price.price_local), currency=country_currency,
            )
            basis = PriceBasis(price.price_basis)
            gross_to_net = price.gross_to_net_pct
            provenance = Provenance(
                source=price.source,
                confidence_tier=ConfidenceTier(price.confidence_tier),
                resolution_level=ResolutionLevel.COUNTRY_OVERRIDE,
                vintage_year=price.effective_date.year if price.effective_date else None,
            )
        else:
            unit_price, provenance = self._derive_price(
                drug, code, country_currency, prices, resolver, fx_rates,
            )
            basis = PriceBasis.PPP_DERIVED
            gross_to_net = None
        flat = _flat_provenance(regimen_row.source, regimen_row.confidence_tier)

        return TherapyInput(
            drug_id=drug.drug_id,
            name=drug.drug_name,
            is_new=not drug.is_comparator,
            regimen=Regimen(
                units_per_admin=Valued(
                    value=float(regimen_row.units_per_admin), provenance=flat,
                ),
                admins_per_year=Valued(
                    value=float(regimen_row.admins_per_year), provenance=flat,
                ),
                wastage_pct=Valued(
                    value=float(regimen_row.wastage_pct), provenance=flat,
                ),
            ),
            unit_price=unit_price,
            price_basis=basis,
            price_provenance=provenance,
            discount_pct=Valued(
                value=1.0 - float(gross_to_net) if gross_to_net is not None else 0.0,
                provenance=provenance,
            ),
            admin_cost=Money(amount=_ZERO_COST, currency=country_currency),
            monitoring_cost=Money(amount=_ZERO_COST, currency=country_currency),
            ae_cost=Money(amount=_ZERO_COST, currency=country_currency),
            offset=Money(amount=_ZERO_COST, currency=country_currency),
            persistence_12m=Valued(
                value=float(regimen_row.persistence_12m), provenance=flat,
            ),
        )

    def _derive_price(
        self,
        drug: Drug,
        code: str,
        country_currency: str,
        prices: dict[tuple[int, str], DrugPrice],
        resolver: ResolutionService,
        fx_rates: dict[str, float],
    ) -> tuple[Money, Provenance]:
        """A PPP-derived unit price for a market with no observed one.

        M5 section 5.3. The derivation runs on USD-normalised values —
        convert in, convert out — because GDP per capita PPP is a USD series
        and mixing it with a local-currency price would scale the result by
        an exchange rate that has nothing to do with purchasing power.

        The result is a modelling assumption, not an observation, so it
        carries tier C and says so in its `source`. Every surface that shows
        it must label it derived (M5 section 9); the `price_basis` the caller
        sets to `PPP_DERIVED` is what makes that possible.

        Raises:
            UnpricedReferenceError: the reference market has no observed
                price either, so there is nothing to derive from.
        """
        reference = prices.get((drug.drug_id, REFERENCE_MARKET))
        if reference is None:
            raise UnpricedReferenceError(
                f"{drug.drug_name!r} has no price in the reference market "
                f"{REFERENCE_MARKET!r}, so no price can be derived for {code!r}",
                drug_id=drug.drug_id, country_code=code,
            )

        # Read the reference row's own currency rather than assuming USD:
        # that only holds while REFERENCE_MARKET is the USA, and a silent
        # wrong-currency assumption would scale every derived price.
        reference_usd = convert(
            Money(
                amount=float(reference.price_local),
                currency=reference.currency_code,
            ),
            "USD", fx_rates,
        )
        derived_usd = derive_ppp_price(
            reference_price=reference_usd.amount,
            gdp_pc_ppp_target=resolver.resolve("economics.gdp_pc_ppp", code).value,
            gdp_pc_ppp_reference=resolver.resolve(
                "economics.gdp_pc_ppp", REFERENCE_MARKET
            ).value,
            elasticity=PPP_DEFAULT_ELASTICITY,
            floor=PPP_PRICE_FLOOR,
        )
        local = convert(
            Money(amount=derived_usd, currency="USD"), country_currency, fx_rates,
        )

        return local, Provenance(
            source=(
                f"purchasing-power-parity derived from {REFERENCE_MARKET} "
                f"({reference.source}) at elasticity {PPP_DEFAULT_ELASTICITY}"
            ),
            confidence_tier=ConfidenceTier.C,
            resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
            note="derived price, not observed",
        )

    # ----------------------------------------------------------------- scenario level

    def _build_uptake(self, resolver: ResolutionService, horizon: int) -> UptakeInput:
        curve = UptakeCurve.LOGISTIC
        curve_override = resolver_note(resolver, "uptake.curve")
        if curve_override is not None:
            curve = UptakeCurve(curve_override)

        return UptakeInput(
            curve=curve,
            year_1=_scenario_valued(resolver, "uptake.year_1", DEFAULT_UPTAKE_YEAR_1),
            terminal=_scenario_valued(
                resolver, "uptake.terminal", DEFAULT_UPTAKE_TERMINAL
            ),
        )

    @staticmethod
    def _build_baseline_shares(
        therapies: Sequence[TherapyInput], horizon_years: int,
    ) -> dict[int, tuple[float, ...]]:
        """World-without market mix, `drug_id -> per-year share`.

        M0 seeds no market-share data, so this defaults to an equal split
        held constant across the horizon (M4 section 5.5 permits constant).
        The last share absorbs the rounding residue so the vector sums to
        exactly 1.0 — M4 validates that to 1e-6 and would reject
        0.9999999999999999.
        """
        count = len(therapies)
        share = 1.0 / count
        values = [share] * (count - 1) + [1.0 - share * (count - 1)]
        return {
            therapy.drug_id: tuple([value] * horizon_years)
            for therapy, value in zip(therapies, values, strict=True)
        }

    def _build_substitution(
        self, resolver: ResolutionService, therapies: Sequence[TherapyInput],
    ) -> Substitution:
        """Source of business, defaulting to an equal split across incumbents.

        M4 section 5.3 requires sigma to sum to 1. With no seeded vector, an
        equal split is the only assumption that is both valid and free of an
        implied claim about which incumbent loses share — and it stays
        visible as an assumption rather than buried in a constant.
        """
        count = len(therapies)
        share = 1.0 / count
        flat = Provenance(
            source="assumed equal source of business across incumbent therapies",
            confidence_tier=ConfidenceTier.C,
            resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
        )
        shares: dict[int, Valued] = {}
        for index, therapy in enumerate(therapies):
            try:
                shares[therapy.drug_id] = resolver.resolve(
                    f"substitution.{therapy.drug_id}"
                )
            except UnresolvedParameterError:
                value = (
                    1.0 - share * (count - 1) if index == count - 1 else share
                )
                shares[therapy.drug_id] = Valued(value=value, provenance=flat)
        return Substitution(shares=shares)


def _opt_float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def _flat_provenance(source: str, tier: str) -> Provenance:
    return Provenance(
        source=source,
        confidence_tier=ConfidenceTier(tier),
        resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
    )


def resolver_note(resolver: ResolutionService, path: str) -> str | None:
    """A non-numeric override's payload, stashed in `note` as JSON."""
    try:
        resolved = resolver.resolve(path)
    except UnresolvedParameterError:
        return None
    if resolved.provenance.note is None:
        return None
    try:
        parsed = json.loads(resolved.provenance.note)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, str) else None


def _scenario_valued(
    resolver: ResolutionService, path: str, default: float,
) -> Valued:
    try:
        return resolver.resolve(path)
    except UnresolvedParameterError:
        return Valued(
            value=default,
            provenance=Provenance(
                source=f"default {path}",
                confidence_tier=ConfidenceTier.C,
                resolution_level=ResolutionLevel.GLOBAL_DEFAULT,
            ),
        )
