"""Narrative safety core — module M10, the pure half.

M10 is an I/O-heavy module (pgvector retrieval, an LLM call, PDF/PPTX
generation), and none of that can live in `biet_engine`, which performs no
I/O by non-negotiable 1. What *is* pure — and, by the module doc's
own assessment, the most important part of it — lives here:

- `validate_numbers`, the post-generation half of section 5.1's two-layer
  enforcement that **every number in generated text comes from the engine**.
  Section 10: "The numeric validator tests are the most important in this
  module. They are what enforce section 5.1."
- `MANDATORY_LIMITATIONS`, the seven statements section 5.5 requires in
  every narrative and every export, "not optional and not subject to the
  model's discretion."
- `filter_by_similarity`, section 5.3's retrieval floor.
- `build_assumption_register`, section 5.7's table, built from a run
  snapshot rather than live reference data.

The retrieval query, the LLM call, the prompt assembly and the exporters
belong in `biet_api` and arrive with Phase 3, when that layer exists.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from enum import StrEnum

from .models import AssumptionEntry, CountryInput, EngineInput, RetrievedChunk, Valued

#: Below this cosine similarity a retrieved chunk is not evidence (section 5.3).
DEFAULT_SIMILARITY_FLOOR = 0.35

#: Top-k retrieved chunks (section 5.3).
DEFAULT_RETRIEVAL_K = 5


class NarrativeSection(StrEnum):
    """The five sections generated in one call (section 5.4)."""

    POPULATION = "population"
    IMPACT = "impact"
    AFFORDABILITY = "affordability"
    UNCERTAINTY = "uncertainty"
    LIMITATIONS = "limitations"


#: Section 5.5's seven mandatory limitations, each attributed to the module
#: that owns the assumption. Every narrative and every export includes all
#: seven verbatim — they are the honest statement of what this model does
#: not do, and dropping one would misrepresent the estimate.
MANDATORY_LIMITATIONS: tuple[str, ...] = (
    ("Persistence is applied at the first-year fraction uniformly across the horizon, "
     "which understates later-year consumption and is therefore conservative (M6)."),
    ("Costs are held constant across the horizon; no price erosion or loss of "
     "exclusivity is modelled (M5)."),
    "Eligibility criteria are combined assuming conditional independence (M3).",
    ("Probabilistic sensitivity analysis samples parameters independently; no "
     "correlation structure is imposed (M9)."),
    ("Affordability is assessed against total national health expenditure, not a "
     "pharmaceutical budget subset (M8)."),
    ("Any market whose price is purchasing-power-parity derived rather than observed "
     "is flagged individually (M5)."),
    ("Any input with a stale vintage, a projected value, or tier-D confidence is "
     "named explicitly (M1)."),
)

#: A numeric token in generated prose: optional sign, digits with optional
#: thousands separators, optional decimal part. Deliberately does not try to
#: capture currency symbols or percent signs — those are formatting around
#: the number, and `_normalise_number` strips them from consideration by
#: only ever comparing the numeric value itself.
_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

#: Numbers this validator ignores. Years and small integers appear
#: constantly in ordinary prose ("the five sections", "over 3 years",
#: "2028") and are not engine outputs; demanding they appear in the context
#: would make the validator unusable without making the text safer.
_IGNORED_SMALL_INTEGER_MAX = 10


def _context_values(context: Iterable[float]) -> set[float]:
    return {float(v) for v in context}


def _is_ignorable(value: float) -> bool:
    """Years and small counts are prose, not engine output."""
    if value.is_integer():
        integer = int(value)
        if 0 <= integer <= _IGNORED_SMALL_INTEGER_MAX:
            return True
        if 1900 <= integer <= 2200:                  # a calendar year
            return True
    return False


def extract_numbers(text: str) -> tuple[float, ...]:
    """Every numeric token in `text`, normalised to float.

    Thousands separators are stripped, so `1,234,567` and `1234567` both
    normalise to the same value — section 10's "tolerates formatting
    variants of a supplied number".
    """
    # Every `_NUMBER_PATTERN` match is parseable by construction once
    # thousands separators are stripped, so there is no unparseable-token
    # branch to guard here.
    return tuple(
        float(match.group().replace(",", "")) for match in _NUMBER_PATTERN.finditer(text)
    )


def unsupported_numbers(
    text: str, context: Sequence[float], *, tolerance: float = 0.01,
) -> tuple[float, ...]:
    """Numbers in `text` that do not appear in `context`.

    `tolerance` is relative and exists for one reason only: a narrative that
    presents an engine value rounded for readability (38,218,333 as
    "38.2 million" -> 38.2) must not be rejected as fabricated. It is *not*
    licence for the model to compute — an unmatched number is still an
    unmatched number, and any value not within tolerance of a supplied one
    is returned here.

    Returns:
        The offending values, empty when every number is supported. The
        caller fails generation and logs these (section 6).
    """
    supplied = _context_values(context)
    offending = []

    for value in extract_numbers(text):
        if _is_ignorable(value):
            continue
        if any(_matches(value, candidate, tolerance) for candidate in supplied):
            continue
        offending.append(value)

    return tuple(offending)


def _matches(value: float, candidate: float, tolerance: float) -> bool:
    if value == candidate:
        return True
    if candidate == 0:
        return value == 0
    # Relative match against the candidate itself, and against the candidate
    # scaled by powers of a thousand — "38.2" legitimately stands for
    # 38,218,333 when the prose says "38.2 million".
    for scale in (1.0, 1e-3, 1e-6, 1e-9):
        scaled = candidate * scale
        if scaled != 0 and abs(value - scaled) / abs(scaled) <= tolerance:
            return True
    return False


def validate_numbers(text: str, context: Sequence[float], *, tolerance: float = 0.01) -> None:
    """Section 5.1's post-generation enforcement.

    Raises:
        ValueError: the text contains a number absent from `context`. The
            message names the offending tokens, since section 6 requires
            logging them.
    """
    offending = unsupported_numbers(text, context, tolerance=tolerance)
    if offending:
        raise ValueError(
            "generated text contains number(s) absent from the supplied engine "
            f"context: {list(offending)} — every quantitative value in a narrative "
            "must originate from the deterministic engine (M10 section 5.1)"
        )


def filter_by_similarity(
    chunks: Sequence[RetrievedChunk], *, floor: float = DEFAULT_SIMILARITY_FLOOR,
) -> tuple[RetrievedChunk, ...]:
    """Drop retrieved chunks below the similarity floor (section 5.3).

    An empty result is not an error — section 6 says to generate without
    citations and warn `NO_GROUNDING`.
    """
    return tuple(chunk for chunk in chunks if chunk.similarity >= floor)


def _register_entries_for(country: CountryInput) -> list[AssumptionEntry]:
    entries: list[AssumptionEntry] = []

    def _add(path: str, value: Valued | None) -> None:
        if value is None:
            return
        entries.append(AssumptionEntry(
            parameter_path=path,
            country_code=country.country_code,
            value=value.value,
            source=value.provenance.source,
            vintage_year=value.provenance.vintage_year,
            confidence_tier=value.provenance.confidence_tier,
            resolution_level=value.provenance.resolution_level,
            is_projected=value.provenance.is_projected,
        ))

    _add("population.total", country.population_total)
    _add("countries.adult_share", country.adult_share)
    _add("population.growth", country.population_growth)
    _add("epidemiology.prevalence", country.prevalence)
    _add("economics.health_exp_pc", country.health_exp_pc)
    _add("economics.gdp_pc_ppp", country.gdp_pc_ppp)
    _add("funnel.diagnosis_rate", country.funnel.diagnosis_rate)
    _add("funnel.treatment_rate", country.funnel.treatment_rate)
    _add("funnel.access_rate", country.funnel.access_rate)

    for criterion in country.criteria:
        _add(f"criteria.{criterion.code}.factor", criterion.factor)

    for therapy in (*country.therapies, country.new_therapy):
        _add(f"therapy.{therapy.drug_id}.persistence_12m", therapy.persistence_12m)
        _add(f"therapy.{therapy.drug_id}.discount_pct", therapy.discount_pct)
        _add(f"therapy.{therapy.drug_id}.wastage_pct", therapy.regimen.wastage_pct)

    return entries


def build_assumption_register(snapshot: EngineInput) -> tuple[AssumptionEntry, ...]:
    """Every resolved input the run consumed, with its provenance.

    Built from the run's own `EngineInput` snapshot rather than live
    reference data (section 5.7), so an export of an old run reflects what
    that run actually used — not what the database says today. That is the
    whole point of the requirement: text and numbers must never drift apart.
    """
    entries: list[AssumptionEntry] = []
    for country in snapshot.countries:
        entries.extend(_register_entries_for(country))
    return tuple(entries)
