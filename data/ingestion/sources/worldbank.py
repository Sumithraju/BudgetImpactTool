"""World Bank Open Data — population, income and health expenditure.

The critical rule here is latest-non-null-year resolution, applied per indicator
per country **independently** (M0 section 5.2). Population and GDP are populated
through 2025 while health expenditure lags to 2023 or 2024 with null 2025 rows
present, so a join on a single fixed year silently discards health expenditure
for every market.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ..constants import (
    ADOLESCENT_BAND_RATIO,
    ADULT_SHARE_MAX,
    ADULT_SHARE_MIN,
    SourceId,
    TARGET_COUNTRIES,
    WORLD_BANK_BASE_URL,
    WORLD_BANK_DATE_RANGE,
    WORLD_BANK_INDICATORS,
    WORLD_BANK_PAGE_SIZE,
)
from ..errors import CoverageError, MissingValueError
from ..http import get_json
from ..base import Fetcher

log = logging.getLogger(__name__)

SOURCE_LABEL = "World Bank Open Data"


def latest_non_null(
    rows: list[dict[str, Any]], country: str, indicator: str
) -> tuple[int, float]:
    """Most recent year with a non-null value, for one country and indicator.

    Raises:
        MissingValueError: when no year carries a value.
    """
    candidates = [
        (int(row["date"]), float(row["value"]))
        for row in rows
        if row.get("countryiso3code") == country
        and (row.get("indicator") or {}).get("id") == indicator
        and row.get("value") is not None
    ]
    if not candidates:
        raise MissingValueError(
            f"no non-null value for {country}/{indicator}",
            country=country,
            indicator=indicator,
        )
    return max(candidates, key=lambda pair: pair[0])


def derive_adult_share(
    pop_0014_pct: float, age_15_17_pct: float | None = None
) -> float:
    """Share of the population aged 18+.

    WHO prevalence is published for adults 18 and over while World Bank population
    is all ages; applying one to the other without this adjustment inflates the
    diseased population by the paediatric share (M2 section 5.1).

    The World Bank publishes a 0-14 band, not 0-17. Taking "not 0-14" as the adult
    share would still include the 15-17 cohort and overstate the denominator by
    3-6% depending on market. `age_15_17_pct` removes that cohort; when not
    supplied it is approximated as `ADOLESCENT_BAND_RATIO` of the 0-14 band, which
    assumes roughly uniform single-year cohorts.

    The approximation is why this value carries confidence tier B, not A. Supplying
    an observed 15-17 share per market from `data/seed/age_bands.csv` upgrades it.
    """
    if age_15_17_pct is None:
        age_15_17_pct = pop_0014_pct * ADOLESCENT_BAND_RATIO

    share = 1.0 - (pop_0014_pct + age_15_17_pct) / 100.0
    if not ADULT_SHARE_MIN < share < ADULT_SHARE_MAX:
        raise MissingValueError(
            f"derived adult share {share:.4f} outside plausible bounds",
            pop_0014_pct=pop_0014_pct, age_15_17_pct=age_15_17_pct,
        )
    return share


class WorldBankFetcher(Fetcher):
    source_id = SourceId.WORLD_BANK

    def extract(self) -> Path:
        payload: dict[str, list[dict[str, Any]]] = {}
        countries = ";".join(TARGET_COUNTRIES)

        for code in WORLD_BANK_INDICATORS:
            url = f"{WORLD_BANK_BASE_URL}/country/{countries}/indicator/{code}"
            body = get_json(
                url,
                params={
                    "format": "json",
                    "per_page": WORLD_BANK_PAGE_SIZE,
                    "date": WORLD_BANK_DATE_RANGE,
                },
            )
            rows = body[1] if isinstance(body, list) and len(body) > 1 else []
            payload[code] = rows or []
            log.info("worldbank_fetched", extra={"indicator": code, "rows": len(rows)})

        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_path.write_text(json.dumps(payload), encoding="utf-8")
        return self.raw_path

    def validate(self, raw: Path) -> None:
        payload = json.loads(raw.read_text(encoding="utf-8"))

        for code in WORLD_BANK_INDICATORS:
            rows = payload.get(code) or []
            if not rows:
                raise CoverageError(f"indicator {code} returned no rows", indicator=code)

            covered = {
                r["countryiso3code"]
                for r in rows
                if r.get("value") is not None and r.get("countryiso3code")
            }
            missing = set(TARGET_COUNTRIES) - covered
            if missing:
                raise CoverageError(
                    f"indicator {code} missing markets: {sorted(missing)}",
                    indicator=code,
                    missing=sorted(missing),
                )

    def transform(self, raw: Path) -> pd.DataFrame:
        payload = json.loads(raw.read_text(encoding="utf-8"))
        records: list[dict[str, Any]] = []

        for code, name in WORLD_BANK_INDICATORS.items():
            rows = payload[code]
            # Iterate the markets actually present. Enforcing full coverage is
            # validate()'s job, not transform()'s; keeping the two separate lets
            # transform run against a fixture holding a subset of markets.
            present = [
                c for c in TARGET_COUNTRIES
                if any(r.get("countryiso3code") == c and r.get("value") is not None
                       for r in rows)
            ]
            for country in present:
                year, value = latest_non_null(rows, country, code)
                records.append(
                    {
                        "country_code": country,
                        "indicator": name,
                        "year": year,
                        "value": value,
                        "source": f"{SOURCE_LABEL} {code}",
                        "confidence_tier": "A",
                    }
                )

        return pd.DataFrame.from_records(records)


def build_countries(economics: pd.DataFrame) -> pd.DataFrame:
    """Country rows carrying the derived adult share."""
    from ..constants import COUNTRY_CURRENCY

    paediatric = economics[economics["indicator"] == "pop_0014_pct"]
    records = []
    for row in paediatric.itertuples():
        records.append(
            {
                "country_code": row.country_code,
                "currency_code": COUNTRY_CURRENCY[row.country_code],
                "adult_share": round(derive_adult_share(row.value), 4),
                "adult_share_source": (
                    f"{SOURCE_LABEL} SP.POP.0014.TO.ZS {row.year}, "
                    "less an approximated 15-17 cohort"
                ),
                "adult_share_vintage": row.year,
                "adult_share_tier": "B",
            }
        )
    return pd.DataFrame.from_records(records)
