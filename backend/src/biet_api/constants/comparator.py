"""Comparator discovery constants — M11.

Weights and endpoints in one place. The relevance weights must sum to 1.0;
a test asserts it, because a set that quietly sums to 0.9 would rank
plausibly while compressing every score.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class CompetitorClass(StrEnum):
    DIRECT = "direct"            # same indication + target + mechanism
    THERAPEUTIC = "therapeutic"  # same indication, different mechanism
    PIPELINE = "pipeline"        # not yet marketed
    EXCLUDED = "excluded"        # retrieved but not a plausible comparator


class LineOfTherapy(StrEnum):
    """Where in the treatment sequence a therapy sits.

    Curated in M12, never retrieved: no public target database records it,
    and it is one of the two things that decide whether a mechanistically
    similar drug is actually a comparator (M11 section 5.4).
    """

    FIRST = "first"
    SECOND = "second"
    THIRD_PLUS = "third_plus"
    ANY = "any"


class ClinicalStage(StrEnum):
    APPROVAL = "APPROVAL"
    PHASE_4 = "PHASE_4"
    PHASE_3 = "PHASE_3"
    PHASE_2 = "PHASE_2"
    PHASE_1 = "PHASE_1"
    EARLY_PHASE_1 = "EARLY_PHASE_1"
    PRECLINICAL = "PRECLINICAL"
    UNKNOWN = "UNKNOWN"


#: Stages that mean the drug is on the market. Everything else is pipeline.
MARKETED_STAGES: Final[frozenset[ClinicalStage]] = frozenset(
    {ClinicalStage.APPROVAL, ClinicalStage.PHASE_4}
)

#: Stages late enough to plausibly reach market before a 3-5 year horizon ends.
LATE_STAGE: Final[frozenset[ClinicalStage]] = frozenset(
    {ClinicalStage.PHASE_3, ClinicalStage.PHASE_2}
)

#: Section 5.5, base factors. Always in play; must sum to 1.0 so that a
#: discovery-only score is unchanged by the weighted-mean formulation.
WEIGHT_INDICATION: Final[float] = 0.40
WEIGHT_TARGET: Final[float] = 0.25
WEIGHT_MECHANISM: Final[float] = 0.15
WEIGHT_APPROVAL: Final[float] = 0.15
WEIGHT_SEEDED: Final[float] = 0.05

#: Section 5.5, optional factors. In play only when the underlying value
#: exists — pathway membership requires the opt-in Reactome step, and market
#: and line of therapy are curated in M12. Excluded rather than defaulted:
#: scoring a candidate as line-matched when nothing said so produces a
#: confident number out of an absence of evidence, which is worse than not
#: scoring it. The score is re-normalised over whichever factors are in play,
#: so a registered candidate and a bare one stay comparable.
WEIGHT_PATHWAY: Final[float] = 0.10
WEIGHT_MARKET: Final[float] = 0.10
WEIGHT_LINE_OF_THERAPY: Final[float] = 0.10

#: Verified against the live endpoints 2026-08-24. Open Targets renamed
#: `knownDrugs` to `drugAndClinicalCandidates` and dropped `Drug.isApproved`
#: and `maximumClinicalTrialPhase`; approval is now read from
#: `maxClinicalStage`. Re-verify before assuming a query still works.
OPEN_TARGETS_URL: Final[str] = "https://api.platform.opentargets.org/api/v4/graphql"
CHEMBL_BASE_URL: Final[str] = "https://www.ebi.ac.uk/chembl/api/data"

#: Reactome maps a UniProt accession straight to the pathways containing it.
#: `pathways/low/entity/{stable_id}` is the documented route but takes a
#: Reactome PhysicalEntity id, and a UniProt accession is a
#: ReferenceGeneProduct — it 404s. The mapping endpoint takes the accession
#: directly. Verified 2026-08-25: P43220 (GLP1R) returns R-HSA-420092,
#: R-HSA-381676 and R-HSA-418555.
REACTOME_MAPPING_URL: Final[str] = (
    "https://reactome.org/ContentService/data/mapping/UniProt/{accession}/pathways"
)
HUMAN_TAXON_ID: Final[str] = "9606"

#: Open Targets returns several protein identifiers per target; only the
#: reviewed Swiss-Prot one is a stable key Reactome will resolve.
UNIPROT_REVIEWED_SOURCE: Final[str] = "uniprot_swissprot"

REACTOME_PARTICIPANTS_URL: Final[str] = (
    "https://reactome.org/ContentService/data/participants/{st_id}/referenceEntities"
)

#: Pathway expansion is bounded on both sides. A target sits in pathways of
#: wildly different specificity — GLP1R is in "Glucagon-type ligand
#: receptors" (35 participants, every one of them a plausible metabolic
#: competitor) and in "G alpha (s) signalling events" (hundreds, most of them
#: irrelevant). The most specific pathway is the one with fewest
#: participants, so participants are counted for at most this many pathways
#: and the smallest wins.
PATHWAY_PROBE_LIMIT: Final[int] = 5

#: And only this many of its participants are expanded into, so one query
#: cannot turn into a hundred.
PATHWAY_EXPANSION_MAX_TARGETS: Final[int] = 20

DISCOVERY_TIMEOUT_S: Final[float] = 25.0

#: Every network call in discovery is an idempotent read, so a transient
#: failure is worth retrying rather than reporting. The common failure here
#: is not the service being down — it is a single connection reset or a
#: brief 5xx on the way to a healthy endpoint, which is precisely what a
#: user is doing by hand when they follow "try again in a moment".
#: Two retries cost at most ~1.5 s on the way to an error that was going to
#: be shown anyway, and well under the request timeout.
DISCOVERY_RETRY_ATTEMPTS: Final[int] = 3
DISCOVERY_RETRY_BACKOFF_S: Final[float] = 0.5

#: Status codes worth a second attempt. A 4xx other than 429 is a statement
#: about the request itself, which will not read differently on repeat.
DISCOVERY_RETRY_STATUSES: Final[frozenset[int]] = frozenset(
    {408, 429, 500, 502, 503, 504},
)

#: Connections are pooled and reused across requests. Before this, every
#: discovery built its own client and paid a fresh TLS handshake to a remote
#: public API — the single most likely place for the transient connect error
#: that surfaced as "we could not reach the drug database".
DISCOVERY_MAX_CONNECTIONS: Final[int] = 10
DISCOVERY_KEEPALIVE_EXPIRY_S: Final[float] = 30.0
