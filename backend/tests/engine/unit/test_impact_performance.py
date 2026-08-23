"""Performance benchmark — M7 acceptance criterion: "< 200 ms for 10 markets
x 5 years" (ARCHITECTURE.md section 13.1).
"""

from __future__ import annotations

import time

from biet_engine.impact import compute_budget_impact
from biet_engine.models import Substitution

from ..conftest import make_country_input, make_engine_input, make_uptake_input, make_valued

_MARKET_CODES = ("USA", "GBR", "DEU", "FRA", "ITA", "ESP", "JPN", "CHN", "BRA", "IND")


def test_ten_markets_five_years_under_200ms() -> None:
    horizon = 5
    countries = tuple(
        make_country_input(
            country_code=code, currency="USD", horizon=horizon,
            baseline_shares={1: (1.0,) * horizon},
            substitution=Substitution(shares={1: make_valued(1.0)}),
        )
        for code in _MARKET_CODES
    )
    inputs = make_engine_input(
        countries=countries, horizon_years=horizon, reporting_currency="USD",
        fx_rates={"USD": 1.0},
        uptake=make_uptake_input(vector=(0.02, 0.05, 0.08, 0.10, 0.12)),
    )

    start = time.perf_counter()
    result = compute_budget_impact(inputs)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(result.countries) == 10
    assert elapsed_ms < 200, f"took {elapsed_ms:.1f} ms, budget is 200 ms"
