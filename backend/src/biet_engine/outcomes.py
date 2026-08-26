"""Clinical Outcomes and Avoided Events — module M16, ARCHITECTURE.md §4B.

Budget impact without outcomes is half an argument. A payer asked to fund a
therapy at $8,800 net per switched patient will ask what the $8,800 buys, and
"weight loss" is not something a budget holder can act on. Avoided incident
diabetes, avoided cardiovascular events and the hospitalisations that come with
them are.

Every effect here is *supplied*, never inferred. Nothing derives an effect from
a drug class, from a mechanism, or from another therapy's result. A therapy
with no supplied effect avoids no events and says so — zero avoided events and
no evidence about avoided events are different claims, and this module keeps
them apart.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .constants import EventClass
from .exceptions import CurrencyMismatchError
from .models import (
    AvoidedEvents,
    Money,
    OutcomeResult,
    ResponseProfile,
    TreatmentEffect,
    Warning_,
)

#: M16 section 5.4. Effect is full in year 1 and decays from year 2.
_FIRST_YEAR = 1


def effect_retained(year: int, regain_per_year: float) -> float:
    """The share of the achieved effect still held in a given year.

        effect_retained(y) = (1 - regain_per_year) ^ (y - 1)

    Full in year 1 by construction: a trial's reported effect *is* the year-one
    effect, so decaying it in the year it was measured would double-count the
    regain the trial already observed.

    `regain_per_year = 0` holds the effect flat, which is defensible on
    continuous therapy and belongs in the assumption register as a stated
    choice rather than a silent default.
    """
    if regain_per_year <= 0.0:
        return 1.0
    return float((1.0 - regain_per_year) ** (year - _FIRST_YEAR))


def project_outcomes(
    treated_on_new: Sequence[float],
    effects: Sequence[TreatmentEffect],
    profile: ResponseProfile | None,
    *,
    persistence: float,
    country_code: str,
    currency: str,
) -> OutcomeResult:
    """Events avoided, and what they would have cost, per year.

        Exposed(y)     = TreatedOnNew(y) x f
        Avoided(e,y)   = Exposed(y) x baseline_rate(e) x rr(e) x retained(y)
        CostAvoided(y) = sum_e Avoided(e,y) x unit_cost(e)

    `Exposed` is persistence-adjusted rather than the headline uptake figure.
    An effect accrues only while a patient is on therapy, and counting a
    discontinued patient as a responder overstates the clinical result and the
    economic one together.

    The returned cost becomes M5's `offset` for the new therapy, so it reaches
    M7 through the annual cost of the therapy that produced it. It is never
    added as a separate line at the end — an avoided cost is part of the cost
    of the therapy that avoided it, and adding it elsewhere would double-count
    against the offset M5 already accepts.

    Args:
        treated_on_new: patients on the new therapy, per year.
        effects: supplied effects. An empty sequence is a real state.
        profile: the response profile, or None when none was supplied.
        persistence: M6's persistence-adjusted treatment-year fraction.
        country_code: the market, for the returned result.
        currency: the market's currency; every unit cost must be in it.

    Returns:
        Responders, avoided events per class per year, and the cost avoided.

    Raises:
        CurrencyMismatchError: an event unit cost is in another currency.
    """
    horizon = len(treated_on_new)
    exposed = [patients * persistence for patients in treated_on_new]

    warnings: list[Warning_] = []
    if not effects:
        # The distinction this module exists to preserve. Returning zeros
        # without saying why would read as "this therapy avoids nothing".
        warnings.append(Warning_(
            code="NO_OUTCOME_EVIDENCE",
            message=(
                "No treatment effect was supplied for this therapy, so no avoided "
                "events are modelled. That is an absence of evidence, not a finding "
                "that the therapy avoids nothing."
            ),
            country_code=country_code,
        ))

    avoided: list[AvoidedEvents] = []
    cost_by_year = [0.0] * horizon

    for effect in effects:
        if effect.unit_cost.currency != currency:
            raise CurrencyMismatchError(
                f"unit cost for {effect.event.value!r} is in "
                f"{effect.unit_cost.currency}, but {country_code} settles in {currency}",
                currency_a=currency, currency_b=effect.unit_cost.currency,
            )

        retained_full = effect.follow_up_weeks
        for index, patients in enumerate(exposed):
            year = index + _FIRST_YEAR
            retained = effect_retained(
                year, profile.regain_per_year.value if profile else 0.0,
            )
            without = patients * effect.baseline_rate.value
            prevented = without * effect.relative_reduction.value * retained
            cost = prevented * effect.unit_cost.amount
            cost_by_year[index] += cost

            avoided.append(AvoidedEvents(
                event=effect.event, year=year,
                events_without=without,
                events_with=without - prevented,
                avoided=prevented,
                cost_avoided=Money(amount=cost, currency=currency),
                trial=effect.trial,
            ))

        # A three-year horizon against a 68-week trial extrapolates beyond what
        # was observed. Stated rather than silently assumed away.
        if retained_full is not None and horizon * 52 > retained_full:
            warnings.append(Warning_(
                code="EFFECT_BEYOND_FOLLOW_UP",
                message=(
                    f"The effect on {effect.event.value} is applied across "
                    f"{horizon} years, but {effect.trial} followed patients for "
                    f"{retained_full} weeks. Years beyond that are an extrapolation."
                ),
                country_code=country_code,
            ))

    responders: tuple[float, ...] | None = None
    mean_loss: float | None = None
    if profile is not None:
        responders = tuple(
            patients * profile.responder_share.value for patients in exposed
        )
        mean_loss = profile.mean_weight_loss_pct.value

    return OutcomeResult(
        country_code=country_code,
        responders=responders,
        mean_weight_loss_pct=mean_loss,
        avoided=tuple(avoided),
        total_cost_avoided=tuple(
            Money(amount=amount, currency=currency) for amount in cost_by_year
        ),
        warnings=tuple(warnings),
    )


def offset_per_patient(result: OutcomeResult, treated: Sequence[float]) -> Money:
    """Cost avoided per treated patient-year, for M5's `offset`.

    Averaged across the horizon rather than taken from year 1, because M5's
    therapy input carries one offset figure and the effect decays (§5.4). Using
    year 1 alone would credit the therapy with its best year for every year.
    """
    currency = result.total_cost_avoided[0].currency if result.total_cost_avoided else "USD"
    total_cost = math.fsum(money.amount for money in result.total_cost_avoided)
    total_patients = math.fsum(treated)
    if total_patients <= 0:
        return Money(amount=0.0, currency=currency)
    return Money(amount=total_cost / total_patients, currency=currency)


__all__ = ["EventClass", "effect_retained", "offset_per_patient", "project_outcomes"]
