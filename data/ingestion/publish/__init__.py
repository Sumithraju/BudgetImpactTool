"""Publish stage — writes transformed frames and curated seed data to Postgres.

Not exercised by the offline test suite: everything here needs a live
database, by design (M0 section 5.1 / STATUS.md section 5.1).

Imports `biet_api` from the sibling `backend/src` package. `pip install -e
backend` registers that via a `.pth` file, but this machine's Python (a
python.org 3.13 build) silently skips every `.pth` file in site-packages —
confirmed independent of any sandboxing, so it is a property of the
interpreter, not of how this session runs commands. Bootstrapping the path
explicitly here works regardless of whether the editable install's `.pth`
is honoured.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parents[3] / "backend" / "src"
if str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

from .corpus import ingest_corpus  # noqa: E402
from .pipeline import publish_seed, publish_source  # noqa: E402

__all__ = ["ingest_corpus", "publish_seed", "publish_source"]
