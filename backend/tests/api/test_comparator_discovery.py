"""Comparator discovery — M11 section 10.

Classification and ranking are pure, so they are tested against fixtures
rather than a live API. That matters more here than elsewhere: the upstream
contents change as trials progress, so a test asserting "retatrutide is
Phase III" would start failing the day it is approved — which would be the
test breaking on good news, not a defect.

The one live-API test is marked `network` and skipped by default, so the
offline suite stays offline.
"""

from __future__ import annotations

import pytest

from biet_api.constants.comparator import (
    WEIGHT_APPROVAL,
    WEIGHT_INDICATION,
    WEIGHT_MECHANISM,
    WEIGHT_SEEDED,
    WEIGHT_TARGET,
    ClinicalStage,
    CompetitorClass,
)
from biet_api.services.comparator_classify import (
    Candidate,
    Classified,
    DiscoveryContext,
    classify,
    deduplicate,
    rank,
)

OBESITY = frozenset({"obesity"})


def _candidate(
    name: str = "TESTDRUG",
    *,
    stage: ClinicalStage = ClinicalStage.APPROVAL,
    target: str = "GLP1R",
    action: str | None = "AGONIST",
    indications: tuple[str, ...] = ("Obesity",),
    seeded: int | None = None,
    sources: tuple[str, ...] = ("open_targets",),
    pathways: tuple[str, ...] = (),
    markets: tuple[str, ...] = (),
    line: str | None = None,
) -> Candidate:
    # The mechanism text is derived from the action type rather than fixed.
    # A real antagonist's description says "antagonist"; hard-coding an
    # agonist string onto an ANTAGONIST candidate builds a molecule that
    # cannot exist, and a test built on one proves nothing about the code.
    moa = (
        f"Glucagon-like peptide 1 receptor {action.lower()}"
        if action else "Glucagon-like peptide 1 receptor modulator"
    )
    return Candidate(
        source_id=f"CHEMBL_{name}", name=name, target_symbol=target,
        max_clinical_stage=stage, action_type=action,
        mechanism_of_action=moa,
        indications=indications, seeded_drug_id=seeded, sources=sources,
        pathway_ids=pathways, market_codes=markets, line_of_therapy=line,
    )


def _classify(
    candidate: Candidate,
    mechanism: str | None = "agonist",
    **context: object,
) -> Classified:
    return classify(
        candidate,
        context=DiscoveryContext(
            target_symbol="GLP1R",
            indication_terms=OBESITY,
            mechanism=mechanism,
            **context,  # type: ignore[arg-type]
        ),
    )


# --------------------------------------------------------------------------- classification


def test_same_indication_target_and_mechanism_is_direct() -> None:
    assert _classify(_candidate()).competitor_class is CompetitorClass.DIRECT


def test_different_action_type_is_therapeutic_not_direct() -> None:
    """Same disease, same target, different mechanism — still competing for
    the same patients, so it belongs in the basket, just not as a direct."""
    result = _classify(_candidate(action="ANTAGONIST"))
    assert result.competitor_class is CompetitorClass.THERAPEUTIC


def test_different_target_is_therapeutic() -> None:
    result = _classify(_candidate(target="GIPR", action=None))
    assert result.competitor_class is CompetitorClass.THERAPEUTIC


def test_unapproved_is_pipeline_whatever_its_mechanism() -> None:
    """Pipeline outranks direct. An unapproved drug is not part of the
    world-without today however well it matches — that is a different fact
    and gets a different bucket (M11 section 5.3)."""
    for stage in (ClinicalStage.PHASE_3, ClinicalStage.PHASE_2, ClinicalStage.PHASE_1):
        result = _classify(_candidate(stage=stage))
        assert result.competitor_class is CompetitorClass.PIPELINE, stage


def test_unrecognised_stage_reads_as_pipeline_not_marketed() -> None:
    """The conservative direction: treating an unknown stage as marketed
    would put an unapproved drug into the world-without."""
    result = _classify(_candidate(stage=ClinicalStage.UNKNOWN))
    assert result.competitor_class is CompetitorClass.PIPELINE


def test_different_indication_is_excluded() -> None:
    result = _classify(_candidate(indications=("type 2 diabetes mellitus",)))
    assert result.competitor_class is CompetitorClass.EXCLUDED


def test_missing_indication_data_does_not_exclude() -> None:
    """A source that says nothing about indication has told us nothing —
    excluding on absent data would silently drop real competitors."""
    result = _classify(_candidate(indications=()))
    assert result.competitor_class is not CompetitorClass.EXCLUDED


# --------------------------------------------------------------------------- scoring


def test_relevance_weights_sum_to_one() -> None:
    """A set that quietly summed to 0.9 would still rank plausibly while
    compressing every score toward zero."""
    total = (
        WEIGHT_INDICATION + WEIGHT_TARGET + WEIGHT_MECHANISM
        + WEIGHT_APPROVAL + WEIGHT_SEEDED
    )
    assert total == pytest.approx(1.0)


def test_a_perfect_match_scores_one() -> None:
    assert _classify(_candidate(seeded=1)).relevance == pytest.approx(1.0)


def test_a_seeded_drug_outranks_an_otherwise_identical_unseeded_one() -> None:
    """Not a clinical judgement — a seeded drug is the only kind that can
    enter a calculation without further data entry, and surfacing it first
    is honest about what the tool can actually do next."""
    seeded = _classify(_candidate(name="A", seeded=7)).relevance
    unseeded = _classify(_candidate(name="A")).relevance
    assert seeded > unseeded
    assert seeded - unseeded == pytest.approx(WEIGHT_SEEDED)


def test_pipeline_scores_below_an_equivalent_approved_drug() -> None:
    approved = _classify(_candidate(name="A")).relevance
    pipeline = _classify(_candidate(name="A", stage=ClinicalStage.PHASE_3)).relevance
    assert pipeline == pytest.approx(approved - WEIGHT_APPROVAL)


def test_every_result_carries_a_rationale() -> None:
    for candidate in (
        _candidate(), _candidate(stage=ClinicalStage.PHASE_2),
        _candidate(indications=("asthma",)), _candidate(action="ANTAGONIST"),
    ):
        assert _classify(candidate).rationale.strip()


def test_rationale_says_whether_the_drug_is_priced() -> None:
    assert "no price" in _classify(_candidate()).rationale
    assert "already priced" in _classify(_candidate(seeded=3)).rationale


# --------------------------------------------------------------------------- optional factors


def test_optional_factors_are_absent_when_nothing_supplied_them() -> None:
    """The default case must be unchanged by the weighted-mean formulation:
    with only base factors in play the divisor is 1.0."""
    result = _classify(_candidate(seeded=1))
    assert {f.name for f in result.factors} == {
        "indication", "target", "mechanism", "approval", "seeded",
    }
    assert result.relevance == pytest.approx(1.0)


def test_an_unknown_optional_factor_is_not_scored_as_a_miss() -> None:
    """A candidate with no stated line of therapy must not be penalised for
    it. Counting absent evidence as a mismatch would rank a well-documented
    poor match above a barely-documented good one."""
    unknown = _classify(_candidate(name="A"), line_of_therapy="first")
    mismatch = _classify(
        _candidate(name="A", line="second"), line_of_therapy="first",
    )
    assert "line of therapy" not in {f.name for f in unknown.factors}
    assert "line of therapy" in {f.name for f in mismatch.factors}
    assert unknown.relevance > mismatch.relevance


def test_a_matched_optional_factor_leaves_a_perfect_score_perfect() -> None:
    """Re-normalisation, not addition: 1.0 stays 1.0 rather than exceeding it."""
    result = _classify(
        _candidate(seeded=1, markets=("USA",)), market_codes=frozenset({"USA"}),
    )
    assert result.relevance == pytest.approx(1.0)


def test_a_missed_optional_factor_lowers_the_score_below_one() -> None:
    result = _classify(
        _candidate(seeded=1, markets=("JPN",)), market_codes=frozenset({"USA"}),
    )
    assert result.relevance < 1.0


def test_a_shared_pathway_outranks_an_unrelated_drug_on_the_same_evidence() -> None:
    shared = _classify(
        _candidate(name="A", target="GIPR", action=None, pathways=("R-HSA-420092",)),
        pathway_ids=frozenset({"R-HSA-420092"}),
    )
    unrelated = _classify(
        _candidate(name="A", target="GIPR", action=None, pathways=("R-HSA-999999",)),
        pathway_ids=frozenset({"R-HSA-420092"}),
    )
    assert shared.relevance > unrelated.relevance


def test_a_shared_pathway_does_not_promote_a_drug_to_direct() -> None:
    """M11 section 5.4. Two drugs can share a signalling pathway and never
    compete for a patient, so pathway proximity scores but never reclassifies."""
    result = _classify(
        _candidate(target="GIPR", action=None, pathways=("R-HSA-420092",)),
        pathway_ids=frozenset({"R-HSA-420092"}),
    )
    assert result.competitor_class is CompetitorClass.THERAPEUTIC


def test_the_rationale_names_the_shared_pathway_by_id() -> None:
    """A rationale a reader can check. "shares Reactome R-HSA-420092" is
    verifiable against a public database; "related pathway" is not."""
    result = _classify(
        _candidate(target="GIPR", action=None, pathways=("R-HSA-420092",)),
        pathway_ids=frozenset({"R-HSA-420092"}),
    )
    assert "R-HSA-420092" in result.rationale


# --------------------------------------------------------------------------- needs_pricing


def test_unseeded_drug_needs_pricing() -> None:
    """Retrieval yields a molecule, never a price or a regimen — M5 needs
    both before it can compute anything (M11 section 5.7)."""
    assert _classify(_candidate()).needs_pricing is True
    assert _classify(_candidate(seeded=1)).needs_pricing is False


# --------------------------------------------------------------------------- dedupe & rank


def test_deduplication_unions_sources_rather_than_keeping_two_rows() -> None:
    merged = deduplicate([
        _candidate(name="X", sources=("open_targets",)),
        Candidate(
            source_id="CHEMBL_X", name="X", target_symbol="GLP1R",
            max_clinical_stage=ClinicalStage.APPROVAL,
            action_type=None, sources=("chembl",),
        ),
    ])
    assert len(merged) == 1
    assert set(merged[0].sources) == {"open_targets", "chembl"}


def test_deduplication_fills_gaps_from_the_second_source() -> None:
    merged = deduplicate([
        Candidate(
            source_id="C1", name="X", target_symbol="GLP1R",
            max_clinical_stage=ClinicalStage.APPROVAL, action_type=None,
        ),
        Candidate(
            source_id="C1", name="X", target_symbol="GLP1R",
            max_clinical_stage=ClinicalStage.APPROVAL, action_type="AGONIST",
            seeded_drug_id=4,
        ),
    ])
    assert merged[0].action_type == "AGONIST"
    assert merged[0].seeded_drug_id == 4


def test_deduplication_unions_pathway_ids() -> None:
    """A molecule reachable through two pathways is one row that knows about
    both, not two rows each knowing half."""
    merged = deduplicate([
        _candidate(name="X", pathways=("R-HSA-420092",)),
        _candidate(name="X", pathways=("R-HSA-381676",)),
    ])
    assert len(merged) == 1
    assert set(merged[0].pathway_ids) == {"R-HSA-420092", "R-HSA-381676"}


def test_ranking_is_most_relevant_first_and_stable_on_ties() -> None:
    items = [
        _classify(_candidate(name="Zeta")),
        _classify(_candidate(name="Alpha")),
        _classify(_candidate(name="Priced", seeded=1)),
    ]
    ordered = [c.candidate.name for c in rank(items)]
    assert ordered[0] == "Priced"          # highest relevance
    assert ordered[1:] == ["Alpha", "Zeta"]  # tie broken by name, not input order


# --------------------------------------------------------------------------- live API


@pytest.mark.network
def test_live_discovery_returns_a_plausible_glp1r_basket() -> None:
    """Deliberately loose. Asserting a specific drug is Phase III would make
    this test fail the day that drug is approved — the test breaking on good
    news. What must hold is structural: the target resolves, approved GLP-1
    agonists come back as direct, and something is still in the pipeline.
    """
    from biet_api.repositories.comparator import ComparatorRepository

    repo = ComparatorRepository()
    ensembl_id, symbol = repo.resolve_target("GLP1R")
    assert symbol == "GLP1R"
    assert ensembl_id.startswith("ENSG")

    candidates = repo.open_targets_candidates(ensembl_id)
    assert len(candidates) > 5

    names = {c.name.upper() for c in candidates}
    assert {"SEMAGLUTIDE", "LIRAGLUTIDE"} <= names, "core GLP-1 agonists should appear"
    assert any(
        c.max_clinical_stage not in {ClinicalStage.APPROVAL, ClinicalStage.PHASE_4}
        for c in candidates
    ), "this target should have unapproved candidates"


@pytest.mark.network
def test_live_pathway_expansion_reaches_other_targets_in_the_class() -> None:
    """The point of pathway expansion, stated as a test.

    Target-based retrieval on GLP1R cannot see a GIPR agonist, and for an
    obesity asset the GIPR and GCGR co-agonists are the competitors that
    matter most. Asserted structurally — that expansion reaches targets the
    original query could not — rather than by naming drugs whose stage will
    change.
    """
    from biet_api.repositories.comparator import ComparatorRepository

    repo = ComparatorRepository()
    ensembl_id, symbol = repo.resolve_target("GLP1R")

    accession = repo.uniprot_accession(ensembl_id)
    assert accession == "P43220", "GLP1R's reviewed Swiss-Prot accession"

    pathways = repo.reactome_pathways(accession)
    assert pathways, "GLP1R is annotated in Reactome"

    st_id = repo.most_specific_pathway(pathways)
    assert st_id is not None

    participants = repo.pathway_participants(st_id)
    assert "GIPR" in participants, "the incretin receptors share a pathway"

    resolved = repo.resolve_symbols([p for p in participants if p != symbol][:20])
    assert resolved, "participants resolve to Ensembl ids in one call"

    neighbours = repo.open_targets_candidates(*resolved.values(), pathway_ids=pathways)
    reached = {c.target_symbol for c in neighbours}
    assert reached - {symbol}, "expansion reached targets the original query could not"
    assert all(c.pathway_ids == pathways for c in neighbours)


@pytest.mark.network
def test_live_target_resolution_rejects_a_nonsense_symbol() -> None:
    """A typo and an uncontested target must not look the same
    (M11 section 5.1)."""
    from biet_api.repositories.comparator import (
        ComparatorRepository,
        UnknownTargetError,
    )

    with pytest.raises(UnknownTargetError):
        ComparatorRepository().resolve_target("NOTAGENE9Z")
