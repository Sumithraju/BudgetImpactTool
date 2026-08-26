"""Classification and ranking — the pure half of M11.

Deliberately separated from retrieval. Everything here is a function of its
arguments: no HTTP, no session, no clock. That is what lets the interesting
logic — which drug counts as a direct competitor, how relevance is scored —
be tested against fixtures rather than against a live API whose contents
change as trials progress.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..constants.comparator import (
    MARKETED_STAGES,
    WEIGHT_APPROVAL,
    WEIGHT_INDICATION,
    WEIGHT_LINE_OF_THERAPY,
    WEIGHT_MARKET,
    WEIGHT_MECHANISM,
    WEIGHT_PATHWAY,
    WEIGHT_SEEDED,
    WEIGHT_TARGET,
    ClinicalStage,
    CompetitorClass,
)


@dataclass(frozen=True)
class Candidate:
    """One retrieved molecule, before classification."""

    source_id: str
    name: str
    target_symbol: str
    max_clinical_stage: ClinicalStage
    drug_type: str | None = None
    mechanism_of_action: str | None = None
    action_type: str | None = None
    indications: tuple[str, ...] = ()
    seeded_drug_id: int | None = None
    sources: tuple[str, ...] = ()
    # Populated only where a source actually supplied them: pathway ids by
    # the opt-in Reactome step, the last two by M12's curated registry. An
    # empty tuple and a None mean "not known", never "does not match".
    pathway_ids: tuple[str, ...] = ()
    market_codes: tuple[str, ...] = ()
    line_of_therapy: str | None = None


@dataclass(frozen=True)
class Classified:
    """A candidate with its verdict and the reasoning behind it."""

    candidate: Candidate
    competitor_class: CompetitorClass
    relevance: float
    rationale: str
    #: Which factors participated and how each scored. The interface shows a
    #: tick per factor, so it needs the breakdown rather than only the total.
    factors: tuple[Factor, ...] = ()

    @property
    def needs_pricing(self) -> bool:
        """Retrieval yields a molecule, never a price or a regimen. A drug
        with no seeded row cannot enter a calculation until one exists
        (M11 section 5.7)."""
        return self.candidate.seeded_drug_id is None


def _normalise(text: str | None) -> str:
    return (text or "").strip().lower()


def _mechanism_matches(mechanism: str | None, candidate: Candidate) -> bool:
    """Whole-word match, never a substring one.

    "agonist" is a substring of "antagonist", so a naive `in` test classifies
    every antagonist as an agonist — a drug that does the opposite of what
    was asked for, promoted to direct competitor. Word boundaries are what
    make this correct, and the two are indistinguishable until a test looks
    for exactly this case.
    """
    if not mechanism:
        return False
    wanted = _normalise(mechanism)
    if not wanted:
        return False

    if _normalise(candidate.action_type) == wanted:
        return True
    pattern = rf"\b{re.escape(wanted)}\b"
    return bool(re.search(pattern, _normalise(candidate.mechanism_of_action)))


@dataclass(frozen=True)
class DiscoveryContext:
    """The asset a candidate is being scored against.

    Optional fields default to "not known", never to "does not match". That
    distinction is the whole of M11 section 5.5: a factor nothing supplied a
    value for is left out of the score rather than counted as a miss, because
    counting it as a miss would penalise a candidate for the retrieval step
    the user declined to run.
    """

    target_symbol: str
    indication_terms: frozenset[str]
    mechanism: str | None = None
    pathway_ids: frozenset[str] = frozenset()
    market_codes: frozenset[str] = frozenset()
    line_of_therapy: str | None = None


@dataclass(frozen=True)
class Factor:
    """One scoring factor and whether it was satisfied."""

    name: str
    weight: float
    matched: bool


def _score(factors: Sequence[Factor]) -> float:
    """Weighted mean over the factors in play (M11 section 5.5).

    Dividing by the weights actually used, rather than by a fixed 1.0, is
    what keeps a richly-described candidate comparable with a bare one. With
    only the base factors present the divisor is 1.0 and this is the plain
    weighted sum it replaces.
    """
    total_weight = sum(f.weight for f in factors)
    if total_weight <= 0:
        return 0.0
    return sum(f.weight * float(f.matched) for f in factors) / total_weight


def _optional_factors(candidate: Candidate, context: DiscoveryContext) -> list[Factor]:
    """The factors that exist only when something supplied the underlying
    value. Each requires evidence on *both* sides — an asset with no stated
    line of therapy cannot match one, and neither can a candidate."""
    factors: list[Factor] = []

    if context.pathway_ids and candidate.pathway_ids:
        factors.append(Factor(
            "pathway", WEIGHT_PATHWAY,
            bool(context.pathway_ids & set(candidate.pathway_ids)),
        ))

    if context.market_codes and candidate.market_codes:
        factors.append(Factor(
            "market", WEIGHT_MARKET,
            bool(context.market_codes & set(candidate.market_codes)),
        ))

    if context.line_of_therapy and candidate.line_of_therapy:
        factors.append(Factor(
            "line of therapy", WEIGHT_LINE_OF_THERAPY,
            _normalise(candidate.line_of_therapy) == _normalise(context.line_of_therapy),
        ))

    return factors


def classify(candidate: Candidate, *, context: DiscoveryContext) -> Classified:
    """Bucket one candidate and score it.

    Pipeline takes precedence over direct and therapeutic: an unapproved
    drug is not part of the world-without today whatever its mechanism, but
    it is exactly what an asset launching in four years will meet. Those are
    different facts, so they get different buckets rather than one ranked
    list (M11 section 5.3).
    """
    is_marketed = candidate.max_clinical_stage in MARKETED_STAGES
    target_match = _normalise(candidate.target_symbol) == _normalise(context.target_symbol)

    # An empty indication set means the source told us nothing about
    # indication — treated as unknown-but-plausible rather than a mismatch,
    # since excluding on missing data would silently drop real competitors.
    candidate_terms = {_normalise(i) for i in candidate.indications}
    indication_match = (
        True if not candidate_terms or not context.indication_terms
        else bool(candidate_terms & {_normalise(t) for t in context.indication_terms})
    )

    mechanism_match = _mechanism_matches(context.mechanism, candidate)

    if not indication_match:
        klass = CompetitorClass.EXCLUDED
        why = "retrieved for this target but indicated for a different disease"
    elif not is_marketed:
        klass = CompetitorClass.PIPELINE
        why = (
            f"not yet marketed ({candidate.max_clinical_stage.value}); not part of the "
            "world-without today, but may reach market within the horizon"
        )
    elif target_match and mechanism_match:
        klass = CompetitorClass.DIRECT
        why = "same indication, same target and same mechanism"
    else:
        klass = CompetitorClass.THERAPEUTIC
        why = (
            "same indication, "
            + ("different mechanism" if target_match else "different target")
            + " — competes for the same patients"
        )

    factors = [
        Factor("indication", WEIGHT_INDICATION, indication_match),
        Factor("target", WEIGHT_TARGET, target_match),
        Factor("mechanism", WEIGHT_MECHANISM, mechanism_match),
        Factor("approval", WEIGHT_APPROVAL, is_marketed),
        Factor("seeded", WEIGHT_SEEDED, candidate.seeded_drug_id is not None),
        *_optional_factors(candidate, context),
    ]

    # A pathway match is worth stating explicitly and by id, because it is
    # the one claim in the rationale a reader would otherwise have to take
    # on trust — "shares Reactome R-HSA-420092" is checkable, "related
    # pathway" is not (M11 section 5.9).
    shared = context.pathway_ids & set(candidate.pathway_ids)
    if shared:
        why += f"; shares Reactome {', '.join(sorted(shared))}"

    if candidate.seeded_drug_id is not None:
        why += "; already priced in this system"
    else:
        why += "; no price or regimen seeded yet"

    return Classified(
        candidate=candidate,
        competitor_class=klass,
        relevance=round(_score(factors), 4),
        rationale=why,
        factors=tuple(factors),
    )


def deduplicate(candidates: list[Candidate]) -> list[Candidate]:
    """One row per molecule, keyed on the source id.

    Two sources describing the same drug is the normal case, not a
    conflict — the union of what they each knew is strictly better than
    either alone, so fields are filled in from whichever source has them
    and `sources` records both.
    """
    merged: dict[str, Candidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.source_id)
        if existing is None:
            merged[candidate.source_id] = candidate
            continue
        merged[candidate.source_id] = replace(
            existing,
            drug_type=existing.drug_type or candidate.drug_type,
            mechanism_of_action=(
                existing.mechanism_of_action or candidate.mechanism_of_action
            ),
            action_type=existing.action_type or candidate.action_type,
            indications=tuple(dict.fromkeys(existing.indications + candidate.indications)),
            seeded_drug_id=existing.seeded_drug_id or candidate.seeded_drug_id,
            sources=tuple(dict.fromkeys(existing.sources + candidate.sources)),
            pathway_ids=tuple(dict.fromkeys(existing.pathway_ids + candidate.pathway_ids)),
            market_codes=tuple(dict.fromkeys(existing.market_codes + candidate.market_codes)),
            line_of_therapy=existing.line_of_therapy or candidate.line_of_therapy,
        )
    return list(merged.values())


def rank(classified: list[Classified]) -> list[Classified]:
    """Most relevant first; ties broken by name so the order is stable
    across runs rather than dependent on retrieval order."""
    return sorted(classified, key=lambda c: (-c.relevance, c.candidate.name))
