"""Evidence-gap ranking — M15, the impure half.

Joins M9's swings to the provenance already carried by every resolved value.
The ranking arithmetic is in `biet_engine.evidence_gap`; this file's job is
only to find the provenance for each swept path.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from biet_engine.evidence_gap import rank_evidence_gaps
from biet_engine.models import CountryInput, EngineInput, EvidenceGapReport, Provenance
from biet_engine.sensitivity import run_owsa

from ..models.scenario import Scenario
from .engine_input import EngineInputBuilder

log = logging.getLogger("biet.evidence_gap")


class EvidenceGapService:
    def __init__(self, session: Session) -> None:
        self._builder = EngineInputBuilder(session)

    def rank(self, scenario: Scenario) -> tuple[EvidenceGapReport, str]:
        """Rank this scenario's parameters by what is worth finding out.

        Runs a one-way sensitivity if the caller has not: the swings are the
        input, and computing them here is cheaper than making every caller
        remember to.
        """
        engine_input, _ = self._builder.build(scenario)
        owsa = run_owsa(engine_input)
        report = rank_evidence_gaps(
            owsa.entries,
            _provenance_map(engine_input),
            currency=engine_input.reporting_currency,
        )
        return report, engine_input.reporting_currency


def _provenance_map(engine_input: EngineInput) -> dict[str, Provenance]:
    """`parameter_path -> provenance`, for the paths M9 actually sweeps.

    Read from the first market, which is the one `default_params` builds its
    sweep from. A parameter resolved from different sources in different
    markets therefore reports the first market's tier — a real limitation,
    and the honest alternative (a tier per market per parameter) would make
    the ranking a matrix rather than a list and answer a question nobody
    asked.
    """
    if not engine_input.countries:
        return {}

    country: CountryInput = engine_input.countries[0]
    mapping: dict[str, Provenance] = {
        "epidemiology.prevalence": country.prevalence.provenance,
        "funnel.diagnosis_rate": country.funnel.diagnosis_rate.provenance,
        "funnel.treatment_rate": country.funnel.treatment_rate.provenance,
        "funnel.access_rate": country.funnel.access_rate.provenance,
    }
    if country.adult_share is not None:
        mapping["countries.adult_share"] = country.adult_share.provenance
    return mapping
