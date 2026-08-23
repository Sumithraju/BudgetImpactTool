"""Unit tests for biet_engine.narrative — M10 section 10.

The numeric-validator tests are the important ones here: section 10 calls
them "the most important in this module. They are what enforce section
5.1" — the rule that no number in generated text may originate from the
language model rather than the engine.
"""

from __future__ import annotations

import pytest

from biet_engine.models import RetrievedChunk
from biet_engine.narrative import (
    DEFAULT_SIMILARITY_FLOOR,
    MANDATORY_LIMITATIONS,
    NarrativeSection,
    build_assumption_register,
    extract_numbers,
    filter_by_similarity,
    unsupported_numbers,
    validate_numbers,
)

from ..conftest import make_country_input, make_engine_input


def _chunk(similarity: float, chunk_id: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id, document_title="Principles of Good Practice for BIA",
        issuing_body="ISPOR", section="Time Horizon", page_number=5,
        text="BIAs should be presented for the time horizons of relevance to the budget holder.",
        similarity=similarity,
    )


# --------------------------------------------------------------------------- numeric validation


def test_validator_accepts_text_reproducing_supplied_numbers_exactly() -> None:
    context = [38_218_333.0, 311_615.0, 2452.92]
    text = (
        "The addressable population is 311615 patients and the budget impact is "
        "38218333 EUR, at a net cost per switch of 2452.92 EUR."
    )
    validate_numbers(text, context)          # must not raise


def test_validator_tolerates_thousands_separators() -> None:
    context = [1_234_567.0]
    validate_numbers("The figure is 1,234,567 patients.", context)
    validate_numbers("The figure is 1234567 patients.", context)


def test_validator_rejects_text_containing_an_unsupplied_number() -> None:
    context = [38_218_333.0]
    text = "The budget impact is 38218333 EUR, or 91234567 EUR at scale."
    with pytest.raises(ValueError, match="absent from the supplied engine context"):
        validate_numbers(text, context)


def test_validator_names_the_offending_token() -> None:
    context = [100.0]
    with pytest.raises(ValueError, match="99999"):
        validate_numbers("Values were 100 and 99999.", context)


def test_validator_tolerates_a_readable_rounding_of_a_supplied_number() -> None:
    # "38.2 million" is the same engine value as 38,218,333, presented for
    # readability -- not a fabricated number.
    context = [38_218_333.0]
    validate_numbers("The budget impact is about 38.2 million EUR.", context)


def test_validator_ignores_calendar_years_and_small_counts() -> None:
    # Years and small integers are ordinary prose, not engine output.
    context = [38_218_333.0]
    validate_numbers(
        "Across 3 markets over 5 years from 2028 to 2030, impact is 38218333 EUR.",
        context,
    )


def test_validator_rejects_a_plausible_but_uncomputed_number() -> None:
    # The classic failure this rule exists to prevent: the model doing its
    # own arithmetic. 311,615 x 2 is not an engine output.
    context = [311_615.0]
    with pytest.raises(ValueError):
        validate_numbers("Doubling the population gives 623230 patients.", context)


def test_unsupported_numbers_returns_every_offender_not_just_the_first() -> None:
    offending = unsupported_numbers("Values 555555, 666666 and 777777.", [555555.0])
    assert set(offending) == {666666.0, 777777.0}


def test_unsupported_numbers_empty_when_all_supported() -> None:
    assert unsupported_numbers("Just 100000 here.", [100_000.0]) == ()


def test_extract_numbers_handles_negatives_and_decimals() -> None:
    values = extract_numbers("A saving of -1234.56 against 7890.")
    assert -1234.56 in values
    assert 7890.0 in values


def test_validator_accepts_a_negative_budget_impact_as_a_supplied_value() -> None:
    # A saving is a real result (M7 section 5.3) and must pass validation.
    validate_numbers("The result is a saving of -1234567 USD.", [-1_234_567.0])


def test_validator_with_empty_context_rejects_any_substantive_number() -> None:
    with pytest.raises(ValueError):
        validate_numbers("The impact is 987654 USD.", [])


def test_zero_in_context_matches_only_zero() -> None:
    # A zero engine value (zero uptake, zero impact) is a legitimate result,
    # but it must not act as a wildcard that validates any other number --
    # relative tolerance against zero is undefined.
    validate_numbers("The budget impact is 0 USD.", [0.0])
    with pytest.raises(ValueError):
        validate_numbers("The budget impact is 987654 USD.", [0.0])


# --------------------------------------------------------------------------- retrieval floor


def test_similarity_floor_excludes_below_and_includes_above() -> None:
    kept = filter_by_similarity([_chunk(0.30, 1), _chunk(0.40, 2)])
    assert [c.chunk_id for c in kept] == [2]


def test_similarity_floor_is_inclusive_at_the_boundary() -> None:
    kept = filter_by_similarity([_chunk(DEFAULT_SIMILARITY_FLOOR)])
    assert len(kept) == 1


def test_no_chunks_above_floor_returns_empty_rather_than_raising() -> None:
    # Section 6: generate without citations and warn NO_GROUNDING -- an
    # empty retrieval is a documented state, not an error.
    assert filter_by_similarity([_chunk(0.10), _chunk(0.20)]) == ()


# --------------------------------------------------------------------------- mandatory limitations


def test_all_seven_mandatory_limitations_are_present() -> None:
    assert len(MANDATORY_LIMITATIONS) == 7
    assert len(set(MANDATORY_LIMITATIONS)) == 7


def test_each_mandatory_limitation_names_its_owning_module() -> None:
    # Section 5.5 draws each limitation "from the modules that own them";
    # keeping the attribution makes each one traceable to its source spec.
    for limitation in MANDATORY_LIMITATIONS:
        assert any(f"(M{n})" in limitation for n in (1, 3, 5, 6, 8, 9))


def test_mandatory_limitations_cover_the_documented_subjects() -> None:
    joined = " ".join(MANDATORY_LIMITATIONS).lower()
    for subject in ("persistence", "price erosion", "independence",
                     "correlation", "health expenditure", "parity", "vintage"):
        assert subject in joined


def test_narrative_sections_are_the_documented_five() -> None:
    assert {s.value for s in NarrativeSection} == {
        "population", "impact", "affordability", "uncertainty", "limitations",
    }


# --------------------------------------------------------------------------- assumption register


def test_assumption_register_is_built_from_the_snapshot_not_live_data() -> None:
    snapshot = make_engine_input(
        countries=(make_country_input(country_code="DEU", currency="EUR", horizon=1),),
        horizon_years=1, reporting_currency="EUR",
    )
    register = build_assumption_register(snapshot)

    paths = {e.parameter_path for e in register}
    assert "epidemiology.prevalence" in paths
    assert "funnel.diagnosis_rate" in paths
    assert all(e.country_code == "DEU" for e in register)

    # The register reflects the snapshot's values, so mutating the source
    # scenario afterwards cannot change an already-built register.
    prevalence = next(e for e in register if e.parameter_path == "epidemiology.prevalence")
    assert prevalence.value == pytest.approx(0.2064)


def test_assumption_register_carries_full_provenance_on_every_row() -> None:
    snapshot = make_engine_input(
        countries=(make_country_input(horizon=1),), horizon_years=1,
    )
    register = build_assumption_register(snapshot)

    assert register
    for entry in register:
        assert entry.source
        assert entry.confidence_tier
        assert entry.resolution_level


def test_assumption_register_skips_unresolved_values() -> None:
    snapshot = make_engine_input(
        countries=(make_country_input(horizon=1, adult_share=None, health_exp_pc=None),),
        horizon_years=1,
    )
    paths = {e.parameter_path for e in build_assumption_register(snapshot)}
    assert "countries.adult_share" not in paths
    assert "economics.health_exp_pc" not in paths


def test_assumption_register_covers_every_market() -> None:
    snapshot = make_engine_input(
        countries=(
            make_country_input(country_code="USA", currency="USD", horizon=1),
            make_country_input(country_code="DEU", currency="EUR", horizon=1),
        ),
        horizon_years=1, reporting_currency="USD",
    )
    register = build_assumption_register(snapshot)
    assert {e.country_code for e in register} == {"USA", "DEU"}
