"""ClinicalTrials.gov v2 — competitive entry context.

Off the calculation path. Staged only; never read by the engine.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ..constants import CLINICALTRIALS_URL, SourceId
from ..errors import SourceValidationError
from ..http import get_json
from ..base import Fetcher

log = logging.getLogger(__name__)

SOURCE_LABEL = "ClinicalTrials.gov"
QUERY_TERM = "semaglutide OR tirzepatide OR orforglipron OR obesity"
STATUS_FILTER = "RECRUITING,ACTIVE_NOT_RECRUITING"
PAGE_SIZE = 200


class ClinicalTrialsFetcher(Fetcher):
    source_id = SourceId.CLINICALTRIALS

    def extract(self) -> Path:
        body = get_json(
            CLINICALTRIALS_URL,
            params={
                "query.term": QUERY_TERM,
                "filter.overallStatus": STATUS_FILTER,
                "pageSize": PAGE_SIZE,
                "format": "json",
            },
        )
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_path.write_text(json.dumps(body), encoding="utf-8")
        return self.raw_path

    def validate(self, raw: Path) -> None:
        body = json.loads(raw.read_text(encoding="utf-8"))
        if not body.get("studies"):
            raise SourceValidationError("no studies returned")

    def transform(self, raw: Path) -> pd.DataFrame:
        body = json.loads(raw.read_text(encoding="utf-8"))
        records: list[dict[str, Any]] = []

        for study in body["studies"]:
            proto = study.get("protocolSection") or {}
            ident = proto.get("identificationModule") or {}
            status = proto.get("statusModule") or {}
            design = proto.get("designModule") or {}
            sponsor = (proto.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}
            conditions = (proto.get("conditionsModule") or {}).get("conditions") or []

            records.append(
                {
                    "nct_id": ident.get("nctId"),
                    "brief_title": ident.get("briefTitle"),
                    "status": status.get("overallStatus"),
                    "phase": ",".join(design.get("phases") or []),
                    "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
                    "sponsor": sponsor.get("name"),
                    "conditions": ",".join(conditions[:3]),
                    "start_date": (status.get("startDateStruct") or {}).get("date"),
                    "source": SOURCE_LABEL,
                }
            )

        return pd.DataFrame.from_records(records)
