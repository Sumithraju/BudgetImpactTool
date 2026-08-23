"""NADAC (CMS Medicaid) — US pharmacy acquisition cost.

Two established constraints shape this module (M0 section 5.4).

First, the weekly file URL is dated and rolls off, so the current file is resolved
by walking recent Wednesdays backwards rather than hardcoding a date.

Second, and more importantly: **NADAC carries no branded incretin pricing.**
Filtering the full extract to the therapy classes of interest yields ~1,204 rows,
of which ~1,174 are insulin and ~30 generic liraglutide, with zero semaglutide and
zero tirzepatide. NADAC reports pharmacy acquisition cost, which exists principally
for multi-source products. This module's output is therefore confined to insulin
and generic comparators; branded prices come from the curated seed table.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..config import settings
from ..constants import (
    NADAC_CHUNK_SIZE,
    NADAC_DATASET_URL,
    NADAC_FALLBACK_WEEKS,
    NADAC_MOLECULES,
    SourceId,
)
from ..errors import SourceFetchError, SourceValidationError
from ..http import get
from ..base import Fetcher

log = logging.getLogger(__name__)

SOURCE_LABEL = "NADAC (CMS Medicaid)"

DESCRIPTION_COLUMNS = ("NDC Description", "NDC_Description", "Description")


def candidate_dates(today: date | None = None) -> list[str]:
    """Recent weekly file dates, most recent first.

    NADAC files are published Wednesdays and dated MM-DD-YYYY.
    """
    today = today or date.today()
    last_wednesday = today - timedelta(days=(today.weekday() - 2) % 7)
    return [
        (last_wednesday - timedelta(weeks=w)).strftime("%m-%d-%Y")
        for w in range(NADAC_FALLBACK_WEEKS)
    ]


class NadacFetcher(Fetcher):
    source_id = SourceId.NADAC

    @property
    def raw_path(self) -> Path:
        return settings.raw_dir / "nadac_full.csv"

    def extract(self) -> Path:
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)

        for stamp in candidate_dates():
            url = NADAC_DATASET_URL.format(date=stamp)
            try:
                response = get(url)
            except SourceFetchError:
                log.info("nadac_miss", extra={"date": stamp})
                continue

            self.raw_path.write_bytes(response.content)
            log.info(
                "nadac_fetched",
                extra={"date": stamp, "bytes": len(response.content)},
            )
            return self.raw_path

        raise SourceFetchError(
            f"no NADAC file found in the last {NADAC_FALLBACK_WEEKS} weeks"
        )

    def validate(self, raw: Path) -> None:
        header = pd.read_csv(raw, nrows=1)
        if not any(col in header.columns for col in DESCRIPTION_COLUMNS):
            raise SourceValidationError(
                f"no description column; saw {list(header.columns)[:6]}"
            )
        for required in ("NADAC Per Unit", "Pricing Unit", "Effective Date"):
            if required not in header.columns:
                raise SourceValidationError(f"missing column {required!r}")

    def transform(self, raw: Path) -> pd.DataFrame:
        pattern = "|".join(NADAC_MOLECULES)
        matched: list[pd.DataFrame] = []
        total = 0

        for chunk in pd.read_csv(raw, chunksize=NADAC_CHUNK_SIZE, low_memory=False):
            total += len(chunk)
            column = next(c for c in DESCRIPTION_COLUMNS if c in chunk.columns)
            hit = chunk[
                chunk[column].astype(str).str.contains(pattern, case=False, na=False)
            ]
            if not hit.empty:
                matched.append(hit)

        if not matched:
            raise SourceValidationError("no rows matched the target molecules")

        frame = pd.concat(matched, ignore_index=True)
        frame = frame.rename(
            columns={
                "NDC Description": "ndc_description",
                "NADAC Per Unit": "nadac_per_unit",
                "Pricing Unit": "pricing_unit",
                "Effective Date": "effective_date",
                "NDC": "ndc",
            }
        )
        frame["source"] = SOURCE_LABEL

        # Keep the most recent row per NDC.
        frame["effective_date"] = pd.to_datetime(
            frame["effective_date"], format="%m/%d/%Y", errors="coerce"
        )
        frame = (
            frame.sort_values("effective_date")
            .drop_duplicates(subset="ndc", keep="last")
            .reset_index(drop=True)
        )

        log.info(
            "nadac_transformed",
            extra={"scanned": total, "matched": len(frame)},
        )
        return frame[
            ["ndc", "ndc_description", "nadac_per_unit", "pricing_unit",
             "effective_date", "source"]
        ]
