"""openFDA drug approvals — asset and comparator metadata.

Off the calculation path. The payload embeds serialised JSON in `submissions` and
`products`; this module flattens it to a projection and the engine never reads it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from ..constants import GLP1_GENERICS, OPENFDA_URL, SourceId
from ..errors import SourceValidationError
from ..http import get_json
from ..base import Fetcher

log = logging.getLogger(__name__)

SOURCE_LABEL = "openFDA drugsfda"
RESULT_LIMIT = 100


class OpenFdaFetcher(Fetcher):
    source_id = SourceId.OPENFDA

    def extract(self) -> Path:
        payload: dict[str, list[dict[str, Any]]] = {}

        for generic in GLP1_GENERICS:
            try:
                body = get_json(
                    OPENFDA_URL,
                    params={
                        "search": f'openfda.generic_name:"{generic}"',
                        "limit": RESULT_LIMIT,
                    },
                )
                payload[generic] = body.get("results", [])
            except Exception as exc:                      # noqa: BLE001
                # openFDA 404s for a generic with no records; that is information,
                # not a failure of the source.
                log.info("openfda_no_records", extra={"generic": generic, "error": str(exc)})
                payload[generic] = []

        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_path.write_text(json.dumps(payload), encoding="utf-8")
        return self.raw_path

    def validate(self, raw: Path) -> None:
        payload = json.loads(raw.read_text(encoding="utf-8"))
        if not any(payload.values()):
            raise SourceValidationError("no approval records for any target molecule")

    def transform(self, raw: Path) -> pd.DataFrame:
        payload = json.loads(raw.read_text(encoding="utf-8"))
        records: list[dict[str, Any]] = []

        for generic, results in payload.items():
            for entry in results:
                fda = entry.get("openfda") or {}
                for product in entry.get("products") or []:
                    ingredients = product.get("active_ingredients") or [{}]
                    records.append(
                        {
                            "generic_name": generic,
                            "application_number": entry.get("application_number"),
                            "sponsor_name": entry.get("sponsor_name"),
                            "brand_name": product.get("brand_name"),
                            "dosage_form": product.get("dosage_form"),
                            "route": product.get("route"),
                            "strength": ingredients[0].get("strength"),
                            "marketing_status": product.get("marketing_status"),
                            "pharm_class": "; ".join(fda.get("pharm_class_epc") or []),
                            "source": SOURCE_LABEL,
                        }
                    )

        return pd.DataFrame.from_records(records).drop_duplicates()
