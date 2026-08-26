"""Seeded subgroup taxonomy and default shares — M18 sections 5.1 and 7.

**On the honesty of these numbers.** Every share here is **tier C**: derived
from published co-prevalence of each comorbidity within adult populations with
obesity, not from a country-specific survey, and applied globally rather than
per market. Comorbidity co-prevalence within an obese population is published
for type 2 diabetes and hypertension in most of the ten markets, thinner for
dyslipidaemia, and thin everywhere for established cardiovascular disease
within obesity specifically.

Seeding these at tier A would be a lie, and seeding them per market from
figures that do not exist would be a worse one. M15's evidence-gap ranking will
surface the split between subgroups as one of the least certain things in the
model, which is the intended outcome rather than an embarrassment: it is.

The shares are the fraction of the adult obesity population whose *highest
priority* qualifying condition is that one — not raw comorbidity prevalence,
which double-counts, and which is exactly the mistake M18 section 5.2 exists to
prevent. They therefore sum to less than one, and obesity alone is the residual.
"""

from __future__ import annotations

from typing import Final

from biet_engine.constants import Subgroup

#: Human-readable label and one-sentence clinical definition per subgroup.
SUBGROUP_LABELS: Final[dict[Subgroup, str]] = {
    Subgroup.OBESITY_ESTABLISHED_CVD: "Obesity with established cardiovascular disease",
    Subgroup.OBESITY_T2D: "Obesity with type 2 diabetes",
    Subgroup.OBESITY_HYPERTENSION: "Obesity with hypertension",
    Subgroup.OBESITY_DYSLIPIDAEMIA: "Obesity with dyslipidaemia",
    Subgroup.OBESITY_ALONE: "Obesity with none of the above",
    Subgroup.PAEDIATRIC_OBESITY: "Paediatric obesity",
}

SUBGROUP_DEFINITIONS: Final[dict[Subgroup, str]] = {
    Subgroup.OBESITY_ESTABLISHED_CVD: (
        "BMI 30 or above with prior myocardial infarction, stroke or symptomatic "
        "peripheral arterial disease. The highest baseline event rate, and the "
        "population where an avoided event is worth most."
    ),
    Subgroup.OBESITY_T2D: (
        "BMI 30 or above with diagnosed type 2 diabetes and no established "
        "cardiovascular disease. Already on glucose-lowering therapy, so the cost "
        "a new therapy displaces is large."
    ),
    Subgroup.OBESITY_HYPERTENSION: (
        "BMI 30 or above with diagnosed hypertension and neither of the above. "
        "Large, and cheaply treated today, so displaced cost is small."
    ),
    Subgroup.OBESITY_DYSLIPIDAEMIA: (
        "BMI 30 or above with diagnosed dyslipidaemia and none of the above. "
        "Typically on statin therapy."
    ),
    Subgroup.OBESITY_ALONE: (
        "BMI 30 or above with none of the qualifying comorbidities. The lowest "
        "event rate, and the segment a payer is least likely to fund."
    ),
    Subgroup.PAEDIATRIC_OBESITY: (
        "Under 18, with BMI at or above the 95th centile for age and sex. Not the "
        "adult BMI-30 cut-off: applying that to a child selects a far smaller and "
        "sicker group than the label suggests. Its own denominator, so it is not "
        "part of the adult partition."
    ),
}

#: Fraction of the adult obesity population allocated to each comorbidity
#: subgroup under the priority rule. Obesity alone is the residual (0.30) and
#: is deliberately absent — it is derived, never supplied.
DEFAULT_SUBGROUP_SHARES: Final[dict[Subgroup, float]] = {
    Subgroup.OBESITY_ESTABLISHED_CVD: 0.08,
    Subgroup.OBESITY_T2D: 0.19,
    Subgroup.OBESITY_HYPERTENSION: 0.30,
    Subgroup.OBESITY_DYSLIPIDAEMIA: 0.13,
}

SUBGROUP_SHARE_SOURCE: Final[str] = (
    "Seeded co-prevalence within adult obesity — global default, not country-specific"
)
SUBGROUP_SHARE_TIER: Final[str] = "C"
