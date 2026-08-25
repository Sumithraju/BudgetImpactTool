"""Comparator discovery orchestration — M11.

Retrieval, seeded matching, classification and ranking, in that order.
Everything interesting is delegated: retrieval to the repository,
classification to the pure module. This file's job is only to sequence them
and to decide what a partial failure means.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants.comparator import PATHWAY_EXPANSION_MAX_TARGETS, CompetitorClass
from ..exceptions import UpstreamUnavailableError, ValidationError
from ..models.reference import Drug, Indication
from ..repositories.comparator import ComparatorRepository, UnknownTargetError
from .comparator_classify import (
    Candidate,
    Classified,
    DiscoveryContext,
    classify,
    deduplicate,
    rank,
)

log = logging.getLogger("biet.comparator")


class ComparatorService:
    def __init__(self, session: Session, repo: ComparatorRepository | None = None) -> None:
        self._session = session
        self._repo = repo or ComparatorRepository()

    def discover(
        self,
        target: str,
        indication_id: int,
        *,
        mechanism: str | None = None,
        include_pathway: bool = False,
    ) -> dict[str, object]:
        indication = self._session.get(Indication, indication_id)
        if indication is None:
            raise ValidationError(
                f"no indication {indication_id}", indication_id=indication_id,
            )

        try:
            ensembl_id, symbol = self._repo.resolve_target(target)
        except UnknownTargetError as exc:
            raise ValidationError(str(exc), target=target) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"could not reach Open Targets to resolve {target!r}", target=target,
            ) from exc

        warnings: list[dict[str, str]] = []

        pathway_ids: tuple[str, ...] = ()
        if include_pathway:
            pathway_ids, pathway_warning = self._pathways(ensembl_id, symbol)
            if pathway_warning is not None:
                warnings.append(pathway_warning)

        try:
            candidates = self._repo.open_targets_candidates(
                ensembl_id, pathway_ids=pathway_ids,
            )
        except httpx.HTTPError as exc:
            # An empty basket would read as "this target has no competitors",
            # which is a far worse answer than saying the lookup failed.
            raise UpstreamUnavailableError(
                f"could not retrieve candidates for {symbol}", target=symbol,
            ) from exc

        if pathway_ids:
            neighbours, neighbour_warning = self._pathway_neighbours(
                pathway_ids, exclude=symbol,
            )
            candidates.extend(neighbours)
            if neighbour_warning is not None:
                warnings.append(neighbour_warning)

        candidates = self._link_seeded(deduplicate(candidates))
        context = DiscoveryContext(
            target_symbol=symbol,
            indication_terms=self._indication_terms(indication),
            mechanism=mechanism,
            pathway_ids=frozenset(pathway_ids),
        )

        classified = rank([classify(c, context=context) for c in candidates])

        if not classified:
            warnings.append({
                "code": "NO_COMPARATORS_FOUND",
                "message": (
                    f"{symbol} resolved, but no drug or clinical candidate is "
                    "registered against it. That is a real answer, not an error."
                ),
            })

        buckets: dict[str, list[dict[str, object]]] = {
            k: [] for k in ("direct", "therapeutic", "pipeline", "excluded")
        }
        for item in classified:
            buckets[item.competitor_class.value].append(_serialise(item))

        unpriced = sum(
            1 for item in classified
            if item.needs_pricing and item.competitor_class is not CompetitorClass.EXCLUDED
        )
        if unpriced:
            warnings.append({
                "code": "COMPARATORS_NEED_PRICING",
                "message": (
                    f"{unpriced} discovered therapies have no seeded price or regimen. "
                    "Discovery yields a molecule, not a cost — these cannot enter a "
                    "calculation until both are supplied (M11 section 5.7)."
                ),
            })

        return {
            "target_symbol": symbol,
            "target_id": ensembl_id,
            "indication_id": indication_id,
            "indication_name": indication.indication_name,
            "mechanism": mechanism,
            "pathway_ids": list(pathway_ids),
            "direct": buckets["direct"],
            "therapeutic": buckets["therapeutic"],
            "pipeline": buckets["pipeline"],
            "excluded": buckets["excluded"],
            "warnings": warnings,
        }

    @classmethod
    def resolve(cls, symbol: str, repo: ComparatorRepository | None = None) -> dict[str, object]:
        """Resolve a symbol to its identifiers and pathways, nothing more.

        A classmethod because it touches no database: target resolution is
        entirely a question for the public sources, and requiring a session
        for it would be a dependency that exists only to satisfy a
        convention.
        """
        repo = repo or ComparatorRepository()
        try:
            ensembl_id, approved = repo.resolve_target(symbol)
        except UnknownTargetError as exc:
            raise ValidationError(str(exc), target=symbol) from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"could not reach Open Targets to resolve {symbol!r}", target=symbol,
            ) from exc

        accession: str | None = None
        pathways: tuple[str, ...] = ()
        try:
            accession = repo.uniprot_accession(ensembl_id)
            if accession is not None:
                pathways = repo.reactome_pathways(accession)
        except httpx.HTTPError:
            # Resolution succeeded; only the enrichment failed. Returning the
            # identifiers without pathways is the useful half of the answer.
            log.warning("pathway_lookup_failed", extra={"target": approved})

        return {
            "symbol": approved,
            "target_id": ensembl_id,
            "uniprot_accession": accession,
            "pathway_ids": list(pathways),
        }

    # ----------------------------------------------------------------- internals

    def _pathways(
        self, ensembl_id: str, symbol: str,
    ) -> tuple[tuple[str, ...], dict[str, str] | None]:
        """The target's Reactome pathways, or nothing and a warning.

        Pathway lookup is two extra round trips against a third API, and
        M11 section 5.9 requires its failure to degrade rather than fail the
        request: a basket without pathway expansion is a smaller true answer,
        while a 503 is no answer at all.
        """
        try:
            accession = self._repo.uniprot_accession(ensembl_id)
            if accession is None:
                return (), {
                    "code": "PARTIAL_DISCOVERY",
                    "message": (
                        f"{symbol} has no reviewed UniProt accession, so Reactome "
                        "could not be queried. Same-target candidates are unaffected; "
                        "candidates acting on other targets in the same pathway are "
                        "not included."
                    ),
                }
            return self._repo.reactome_pathways(accession), None
        except httpx.HTTPError:
            log.warning("reactome_unavailable", extra={"target": symbol})
            return (), {
                "code": "PARTIAL_DISCOVERY",
                "message": (
                    "Reactome was unreachable, so pathway expansion was skipped. "
                    "The basket contains same-target candidates only."
                ),
            }

    def _pathway_neighbours(
        self, pathway_ids: tuple[str, ...], *, exclude: str,
    ) -> tuple[list[Candidate], dict[str, str] | None]:
        """Candidates acting on *other* targets in the same pathway.

        This is the only route by which a competitor with a different
        mechanism is found at all — target-based retrieval cannot see a GIPR
        agonist when the query was GLP1R, and for an obesity asset that is
        precisely the competitor that matters.
        """
        try:
            st_id = self._repo.most_specific_pathway(pathway_ids)
            if st_id is None:
                return [], None

            symbols = [
                s for s in self._repo.pathway_participants(st_id)
                if s.upper() != exclude.upper()
            ]
            resolved = self._repo.resolve_symbols(symbols[:PATHWAY_EXPANSION_MAX_TARGETS])
            if not resolved:
                return [], None

            return self._repo.open_targets_candidates(
                *resolved.values(), pathway_ids=pathway_ids,
            ), None
        except httpx.HTTPError:
            log.warning("pathway_expansion_failed", extra={"pathways": pathway_ids})
            return [], {
                "code": "PARTIAL_DISCOVERY",
                "message": (
                    "Pathway expansion failed part-way. The basket contains "
                    "same-target candidates and is complete for those."
                ),
            }

    def _link_seeded(self, candidates: list[Candidate]) -> list[Candidate]:
        """Match a discovered molecule to a row already in `drugs`.

        Matched on generic name, case-insensitively — the only key the two
        sides share, since Open Targets has no notion of this system's
        `drug_id`. A match is what makes a comparator immediately usable
        rather than needing a price seeded first.
        """
        from dataclasses import replace

        seeded = self._session.scalars(select(Drug)).all()
        by_name: dict[str, int] = {}
        for drug in seeded:
            for name in (drug.generic_name, drug.drug_name):
                if name:
                    by_name.setdefault(name.strip().lower(), drug.drug_id)

        linked = []
        for candidate in candidates:
            key = candidate.name.strip().lower()
            drug_id = by_name.get(key)
            if drug_id is None:
                # Seeded names carry a dose ("semaglutide 2.4 mg"), so a
                # prefix match catches what an exact one misses.
                drug_id = next(
                    (v for k, v in by_name.items() if k.startswith(key + " ")), None,
                )
            linked.append(replace(candidate, seeded_drug_id=drug_id))
        return linked

    @staticmethod
    def _indication_terms(indication: Indication) -> frozenset[str]:
        """Terms an Open Targets disease name is matched against.

        Open Targets uses EFO disease labels ("Obesity", "type 2 diabetes
        mellitus") which do not equal this system's indication names, so the
        seeded name and therapy area are both offered as match terms.
        """
        terms = {indication.indication_name, indication.therapy_area.replace("_", " ")}
        return frozenset(t.strip().lower() for t in terms if t)


def _serialise(item: Classified) -> dict[str, object]:
    c = item.candidate
    return {
        "source_id": c.source_id,
        "name": c.name,
        "drug_type": c.drug_type,
        "max_clinical_stage": c.max_clinical_stage.value,
        "mechanism_of_action": c.mechanism_of_action,
        "action_type": c.action_type,
        "target_symbol": c.target_symbol,
        "indications": list(c.indications[:6]),
        "competitor_class": item.competitor_class.value,
        "relevance": item.relevance,
        "rationale": item.rationale,
        "seeded_drug_id": c.seeded_drug_id,
        "needs_pricing": item.needs_pricing,
        "sources": list(c.sources),
        "pathway_ids": list(c.pathway_ids),
        # The per-factor breakdown, so the interface can show a tick per
        # criterion rather than only a score the reader has to trust.
        "factors": [
            {"name": f.name, "weight": f.weight, "matched": f.matched}
            for f in item.factors
        ],
    }
