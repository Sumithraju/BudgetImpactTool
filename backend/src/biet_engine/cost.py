"""Cost & Pricing Engine — ARCHITECTURE.md section 5.5, module M5.

Computes the annual cost per treated patient-year of one therapy in one
market, and derives a price for markets where none is observed. Returns cost
per *full* treated patient-year — M6 scales it by the persistence fraction.
"""

from __future__ import annotations

from .models import Money, TherapyCost, TherapyInput


def compute_therapy_cost(therapy: TherapyInput, country_code: str) -> TherapyCost:
    """Annual cost components and total for one therapy in one market.

        acq = unit_price x units_per_admin x admins_per_year
              x (1 + wastage) x (1 - discount)
        total = acq + admin_cost + monitoring_cost + ae_cost - offset

    Order is fixed in the acquisition formula: wastage inflates volume first,
    discount then reduces the realised price. Applying them the other way
    round gives a different number.

    `total` may legitimately be negative when `offset` exceeds direct costs —
    that is a real cost-saving result and is not floored at zero (flooring it
    would hide a budget saving). The `no_pharmacotherapy` comparator needs no
    special case: with `units_per_admin = 0` its acquisition cost is zero by
    the same formula every other therapy uses, and it carries no admin,
    monitoring, AE cost or offset either, so `total` comes out to exactly 0.

    Args:
        therapy: fully-resolved, already-validated therapy input (positivity,
            range and currency-carrying rules are enforced by `TherapyInput`
            and `Money` themselves at construction).
        country_code: the market this cost applies to.

    Returns:
        Each cost component plus the total, all in the therapy's local
        currency, carrying the therapy's price provenance.
    """
    regimen = therapy.regimen
    acquisition = therapy.unit_price * (
        regimen.units_per_admin.value
        * regimen.admins_per_year.value
        * (1 + regimen.wastage_pct.value)
        * (1 - therapy.discount_pct.value)
    )

    total: Money = (
        acquisition
        + therapy.admin_cost
        + therapy.monitoring_cost
        + therapy.ae_cost
        - therapy.offset
    )

    return TherapyCost(
        drug_id=therapy.drug_id,
        country_code=country_code,
        acquisition=acquisition,
        admin=therapy.admin_cost,
        monitoring=therapy.monitoring_cost,
        ae=therapy.ae_cost,
        offset=therapy.offset,
        total=total,
        price_basis=therapy.price_basis,
        provenance=therapy.price_provenance,
    )


def derive_ppp_price(
    reference_price: float,
    gdp_pc_ppp_target: float,
    gdp_pc_ppp_reference: float,
    elasticity: float,
    floor: float,
) -> float:
    """Cross-market price where no observed price exists for the target market.

        price(c) = max( price(ref) x [gdp_pc_ppp(c) / gdp_pc_ppp(ref)] ^ elasticity,
                         floor x price(ref) )

    This is a modelling assumption, not an observation. The caller is
    responsible for: labelling the resulting price `price_basis =
    PPP_DERIVED` with `confidence_tier = C`; emitting an `UNPRICED_MARKET`
    warning; and, when this function's floor term is what determines the
    result (i.e. the return value equals `floor * reference_price` rather
    than the elasticity term), emitting `PPP_FLOOR_APPLIED` too — detectable
    by comparing the return value against `floor * reference_price`, exactly
    as this function does internally. `derive_ppp_price` itself returns a
    bare float, matching M5's contract; it has no channel to carry a warning
    without becoming a different, richer type M5 doesn't specify.

    `elasticity = 0` yields `reference_price` everywhere — permitted, not a
    special case in the formula.

    Args:
        reference_price: observed price in the reference market (USD), per
            M5 section 5.4 — PPP derivation operates on USD-normalised values.
        gdp_pc_ppp_target: target market's GDP per capita, PPP-adjusted.
        gdp_pc_ppp_reference: reference market's GDP per capita, PPP-adjusted.
        elasticity: price-GDP elasticity (`ARCHITECTURE.md` default 1.0).
        floor: minimum price as a fraction of `reference_price` (default 0.05).

    Returns:
        The derived price in USD, never below `floor * reference_price`.
    """
    scaled = reference_price * float((gdp_pc_ppp_target / gdp_pc_ppp_reference) ** elasticity)
    return max(scaled, floor * reference_price)
