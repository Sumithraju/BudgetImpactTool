"""BIET calculation engine — pure functions only.

No I/O of any kind: no database, no network, no file access, no logging, no
config reads (CLAUDE.md non-negotiable 1). Every function receives resolved
primitives and returns computed results; resolution happens in `biet_api`
before the engine is called.

`__version__` is written into every persisted run (`model_runs.engine_version`)
so a historical run can be reproduced against the exact engine that produced
it. Any change that alters a numerical result is at minimum a minor bump.
"""

from __future__ import annotations

__version__ = "0.1.0"
