"""What every input means — the single description of each field.

This module exists because the same sentence is needed in four places: the
hover text in the interface, the guidance column in the import template, the
assumption register in the PDF, and the note on a rejected cell. Writing it
four times guarantees they drift, and a field described one way on screen and
another way in the workbook is worse than one described nowhere — the reader
cannot tell which is authoritative.

The **grouping and order** follow the input taxonomy from the HEOR review, and
they are load-bearing rather than cosmetic. Population before epidemiology
before eligibility before current care is the order the funnel actually
computes in, so an analyst filling the form top to bottom is walking the model
rather than hunting for fields. `ARCHITECTURE.md` Phase 15 states the same
requirement: inputs first, then outputs, every field explained in place.

`parameter_path` ties a field to the closed override vocabulary. A field with
no path is part of the scenario definition itself (its markets, its horizon)
rather than an assumption that can be overridden per market.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class FieldSpec:
    """One input, and everything a reader needs to know about it in place."""

    key: str
    label: str
    #: What this is, in the words an analyst would use. One or two sentences —
    #: long enough to be an answer, short enough to sit in a tooltip.
    description: str
    #: What it does to the answer, when that is not obvious from the name. The
    #: half of an explanation that a glossary definition always leaves out.
    effect: str | None = None
    unit: str = ""
    parameter_path: str | None = None
    #: A worked example, so the expected magnitude is unambiguous. "0.19" and
    #: "19" are the same intention and differ by a factor of a hundred.
    example: str | None = None
    typical_range: str | None = None
    #: Whether an import template should carry a column for it.
    importable: bool = True


@dataclass(frozen=True)
class FieldGroup:
    """One row of the review's input taxonomy."""

    key: str
    label: str
    summary: str
    fields: list[FieldSpec] = field(default_factory=list)


RATE_NOTE = "A fraction between 0 and 1, not a percentage. 0.19 means 19%."

#: The distinction this whole module exists to keep straight, written once and
#: quoted wherever either term appears. Prevalence and incidence differ by more
#: than an order of magnitude for a persistent condition, and reading one as the
#: other is the commonest error an epidemiology panel makes.
PREVALENCE_NOTE = (
    "PREVALENCE is a stock: the share of a population that has the condition "
    "at a point in time."
)
INCIDENCE_NOTE = (
    "INCIDENCE is a flow: the share that newly acquires the condition each "
    "year. It is conventionally quoted per 100,000 population per year."
)


FIELD_GROUPS: Final[tuple[FieldGroup, ...]] = (
    FieldGroup(
        key="population",
        label="Population",
        summary=(
            "Who the model starts from. Everything below narrows this number; "
            "nothing widens it."
        ),
        fields=[
            FieldSpec(
                key="country_codes",
                label="Markets",
                description=(
                    "The countries this scenario covers. Each one is modelled "
                    "separately in its own currency and rolled up into the "
                    "reporting currency at the run's snapshotted exchange rates."
                ),
                effect=(
                    "Adding a market adds its whole funnel. It does not dilute "
                    "the others."
                ),
                example="USA, DEU, GBR, JPN, IND",
                importable=True,
            ),
            FieldSpec(
                key="covered_population",
                label="Covered lives",
                description=(
                    "How many people the payer reading this actually covers. "
                    "Leave blank for a whole-country view."
                ),
                effect=(
                    "This is the denominator of every per-member figure. An "
                    "insurer's PMPM against a national population is wrong by "
                    "the ratio between them — often a hundredfold."
                ),
                unit="people",
                example="4,000,000",
            ),
            FieldSpec(
                key="population_growth",
                label="Annual population growth",
                description=(
                    "How fast the covered population grows over the horizon. "
                    "Seeded at zero — a stated flat population rather than an "
                    "invented growth rate."
                ),
                unit="fraction per year",
                example="0.004",
                typical_range="0 to 0.02",
            ),
        ],
    ),
    FieldGroup(
        key="epidemiology",
        label="Epidemiology",
        summary="How much of that population has the disease, and how much of it is known about.",
        fields=[
            FieldSpec(
                key="prevalence",
                label="Prevalence",
                description=(
                    "The share of adults who have the condition right now, from "
                    "WHO's age-standardised indicator. " + PREVALENCE_NOTE
                    + " " + RATE_NOTE
                ),
                effect=(
                    "Applied to the *adult* population, never the total — WHO "
                    "publishes it for ages 18 and over, and applying it to a "
                    "total population inflates the prevalent count by the "
                    "paediatric share. This is the standing pool the funnel "
                    "narrows down; every patient figure in the budget descends "
                    "from it."
                ),
                unit="fraction of adults",
                parameter_path="epidemiology.prevalence",
                example="0.429 (USA, WHO 2024)",
                typical_range="0.05 to 0.45",
            ),
            FieldSpec(
                key="incidence",
                label="Incidence",
                description=(
                    "New cases arising each year among adults who do not "
                    "already have the condition. " + INCIDENCE_NOTE
                ),
                effect=(
                    "Not the same quantity as prevalence and never added to it. "
                    "US adult obesity is 42.9% prevalent but roughly 1,716 new "
                    "cases per 100,000 a year — a factor of twenty-five apart. "
                    "Incidence is what makes a five-year addressable population "
                    "larger than a one-year one; prevalence is what the funnel "
                    "starts from."
                ),
                unit="per 100,000 at risk per year",
                example="1,716 (USA, derived)",
                typical_range="400 to 2,000 per 100,000",
                importable=False,
            ),
            FieldSpec(
                key="diagnosis_rate",
                label="Diagnosed share of prevalent cases",
                description=(
                    "Of everyone with the condition, the share carrying a "
                    "documented diagnosis. " + RATE_NOTE
                ),
                effect=(
                    "For obesity this is the most surprising number in the "
                    "model: documented diagnosis runs near 19%, so four in "
                    "five people with the condition are invisible to the "
                    "health system that would pay for treating it."
                ),
                unit="fraction",
                parameter_path="funnel.diagnosis_rate",
                example="0.19",
                typical_range="0.15 to 0.75",
            ),
        ],
    ),
    FieldGroup(
        key="eligibility",
        label="Eligibility",
        summary=(
            "Which of the diagnosed patients the label and the formulary "
            "actually allow onto this therapy."
        ),
        fields=[
            FieldSpec(
                key="subgroup_codes",
                label="Clinical subgroup",
                description=(
                    "The clinically distinct population inside the disease that "
                    "this run models — obesity with type 2 diabetes, with "
                    "established cardiovascular disease, with hypertension or "
                    "sleep apnoea, or severe obesity. Choose none to model "
                    "every adult with the condition."
                ),
                effect=(
                    "One at a time, because these subgroups OVERLAP: a patient "
                    "with both diabetes and hypertension is in two of them, and "
                    "across WHO's ten source countries the four shares sum to "
                    "roughly 1.5x the obese population. They are alternative "
                    "eligibility definitions to compare, not components of a "
                    "total to add — the Subgroups tab runs each independently "
                    "and shows them side by side."
                ),
                example="cvd_mace_risk",
            ),
            FieldSpec(
                key="criteria",
                label="Eligibility criteria",
                description=(
                    "The label and formulary restrictions — BMI threshold, "
                    "required comorbidity, age band, prior therapy. Each is a "
                    "multiplier on the treated population."
                ),
                effect=(
                    "Criteria multiply, so two 50% criteria leave 25%. "
                    "Clinically overlapping pairs are flagged rather than "
                    "silently multiplied, because BMI over 35 and established "
                    "cardiovascular disease describe substantially the same "
                    "patients."
                ),
                unit="fraction",
                parameter_path="criteria.<criterion_code>.factor",
                example="0.45",
            ),
            FieldSpec(
                key="treatment_rate",
                label="Treated share",
                description=(
                    "Of the diagnosed patients, the share on any drug therapy "
                    "for the condition today. " + RATE_NOTE
                ),
                unit="fraction",
                parameter_path="funnel.treatment_rate",
                example="0.23",
                typical_range="0.10 to 0.90",
            ),
            FieldSpec(
                key="access_rate",
                label="Reimbursed access",
                description=(
                    "Of the label-eligible patients, the share with reimbursed "
                    "access under the assumed formulary position. " + RATE_NOTE
                ),
                effect=(
                    "Distinct from uptake, and the distinction matters: access "
                    "is who *may* receive the therapy, uptake is what share of "
                    "those actually do."
                ),
                unit="fraction",
                parameter_path="funnel.access_rate",
                example="0.70",
                typical_range="0.30 to 0.95",
            ),
        ],
    ),
    FieldGroup(
        key="current_care",
        label="Current care",
        summary=(
            "What these patients receive today. This is the world-without, and "
            "its cost is subtracted from the world-with."
        ),
        fields=[
            FieldSpec(
                key="comparator_prices",
                label="Comparator prices",
                description=(
                    "The unit price of every therapy the new asset displaces, "
                    "per market. Editable everywhere, and pre-filled with the "
                    "model's own derivation where no observed price exists."
                ),
                effect=(
                    "Budget impact is incremental, so a comparator priced too "
                    "low overstates the impact by exactly that difference. "
                    "This is the input most worth correcting from local "
                    "knowledge."
                ),
                unit="local currency per unit",
                parameter_path="therapy.<drug_id>.price_local",
                example="31.45",
            ),
            FieldSpec(
                key="substitution",
                label="Source of business",
                description=(
                    "Where the new therapy's patients come from — which "
                    "incumbent each one leaves, or whether they are new to "
                    "treatment. The shares sum to 1."
                ),
                effect=(
                    "A patient switching from an expensive comparator carries "
                    "far less incremental cost than one starting therapy for "
                    "the first time. Getting this wrong moves the answer more "
                    "than the price does."
                ),
                unit="fraction",
                parameter_path="substitution.<drug_id>",
                example="0.35",
            ),
        ],
    ),
    FieldGroup(
        key="new_intervention",
        label="New intervention",
        summary="The asset being evaluated, and what it costs to give.",
        fields=[
            FieldSpec(
                key="asset_name",
                label="Asset",
                description="The therapy under evaluation, as it should appear in the report.",
                example="Wegovy (semaglutide 2.4 mg)",
            ),
            FieldSpec(
                key="asset_price",
                label="Price",
                description=(
                    "The new asset's unit price in each market. Enter either "
                    "the unit price or the annual cost — the other is derived "
                    "from the regimen."
                ),
                effect=(
                    "A 'monthly' package for this class is 28 days, so a year "
                    "is thirteen packages and not twelve. A model built the "
                    "other way will differ by 8.3%."
                ),
                unit="local currency per unit",
                parameter_path="therapy.<drug_id>.price_local",
                example="31.45",
            ),
            FieldSpec(
                key="launch_year",
                label="Launch year",
                description=(
                    "The calendar year of market entry. Year 1 of the model is "
                    "the launch year; calendar years are derived from it for "
                    "display only."
                ),
                example="2028",
            ),
        ],
    ),
    FieldGroup(
        key="uptake",
        label="Uptake",
        summary="How fast the market adopts it, year by year.",
        fields=[
            FieldSpec(
                key="uptake_year_1",
                label="Year-1 uptake",
                description=(
                    "The share of the addressable population on the new "
                    "therapy in its launch year. " + RATE_NOTE
                ),
                unit="fraction",
                parameter_path="uptake.year_1",
                example="0.05",
                typical_range="0.01 to 0.15",
            ),
            FieldSpec(
                key="uptake_terminal",
                label="Terminal uptake",
                description=(
                    "The plateau share by the end of the horizon. " + RATE_NOTE
                ),
                effect=(
                    "Reported at half and 1.75 times this figure as well, so "
                    "the conversation happens across three adoption cases "
                    "rather than one."
                ),
                unit="fraction",
                parameter_path="uptake.terminal",
                example="0.15",
                typical_range="0.05 to 0.40",
            ),
            FieldSpec(
                key="uptake_curve",
                label="Adoption curve",
                description=(
                    "Logistic for a therapy entering an established "
                    "competitive class; linear for first-in-class entry into "
                    "an untreated population."
                ),
                parameter_path="uptake.curve",
                example="logistic",
            ),
        ],
    ),
    FieldGroup(
        key="treatment_behaviour",
        label="Treatment behaviour",
        summary=(
            "What happens after the prescription. Patients who stop consume "
            "less drug and gain less benefit, and both need counting."
        ),
        fields=[
            FieldSpec(
                key="persistence_12m",
                label="12-month persistence",
                description=(
                    "The share of patients still on therapy twelve months "
                    "after starting. " + RATE_NOTE
                ),
                effect=(
                    "Converted to a treatment-year fraction rather than "
                    "applied directly: a patient who stops at month five "
                    "consumes five months of drug, not none and not twelve."
                ),
                unit="fraction",
                parameter_path="therapy.<drug_id>.persistence_12m",
                example="0.55",
                typical_range="0.30 to 0.80",
            ),
            FieldSpec(
                key="regain_per_year",
                label="Weight regain per year",
                description=(
                    "How much of the achieved effect is lost each year after "
                    "the first. Seeded at zero on the strength of the "
                    "maintenance trials."
                ),
                effect=(
                    "Applied from year 2 only. A trial's reported effect is "
                    "the year-one effect, so decaying it in the year it was "
                    "measured would double-count regain the trial already saw."
                ),
                unit="fraction per year",
                parameter_path="outcomes.regain_per_year",
                example="0.10",
                typical_range="0 to 0.30",
            ),
        ],
    ),
    FieldGroup(
        key="outcomes",
        label="Outcomes",
        summary=(
            "What the spend buys. Effects are supplied from named trials and "
            "never inferred from a drug class or a mechanism."
        ),
        fields=[
            FieldSpec(
                key="treatment_effects",
                label="Relative risk reductions",
                description=(
                    "Each therapy's published reduction in cardiovascular "
                    "events and in progression to diabetes, with the trial it "
                    "comes from."
                ),
                effect=(
                    "Relative, never absolute. An absolute reduction observed "
                    "in one population cannot be transported to a population "
                    "with a different baseline rate, and doing it anyway is "
                    "the commonest way a model overstates what a therapy buys."
                ),
                unit="fraction",
                example="0.20 (SELECT, hazard ratio 0.80)",
                importable=False,
            ),
            FieldSpec(
                key="responder_share",
                label="Weight-loss responders",
                description=(
                    "The share of patients reaching the trial's weight-loss "
                    "threshold, at 5% or more."
                ),
                unit="fraction",
                example="0.864 (STEP 1)",
                importable=False,
            ),
        ],
    ),
    FieldGroup(
        key="healthcare_costs",
        label="Healthcare costs",
        summary=(
            "Everything beyond the drug itself — giving it, monitoring it, "
            "managing its side effects, and the complications it avoids."
        ),
        fields=[
            FieldSpec(
                key="admin_cost",
                label="Administration cost",
                description=(
                    "The annual cost of administering the therapy, beyond "
                    "acquisition. Zero for a self-injected or oral product."
                ),
                unit="local currency per year",
                example="0",
            ),
            FieldSpec(
                key="monitoring_cost",
                label="Monitoring cost",
                description=(
                    "Annual consultations, laboratory tests and follow-up "
                    "attributable to being on this therapy."
                ),
                unit="local currency per year",
                example="180",
            ),
            FieldSpec(
                key="ae_cost",
                label="Adverse-event cost",
                description=(
                    "Expected annual cost of managing the therapy's side "
                    "effects, from published incidences and market unit costs."
                ),
                effect=(
                    "For this class it lands at $37-60 a year against "
                    "acquisition costs of $13,000-17,500 — economically "
                    "negligible, and the model says so rather than "
                    "manufacturing a story."
                ),
                unit="local currency per year",
                importable=False,
            ),
            FieldSpec(
                key="event_costs",
                label="Avoided-event costs",
                description=(
                    "What one avoided cardiovascular event or new diabetes "
                    "case would have cost the payer."
                ),
                effect=(
                    "Enters as an offset against the new therapy's own annual "
                    "cost, not as a separate line — an avoided cost is part of "
                    "the cost of the therapy that avoided it."
                ),
                unit="local currency per event",
                example="23,000",
                importable=False,
            ),
        ],
    ),
    FieldGroup(
        key="time_horizon",
        label="Time horizon",
        summary="How many years the budget holder is planning over.",
        fields=[
            FieldSpec(
                key="horizon_years",
                label="Horizon",
                description=(
                    "The number of years modelled, from launch. Three to five "
                    "is the usual budget-impact window."
                ),
                effect=(
                    "A horizon longer than the trial's follow-up is an "
                    "extrapolation, and the run says so by name rather than "
                    "projecting past what was observed in silence."
                ),
                unit="years",
                example="3",
                typical_range="1 to 5",
            ),
            FieldSpec(
                key="reporting_currency",
                label="Reporting currency",
                description=(
                    "The currency the cross-market total is presented in. Each "
                    "market is still computed in its own."
                ),
                effect=(
                    "Exchange rates are snapshotted into the run, never looked "
                    "up live, so re-opening an old run reproduces its original "
                    "numbers exactly."
                ),
                example="EUR",
            ),
        ],
    ),
    FieldGroup(
        key="perspective",
        label="Perspective",
        summary=(
            "Whose budget this lands on. It selects the denominator and "
            "decides which costs are in scope at all."
        ),
        fields=[
            FieldSpec(
                key="perspective",
                label="Payer perspective",
                description=(
                    "Commercial insurer, self-insured employer, government "
                    "payer, or the whole health system."
                ),
                effect=(
                    "The same national impact reads as a very different "
                    "per-member figure to each of them. An employer covering "
                    "forty thousand lives and a health system covering eighty "
                    "million are three orders of magnitude apart."
                ),
                example="insurer",
            ),
        ],
    ),
)


#: `key -> spec`, for a lookup by field. Built once rather than searched, since
#: the interface asks for a tooltip on every hover.
FIELD_INDEX: Final[dict[str, FieldSpec]] = {
    spec.key: spec for group in FIELD_GROUPS for spec in group.fields
}


def importable_fields() -> list[tuple[str, FieldSpec]]:
    """The fields a workbook template carries a column for, in taxonomy order.

    Outcome evidence is excluded by design: a relative risk reduction belongs
    to a trial, not to a scenario, and letting one be typed into a spreadsheet
    would be exactly the "effect asserted without a trial behind it" that M16
    exists to prevent.
    """
    return [
        (group.key, spec)
        for group in FIELD_GROUPS
        for spec in group.fields
        if spec.importable
    ]
