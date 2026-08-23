"""Shared test factories for engine fixtures.

`CountryInput` is a big composite (M1's contract) that most engine tests only
need a thin, structurally-valid slice of — these builders exist so each test
file states only the values it actually cares about, per the DRY rule in the
biet-backend skill ("extract on the second occurrence").
"""

from __future__ import annotations

from biet_engine.constants import CriterionType, PriceBasis
from biet_engine.models import (
    ConfidenceTier,
    CountryInput,
    Criterion,
    FunnelRates,
    Money,
    Provenance,
    Regimen,
    ResolutionLevel,
    TherapyInput,
    Valued,
)


def make_provenance(
    source: str = "test fixture",
    *,
    tier: ConfidenceTier = ConfidenceTier.A,
    level: ResolutionLevel = ResolutionLevel.GLOBAL_DEFAULT,
) -> Provenance:
    return Provenance(source=source, confidence_tier=tier, resolution_level=level)


def make_valued(value: float, **provenance_kwargs: object) -> Valued:
    return Valued(value=value, provenance=make_provenance(**provenance_kwargs))  # type: ignore[arg-type]


def make_therapy_input(*, drug_id: int = 1, is_new: bool = True) -> TherapyInput:
    """A structurally-valid but not semantically-meaningful therapy.

    `CountryInput.therapies`/`new_therapy` are M5's contract; funnel tests
    don't exercise them but must supply something valid to construct a
    `CountryInput` at all.
    """
    zero = make_valued(0.0)
    return TherapyInput(
        drug_id=drug_id,
        name=f"test-drug-{drug_id}",
        is_new=is_new,
        regimen=Regimen(
            units_per_admin=make_valued(1.0),
            admins_per_year=make_valued(52.0),
            wastage_pct=zero,
        ),
        unit_price=Money(amount=100.0, currency="USD"),
        price_basis=PriceBasis.LIST,
        discount_pct=zero,
        admin_cost=Money(amount=0.0, currency="USD"),
        monitoring_cost=Money(amount=0.0, currency="USD"),
        ae_cost=Money(amount=0.0, currency="USD"),
        offset=Money(amount=0.0, currency="USD"),
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
        criteria=(
            Criterion(
                code="test_criterion", label="test", type=CriterionType.BMI,
                factor=make_valued(1.0), enabled=True,
            ),
        ),
        therapies=(make_therapy_input(drug_id=1, is_new=False),),
        new_therapy=make_therapy_input(drug_id=2, is_new=True),
    )
