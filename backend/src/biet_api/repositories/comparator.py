"""Retrieval from public drug-discovery APIs — M11 section 5.2.

The only module in the API package that reaches the network. Everything it
returns is a `Candidate`; classification and ranking happen elsewhere,
against fixtures, so the interesting logic is not hostage to a live
endpoint whose contents change as trials progress.

**Schema note, and why it is here rather than in a commit message.**
Open Targets renamed `knownDrugs` to `drugAndClinicalCandidates` and removed
`Drug.isApproved` and `Drug.maximumClinicalTrialPhase`; approval is now read
from `maxClinicalStage == APPROVAL`. Most documentation and most training
data still describe the old shape. The query below was verified against the
live endpoint on **2026-08-24**. A renamed *field* fails loudly, which is
the good case; a renamed *enum value* would not, so re-verify rather than
assume.

**Why Open Targets alone.** M11 section 5.2 planned ChEMBL as a second
source for mechanism and action type. Measured against the live endpoints,
ChEMBL took 27 seconds for a single-molecule lookup and rejected the batch
filter outright, while Open Targets returns mechanism, action type and
indications in the same sub-second call that returns the candidates. Two
sources are not better than one when the second is slower than the timeout
and supplies nothing the first does not. ChEMBL remains a reasonable
fallback if Open Targets ever drops `mechanismsOfAction`.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from http import HTTPStatus
from typing import Any

import httpx

from ..constants.comparator import (
    DISCOVERY_KEEPALIVE_EXPIRY_S,
    DISCOVERY_MAX_CONNECTIONS,
    DISCOVERY_RETRY_ATTEMPTS,
    DISCOVERY_RETRY_BACKOFF_S,
    DISCOVERY_RETRY_STATUSES,
    DISCOVERY_TIMEOUT_S,
    HUMAN_TAXON_ID,
    OPEN_TARGETS_URL,
    PATHWAY_EXPANSION_MAX_TARGETS,
    PATHWAY_PROBE_LIMIT,
    REACTOME_MAPPING_URL,
    REACTOME_PARTICIPANTS_URL,
    UNIPROT_REVIEWED_SOURCE,
    ClinicalStage,
)
from ..services.comparator_classify import Candidate

log = logging.getLogger("biet.comparator")

_TARGET_SEARCH = """
query($q: String!) {
  search(queryString: $q, entityNames: ["target"], page: {index: 0, size: 5}) {
    hits { id name entity }
  }
}
"""

_TARGET_PROTEINS = """
query($id: String!) {
  target(ensemblId: $id) {
    approvedSymbol
    proteinIds { id source }
  }
}
"""

_MAP_IDS = """
query($terms: [String!]!) {
  mapIds(queryTerms: $terms, entityNames: ["target"]) {
    mappings { term hits { id name entity } }
  }
}
"""

_CANDIDATES = """
query($ids: [String!]!) {
  targets(ensemblIds: $ids) {
    approvedSymbol
    drugAndClinicalCandidates {
      count
      rows {
        maxClinicalStage
        drug {
          id
          name
          drugType
          mechanismsOfAction { rows { actionType mechanismOfAction } }
          indications { rows { disease { name } } }
        }
      }
    }
  }
}
"""


class UnknownTargetError(Exception):
    """The symbol resolved to nothing. Raised rather than returning an empty
    basket, because a typo and a genuinely uncontested target must not look
    the same (M11 section 5.1)."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"no target matches {symbol!r}")


class SchemaRejectedError(Exception):
    """The endpoint answered, and refused the query.

    Kept distinct from a transport failure because the remedy is distinct.
    A rejected query means the source's schema moved and this module has to
    be updated; it will not come right on its own, so it is neither retried
    nor reported to the reader as a temporary outage.
    """


_client_lock = threading.Lock()
_shared: httpx.Client | None = None


def _shared_client() -> httpx.Client:
    """One pooled client for the process.

    Previously every request built its own client, so every discovery paid a
    fresh TLS handshake to a remote public API — slower, and the single most
    likely place for the transient connect error that reached the reader as
    "we could not reach the drug database". A pooled connection is reused and
    does not re-run that handshake. `httpx.Client` is thread-safe for sending
    requests, which is what FastAPI's threadpool asks of it.
    """
    global _shared
    if _shared is None:
        with _client_lock:
            if _shared is None:
                _shared = httpx.Client(
                    timeout=DISCOVERY_TIMEOUT_S,
                    headers={"User-Agent": "BIET/1.0 (budget impact estimation)"},
                    limits=httpx.Limits(
                        max_connections=DISCOVERY_MAX_CONNECTIONS,
                        max_keepalive_connections=DISCOVERY_MAX_CONNECTIONS,
                        keepalive_expiry=DISCOVERY_KEEPALIVE_EXPIRY_S,
                    ),
                    # No explicit `transport=`, deliberately. httpx only reads
                    # HTTP_PROXY/HTTPS_PROXY/NO_PROXY from the environment when
                    # the transport is left to it — `allow_env_proxies` is
                    # `trust_env and transport is None`. Passing a transport to
                    # get its connect-level retries would silently strip proxy
                    # support from every deployment behind one, which is
                    # exactly where "we could not reach the drug database" is
                    # most likely. `_send` already retries connect failures.
                )
    return _shared


class ComparatorRepository:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or _shared_client()

    # ----------------------------------------------------------------- targets

    def resolve_target(self, symbol: str) -> tuple[str, str]:
        """`(ensembl_id, approved_symbol)` for a gene symbol or Ensembl id."""
        if symbol.upper().startswith("ENSG"):
            return symbol.upper(), symbol.upper()

        body = self._graphql(_TARGET_SEARCH, {"q": symbol})
        hits = ((body.get("search") or {}).get("hits") or [])
        for hit in hits:
            if hit.get("entity") == "target":
                return str(hit["id"]), str(hit.get("name") or symbol)
        raise UnknownTargetError(symbol)

    def uniprot_accession(self, ensembl_id: str) -> str | None:
        """The reviewed Swiss-Prot accession for a target, or None.

        Open Targets returns several protein identifiers per target —
        Ensembl protein ids, obsolete UniProt entries, and the reviewed
        Swiss-Prot one. Only the last is a stable key Reactome resolves, so
        the source is filtered on rather than the first id being taken.
        """
        body = self._graphql(_TARGET_PROTEINS, {"id": ensembl_id})
        proteins = (body.get("target") or {}).get("proteinIds") or []
        for protein in proteins:
            if protein.get("source") == UNIPROT_REVIEWED_SOURCE and protein.get("id"):
                return str(protein["id"])
        return None

    # ----------------------------------------------------------------- pathways

    def reactome_pathways(self, accession: str) -> tuple[str, ...]:
        """Reactome stable ids of the pathways containing a protein.

        A target with no pathway annotation returns 404 with a JSON body
        rather than an empty list, which is Reactome's way of saying "no
        result" and not an error worth propagating — a drug target absent
        from Reactome is an ordinary state, and M11 section 5.9 requires
        pathway failure to degrade rather than fail the request.
        """
        response = self._send(
            "reactome_mapping",
            lambda: self._client.get(
                REACTOME_MAPPING_URL.format(accession=accession),
                params={"species": HUMAN_TAXON_ID},
                headers={"Accept": "application/json"},
            ),
        )
        if response.status_code == HTTPStatus.NOT_FOUND:
            return ()
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            return ()
        return tuple(
            str(row["stId"]) for row in rows
            if isinstance(row, dict) and row.get("stId")
        )

    def most_specific_pathway(self, pathway_ids: Sequence[str]) -> str | None:
        """The pathway with the fewest participants, or None.

        A target sits in pathways of wildly different specificity. GLP1R is
        in "Glucagon-type ligand receptors", whose 35 participants are almost
        all plausible metabolic competitors, and in "G alpha (s) signalling
        events", whose hundreds are mostly irrelevant. Participant count is a
        crude proxy for specificity, and it is the only one available without
        walking the Reactome hierarchy — expanding into the broad pathway
        would bury the useful candidates under signalling machinery.
        """
        # Sequential deliberately. These are independent round trips and the
        # obvious move is to run them concurrently, but measured against the
        # live service it makes no difference — median 1.42 s sequential
        # against 1.72 s over three probes, inside the run-to-run noise.
        # Reactome does not reward the extra machinery, so there is none.
        counts = [
            (len(self.pathway_participants(st_id)), st_id)
            for st_id in list(pathway_ids)[:PATHWAY_PROBE_LIMIT]
        ]
        populated = [pair for pair in counts if pair[0]]
        return min(populated)[1] if populated else None

    def pathway_participants(self, st_id: str) -> tuple[str, ...]:
        """Gene symbols of the proteins participating in a pathway."""
        response = self._send(
            "reactome_participants",
            lambda: self._client.get(
                REACTOME_PARTICIPANTS_URL.format(st_id=st_id),
                headers={"Accept": "application/json"},
            ),
        )
        if response.status_code == HTTPStatus.NOT_FOUND:
            return ()
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            return ()

        symbols: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            names = row.get("geneName") or []
            if names:
                symbols.append(str(names[0]))
        return tuple(dict.fromkeys(symbols))

    # ----------------------------------------------------------------- candidates

    def resolve_symbols(self, symbols: Sequence[str]) -> dict[str, str]:
        """`{symbol: ensembl_id}` for many symbols in one call.

        One request rather than one per symbol: pathway expansion resolves
        twenty at a time, and twenty sequential round trips would cost more
        than the rest of discovery put together.
        """
        if not symbols:
            return {}
        body = self._graphql(_MAP_IDS, {"terms": list(symbols)})
        mappings = ((body.get("mapIds") or {}).get("mappings") or [])

        resolved: dict[str, str] = {}
        for mapping in mappings:
            term = str(mapping.get("term") or "")
            for hit in mapping.get("hits") or []:
                if hit.get("entity") == "target" and hit.get("id"):
                    resolved[term] = str(hit["id"])
                    break
        return resolved

    def open_targets_candidates(
        self, *ensembl_ids: str, pathway_ids: tuple[str, ...] = (),
    ) -> list[Candidate]:
        """Drug and clinical candidates acting on one or more targets.

        Batched deliberately: `targets(ensemblIds:)` returns four targets in
        the same sub-second call that returns one, which is what makes
        pathway expansion affordable. `pathway_ids` is stamped onto every
        candidate returned, since a candidate is only reachable through this
        call because its target sits in those pathways.
        """
        ids = [i for i in dict.fromkeys(ensembl_ids) if i]
        if not ids:
            return []

        body = self._graphql(_CANDIDATES, {"ids": ids[:PATHWAY_EXPANSION_MAX_TARGETS]})
        out: list[Candidate] = []
        for target in body.get("targets") or []:
            out.extend(self._candidates_of(target, pathway_ids))
        return out

    @staticmethod
    def _candidates_of(
        target: dict[str, Any], pathway_ids: tuple[str, ...],
    ) -> list[Candidate]:
        symbol = str(target.get("approvedSymbol") or "")
        rows = ((target.get("drugAndClinicalCandidates") or {}).get("rows") or [])

        out: list[Candidate] = []
        for row in rows:
            drug = row.get("drug") or {}
            if not drug.get("id"):
                continue
            indications = tuple(
                str((i.get("disease") or {}).get("name"))
                for i in ((drug.get("indications") or {}).get("rows") or [])
                if (i.get("disease") or {}).get("name")
            )
            # A molecule can carry several mechanisms; the first is the one
            # Open Targets ranks as primary, which is the one that decides
            # whether this is a direct competitor.
            moa_rows = (drug.get("mechanismsOfAction") or {}).get("rows") or []
            moa = moa_rows[0] if moa_rows else {}

            out.append(Candidate(
                source_id=str(drug["id"]),
                name=str(drug.get("name") or drug["id"]),
                target_symbol=symbol,
                max_clinical_stage=_stage(row.get("maxClinicalStage")),
                drug_type=drug.get("drugType"),
                mechanism_of_action=moa.get("mechanismOfAction"),
                action_type=moa.get("actionType"),
                indications=indications,
                pathway_ids=pathway_ids,
                sources=("open_targets",),
            ))
        return out

    # ----------------------------------------------------------------- internals

    def _send(
        self, endpoint: str, build: Callable[[], httpx.Response],
    ) -> httpx.Response:
        """Perform one idempotent read, retrying only what a retry can fix.

        Every call in this module is a read, so repeating one is safe. What
        is worth repeating is narrow: a transport error, or one of the
        server-side statuses in `DISCOVERY_RETRY_STATUSES`. Any other status
        is a statement about the request itself and is handed back at once
        rather than after three identical round trips — a 404 from Reactome
        means "not annotated", and its caller wants that answer immediately.

        This is the fix for the reader being told to "try again in a moment".
        A single connection reset is the ordinary way these calls fail, and
        retrying it here is the same act the reader was being asked to
        perform by hand — only faster, and without the error.
        """
        for attempt in range(1, DISCOVERY_RETRY_ATTEMPTS + 1):
            final = attempt == DISCOVERY_RETRY_ATTEMPTS
            try:
                response = build()
            except httpx.TransportError as exc:
                if final:
                    raise
                reason = type(exc).__name__
            else:
                if response.status_code not in DISCOVERY_RETRY_STATUSES:
                    return response
                if final:
                    response.raise_for_status()
                reason = str(response.status_code)

            delay = DISCOVERY_RETRY_BACKOFF_S * attempt
            log.warning(
                "discovery_retry endpoint=%s reason=%s attempt=%d/%d sleep=%.1fs",
                endpoint, reason, attempt, DISCOVERY_RETRY_ATTEMPTS, delay,
            )
            time.sleep(delay)

        # Unreachable: the final attempt either returns or raises.
        raise RuntimeError(f"{endpoint}: retry loop exhausted")

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        body = {"query": query, "variables": variables}
        response = self._send(
            "open_targets", lambda: self._client.post(OPEN_TARGETS_URL, json=body),
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            # A GraphQL error is a 200 with an `errors` array — raising here
            # is what stops a schema change reading as "no competitors".
            #
            # Deliberately outside the retry above, and its own type. The
            # query was refused, not lost: three more identical round trips
            # would be refused identically, and calling that a temporary
            # outage points whoever reads it away from the actual cause.
            raise SchemaRejectedError(
                f"Open Targets rejected the query: {payload['errors'][0].get('message')}"
            )
        return dict(payload.get("data") or {})


def _stage(raw: object) -> ClinicalStage:
    """A stage this module does not recognise reads as UNKNOWN, which
    classifies as pipeline — the conservative direction, since treating an
    unrecognised stage as marketed would put an unapproved drug into the
    world-without."""
    try:
        return ClinicalStage(str(raw))
    except ValueError:
        return ClinicalStage.UNKNOWN
