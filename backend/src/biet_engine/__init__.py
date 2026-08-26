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

# 0.2.0 — M13 added `safety.py` (expected adverse-event cost and the cost
# bridge), and adverse-event costs are now resolved from seeded profiles
# rather than defaulting to zero. Results move for any therapy with a
# profile, so runs recorded under 0.1.0 are not comparable to these.
__version__ = "0.4.0"
