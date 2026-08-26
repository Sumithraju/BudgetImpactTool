"""Outcome and subgroup persistence — M16 and M18.

Every loader here returns the whole matrix in one query. A calculation touches
every therapy across every market across every selected subgroup, so a
per-therapy or per-market query is the N+1 the standards call a defect — and it
would be an N x M x K one here, not a plain N.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models.outcomes import (
    CountryHealthIndicator,
    DiseaseSubgroup,
    EventCost,
    ResponseProfile,
    SubgroupCountryRate,
    SubgroupEventRate,
    TreatmentEffect,
)
from .base import BaseRepository


class OutcomesRepository(BaseRepository[TreatmentEffect]):
    model = TreatmentEffect

    # ------------------------------------------------------------- subgroups

    def list_subgroups(self, indication_id: int) -> Sequence[DiseaseSubgroup]:
        """Every segment of one disease, in presentation order, with its
        baseline event rates and per-market rates already loaded."""
        return self._session.scalars(
            select(DiseaseSubgroup)
            .where(DiseaseSubgroup.indication_id == indication_id)
            .options(
                selectinload(DiseaseSubgroup.event_rates),
                selectinload(DiseaseSubgroup.country_rates),
            )
            .order_by(DiseaseSubgroup.sort_order, DiseaseSubgroup.subgroup_code)
        ).all()

    def default_population(self, indication_id: int) -> DiseaseSubgroup | None:
        """The row standing for the whole diseased population.

        The denominator every other subgroup's share is a share of, and the
        population a run models when no subgroup is chosen — so it carries the
        population-level event rates that an un-segmented run needs.
        """
        return next(
            (s for s in self.list_subgroups(indication_id) if s.is_default_population),
            None,
        )

    def country_rates(
        self, indication_id: int,
    ) -> dict[tuple[str, str], SubgroupCountryRate]:
        """`(subgroup_code, country_code) -> rate`, for the whole disease."""
        return {
            (subgroup.subgroup_code, str(rate.country_code)): rate
            for subgroup in self.list_subgroups(indication_id)
            for rate in subgroup.country_rates
        }

    def subgroups_by_code(
        self, indication_id: int, codes: Sequence[str],
    ) -> dict[str, DiseaseSubgroup]:
        subgroups = self.list_subgroups(indication_id)
        wanted = set(codes)
        return {
            s.subgroup_code: s for s in subgroups if not wanted or s.subgroup_code in wanted
        }

    def baseline_rates(self, subgroup_id: int) -> dict[str, SubgroupEventRate]:
        """`event_class -> rate` for one segment.

        An event class absent from the mapping has *no* baseline rate in this
        segment, which is a different statement from a rate of zero — the
        obesity-with-diabetes segment has no incident-diabetes row because
        those patients already have diabetes, not because the therapy prevents
        none. The caller keeps the two apart.
        """
        rows = self._session.scalars(
            select(SubgroupEventRate).where(
                SubgroupEventRate.subgroup_id == subgroup_id
            )
        ).all()
        return {row.event_class: row for row in rows}

    # ------------------------------------------------------------- effects

    def load_effects(
        self, drug_ids: Sequence[int],
    ) -> dict[int, list[TreatmentEffect]]:
        """`drug_id -> [effect, ...]`. An absent drug has no supplied effect,
        and the engine says so rather than modelling zero avoided events as a
        finding."""
        if not drug_ids:
            return {}
        rows = self._session.scalars(
            select(TreatmentEffect).where(TreatmentEffect.drug_id.in_(drug_ids))
        ).all()
        out: dict[int, list[TreatmentEffect]] = {}
        for row in rows:
            out.setdefault(row.drug_id, []).append(row)
        return out

    def load_profiles(self, drug_ids: Sequence[int]) -> dict[int, ResponseProfile]:
        """`drug_id -> profile`, taking the lowest threshold where a therapy
        has several — the `>= 5%` responder share is the one every trial in
        this class reports, so it is the only one comparable across them."""
        if not drug_ids:
            return {}
        rows = self._session.scalars(
            select(ResponseProfile)
            .where(ResponseProfile.drug_id.in_(drug_ids))
            .order_by(ResponseProfile.drug_id, ResponseProfile.threshold)
        ).all()
        out: dict[int, ResponseProfile] = {}
        for row in rows:
            out.setdefault(row.drug_id, row)
        return out

    # ------------------------------------------------------------- costs

    def load_event_costs(
        self, country_codes: Sequence[str],
    ) -> dict[tuple[str, str], EventCost]:
        """`(event_class, country_code) -> cost`, for every market at once."""
        if not country_codes:
            return {}
        rows = self._session.scalars(
            select(EventCost).where(EventCost.country_code.in_(country_codes))
        ).all()
        return {(r.event_class, str(r.country_code)): r for r in rows}

    def reference_event_costs(self, reference_market: str) -> dict[str, EventCost]:
        """The reference market's costs, which every unpriced market derives
        from. Loaded separately because the reference market is not always in
        the scenario's own market set."""
        rows = self._session.scalars(
            select(EventCost).where(EventCost.country_code == reference_market)
        ).all()
        return {r.event_class: r for r in rows}

    # ------------------------------------------------------------- indicators

    def health_indicators(
        self, country_codes: Sequence[str],
    ) -> dict[tuple[str, str], CountryHealthIndicator]:
        """`(country_code, indicator) -> row` — WHO's published burden figures.

        Kept apart from `country_economics` because they answer a different
        question and carry a different unit. `indicator_kind` on each row says
        whether the number is a prevalence, an incidence, a coverage or a
        categorical policy status, and nothing downstream should read one as
        another.
        """
        if not country_codes:
            return {}
        rows = self._session.scalars(
            select(CountryHealthIndicator).where(
                CountryHealthIndicator.country_code.in_(country_codes)
            )
        ).all()
        return {(str(r.country_code), r.indicator): r for r in rows}
