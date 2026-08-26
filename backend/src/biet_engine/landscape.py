"""Launch-Year Competitive Landscape — ARCHITECTURE.md section 5.11, module M14.

An asset launching in four years does not compete against today's market. A
Phase III competitor approved two years from now is part of the world-without
from year three onward, and a budget impact computed against the current mix
silently assumes it away.

That assumption may well be the right one — it is conservative and it is
defensible. This module exists so that it is a choice rather than an oversight.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .constants import MAX_ENTRANT_TOTAL_SHARE, SHARE_SUM_TOLERANCE
from .exceptions import DisplacementError
from .models import LandscapeResult, PipelineEntrant, Warning_


def expected_entry_year(
    completion_year: int, *, launch_year: int, regulatory_lag_years: float,
) -> int:
    """When an entrant reaches market, launch-relative and 1-indexed.

        y_e = max(1, ceil(completion_year + lag - L + 1))

    Clamped at 1 because an entrant already marketed by the time this asset
    launches is not an entrant at all — it is an incumbent, and belongs in the
    baseline from year one.

    Args:
        completion_year: calendar year of the trial's primary completion.
        launch_year: calendar year the modelled asset launches.
        regulatory_lag_years: interval from completion to approval.

    Returns:
        Launch-relative year, at least 1.
    """
    return max(1, math.ceil(completion_year + regulatory_lag_years - launch_year + 1))


def entrant_share(entrant: PipelineEntrant, year: int) -> float:
    """One entrant's share of the addressable market in a given year.

        m_e(y) = 0                                    for y < y_e
        m_e(y) = s_e x min(1, (y - y_e + 1) / r_e)    for y >= y_e

    A linear ramp, matching M4's linear uptake curve. Logistic diffusion would
    be equally defensible and no more accurate: `terminal_share` is itself an
    assumption, and a second shape parameter on top of a guessed plateau adds
    precision without adding information.
    """
    if year < entrant.entry_year:
        return 0.0
    progress = (year - entrant.entry_year + 1) / entrant.ramp_years
    return entrant.terminal_share.value * min(1.0, progress)


def project_landscape(
    baseline: Mapping[int, tuple[float, ...]],
    entrants: Sequence[PipelineEntrant],
    *,
    horizon_years: int,
) -> LandscapeResult:
    """Admit entrants into the baseline mix and rescale incumbents to fit.

        E(y)     = sum_e m_e(y),  capped at MAX_ENTRANT_TOTAL_SHARE
        m'_t(y)  = m_t(y) x (1 - E(y))

    so that `sum_t m'_t(y) + sum_e m_e(y) = 1` at every year.

    **Proportional, not nominated.** Entrants take share from every incumbent
    in proportion to what it holds, because no public source says which
    incumbent an entrant displaces. Nominating one would be a market-access
    judgement dressed up as a computation. A user who has that judgement can
    express it through the substitution vector, where it is visible as an
    assumption.

    An entrant expected after the horizon ends is dropped rather than carried
    as a row of zeros: it cannot affect a result that finishes before it
    arrives, and a zero row would suggest it was considered and found
    immaterial.

    Args:
        baseline: `drug_id -> per-year share`, summing to 1.0 at each year.
        entrants: candidates to admit; those beyond the horizon are ignored.
        horizon_years: the model horizon.

    Returns:
        The rescaled baseline including entrants, which entrants were
        admitted, and any warnings the admission raised.

    Raises:
        DisplacementError: the rescaled shares do not sum to 1.0. Never
            returned — a mix that does not sum is not a market.
    """
    admitted = tuple(e for e in entrants if e.entry_year <= horizon_years)
    clashing = {e.drug_id for e in admitted} & set(baseline)
    if clashing:
        # An entrant that is already in the baseline would have its share
        # written twice — once rescaled as an incumbent and once as an
        # entrant — and the year would sum past 1.0.
        raise DisplacementError(
            f"entrant drug_id(s) {sorted(clashing)} are already in the baseline mix; "
            "a therapy is an incumbent or an entrant, not both"
        )
    if not admitted:
        # The ordinary case, and deliberately silent: a scenario with no
        # entrants inside the horizon is not a degraded scenario.
        return LandscapeResult(baseline_shares=dict(baseline), admitted=())

    warnings: list[Warning_] = []
    entrant_by_year: dict[int, list[float]] = {}
    capped_years: list[int] = []

    for year in range(1, horizon_years + 1):
        shares = [entrant_share(e, year) for e in admitted]
        total = math.fsum(shares)
        if total > MAX_ENTRANT_TOTAL_SHARE:
            scale = MAX_ENTRANT_TOTAL_SHARE / total
            shares = [s * scale for s in shares]
            capped_years.append(year)
        entrant_by_year[year] = shares

    if capped_years:
        warnings.append(Warning_(
            code="ENTRANT_SHARE_CAPPED",
            message=(
                f"Modelled entrants would have taken more than "
                f"{MAX_ENTRANT_TOTAL_SHARE:.0%} of the market in year(s) "
                f"{', '.join(str(y) for y in capped_years)}; scaled to the cap. "
                "An uncapped total leaves a world-without made entirely of drugs "
                "that do not yet exist."
            ),
        ))

    projected: dict[int, list[float]] = {drug_id: [] for drug_id in baseline}
    for entrant in admitted:
        projected.setdefault(entrant.drug_id, [])

    for year in range(1, horizon_years + 1):
        occupied = math.fsum(entrant_by_year[year])
        room = 1.0 - occupied
        for drug_id, incumbent_vector in baseline.items():
            # An entrant admitted mid-horizon shortens no vector: baseline
            # shares are per-year already, and the last year repeats if the
            # caller supplied fewer than the horizon.
            existing = incumbent_vector[min(year - 1, len(incumbent_vector) - 1)]
            projected[drug_id].append(existing * room)
        for entrant, share in zip(admitted, entrant_by_year[year], strict=True):
            projected[entrant.drug_id].append(share)

    for index in range(horizon_years):
        total = math.fsum(v[index] for v in projected.values())
        if abs(total - 1.0) > SHARE_SUM_TOLERANCE:
            raise DisplacementError(
                f"projected baseline shares sum to {total!r} in year {index + 1}, not 1.0"
            )

    warnings.append(Warning_(
        code="PIPELINE_ENTRANT_MODELLED",
        message=(
            "The world-without includes therapies that are not yet approved: "
            + "; ".join(
                f"{e.name} from year {e.entry_year} to {e.terminal_share.value:.0%}"
                for e in admitted
            )
            + ". Each carries three assumptions the evidence does not supply — that it "
            "is approved at all, when, and at what price. All three are tier D."
        ),
    ))

    return LandscapeResult(
        baseline_shares={k: tuple(v) for k, v in projected.items()},
        admitted=admitted,
        warnings=tuple(warnings),
    )
