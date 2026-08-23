"""Performance benchmark — M8 acceptance criterion: "< 300 ms for 10 markets"
(section 8, POST /scenarios/{id}/solve-price).
"""

from __future__ import annotations

import time

from biet_engine.solver import solve_price

from ..conftest import make_country_input, make_engine_input, make_uptake_input

_MARKET_CODES = ("USA", "GBR", "DEU", "FRA", "ITA", "ESP", "JPN", "CHN", "BRA", "IND")


def test_ten_markets_under_300ms() -> None:
    countries = tuple(
        make_country_input(country_code=code, currency="USD", horizon=3)
        for code in _MARKET_CODES
    )
    inputs = make_engine_input(
        countries=countries, horizon_years=3, reporting_currency="USD",
        fx_rates={"USD": 1.0}, uptake=make_uptake_input(vector=(0.02, 0.05, 0.08)),
    )

    start = time.perf_counter()
    corridor = solve_price(inputs, target_ratio=0.005)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(corridor.entries) == 10
    assert elapsed_ms < 300, f"took {elapsed_ms:.1f} ms, budget is 300 ms"
