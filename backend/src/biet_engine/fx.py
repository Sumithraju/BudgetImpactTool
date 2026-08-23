"""Currency conversion via the run's FX snapshot — ARCHITECTURE.md section
5.6 (CLAUDE.md non-negotiable 6: "FX is snapshotted into the run, never
looked up live").

Split out of `impact.py` (M7) once `affordability.py` and `solver.py` (M8)
needed the identical conversion — shared calculation belongs here, not
copied into every module that touches money in more than one currency
(biet-backend skill section 6).
"""

from __future__ import annotations

from collections.abc import Mapping

from .exceptions import MissingFxRateError
from .models import Money


def convert(amount: Money, to_currency: str, fx_rates: Mapping[str, float]) -> Money:
    """`(amount_local / rate[local]) x rate[to]` — pivots through USD.

    `fx_rates` is `currency_code -> rate_per_usd`, USD itself included as an
    identity row (1.0).

    Raises:
        MissingFxRateError: `amount.currency` or `to_currency` has no rate.
    """
    if amount.currency not in fx_rates:
        raise MissingFxRateError(f"no FX rate for {amount.currency!r}", currency=amount.currency)
    if to_currency not in fx_rates:
        raise MissingFxRateError(f"no FX rate for {to_currency!r}", currency=to_currency)
    usd = amount.amount / fx_rates[amount.currency]
    return Money(amount=usd * fx_rates[to_currency], currency=to_currency)
