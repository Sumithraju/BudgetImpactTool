"""Ingestion CLI.

    python -m data.ingestion.run                 # all sources, fetch + transform
    python -m data.ingestion.run --no-extract    # reuse raw payloads on disk
    python -m data.ingestion.run worldbank who_gho

Publishing to PostgreSQL is a separate stage; this entry point stops after
transform so it can be run and verified without a database.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .constants import SourceId
from .errors import IngestionError
from .sources.clinicaltrials import ClinicalTrialsFetcher
from .sources.frankfurter import FrankfurterFetcher
from .sources.nadac import NadacFetcher
from .sources.openfda import OpenFdaFetcher
from .sources.who_gho import WhoGhoFetcher
from .sources.worldbank import WorldBankFetcher

log = logging.getLogger("ingestion")

FETCHERS = {
    SourceId.WORLD_BANK: WorldBankFetcher,
    SourceId.WHO_GHO: WhoGhoFetcher,
    SourceId.FRANKFURTER: FrankfurterFetcher,
    SourceId.NADAC: NadacFetcher,
    SourceId.OPENFDA: OpenFdaFetcher,
    SourceId.CLINICALTRIALS: ClinicalTrialsFetcher,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BIET reference data ingestion")
    parser.add_argument("sources", nargs="*", choices=[s.value for s in SourceId] or None,
                        help="sources to run (default: all)")
    parser.add_argument("--no-extract", action="store_true",
                        help="reuse raw payloads already on disk")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    selected = [SourceId(s) for s in args.sources] if args.sources else list(SourceId)
    failures = 0

    for source_id in selected:
        fetcher = FETCHERS[source_id]()
        try:
            frame, result = fetcher.run(extract=not args.no_extract)
            print(f"  OK    {source_id.value:16s} {len(frame):>8,} rows")
        except IngestionError as exc:
            failures += 1
            print(f"  FAIL  {source_id.value:16s} {exc.code}: {exc.message}")
        except Exception as exc:                          # noqa: BLE001
            failures += 1
            print(f"  ERROR {source_id.value:16s} {type(exc).__name__}: {exc}")

    print(f"\n{len(selected) - failures}/{len(selected)} sources succeeded")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
