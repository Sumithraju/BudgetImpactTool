"""Publish orchestration — wires `.seed` and `.live` into one CLI-callable entry.

Seed data publishes first (countries, indications, drugs...) so the live
sources, which reference them by foreign key, have something to attach to.
Each live source publishes in its own transaction: a source that fails here
does not touch data another source already committed (M0 section 5.7).
"""

from __future__ import annotations

import logging

import pandas as pd
from biet_api.dal import session_scope

from ..constants import SourceId
from . import live, seed

log = logging.getLogger(__name__)


def publish_seed() -> dict[str, int]:
    with session_scope() as session:
        return seed.publish_seed_all(session)


def publish_source(source_id: SourceId, frame: pd.DataFrame) -> int:
    """Publish one already-transformed source frame."""
    with session_scope() as session:
        live.stage_frame(session, source_id.value, frame)

        if source_id is SourceId.WORLD_BANK:
            return live.publish_worldbank(session, frame, seed.load_age_bands())
        if source_id is SourceId.WHO_GHO:
            return live.publish_who_gho(session, frame, seed.load_diabetes_cagr())
        if source_id is SourceId.FRANKFURTER:
            return live.publish_frankfurter(session, frame)
        if source_id is SourceId.NADAC:
            return live.publish_nadac(session, frame, seed.load_ndc_regimen_map())
        if source_id in (SourceId.OPENFDA, SourceId.CLINICALTRIALS):
            return len(frame)              # off calc path; staging above is enough

        raise ValueError(f"no publisher registered for {source_id}")
