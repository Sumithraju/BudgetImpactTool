"""Unit tests for the resolution chain — M1 sections 5.2 and 5.3.

Resolution is where a wrong answer would be least visible: every value the
engine consumes passes through here, and a silently-defaulted or
wrongly-levelled value produces a plausible result rather than an error.
These tests pin the ordering and the provenance that make it auditable.
"""

from __future__ import annotations

import pytest

from biet_api.services.resolution import (
    ReferenceValue,
    ResolutionContext,
    ResolutionService,
    UnresolvedParameterError,
)
from biet_engine.models import ConfidenceTier, ResolutionLevel

PATH = "funnel.diagnosis_rate"


def _ref(value: float, source: str = "test", **kwargs: object) -> ReferenceValue:
    return ReferenceValue(  # type: ignore[arg-type]
        value=value, source=source,
        confidence_tier=kwargs.pop("confidence_tier", ConfidenceTier.A), **kwargs,
    )


# --------------------------------------------------------------------------- ordering


def test_scenario_override_beats_country_default_beats_global_default() -> None:
    service = ResolutionService(ResolutionContext(
        scenario_overrides={(PATH, "DEU"): _ref(0.9)},
        country_defaults={(PATH, "DEU"): _ref(0.6)},
        global_defaults={(PATH, None): _ref(0.3)},
    ))
    assert service.resolve(PATH, "DEU").value == 0.9


def test_country_default_beats_global_default_when_no_override() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={(PATH, "DEU"): _ref(0.6)},
        global_defaults={(PATH, None): _ref(0.3)},
    ))
    resolved = service.resolve(PATH, "DEU")
    assert resolved.value == 0.6
    assert resolved.provenance.resolution_level is ResolutionLevel.COUNTRY_OVERRIDE


def test_global_default_used_when_nothing_more_specific_exists() -> None:
    service = ResolutionService(ResolutionContext(
        global_defaults={(PATH, None): _ref(0.3)},
    ))
    resolved = service.resolve(PATH, "DEU")
    assert resolved.value == 0.3
    assert resolved.provenance.resolution_level is ResolutionLevel.GLOBAL_DEFAULT


def test_all_markets_scenario_override_applies_to_every_market() -> None:
    service = ResolutionService(ResolutionContext(
        scenario_overrides={(PATH, None): _ref(0.75)},
        global_defaults={(PATH, None): _ref(0.3)},
    ))
    assert service.resolve(PATH, "DEU").value == 0.75
    assert service.resolve(PATH, "USA").value == 0.75


def test_explicit_country_override_beats_all_markets_override() -> None:
    # Both live at the same level, so this is the within-level tiebreak:
    # naming the market explicitly wins over applying to all of them.
    service = ResolutionService(ResolutionContext(
        scenario_overrides={(PATH, None): _ref(0.75), (PATH, "DEU"): _ref(0.42)},
    ))
    assert service.resolve(PATH, "DEU").value == 0.42
    assert service.resolve(PATH, "USA").value == 0.75


def test_unresolved_path_raises_rather_than_defaulting() -> None:
    service = ResolutionService(ResolutionContext())
    with pytest.raises(UnresolvedParameterError, match="funnel.diagnosis_rate"):
        service.resolve(PATH, "DEU")


# --------------------------------------------------------------------------- provenance


def test_provenance_records_the_level_that_supplied_the_value() -> None:
    for level, context in (
        (ResolutionLevel.SCENARIO_OVERRIDE,
         ResolutionContext(scenario_overrides={(PATH, "DEU"): _ref(0.9)})),
        (ResolutionLevel.COUNTRY_OVERRIDE,
         ResolutionContext(country_defaults={(PATH, "DEU"): _ref(0.6)})),
        (ResolutionLevel.GLOBAL_DEFAULT,
         ResolutionContext(global_defaults={(PATH, None): _ref(0.3)})),
    ):
        resolved = ResolutionService(context).resolve(PATH, "DEU")
        assert resolved.provenance.resolution_level is level


def test_override_carries_tier_c_regardless_of_the_underlying_row() -> None:
    # An override is an assertion by the user, not an observation, so it
    # cannot inherit tier A from whatever it replaced.
    service = ResolutionService(ResolutionContext(
        scenario_overrides={(PATH, "DEU"): _ref(0.9, confidence_tier=ConfidenceTier.A)},
    ))
    assert service.resolve(PATH, "DEU").provenance.confidence_tier is ConfidenceTier.C


def test_non_override_levels_keep_their_published_tier() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={(PATH, "DEU"): _ref(0.6, confidence_tier=ConfidenceTier.B)},
    ))
    assert service.resolve(PATH, "DEU").provenance.confidence_tier is ConfidenceTier.B


def test_bounds_and_source_survive_resolution() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={
            (PATH, "DEU"): ReferenceValue(
                value=0.6, low=0.5, high=0.7, source="WHO NCD_BMI_30A",
                confidence_tier=ConfidenceTier.A, vintage_year=2024,
            )
        },
    ))
    resolved = service.resolve(PATH, "DEU")
    assert (resolved.low, resolved.high) == (0.5, 0.7)
    assert resolved.provenance.source == "WHO NCD_BMI_30A"
    assert resolved.provenance.vintage_year == 2024


# --------------------------------------------------------------------------- warnings (section 5.3)


def test_stale_vintage_emitted_at_six_years_not_five() -> None:
    # The boundary is "> 5", so a five-year gap is silent and six warns.
    for gap, expect_warning in ((5, False), (6, True)):
        service = ResolutionService(ResolutionContext(
            country_defaults={
                (PATH, "DEU"): _ref(0.6, vintage_year=2028 - gap)
            },
            launch_year=2028,
        ))
        service.resolve(PATH, "DEU")
        codes = [w.code for w in service.warnings]
        assert ("STALE_VINTAGE" in codes) is expect_warning, gap


def test_projected_value_warns() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={(PATH, "DEU"): _ref(0.6, is_projected=True)},
        launch_year=2028,
    ))
    service.resolve(PATH, "DEU")
    assert [w.code for w in service.warnings] == ["PROJECTED_VALUE"]


def test_tier_d_input_warns() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={(PATH, "DEU"): _ref(0.6, confidence_tier=ConfidenceTier.D)},
        launch_year=2028,
    ))
    service.resolve(PATH, "DEU")
    assert [w.code for w in service.warnings] == ["TIER_D_INPUT"]


def test_no_vintage_year_never_triggers_stale_warning() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={(PATH, "DEU"): _ref(0.6)}, launch_year=2028,
    ))
    service.resolve(PATH, "DEU")
    assert service.warnings == ()


def test_warnings_carry_the_market_and_path_that_produced_them() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={(PATH, "DEU"): _ref(0.6, vintage_year=2014)},
        launch_year=2028,
    ))
    service.resolve(PATH, "DEU")
    warning = service.warnings[0]
    assert warning.country_code == "DEU"
    assert warning.parameter_path == PATH


def test_repeated_resolution_does_not_duplicate_a_warning() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={(PATH, "DEU"): _ref(0.6, vintage_year=2014)},
        launch_year=2028,
    ))
    service.resolve(PATH, "DEU")
    service.resolve(PATH, "DEU")
    assert len(service.warnings) == 1


def test_one_value_can_raise_several_warnings() -> None:
    service = ResolutionService(ResolutionContext(
        country_defaults={
            (PATH, "DEU"): _ref(
                0.6, vintage_year=2014, is_projected=True,
                confidence_tier=ConfidenceTier.D,
            )
        },
        launch_year=2028,
    ))
    service.resolve(PATH, "DEU")
    assert {w.code for w in service.warnings} == {
        "STALE_VINTAGE", "PROJECTED_VALUE", "TIER_D_INPUT",
    }
