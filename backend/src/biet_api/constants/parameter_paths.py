"""The closed override vocabulary — M1 section 5.1.

Overrides address values by dotted path. This module is the single
definition of which paths exist and what each accepts; an unknown path is
rejected at validation rather than silently ignored, because an override
that quietly does nothing is worse than one that errors — the user believes
they changed an assumption when they did not.

Some paths are literal (`funnel.diagnosis_rate`); others carry a variable
segment (`criteria.<criterion_code>.factor`, `therapy.<drug_id>.price_local`).
Both are declared here in one table, so adding a path means adding a row and
nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from .domain import UptakeCurve


class PathValueType(StrEnum):
    FLOAT = "float"
    BOOL = "bool"
    ENUM = "enum"
    FLOAT_LIST = "float_list"


@dataclass(frozen=True)
class ParameterPathSpec:
    """One entry in the override vocabulary.

    `pattern` matches the whole path. `minimum`/`maximum` bound a float, with
    `exclusive_min`/`exclusive_max` selecting open or closed at each end — the
    distinction matters: a rate of exactly 0 is invalid (nobody is diagnosed)
    while exactly 1 is fine (everybody is), and prevalence is open at both
    ends.
    """

    pattern: re.Pattern[str]
    template: str
    value_type: PathValueType
    minimum: float | None = None
    maximum: float | None = None
    exclusive_min: bool = False
    exclusive_max: bool = False
    allowed: frozenset[str] = frozenset()

    def matches(self, path: str) -> bool:
        return self.pattern.fullmatch(path) is not None


def _literal(template: str, value_type: PathValueType, **kwargs: Any) -> ParameterPathSpec:
    return ParameterPathSpec(
        pattern=re.compile(re.escape(template)), template=template,
        value_type=value_type, **kwargs,
    )


def _templated(
    template: str, regex: str, value_type: PathValueType, **kwargs: Any,
) -> ParameterPathSpec:
    return ParameterPathSpec(
        pattern=re.compile(regex), template=template, value_type=value_type, **kwargs,
    )


#: A rate in (0, 1] — zero would mean the stage passes nobody, which is a
#: degenerate scenario rather than an assumption worth modelling.
_RATE: Final[dict[str, Any]] = {
    "minimum": 0.0, "maximum": 1.0, "exclusive_min": True,
}

#: A share/probability in [0, 1] — zero is meaningful here (a therapy that
#: takes no share, a year with no uptake).
_SHARE: Final[dict[str, Any]] = {"minimum": 0.0, "maximum": 1.0}

PARAMETER_PATHS: Final[tuple[ParameterPathSpec, ...]] = (
    _literal("funnel.diagnosis_rate", PathValueType.FLOAT, **_RATE),
    _literal("funnel.treatment_rate", PathValueType.FLOAT, **_RATE),
    _literal("funnel.access_rate", PathValueType.FLOAT, **_RATE),
    _literal(
        "epidemiology.prevalence", PathValueType.FLOAT,
        minimum=0.0, maximum=1.0, exclusive_min=True, exclusive_max=True,
    ),
    _templated(
        "criteria.<criterion_code>.factor", r"criteria\.[A-Za-z0-9_]+\.factor",
        PathValueType.FLOAT, **_RATE,
    ),
    _templated(
        "criteria.<criterion_code>.enabled", r"criteria\.[A-Za-z0-9_]+\.enabled",
        PathValueType.BOOL,
    ),
    _literal(
        "uptake.curve", PathValueType.ENUM,
        allowed=frozenset(member.value for member in UptakeCurve),
    ),
    _literal("uptake.year_1", PathValueType.FLOAT, **_SHARE),
    _literal("uptake.terminal", PathValueType.FLOAT, **_SHARE),
    _literal("uptake.vector", PathValueType.FLOAT_LIST, **_SHARE),
    _templated(
        "therapy.<drug_id>.price_local", r"therapy\.\d+\.price_local",
        PathValueType.FLOAT, minimum=0.0, exclusive_min=True,
    ),
    _templated(
        "therapy.<drug_id>.persistence_12m", r"therapy\.\d+\.persistence_12m",
        PathValueType.FLOAT, **_RATE,
    ),
    _templated(
        "therapy.<drug_id>.market_share.<year>", r"therapy\.\d+\.market_share\.\d+",
        PathValueType.FLOAT, **_SHARE,
    ),
    _literal("substitution.naive", PathValueType.FLOAT, **_SHARE),
    _templated(
        "substitution.<drug_id>", r"substitution\.\d+", PathValueType.FLOAT, **_SHARE,
    ),
)

#: Every declared template, for the "listing valid paths" half of the 422
#: response M1 section 6 requires on an unknown path.
VALID_PATH_TEMPLATES: Final[tuple[str, ...]] = tuple(
    spec.template for spec in PARAMETER_PATHS
)


def spec_for(path: str) -> ParameterPathSpec | None:
    """The spec matching `path`, or None when the path is not in the closed
    vocabulary.

    `substitution.naive` is declared before `substitution.<drug_id>` so the
    literal wins; the templated pattern only matches digits, so they cannot
    collide, but order-independence there is worth not relying on.
    """
    for spec in PARAMETER_PATHS:
        if spec.matches(path):
            return spec
    return None
