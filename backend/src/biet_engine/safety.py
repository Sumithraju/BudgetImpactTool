"""Safety & Adverse-Event Economics — ARCHITECTURE.md section 5.10, module M13.

Two calculations, both pure.

The first turns an observed adverse-event profile into the annual management
cost M5 already consumes. The second decomposes M7's net cost per patient
switched into the components that produce it — the answer to what a payer
actually asks, which is not "what does the new drug cost" but "of the
difference, how much is price and how much is everything else".

Nothing here decides whether a safety difference is real. That is a question
about evidence, and it is settled before this module is called.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .constants import WEEKS_PER_YEAR, CostComponent
from .exceptions import CurrencyMismatchError
from .models import BridgeTerm, CostBridge, Money, SafetyProfile, TherapyCost


def annualise(incidence: float, exposure_weeks: int | None) -> float:
    """An incidence observed over `exposure_weeks`, expressed per year.

        p = 1 - (1 - p_obs) ^ (52 / exposure_weeks)

    Under a constant-hazard assumption. A 68-week trial rate quoted as annual
    overstates it and a 26-week rate understates it, and the difference is
    large enough to matter: a 20% incidence over 68 weeks is 15.7% a year, not
    20%.

    The transformation is the identity at 52 weeks, and is skipped entirely
    when `exposure_weeks` is None — meaning the source already reports an
    annual rate and converting again would be double-counting.

    Certainty is preserved: an incidence of 1.0 annualises to 1.0 at any
    window, since no extrapolation beyond "every patient" is available.

    The constant-hazard assumption is wrong in a known direction. For events
    concentrated in a titration period — gastrointestinal events on an
    incretin, characteristically — it overstates the back half of the year.
    That is stated wherever an annualised figure is displayed rather than
    buried here.
    """
    if exposure_weeks is None or exposure_weeks == WEEKS_PER_YEAR:
        return incidence
    if incidence <= 0.0:
        return 0.0
    if incidence >= 1.0:
        return 1.0
    return 1.0 - float((1.0 - incidence) ** (WEEKS_PER_YEAR / exposure_weeks))


def expected_ae_cost(profile: SafetyProfile, currency: str) -> Money:
    """Annual adverse-event management cost per treated patient-year.

        AECost(t,c) = sum_e [ p(e,t) x unit_cost(e,c) ]

    Currency is checked rather than assumed. Two costs in different
    currencies summed into one number produce something plausible and wrong,
    which is the failure mode this system exists to prevent — so a mismatch
    raises instead.

    An empty event set returns zero, which is a real answer and distinct from
    "this therapy has no profile". The caller knows which it is holding; this
    function does not need to.

    Args:
        profile: the therapy's priced events for one market.
        currency: the market's currency, which every unit cost must be in.

    Returns:
        Expected annual cost, in `currency`.

    Raises:
        CurrencyMismatchError: a unit cost is denominated in another currency.
    """
    total = 0.0
    for entry in profile.events:
        if entry.unit_cost.currency != currency:
            raise CurrencyMismatchError(
                f"adverse-event cost for {entry.event.code!r} is in "
                f"{entry.unit_cost.currency}, but {profile.country_code} settles in "
                f"{currency}",
                currency_a=currency, currency_b=entry.unit_cost.currency,
            )
        total += annualise(entry.incidence.value, entry.exposure_weeks) * entry.unit_cost.amount

    return Money(amount=total, currency=currency)


def _component(cost: TherapyCost, component: CostComponent) -> float:
    match component:
        case CostComponent.ACQUISITION:
            return cost.acquisition.amount
        case CostComponent.ADMIN:
            return cost.admin.amount
        case CostComponent.MONITORING:
            return cost.monitoring.amount
        case CostComponent.AE:
            return cost.ae.amount
        case CostComponent.OFFSET:
            return cost.offset.amount


def build_cost_bridge(
    new_therapy: TherapyCost,
    comparators: Sequence[TherapyCost],
    *,
    substitution: Mapping[int, float],
    persistence: Mapping[int, float],
    country_code: str,
) -> CostBridge:
    """Decompose the net incremental cost per patient switched.

    M7 computes the total (section 5.6):

        NetCostPerSwitch = f_n x AC(n) - sum_t sigma_t x f_t x AC(t)

    `AC` is a sum of components, so that term decomposes exactly, component by
    component:

        delta_k = f_n x k(n) - sum_t sigma_t x f_t x k(t)

    with the offset entering negatively, as it does in `AC` itself. The five
    deltas sum to the total by construction — not approximately, and not as
    an accounting convention. A property test asserts the identity for random
    inputs, because "exact by construction" is a claim about code that has to
    keep being true after the code changes.

    A substitution weight naming a therapy absent from `comparators` is
    ignored rather than raising: M4 already validates the vector against the
    therapy set, and duplicating that check here would fail twice for one
    defect while giving this function a second reason to exist.

    Args:
        new_therapy: the new therapy's computed cost for this market.
        comparators: the therapies it displaces.
        substitution: `drug_id -> sigma`, the source-of-business vector.
        persistence: `drug_id -> f`, the persistence-adjusted year fraction.
        country_code: the market, for the returned bridge.

    Returns:
        One term per cost component, plus the total they sum to.

    Raises:
        CurrencyMismatchError: a comparator is priced in another currency.
    """
    currency = new_therapy.total.currency
    for comparator in comparators:
        if comparator.total.currency != currency:
            raise CurrencyMismatchError(
                f"comparator {comparator.drug_id} is priced in "
                f"{comparator.total.currency}, the new therapy in {currency}",
                currency_a=currency, currency_b=comparator.total.currency,
            )

    f_new = persistence.get(new_therapy.drug_id, 1.0)

    terms: list[BridgeTerm] = []
    net = 0.0
    for component in CostComponent:
        new_side = f_new * _component(new_therapy, component)
        displaced_side = math.fsum(
            substitution.get(c.drug_id, 0.0)
            * persistence.get(c.drug_id, 1.0)
            * _component(c, component)
            for c in comparators
        )
        delta = new_side - displaced_side

        # The offset is a saving: it enters the annual cost negatively, so it
        # enters the bridge negatively too. Getting this sign wrong would
        # make an avoided-cost advantage read as an extra cost.
        net += -delta if component is CostComponent.OFFSET else delta

        terms.append(BridgeTerm(
            component=component,
            new_therapy=Money(amount=new_side, currency=currency),
            displaced=Money(amount=displaced_side, currency=currency),
            delta=Money(amount=delta, currency=currency),
        ))

    return CostBridge(
        country_code=country_code,
        terms=tuple(terms),
        net_cost_per_switch=Money(amount=net, currency=currency),
    )
