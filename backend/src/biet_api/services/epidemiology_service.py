"""Prevalence, incidence, and the funnel that connects them to the budget.

The point of this module is a distinction the rest of the model depends on and
that an epidemiology panel is uniquely good at blurring:

**Prevalence** is the share of a population that has the condition *now* — the
standing pool a therapy can be launched into.

**Incidence** is the share that newly acquires it *each year* — the flow that
refills that pool over a multi-year horizon.

They differ by more than an order of magnitude for a persistent condition. US
adult obesity prevalence is 42.9%; the derived annual incidence is about 1.7%,
or 1,716 new cases per 100,000 adults a year. Reading one as the other
misstates the addressable population by a factor of twenty-five, and the two
are therefore carried as separate fields, with separate units, all the way to
the screen.

The funnel each step of which carries its own arithmetic exists for one
question: *where did the patient number in the budget come from?* A funnel that
shows only its outputs cannot answer it. Every step here reports the multiplier
it applied and the multiplication written out, so a reader can check the chain
rather than trust it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from biet_engine.constants import FunnelStage
from biet_engine.models import CountryInput

from ..models.outcomes import CountryHealthIndicator
from ..repositories.outcomes import OutcomesRepository
from ..repositories.reference import ReferenceRepository
from ..schemas.calculation import (
    CountryRead,
    EpidemiologyRead,
    FunnelStepRead,
    HealthIndicatorRead,
    ProvenanceRead,
)

PER_100K = 100_000

#: The WHO indicator holding this disease's annual incidence, per indication.
#: Incidence is not published by WHO and is derived; the row says so in its own
#: `source`, and the interface repeats that rather than presenting it as
#: observed.
INCIDENCE_INDICATOR = {
    1: "obesity_incidence_annual",
    2: "diabetes_incidence_annual",
}

#: What each funnel stage means, in the words a reader would use. Beside the
#: stage vocabulary rather than in the interface, so the exported workbook and
#: the screen define a stage identically.
STAGE_DEFINITIONS: dict[str, tuple[str, str]] = {
    FunnelStage.TOTAL_POPULATION: (
        "Total population",
        (
            "Everyone in the market, all ages. The denominator every figure "
            "below is a share of."
        ),
    ),
    FunnelStage.ADULT_POPULATION: (
        "Adult population",
        (
            "Adults aged 18 and over. WHO publishes obesity prevalence for this "
            "age band, so applying it to the total population instead would "
            "inflate the diseased count by the paediatric share."
        ),
    ),
    FunnelStage.DISEASED: (
        "Prevalent patients",
        (
            "Adults who have the condition right now. This is PREVALENCE — the "
            "standing pool — not the number of new cases a year."
        ),
    ),
    FunnelStage.DIAGNOSED: (
        "Diagnosed patients",
        (
            "Of those, the ones carrying a documented diagnosis. A patient the "
            "health system does not know about cannot be prescribed for."
        ),
    ),
    FunnelStage.TREATED: (
        "Treated patients",
        "Of the diagnosed, those on any drug therapy for the condition today.",
    ),
    FunnelStage.LABEL_ELIGIBLE: (
        "Clinically eligible",
        (
            "Of the treated, those meeting the label and formulary restrictions "
            "— the subgroup definition, BMI threshold, comorbidity requirement "
            "and age band, multiplied together."
        ),
    ),
    FunnelStage.ADDRESSABLE: (
        "Addressable patients",
        (
            "Of the eligible, those with reimbursed access under the assumed "
            "formulary position. This is the population uptake is a share of."
        ),
    ),
}


def _count(value: float) -> str:
    return f"{value:,.0f}"


class EpidemiologyService:
    """The burden figures, and the funnel that turns them into patients."""

    def __init__(self, session: Session) -> None:
        self._outcomes = OutcomesRepository(session)
        self._reference = ReferenceRepository(session)

    def build(
        self,
        *,
        indication_id: int,
        countries: Sequence[CountryInput],
        results: Sequence[CountryRead],
    ) -> dict[str, EpidemiologyRead]:
        """`country_code -> epidemiology block`, one per market in the run."""
        codes = [c.country_code for c in countries]
        indicators = self._outcomes.health_indicators(codes)
        names = {
            str(c.country_code): c.country_name
            for c in self._reference.list_countries(codes)
        }
        incidence_key = INCIDENCE_INDICATOR.get(indication_id)

        out: dict[str, EpidemiologyRead] = {}
        for country_input, result in zip(countries, results, strict=True):
            code = country_input.country_code
            out[code] = self._for_market(
                code, names.get(code, code), country_input, result,
                indicators, incidence_key,
            )
        return out

    def _for_market(
        self,
        code: str,
        country_name: str,
        country_input: CountryInput,
        result: CountryRead,
        indicators: Mapping[tuple[str, str], CountryHealthIndicator],
        incidence_key: str | None,
    ) -> EpidemiologyRead:
        stages = {step.stage: step.value for step in result.funnel}
        adults = stages.get(FunnelStage.ADULT_POPULATION.value, 0.0)
        prevalence = country_input.prevalence.value

        # Incidence applies to the population **at risk** — adults who do not
        # already have the condition. Applying it to all adults would count new
        # cases among people who already have it, which is not a thing that can
        # happen.
        at_risk = max(adults - stages.get(FunnelStage.DISEASED.value, 0.0), 0.0)
        incidence_row = indicators.get((code, incidence_key)) if incidence_key else None
        incidence = (
            float(incidence_row.value)
            if incidence_row is not None and incidence_row.value is not None
            else None
        )

        return EpidemiologyRead(
            country_code=code,
            country_name=country_name,
            population_total=stages.get(FunnelStage.TOTAL_POPULATION.value, 0.0),
            adult_population=adults,
            prevalence=prevalence,
            prevalent_cases=stages.get(FunnelStage.DISEASED.value, 0.0),
            prevalence_low=country_input.prevalence.low,
            prevalence_high=country_input.prevalence.high,
            incidence_annual=incidence,
            incidence_per_100k=None if incidence is None else incidence * PER_100K,
            incident_cases_per_year=None if incidence is None else incidence * at_risk,
            diagnosed_cases=stages.get(FunnelStage.DIAGNOSED.value, 0.0),
            eligible_cases=stages.get(FunnelStage.LABEL_ELIGIBLE.value, 0.0),
            treated_cases=(
                result.years[-1].patients_on_new if result.years else 0.0
            ),
            funnel=self._funnel(result),
            indicators=self._indicators(code, indicators),
        )

    @staticmethod
    def _funnel(result: CountryRead) -> list[FunnelStepRead]:
        """Each step with the multiplication that produced it written out.

        `working` is the whole reason this exists. "1,022,359" tells a reader
        nothing they can check; "8,519,657 x 12.0% = 1,022,359" lets them
        disagree with the 12% specifically, which is the conversation a budget
        impact model is meant to start.
        """
        steps: list[FunnelStepRead] = []
        previous: float | None = None

        for stage in result.funnel:
            label, definition = STAGE_DEFINITIONS.get(
                stage.stage, (stage.stage.replace("_", " ").title(), "")
            )
            working: str | None = None
            factor_label: str | None = None
            if stage.factor is not None and previous is not None:
                factor_label = f"{stage.factor:.1%}"
                working = (
                    f"{_count(previous)} x {factor_label} = {_count(stage.value)}"
                )
            steps.append(FunnelStepRead(
                stage=stage.stage,
                label=label,
                definition=definition,
                value=stage.value,
                factor=stage.factor,
                factor_label=factor_label,
                working=working,
                provenance=stage.provenance,
            ))
            previous = stage.value
        return steps

    @staticmethod
    def _indicators(
        code: str, indicators: Mapping[tuple[str, str], CountryHealthIndicator],
    ) -> list[HealthIndicatorRead]:
        """Every WHO figure for this market, each carrying its own kind.

        A rate is additionally reported per 100,000, because that is the unit
        an incidence is conventionally quoted and read in — "1,716 per 100,000
        a year" is legible where "0.01716" is not.
        """
        out: list[HealthIndicatorRead] = []
        for (country, name), row in sorted(indicators.items()):
            if country != code:
                continue
            value = row.value
            numeric = None if value is None else float(value)
            kind = row.indicator_kind
            out.append(HealthIndicatorRead(
                country_code=country,
                indicator=name,
                kind=kind,
                label=row.label,
                value=numeric,
                per_100k=(
                    numeric * PER_100K
                    if numeric is not None and kind in {"prevalence", "incidence"}
                    else None
                ),
                source=row.source,
                source_url=row.source_url,
                vintage_year=row.vintage_year,
                confidence_tier=str(row.confidence_tier),
            ))
        return out


def provenance_of(step: FunnelStepRead) -> ProvenanceRead | None:
    return step.provenance
