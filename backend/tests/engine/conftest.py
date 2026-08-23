"""Shared test factories for engine fixtures.

`CountryInput` is a big composite (M1's contract) that most engine tests only
need a thin, structurally-valid slice of — these builders exist so each test
file states only the values it actually cares about, per the DRY rule in the
biet-backend skill ("extract on the second occurrence").
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from biet_engine.constants import CriterionType, PriceBasis, UptakeCurve
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
)


def make_provenance(
    source: str = "test fixture",
    *,
    tier: ConfidenceTier = ConfidenceTier.A,
    level: ResolutionLevel = ResolutionLevel.GLOBAL_DEFAULT,
) -> Provenance:
    return Provenance(source=source, confidence_tier=tier, resolution_level=level)


def make_valued(
    value: float, *, low: float | None = None, high: float | None = None,
    **provenance_kwargs: object,
) -> Valued:
    return Valued(  # type: ignore[arg-type]
        value=value, low=low, high=high, provenance=make_provenance(**provenance_kwargs),
    )


def make_criterion(
    code: str,
    factor: float,
    *,
    enabled: bool = True,
    factor_low: float | None = None,
    factor_high: float | None = None,
    tier: ConfidenceTier = ConfidenceTier.A,
    correlated_with: tuple[str, ...] = (),
    criterion_type: CriterionType = CriterionType.BMI,
) -> Criterion:
    return Criterion(
        code=code, label=code, type=criterion_type,
        factor=make_valued(factor, low=factor_low, high=factor_high, tier=tier),
        enabled=enabled, correlated_with=correlated_with,
    )


def make_therapy_input(
    *,
    drug_id: int = 1,
    is_new: bool = True,
    unit_price: float = 100.0,
    currency: str = "USD",
    units_per_admin: float = 1.0,
    admins_per_year: float = 52.0,
    wastage_pct: float = 0.0,
    discount_pct: float = 0.0,
    admin_cost: float = 0.0,
    monitoring_cost: float = 0.0,
    ae_cost: float = 0.0,
    offset: float = 0.0,
    price_basis: PriceBasis = PriceBasis.LIST,
) -> TherapyInput:
    """A structurally-valid, cheaply-overridable therapy for engine tests."""
    return TherapyInput(
        drug_id=drug_id,
        name=f"test-drug-{drug_id}",
        is_new=is_new,
        regimen=Regimen(
            units_per_admin=make_valued(units_per_admin),
            admins_per_year=make_valued(admins_per_year),
            wastage_pct=make_valued(wastage_pct),
        ),
        unit_price=Money(amount=unit_price, currency=currency),
        price_basis=price_basis,
        price_provenance=make_provenance(),
        discount_pct=make_valued(discount_pct),
        admin_cost=Money(amount=admin_cost, currency=currency),
        monitoring_cost=Money(amount=monitoring_cost, currency=currency),
        ae_cost=Money(amount=ae_cost, currency=currency),
        offset=Money(amount=offset, currency=currency),
        persistence_12m=make_valued(1.0),
    )


def make_country_input(
    *,
    country_code: str = "DEU",
    currency: str = "EUR",
    population_total: float = 83_500_000,
    adult_share: float | None = 0.820,
    population_growth: float = 0.0,
    prevalence: float = 0.2064,
    diagnosis_rate: float = 0.600,
    treatment_rate: float = 0.150,
    access_rate: float = 0.700,
    horizon: int = 3,
    baseline_shares: dict[int, tuple[float, ...]] | None = None,
    substitution: Substitution | None = None,
    therapies: tuple[TherapyInput, ...] | None = None,
    new_therapy: TherapyInput | None = None,
    criteria: tuple[Criterion, ...] | None = None,
) -> CountryInput:
    return CountryInput(
        country_code=country_code,
        currency=currency,
        population_total=make_valued(population_total),
        adult_share=None if adult_share is None else make_valued(adult_share),
        population_growth=make_valued(population_growth),
        prevalence=make_valued(prevalence),
        health_exp_pc=make_valued(0.0),
        gdp_pc_ppp=make_valued(0.0),
        funnel=FunnelRates(
            diagnosis_rate=make_valued(diagnosis_rate),
            treatment_rate=make_valued(treatment_rate),
            access_rate=make_valued(access_rate),
        ),
        criteria=criteria if criteria is not None else (
            Criterion(
                code="test_criterion", label="test", type=CriterionType.BMI,
                factor=make_valued(1.0), enabled=True,
            ),
        ),
        therapies=therapies if therapies is not None else (make_therapy_input(drug_id=1, is_new=False),),
        new_therapy=new_therapy if new_therapy is not None else make_therapy_input(drug_id=2, is_new=True),
        baseline_shares=baseline_shares if baseline_shares is not None else {1: (1.0,) * horizon},
        substitution=substitution if substitution is not None
        else Substitution(shares={1: make_valued(1.0)}),
    )


def make_uptake_input(
    *, curve: UptakeCurve = UptakeCurve.MANUAL, vector: tuple[float, ...] = (0.05, 0.10, 0.15),
    **kwargs: object,
) -> UptakeInput:
    return UptakeInput(curve=curve, vector=vector, **kwargs)  # type: ignore[arg-type]


def make_engine_input(
    *,
    countries: tuple[CountryInput, ...] | None = None,
    horizon_years: int = 3,
    launch_year: int = 2028,
    reporting_currency: str = "USD",
    fx_rates: dict[str, float] | None = None,
    uptake: UptakeInput | None = None,
) -> EngineInput:
    return EngineInput(
        scenario_id=uuid4(),
        indication_id=1,
        launch_year=launch_year,
        horizon_years=horizon_years,
        reporting_currency=reporting_currency,
        fx_rates=fx_rates if fx_rates is not None else {"USD": 1.0, "EUR": 0.86386},
        fx_snapshot_date=date(2026, 8, 23),
        uptake=uptake if uptake is not None
        else make_uptake_input(vector=(0.05,) * horizon_years),
        countries=countries if countries is not None
        else (make_country_input(horizon=horizon_years),),
    )
