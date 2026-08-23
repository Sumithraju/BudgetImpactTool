"""Uptake & Market Mix — ARCHITECTURE.md section 5.3, module M4.

Projects the share of the addressable population receiving the new therapy
in each launch-relative year, and the corresponding displacement of
incumbent therapies. The displacement half is what makes budget impact
incremental rather than gross.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .constants import (
    ACCOUNTING_TOLERANCE,
    LOGISTIC_DEFAULT_STEEPNESS,
    SHARE_SUM_TOLERANCE,
    UptakeCurve,
)
from .exceptions import DisplacementError, UnknownTherapyError, UptakeMonotonicityError
from .models import MarketMix, Substitution, UptakeInput, Warning_


def project_uptake(inputs: UptakeInput, horizon: int) -> tuple[float, ...]:
    """The uptake vector u(1)..u(horizon), share of addressable per year.

    Linear:    u(y) = y1 + (terminal - y1) * (y-1) / max(1, N-1)
    Logistic:  u(y) = terminal / (1 + exp(-k * (y - y_mid)))
               defaults k=1.2, y_mid=N/2. Does not start at zero by design —
               a launch year with meaningful early uptake — see section 5.1.
    Manual:    the supplied vector, unchanged, validated to length N.

    Args:
        inputs: curve family and its parameters.
        horizon: N, the number of launch-relative years.

    Returns:
        A length-`horizon` tuple, each entry in [0, 1].

    Raises:
        ValueError: a required curve parameter is missing, a computed or
            supplied value falls outside [0, 1], or a manual vector's length
            does not match `horizon`.
        UptakeMonotonicityError: the vector decreases year over year and
            `inputs.allow_erosion` is False.
    """
    if inputs.curve is UptakeCurve.LINEAR:
        vector = _linear(inputs, horizon)
    elif inputs.curve is UptakeCurve.LOGISTIC:
        vector = _logistic(inputs, horizon)
    else:
        vector = _manual(inputs, horizon)

    for y, u in enumerate(vector, start=1):
        if not (0 <= u <= 1):
            raise ValueError(f"u({y}) = {u!r} is outside [0, 1]")

    if not inputs.allow_erosion:
        for y in range(1, len(vector)):
            if vector[y] < vector[y - 1]:
                raise UptakeMonotonicityError(
                    f"uptake decreased from {vector[y - 1]!r} (year {y}) to "
                    f"{vector[y]!r} (year {y + 1}) without allow_erosion",
                    year=y + 1,
                )

    return vector


def _linear(inputs: UptakeInput, horizon: int) -> tuple[float, ...]:
    if inputs.year_1 is None or inputs.terminal is None:
        raise ValueError("linear uptake requires year_1 and terminal")
    y1, yn = inputs.year_1.value, inputs.terminal.value
    denom = max(1, horizon - 1)
    return tuple(y1 + (yn - y1) * (y - 1) / denom for y in range(1, horizon + 1))


def _logistic(inputs: UptakeInput, horizon: int) -> tuple[float, ...]:
    if inputs.terminal is None:
        raise ValueError("logistic uptake requires terminal (u_max)")
    u_max = inputs.terminal.value
    k = inputs.steepness.value if inputs.steepness is not None else LOGISTIC_DEFAULT_STEEPNESS
    y_mid = inputs.inflection_year.value if inputs.inflection_year is not None else horizon / 2
    return tuple(
        u_max / (1 + math.exp(-k * (y - y_mid))) for y in range(1, horizon + 1)
    )


def _manual(inputs: UptakeInput, horizon: int) -> tuple[float, ...]:
    if inputs.vector is None:
        raise ValueError("manual uptake requires vector")
    if len(inputs.vector) != horizon:
        raise ValueError(
            f"manual uptake vector length {len(inputs.vector)} != horizon {horizon}"
        )
    return inputs.vector


def displace(
    m_without: Mapping[int, float], u: float, sigma: Mapping[int, float]
) -> tuple[dict[int, float], bool]:
    """One year's world-with shares, per M4 section 5.4.

        m_with(t) = max(0, m_without(t) - u * sigma(t))

    When the floor binds, the undisplaced remainder is redistributed
    proportionally across the therapies that still have headroom, so the
    share accounting still closes to `u + sum(m_with) = 1`.

    Returns:
        The world-with shares, and whether redistribution occurred (the
        caller emits a `SUBSTITUTION_FLOOR` warning when it did).

    Raises:
        DisplacementError: the floor bound and no therapy had headroom left
            to absorb the redistributed deficit.
    """
    deficit = 0.0
    m_with: dict[int, float] = {}
    for t, m in m_without.items():
        take = u * sigma.get(t, 0.0)
        if take > m:
            deficit += take - m
            m_with[t] = 0.0
        else:
            m_with[t] = m - take

    redistributed = deficit > 0
    if redistributed:
        headroom = {t: m for t, m in m_with.items() if m > 0}
        total = sum(headroom.values())
        if total <= 0:
            raise DisplacementError("no headroom to absorb displacement")
        for t, m in headroom.items():
            m_with[t] = m - deficit * (m / total)

    return m_with, redistributed


def build_market_mix(
    baseline: Mapping[int, Sequence[float]],
    uptake: Sequence[float],
    substitution: Substitution,
    country_code: str,
) -> tuple[MarketMix, ...]:
    """One `MarketMix` per year in `uptake`.

    `baseline` maps `drug_id -> per-year baseline share`, defining the full
    therapy set (M4 section 5.3's treatment-naive `no_pharmacotherapy` entry
    is just another key in it). Every year's baseline shares must sum to 1.0.

    Args:
        baseline: drug_id -> sequence of per-year world-without shares, one
            entry per year in `uptake`.
        uptake: the projected uptake vector, e.g. from `project_uptake`.
        substitution: the source-of-business vector, sigma.
        country_code: the market this mix applies to.

    Returns:
        One `MarketMix` per year, each satisfying
        `uptake + sum(shares_with) == 1.0` (+/- accounting tolerance).

    Raises:
        UnknownTherapyError: `substitution` names a drug_id not in `baseline`.
        ValueError: a year's baseline shares don't sum to 1.0.
        DisplacementError: propagated from `displace` when redistribution has
            no headroom to draw on.
    """
    unknown = set(substitution.shares) - set(baseline)
    if unknown:
        raise UnknownTherapyError(
            f"substitution names therapies not in the baseline set: {sorted(unknown)}",
            unknown=sorted(unknown),
        )

    sigma = {drug_id: s.value for drug_id, s in substitution.shares.items()}

    results = []
    for index, u in enumerate(uptake):
        m_without = {drug_id: shares[index] for drug_id, shares in baseline.items()}

        total = sum(m_without.values())
        if abs(total - 1.0) > SHARE_SUM_TOLERANCE:
            raise ValueError(
                f"year {index + 1}: baseline shares sum to {total!r}, not 1.0"
            )

        m_with, redistributed = displace(m_without, u, sigma)

        accounted = u + sum(m_with.values())
        assert abs(accounted - 1.0) <= ACCOUNTING_TOLERANCE, (
            f"share accounting invariant violated: u={u} + sum(m_with)="
            f"{sum(m_with.values())} = {accounted}, expected 1.0"
        )

        warnings = (
            (Warning_(
                code="SUBSTITUTION_FLOOR",
                message="the displacement floor bound and the deficit was "
                        "redistributed across the remaining therapies; the "
                        "source-of-business vector may be inconsistent with "
                        "the baseline mix",
                country_code=country_code,
            ),)
            if redistributed else ()
        )

        results.append(
            MarketMix(
                country_code=country_code, year=index + 1, uptake=u,
                shares_without=m_without, shares_with=m_with, warnings=warnings,
            )
        )

    return tuple(results)
