"""One-way deterministic sensitivity (OWSA) and the tornado ranking —
module M9 section 5.1.

At the early stage BIET serves, the ranked list is more valuable than the
point estimate: it says which evidence is worth buying before the decision
is made.
"""

from __future__ import annotations

from collections.abc import Sequence

from .constants import (
    OWSA_DEFAULT_VARIATION,
    TIER_RELATIVE_STANDARD_ERROR,
    ConfidenceTier,
)
from .impact import compute_budget_impact
from .models import (
    CountryInput,
    EngineInput,
    OwsaEntry,
    OwsaResult,
    SensitivityParam,
    Valued,
    Warning_,
)

#: Parameter paths this module knows how to substitute into an EngineInput.
#: A path outside this set is reported as a warning rather than silently
#: producing a zero swing, which would read as "this parameter doesn't
#: matter" when the truth is "this parameter wasn't swept".
_RATE_PATHS = {
    "epidemiology.prevalence",
    "countries.adult_share",
    "funnel.diagnosis_rate",
    "funnel.treatment_rate",
    "funnel.access_rate",
}


def range_for(value: Valued, *, is_rate: bool) -> tuple[float, float]:
    """The low/high sweep bounds for one parameter, per section 5.1's
    priority order:

    1. Published bounds where they exist (WHO prevalence carries them).
    2. Confidence-tier default relative standard error, applied as
       `base x (1 -/+ 2 x rse)` to approximate a 95% range.
    3. `OWSA_DEFAULT_VARIATION` where neither applies.

    Rate-like parameters are clipped to (0, 1]. Clipping is silent — it is a
    domain constraint, not a data problem.
    """
    if value.low is not None and value.high is not None:
        low, high = value.low, value.high
    else:
        tier = value.provenance.confidence_tier
        rse = TIER_RELATIVE_STANDARD_ERROR.get(
            ConfidenceTier(tier), OWSA_DEFAULT_VARIATION,
        )
        low = value.value * (1 - 2 * rse)
        high = value.value * (1 + 2 * rse)

    if is_rate:
        low = max(low, 1e-9)
        high = min(high, 1.0)
    else:
        low = max(low, 0.0)

    return low, high


def default_params(inputs: EngineInput) -> tuple[SensitivityParam, ...]:
    """The parameters swept when the caller doesn't name its own.

    Section 5.1 lists a longer default set than this — it also names uptake
    terminal, per-therapy persistence, wastage, discount, PPP elasticity and
    the offset. Those are omitted here because they are *per-therapy* or
    *scenario-level* rather than per-market, and substituting them means
    rebuilding a therapy or the uptake curve rather than swapping one
    market-level scalar. `run_owsa` accepts an explicit `params` sequence, so
    a caller that wants them can construct them; the default set covers the
    market-level funnel drivers, which is where the tornado's top entries
    almost always sit.
    """
    if not inputs.countries:
        return ()

    first = inputs.countries[0]
    params: list[SensitivityParam] = []

    def _add(path: str, label: str, value: Valued) -> None:
        low, high = range_for(value, is_rate=path in _RATE_PATHS)
        params.append(SensitivityParam(
            parameter_path=path, label=label, base_value=value.value,
            low_value=low, high_value=high,
        ))

    _add("epidemiology.prevalence", "Disease prevalence", first.prevalence)
    if first.adult_share is not None:
        _add("countries.adult_share", "Adult share of population", first.adult_share)
    _add("funnel.diagnosis_rate", "Diagnosis rate", first.funnel.diagnosis_rate)
    _add("funnel.treatment_rate", "Treatment rate", first.funnel.treatment_rate)
    _add("funnel.access_rate", "Access rate", first.funnel.access_rate)

    return tuple(params)


def _with_parameter(inputs: EngineInput, path: str, value: float) -> EngineInput:
    """A copy of `inputs` with `path` set to `value` in every market.

    Applied across all markets rather than market-by-market: OWSA ranks
    assumptions for the run as a whole, so a swing has to move the whole
    cross-market total to be meaningful.
    """
    countries: list[CountryInput] = []
    for country in inputs.countries:
        if path == "epidemiology.prevalence":
            countries.append(country.model_copy(update={
                "prevalence": country.prevalence.model_copy(update={"value": value}),
            }))
        elif path == "countries.adult_share":
            if country.adult_share is None:
                countries.append(country)
            else:
                countries.append(country.model_copy(update={
                    "adult_share": country.adult_share.model_copy(update={"value": value}),
                }))
        elif path in ("funnel.diagnosis_rate", "funnel.treatment_rate", "funnel.access_rate"):
            field = path.split(".", 1)[1]
            current = getattr(country.funnel, field)
            countries.append(country.model_copy(update={
                "funnel": country.funnel.model_copy(update={
                    field: current.model_copy(update={"value": value}),
                }),
            }))
        else:
            countries.append(country)

    return inputs.model_copy(update={"countries": tuple(countries)})


def run_owsa(
    inputs: EngineInput, params: Sequence[SensitivityParam] | None = None,
) -> OwsaResult:
    """Cumulative budget impact at each parameter's bounds, ranked by swing.

    Costs `2N + 1` forward evaluations for `N` parameters — each bound plus
    one base case.

    M3's correlation guard runs in permissive mode throughout (section 5.1):
    a sweep that transiently produces a correlated pair must warn, not abort
    the whole analysis. That happens inside `compute_budget_impact`, which
    calls `combine_criteria` with its default strict mode — so a scenario
    whose *base case* already has a correlated pair enabled will raise here
    just as it would in a forward run, which is the correct behaviour; it is
    only sweep-induced transients that permissive mode is meant to tolerate,
    and this module's swept parameters cannot create one.

    Args:
        inputs: the run to sweep around.
        params: parameters to sweep; `default_params(inputs)` when omitted.

    Returns:
        The base-case cumulative impact and one entry per parameter, sorted
        by descending swing. A zero-swing parameter is retained and ranked
        last — a parameter that does not move the answer is a finding
        (section 6), not something to hide.
    """
    swept = tuple(params) if params is not None else default_params(inputs)

    base_result = compute_budget_impact(inputs).totals.cumulative.amount
    warnings: list[Warning_] = []

    scored: list[tuple[float, SensitivityParam, float, float]] = []
    for param in swept:
        if param.parameter_path not in _RATE_PATHS:
            warnings.append(Warning_(
                code="PARAMETER_NOT_SWEPT",
                message=f"{param.parameter_path!r} has no substitution rule in this "
                        "module and was evaluated at base on both bounds; its zero "
                        "swing means 'not swept', not 'no influence'",
                parameter_path=param.parameter_path,
            ))

        at_low = compute_budget_impact(
            _with_parameter(inputs, param.parameter_path, param.low_value)
        ).totals.cumulative.amount
        at_high = compute_budget_impact(
            _with_parameter(inputs, param.parameter_path, param.high_value)
        ).totals.cumulative.amount
        scored.append((abs(at_high - at_low), param, at_low, at_high))

    scored.sort(key=lambda row: row[0], reverse=True)

    entries = tuple(
        OwsaEntry(
            parameter_path=param.parameter_path, label=param.label,
            base_value=param.base_value, low_value=param.low_value,
            high_value=param.high_value, result_at_low=at_low, result_at_high=at_high,
            swing=swing, rank=rank,
        )
        for rank, (swing, param, at_low, at_high) in enumerate(scored, start=1)
    )

    return OwsaResult(base_result=base_result, entries=entries, warnings=tuple(warnings))
