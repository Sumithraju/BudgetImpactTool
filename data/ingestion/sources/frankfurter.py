"""Frankfurter (ECB reference rates) — foreign exchange.

On the calculation path: M7 converts per-market results to the reporting currency
using the rate set snapshotted into the run, never a live lookup.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from ..constants import (
    BASE_CURRENCY,
    FRANKFURTER_URL,
    MIN_FX_CURRENCIES,
    REQUIRED_CURRENCIES,
    SourceId,
)
from ..errors import SourceValidationError
from ..http import get_json
from ..base import Fetcher

log = logging.getLogger(__name__)

SOURCE_LABEL = "Frankfurter (ECB)"


class FrankfurterFetcher(Fetcher):
    source_id = SourceId.FRANKFURTER

    def extract(self) -> Path:
        quoted = sorted(REQUIRED_CURRENCIES - {BASE_CURRENCY})
        body = get_json(
            FRANKFURTER_URL,
            params={"base": BASE_CURRENCY, "symbols": ",".join(quoted)},
        )
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_path.write_text(json.dumps(body), encoding="utf-8")
        return self.raw_path

    def validate(self, raw: Path) -> None:
        body = json.loads(raw.read_text(encoding="utf-8"))
        rates = body.get("rates") or {}

        missing = (REQUIRED_CURRENCIES - {BASE_CURRENCY}) - set(rates)
        if missing:
            raise SourceValidationError(
                f"missing rates for {sorted(missing)}", missing=sorted(missing)
            )
        # +1 for the identity row added during transform.
        if len(rates) + 1 < MIN_FX_CURRENCIES:
            raise SourceValidationError(
                f"only {len(rates) + 1} currencies, need {MIN_FX_CURRENCIES}"
            )
        for code, rate in rates.items():
            if rate is None or rate <= 0:
                raise SourceValidationError(f"non-positive rate for {code}", currency=code)
        if not body.get("date"):
            raise SourceValidationError("response carries no rate date")

    def transform(self, raw: Path) -> pd.DataFrame:
        body = json.loads(raw.read_text(encoding="utf-8"))
        fetched = body["date"]

        records = [
            {
                "currency_code": code,
                "rate_per_usd": float(rate),
                "fetched_date": fetched,
                "source": SOURCE_LABEL,
            }
            for code, rate in body["rates"].items()
        ]
        # The identity row lets M7 pivot every conversion through USD without a
        # special case for USD itself.
        records.append(
            {
                "currency_code": BASE_CURRENCY,
                "rate_per_usd": 1.0,
                "fetched_date": fetched,
                "source": "identity",
            }
        )
        return pd.DataFrame.from_records(records).sort_values("currency_code")
