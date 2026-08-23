"""Ingestion CLI.

    python -m data.ingestion.run                 # all sources, fetch + transform
    python -m data.ingestion.run --no-extract    # reuse raw payloads on disk
    python -m data.ingestion.run worldbank who_gho
    python -m data.ingestion.run --publish        # also publish to PostgreSQL
    python -m data.ingestion.run --seed-only      # publish data/seed/*.csv only

Publishing is opt-in via --publish, so the default run can be verified without
a database. --seed-only loads the curated seed CSVs and stops; useful on its
own since seed data must publish before the live sources' foreign keys resolve.
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
    parser.add_argument("--publish", action="store_true",
                        help="also publish seed data and transformed frames to PostgreSQL")
    parser.add_argument("--seed-only", action="store_true",
                        help="publish data/seed/*.csv and exit; implies --publish")
    parser.add_argument("--corpus", action="store_true",
                        help="chunk, embed and publish data/corpus/*.pdf and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
    )

    if args.corpus:
        from .publish import ingest_corpus
        counts = ingest_corpus()
        for name, chunks in counts.items():
            print(f"  OK    {name:60s} {chunks:>6,} chunks")
        return 0

    if args.seed_only:
        from .publish import publish_seed
        counts = publish_seed()
        for name, rows in counts.items():
            print(f"  OK    {name:24s} {rows:>8,} rows")
        return 0

    selected = [SourceId(s) for s in args.sources] if args.sources else list(SourceId)
    failures = 0

    if args.publish:
        from .publish import publish_seed
        counts = publish_seed()
        for name, rows in counts.items():
            print(f"  OK    {name:24s} {rows:>8,} rows")

    for source_id in selected:
        fetcher = FETCHERS[source_id]()
        try:
            frame, result = fetcher.run(extract=not args.no_extract)
            published_note = ""
            if args.publish:
                from .publish import publish_source
                rows = publish_source(source_id, frame)
                published_note = f" -> {rows:,} published"
            print(f"  OK    {source_id.value:16s} {len(frame):>8,} rows{published_note}")
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
