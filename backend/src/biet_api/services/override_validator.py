"""Override validation against the closed path vocabulary — M1 sections 5.1 and 6.

Every override is checked here before it reaches storage or resolution, so
an invalid one fails at the boundary with a message naming the path, rather
than surfacing later as a mysterious engine error or — worse — silently
doing nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..constants.parameter_paths import (
    VALID_PATH_TEMPLATES,
    ParameterPathSpec,
    PathValueType,
    spec_for,
)
from ..exceptions import ParameterOutOfRangeError, UnknownParameterPathError, ValidationError


def _check_float_range(path: str, value: float, spec: ParameterPathSpec) -> None:
    if spec.minimum is not None:
        too_low = value <= spec.minimum if spec.exclusive_min else value < spec.minimum
        if too_low:
            bound = "greater than" if spec.exclusive_min else "at least"
            raise ParameterOutOfRangeError(
                f"{path!r} must be {bound} {spec.minimum}, got {value!r}",
                parameter_path=path, value=value, minimum=spec.minimum,
            )
    if spec.maximum is not None:
        too_high = value >= spec.maximum if spec.exclusive_max else value > spec.maximum
        if too_high:
            bound = "less than" if spec.exclusive_max else "at most"
            raise ParameterOutOfRangeError(
                f"{path!r} must be {bound} {spec.maximum}, got {value!r}",
                parameter_path=path, value=value, maximum=spec.maximum,
            )


def validate_override(path: str, value: Any, *, horizon_years: int | None = None) -> None:
    """Check one override against its path's declared type and range.

    Args:
        path: the dotted parameter path.
        value: the proposed value.
        horizon_years: required to check `uptake.vector`'s length, which must
            equal the horizon (section 6). When omitted, the length check is
            skipped — the caller is expected to supply it wherever a scenario
            context exists.

    Raises:
        UnknownParameterPathError: `path` is outside the closed vocabulary.
        ParameterOutOfRangeError: the value falls outside the path's range.
        ValidationError: the value is the wrong type for the path.
    """
    spec = spec_for(path)
    if spec is None:
        raise UnknownParameterPathError(
            f"{path!r} is not a valid parameter path; valid paths are "
            f"{list(VALID_PATH_TEMPLATES)}",
            parameter_path=path, valid_paths=list(VALID_PATH_TEMPLATES),
        )

    if spec.value_type is PathValueType.BOOL:
        # bool first: bool is a subclass of int in Python, so a plain
        # isinstance(value, (int, float)) check below would accept True for a
        # float path without this ordering.
        if not isinstance(value, bool):
            raise ValidationError(
                f"{path!r} expects a boolean, got {type(value).__name__}",
                parameter_path=path,
            )
        return

    if spec.value_type is PathValueType.ENUM:
        if not isinstance(value, str) or value not in spec.allowed:
            raise ValidationError(
                f"{path!r} expects one of {sorted(spec.allowed)}, got {value!r}",
                parameter_path=path, allowed=sorted(spec.allowed),
            )
        return

    if spec.value_type is PathValueType.FLOAT_LIST:
        if isinstance(value, bool) or not isinstance(value, Sequence) or isinstance(value, str):
            raise ValidationError(
                f"{path!r} expects a list of numbers, got {type(value).__name__}",
                parameter_path=path,
            )
        if horizon_years is not None and len(value) != horizon_years:
            raise ValidationError(
                f"{path!r} must have one entry per year: expected {horizon_years}, "
                f"got {len(value)}",
                parameter_path=path, expected=horizon_years, actual=len(value),
            )
        for index, item in enumerate(value):
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValidationError(
                    f"{path!r}[{index}] expects a number, got {type(item).__name__}",
                    parameter_path=path,
                )
            _check_float_range(f"{path}[{index}]", float(item), spec)
        return

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(
            f"{path!r} expects a number, got {type(value).__name__}",
            parameter_path=path,
        )
    _check_float_range(path, float(value), spec)
