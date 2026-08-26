"""WHO Global Health Observatory — disease prevalence with published intervals.

Three filters are mandatory (M0 section 5.3). The response mixes true country rows
with WORLDBANKINCOMEGROUP and REGION aggregates; without the spatial-dimension
filter those aggregates load as if they were markets. The sex and age-group filters
pin the extract to the both-sexes adult series the funnel denominator assumes.

The published Low/High bounds are carried through untouched: M9 parameterises the
probabilistic sensitivity analysis directly from them, which is what makes the
uncertainty statement empirically grounded rather than assumed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ..constants import (
    PREVALENCE_MAX_PCT,
    PREVALENCE_MIN_PCT,
    SourceId,
    TARGET_COUNTRIES,
    WHO_AGE_GROUP_ADULT,
    WHO_GHO_BASE_URL,
    WHO_INDICATORS,
    WHO_SEX_BOTH,
    WHO_SPATIAL_DIM_TYPE,
)
from ..errors import CoverageError, SourceValidationError
from ..http import get_json
from ..base import Fetcher

log = logging.getLogger(__name__)

SOURCE_LABEL = "WHO GHO"


def apply_who_filters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The three mandatory filters. Never bypass these."""
    return [
        row
        for row in rows
        if row.get("SpatialDimType") == WHO_SPATIAL_DIM_TYPE
        and row.get("SpatialDim") in TARGET_COUNTRIES
        and row.get("Dim1") == WHO_SEX_BOTH
        and row.get("Dim2") == WHO_AGE_GROUP_ADULT
    ]


class WhoGhoFetcher(Fetcher):
    source_id = SourceId.WHO_GHO

    def extract(self) -> Path:
        payload: dict[str, list[dict[str, Any]]] = {}

        for code in WHO_INDICATORS:
            body = get_json(f"{WHO_GHO_BASE_URL}/{code}")
            rows = body.get("value", []) if isinstance(body, dict) else []
            payload[code] = rows
            log.info("who_fetched", extra={"indicator": code, "rows": len(rows)})

        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_path.write_text(json.dumps(payload), encoding="utf-8")
        return self.raw_path

    def validate(self, raw: Path) -> None:
        payload = json.loads(raw.read_text(encoding="utf-8"))

        for code in WHO_INDICATORS:
            filtered = apply_who_filters(payload.get(code) or [])
            if not filtered:
                raise CoverageError(f"indicator {code} yielded no country rows",
                                    indicator=code)

            missing = set(TARGET_COUNTRIES) - {r["SpatialDim"] for r in filtered}
            if missing:
                raise CoverageError(
                    f"indicator {code} missing markets: {sorted(missing)}",
                    indicator=code, missing=sorted(missing),
                )

            for row in filtered:
                value = row.get("NumericValue")
                if value is None or not PREVALENCE_MIN_PCT < value < PREVALENCE_MAX_PCT:
                    raise SourceValidationError(
                        f"{code}/{row['SpatialDim']}: prevalence {value} out of range",
                        indicator=code, country=row.get("SpatialDim"),
                    )
                low, high = row.get("Low"), row.get("High")
                if low is not None and high is not None and not low <= value <= high:
                    raise SourceValidationError(
                        f"{code}/{row['SpatialDim']}: interval [{low}, {high}] "
                        f"does not bracket {value}",
                        indicator=code, country=row.get("SpatialDim"),
                    )

    def transform(self, raw: Path) -> pd.DataFrame:
        payload = json.loads(raw.read_text(encoding="utf-8"))
        records: list[dict[str, Any]] = []

        for code, name in WHO_INDICATORS.items():
            filtered = apply_who_filters(payload[code])
            latest_year = max(int(r["TimeDim"]) for r in filtered)

            for row in filtered:
                if int(row["TimeDim"]) != latest_year:
                    continue
                records.append(
                    {
                        "country_code": row["SpatialDim"],
                        "indicator": name,
                        "year": latest_year,
                        "prevalence_pct": float(row["NumericValue"]),
                        "prevalence_low": _opt_float(row.get("Low")),
                        "prevalence_high": _opt_float(row.get("High")),
                        "age_group": WHO_AGE_GROUP_ADULT,
                        "sex": WHO_SEX_BOTH,
                        "source": f"{SOURCE_LABEL} {code}",
                        "confidence_tier": "A",
                        "is_projected": False,
                    }
                )
            log.info("who_transformed", extra={"indicator": code, "year": latest_year})

        return pd.DataFrame.from_records(records)


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)
