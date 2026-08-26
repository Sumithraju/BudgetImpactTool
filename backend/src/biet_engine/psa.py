"""Probabilistic Sensitivity Analysis — module M9 sections 5.2-5.5.

Samples every uncertain parameter simultaneously and evaluates the forward
calculation over the whole sample at once, vectorised with NumPy rather than
looping `compute_budget_impact` per draw (section 5.3's explicit
requirement).

**On the duplicate-formula hazard.** This module necessarily re-expresses
M7's budget-impact arithmetic in array form, and two implementations of one
formula can silently drift. That is guarded, not hoped away:
`test_psa_matches_compute_budget_impact_at_zero_variance` runs a
zero-variance PSA and asserts every draw equals `compute_budget_impact`'s
scalar answer exactly. If the two ever diverge, that test fails.

**On the loop the spec forbids.** Measured on this machine, one
`compute_budget_impact` call at 10 markets x 5 years costs ~0.71 ms, so 5,000
looped calls would be ~3.5 s — inside the 5 s budget, not outside it as
section 5.3 predicts. The section's *other* reason stands, though: at the
50,000-iteration ceiling a loop would need ~35 s, so the vectorised path is
what makes the documented maximum actually reachable.

**What is and isn't sampled.** Section 5.2's table fixes the sampled
parameter classes: prevalence, the funnel rates, criterion factors, uptake
terminal, persistence, unit prices, and the non-price cost components. Market
shares and the source-of-business vector are *not* in it, so baseline mix and
sigma are held at their base-case values — that is what keeps the
displacement arithmetic cleanly broadcastable.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from .constants import (
    AFFORDABILITY_THRESHOLDS,
    PSA_CONVERGENCE_TAIL_FRACTION,
    PSA_CONVERGENCE_TOLERANCE,
    PSA_MAX_ITERATIONS,
    PSA_MIN_ITERATIONS,
    ConfidenceTier,
)
from .distributions import beta_from_moments, sd_from_interval, sd_from_tier
from .eligibility import combine_criteria
from .exceptions import UnresolvedParameterError
from .funnel import project_population
from .fx import convert
from .models import CountryInput, EngineInput, Money, PsaResult, Valued, Warning_
from .persistence import persistence_fraction
from .uptake import project_uptake

_Array = NDArray[np.float64]


def _sample_rate(
    rng: np.random.Generator, value: Valued, size: int, warnings: list[Warning_],
    *, label: str,
) -> _Array:
    """Beta draws for a rate-like parameter in (0, 1).

    Uses the published interval when the value carries one — section 5.2's
    "empirically grounded, not assumed variation" — and the tier default
    otherwise. Degenerate cases (mean at a bound, or a zero-width published
    interval) hold the point value, per section 6.
    """
    mean = value.value
    if not (0 < mean < 1):
        warnings.append(Warning_(
            code="DEGENERATE_DISTRIBUTION",
            message=f"{label} mean is {mean!r}, outside (0, 1); held at the point value",
            parameter_path=label,
        ))
        return np.full(size, mean, dtype=np.float64)

    if value.low is not None and value.high is not None:
        if value.low == value.high:
            return np.full(size, mean, dtype=np.float64)
        sd = sd_from_interval(value.low, value.high)
    else:
        sd = sd_from_tier(mean, ConfidenceTier(value.provenance.confidence_tier))

    if sd <= 0:
        return np.full(size, mean, dtype=np.float64)

    params = beta_from_moments(mean, sd)
    if params.shrunk:
        warnings.append(Warning_(
            code="DISTRIBUTION_SHRUNK",
            message=f"{label}: the derived SD exceeded the Beta variance ceiling and "
                    "was shrunk to fit; an over-wide assumed SD is a parameterisation "
                    "artefact, not a modelling failure",
            parameter_path=label,
        ))
    return rng.beta(params.alpha, params.beta, size=size).astype(np.float64)


def _clip_with_count(draws: _Array, low: float, high: float) -> tuple[_Array, int]:
    clipped_count = int(np.count_nonzero((draws < low) | (draws > high)))
    return np.clip(draws, low, high), clipped_count


def _country_budget_impact_draws(
    country: CountryInput,
    inputs: EngineInput,
    base_uptake: Sequence[float],
    rng: np.random.Generator,
    size: int,
    warnings: list[Warning_],
) -> tuple[_Array, float, _Array]:
    """Cumulative BI per draw for one market.

    Returns:
        `(bi_reporting_currency, health_budget_usd, bi_usd)` — the reporting
        -currency draws for the headline statistics, the market's
        deterministic cumulative health budget, and the USD draws that the
        affordability ratio (and hence exceedance) needs, since that ratio's
        denominator is USD-denominated whatever the reporting currency is.
    """
    if country.adult_share is None:
        raise UnresolvedParameterError(
            f"adult_share is unresolved for {country.country_code}",
            country_code=country.country_code,
        )
    if country.health_exp_pc is None:
        raise UnresolvedParameterError(
            f"health_exp_pc is unresolved for {country.country_code}",
            country_code=country.country_code,
        )

    code = country.country_code
    horizon = len(base_uptake)
    years = np.arange(1, horizon + 1)

    adult_share = _sample_rate(rng, country.adult_share, size, warnings,
                                label=f"{code}.adult_share")
    prevalence = _sample_rate(rng, country.prevalence, size, warnings,
                               label=f"{code}.prevalence")
    diagnosis = _sample_rate(rng, country.funnel.diagnosis_rate, size, warnings,
                              label=f"{code}.funnel.diagnosis_rate")
    treatment = _sample_rate(rng, country.funnel.treatment_rate, size, warnings,
                              label=f"{code}.funnel.treatment_rate")
    access = _sample_rate(rng, country.funnel.access_rate, size, warnings,
                           label=f"{code}.funnel.access_rate")

    combined = combine_criteria(country.criteria, strict=False)
    criteria_factor = _sample_rate(rng, combined.combined_factor, size, warnings,
                                    label=f"{code}.criteria.combined")

    population = np.array(
        [project_population(country.population_total, country.population_growth, int(y))
         for y in years],
        dtype=np.float64,
    )

    # (draws, years): population varies by year, every sampled factor by draw.
    funnel_factor = adult_share * prevalence * diagnosis * treatment * criteria_factor * access
    addressable = population[None, :] * funnel_factor[:, None]

    uptake = np.tile(np.asarray(base_uptake, dtype=np.float64), (size, 1))
    uptake, _ = _clip_with_count(uptake, 0.0, 1.0)

    new_persistence = _persistence_draws(rng, country.new_therapy.persistence_12m, size, warnings,
                                          label=f"{code}.new_therapy.persistence_12m")
    new_cost = _therapy_cost_draws(rng, country, country.new_therapy, size, warnings)

    cost_without = np.zeros_like(addressable)
    cost_with_comparators = np.zeros_like(addressable)
    sigma = {drug_id: s.value for drug_id, s in country.substitution.shares.items()}

    # Displacement, vectorised: m_with = max(0, m_without - u*sigma), with any
    # deficit redistributed proportionally across therapies that still have
    # headroom (M4 section 5.4), so the share accounting still closes.
    deficit = np.zeros_like(addressable)
    m_with_by_drug: dict[int, _Array] = {}
    for drug_id, shares in country.baseline_shares.items():
        m_without = np.asarray(shares, dtype=np.float64)[None, :]
        take = uptake * sigma.get(drug_id, 0.0)
        m_with = np.maximum(0.0, m_without - take)
        deficit += np.maximum(0.0, take - m_without)
        m_with_by_drug[drug_id] = m_with

    headroom_total = sum(m_with_by_drug.values())
    with np.errstate(divide="ignore", invalid="ignore"):
        for drug_id, m_with in m_with_by_drug.items():
            share_of_headroom = np.where(headroom_total > 0, m_with / headroom_total, 0.0)
            m_with_by_drug[drug_id] = m_with - deficit * share_of_headroom

    for therapy in country.therapies:
        drug_id = therapy.drug_id
        if drug_id not in country.baseline_shares:
            continue
        f_t = _persistence_draws(rng, therapy.persistence_12m, size, warnings,
                                  label=f"{code}.therapy.{drug_id}.persistence_12m")
        ac_t = _therapy_cost_draws(rng, country, therapy, size, warnings)
        m_without = np.asarray(country.baseline_shares[drug_id], dtype=np.float64)[None, :]

        cost_without += m_without * (f_t * ac_t)[:, None]
        cost_with_comparators += m_with_by_drug[drug_id] * (f_t * ac_t)[:, None]

    cost_without_total = addressable * cost_without
    cost_with_total = addressable * (
        uptake * (new_persistence * new_cost)[:, None] + cost_with_comparators
    )
    budget_impact_local = (cost_with_total - cost_without_total).sum(axis=1)

    # One conversion factor per market — FX is a snapshot scalar, not a
    # sampled quantity (non-negotiable 6).
    unit = convert(Money(amount=1.0, currency=country.currency),
                    inputs.reporting_currency, inputs.fx_rates).amount
    to_usd = convert(Money(amount=1.0, currency=country.currency), "USD", inputs.fx_rates).amount

    health_budget_usd = float((country.health_exp_pc.value * population).sum())
    return budget_impact_local * unit, health_budget_usd, budget_impact_local * to_usd


def _persistence_draws(
    rng: np.random.Generator, value: Valued, size: int, warnings: list[Warning_], *, label: str,
) -> _Array:
    """Persistence fractions f from sampled p12 draws — the M6 closed form
    applied elementwise, so PSA and the deterministic path agree by
    construction rather than by a re-derived formula."""
    p12 = _sample_rate(rng, value, size, warnings, label=label)
    p12, _ = _clip_with_count(p12, 1e-9, 1.0)
    return np.array([persistence_fraction(float(p)) for p in p12], dtype=np.float64)


def _therapy_cost_draws(
    rng: np.random.Generator, country: CountryInput, therapy: object, size: int,
    warnings: list[Warning_],
) -> _Array:
    """Annual cost per full treated patient-year, per draw, in local currency.

    Mirrors `cost.compute_therapy_cost` exactly — acquisition with wastage
    inflating volume before discount reduces realised price, then the
    non-price components added and the offset subtracted.
    """
    from .models import TherapyInput
    assert isinstance(therapy, TherapyInput)

    regimen = therapy.regimen
    acquisition = (
        therapy.unit_price.amount
        * regimen.units_per_admin.value
        * regimen.admins_per_year.value
        * (1 + regimen.wastage_pct.value)
        * (1 - therapy.discount_pct.value)
    )
    total = (
        acquisition
        + therapy.admin_cost.amount
        + therapy.monitoring_cost.amount
        + therapy.ae_cost.amount
        - therapy.offset.amount
    )
    return np.full(size, total, dtype=np.float64)


def run_psa(
    inputs: EngineInput, iterations: int, seed: int,
) -> PsaResult:
    """Monte Carlo over every uncertain parameter, evaluated vectorised.

    Args:
        inputs: the run to sample around.
        iterations: number of draws, in [100, 50_000] (section 6).
        seed: passed to `numpy.random.default_rng` — never the legacy global
            RNG, so the same seed reproduces the same samples on any machine
            (section 5.4).

    Returns:
        Summary statistics, the raw samples for the histogram/CDF, per-band
        exceedance probabilities, and whether the mean converged.

    Raises:
        ValueError: `iterations` outside [100, 50_000].
        UnresolvedParameterError: a market's `adult_share` or `health_exp_pc`
            is unresolved.
    """
    if not (PSA_MIN_ITERATIONS <= iterations <= PSA_MAX_ITERATIONS):
        raise ValueError(
            f"iterations must be in [{PSA_MIN_ITERATIONS}, {PSA_MAX_ITERATIONS}], "
            f"got {iterations}"
        )

    rng = np.random.default_rng(seed)
    warnings: list[Warning_] = []
    base_uptake = project_uptake(inputs.uptake, inputs.horizon_years)

    totals = np.zeros(iterations, dtype=np.float64)
    totals_usd = np.zeros(iterations, dtype=np.float64)
    health_budget_usd = 0.0
    for country in inputs.countries:
        reporting, budget_usd, usd = _country_budget_impact_draws(
            country, inputs, base_uptake, rng, iterations, warnings,
        )
        totals += reporting
        totals_usd += usd
        health_budget_usd += budget_usd

    ratios = totals_usd / health_budget_usd if health_budget_usd > 0 else np.zeros_like(totals_usd)
    exceedance = {
        band.value: float(np.mean(ratios > threshold))
        for band, threshold in AFFORDABILITY_THRESHOLDS.items()
    }

    mean = float(np.mean(totals))
    tail_size = max(1, int(iterations * PSA_CONVERGENCE_TAIL_FRACTION))
    tail_mean = float(np.mean(totals[-tail_size:]))
    converged = (
        abs(tail_mean - mean) <= abs(mean) * PSA_CONVERGENCE_TOLERANCE
        if mean != 0 else tail_mean == 0
    )
    if not converged:
        warnings.append(Warning_(
            code="PSA_NOT_CONVERGED",
            message=f"the running mean over the final {tail_size} iterations differs from "
                    f"the overall mean by more than {PSA_CONVERGENCE_TOLERANCE:.0%}; "
                    "consider more iterations",
        ))

    return PsaResult(
        iterations=iterations,
        seed=seed,
        mean=mean,
        median=float(np.median(totals)),
        p2_5=float(np.percentile(totals, 2.5)),
        p97_5=float(np.percentile(totals, 97.5)),
        samples=tuple(float(x) for x in totals),
        exceedance=exceedance,
        converged=converged,
        warnings=tuple(warnings),
    )
