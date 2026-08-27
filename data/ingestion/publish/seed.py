"""Curated seed data — M0 section 5.6, source 4.

Ten CSVs under `data/seed/`. Seven publish directly to a reference table; three
(`ndc_regimen_map`, `diabetes_cagr`, `age_bands`) are auxiliary — consumed by the
live-source publishers in `.live` rather than owning a table of their own.

Loading is transactional per file: a file that fails its check is rejected in
full and does not touch previously published rows (M0 section 5.7, "fail-safe").
Missing files are skipped with a warning rather than failing the run, since
Phase 1 seed curation lands incrementally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from biet_api.models import (
    AdverseEvent,
    AdverseEventCost,
    Country,
    CountryEconomics,
    CountryHealthIndicator,
    DiseaseSubgroup,
    Drug,
    DrugAdverseEvent,
    DrugPrice,
    DrugRegimen,
    EligibilityCriterion,
    Epidemiology,
    EventCost,
    FunnelDefault,
    FxRate,
    Indication,
    ResponseProfile,
    SubgroupCountryRate,
    SubgroupEventRate,
    TreatmentEffect,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import (
    BASE_CURRENCY,
    COUNTRY_CURRENCY,
    MIN_FX_CURRENCIES,
    REQUIRED_CURRENCIES,
    TARGET_COUNTRIES,
)
from ..errors import SourceValidationError
from ..sources.worldbank import derive_adult_share
from .upsert import resync_sequence, upsert

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- IO


def _read(name: str) -> pd.DataFrame | None:
    path: Path = settings.seed_dir / name
    if not path.exists():
        log.warning("seed_missing", extra={"file": name})
        return None
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    return frame.replace("", pd.NA)


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _to_list(value: Any) -> list[str] | None:
    if value is None or pd.isna(value):
        return None
    return [v.strip() for v in str(value).split("|") if v.strip()]


# --------------------------------------------------------------------------- countries.csv


def publish_countries(session: Session) -> int:
    frame = _read("countries.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        if row.country_code not in TARGET_COUNTRIES:
            log.warning("seed_row_skipped", extra={"file": "countries.csv",
                                                     "reason": "not a target market",
                                                     "country_code": row.country_code})
            continue
        if row.currency_code != COUNTRY_CURRENCY[row.country_code]:
            raise SourceValidationError(
                f"countries.csv: {row.country_code} currency {row.currency_code} "
                f"disagrees with COUNTRY_CURRENCY[{row.country_code}]="
                f"{COUNTRY_CURRENCY[row.country_code]}"
            )
        upsert(
            session, Country,
            natural_key={"country_code": row.country_code},
            values={
                "country_name": row.country_name,
                "currency_code": row.currency_code,
                "region": row.region,
                "health_system_type": row.health_system_type,
            },
        )
        published += 1
    log.info("seed_published", extra={"file": "countries.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- indications.csv


def publish_indications(session: Session) -> int:
    frame = _read("indications.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        upsert(
            session, Indication,
            natural_key={"indication_id": int(row.indication_id)},
            values={
                "indication_name": row.indication_name,
                "therapy_area": row.therapy_area,
                "icd10": row.icd10,
                "who_indicator_code": row.who_indicator_code,
            },
        )
        published += 1
    # indications.csv carries its own primary keys, so the sequence never
    # advanced past them. See `resync_sequence`.
    resync_sequence(session, "indications", "indication_id")
    log.info("seed_published", extra={"file": "indications.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- drugs.csv


def publish_drugs(session: Session) -> int:
    frame = _read("drugs.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        upsert(
            session, Drug,
            natural_key={"drug_id": int(row.drug_id)},
            values={
                "drug_name": row.drug_name,
                "generic_name": row.generic_name,
                "company": row.company,
                "drug_class": row.drug_class,
                "route": row.route,
                "indication_id": int(row.indication_id) if pd.notna(row.indication_id) else None,
                "is_comparator": _to_bool(row.is_comparator),
            },
        )
        published += 1
    # As above: drugs.csv carries its own `drug_id`, so without this the
    # first drug the application inserts collides with a seeded one.
    resync_sequence(session, "drugs", "drug_id")
    log.info("seed_published", extra={"file": "drugs.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- drug_regimens.csv


def publish_drug_regimens(session: Session) -> int:
    frame = _read("drug_regimens.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        wastage = float(row.wastage_pct)
        persistence = float(row.persistence_12m)
        if not (0 <= wastage < 1):
            log.warning("seed_row_skipped", extra={"file": "drug_regimens.csv",
                                                     "reason": "wastage_pct out of range",
                                                     "drug_id": row.drug_id})
            continue
        if not (0 < persistence <= 1):
            log.warning("seed_row_skipped", extra={"file": "drug_regimens.csv",
                                                     "reason": "persistence_12m out of range",
                                                     "drug_id": row.drug_id})
            continue
        upsert(
            session, DrugRegimen,
            natural_key={"drug_id": int(row.drug_id)},
            values={
                "dose_amount": float(row.dose_amount),
                "dose_unit": row.dose_unit,
                "units_per_admin": float(row.units_per_admin),
                "admins_per_year": float(row.admins_per_year),
                "wastage_pct": wastage,
                "persistence_12m": persistence,
                "source": row.source,
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    log.info("seed_published", extra={"file": "drug_regimens.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- drug_prices.csv


def publish_drug_prices(session: Session) -> int:
    frame = _read("drug_prices.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        price = float(row.price_local)
        if price <= 0:
            log.warning("seed_row_skipped", extra={"file": "drug_prices.csv",
                                                     "reason": "price_local not positive",
                                                     "drug_id": row.drug_id,
                                                     "country_code": row.country_code})
            continue
        if row.currency_code != COUNTRY_CURRENCY.get(row.country_code):
            log.warning("seed_row_skipped", extra={"file": "drug_prices.csv",
                                                     "reason": "currency does not match market",
                                                     "drug_id": row.drug_id,
                                                     "country_code": row.country_code})
            continue
        gross_to_net = float(row.gross_to_net_pct) if pd.notna(row.gross_to_net_pct) else None
        if row.price_basis == "estimated_net" and gross_to_net is None:
            log.warning("seed_row_skipped", extra={"file": "drug_prices.csv",
                                                     "reason": "estimated_net without gross_to_net_pct",
                                                     "drug_id": row.drug_id,
                                                     "country_code": row.country_code})
            continue
        upsert(
            session, DrugPrice,
            natural_key={
                "drug_id": int(row.drug_id),
                "country_code": row.country_code,
                "price_basis": row.price_basis,
            },
            values={
                "price_local": price,
                "currency_code": row.currency_code,
                "annual_cost_usd": None,
                "gross_to_net_pct": gross_to_net,
                "effective_date": row.effective_date if pd.notna(row.effective_date) else None,
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    log.info("seed_published", extra={"file": "drug_prices.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- funnel_defaults.csv


def publish_funnel_defaults(session: Session) -> int:
    frame = _read("funnel_defaults.csv")
    if frame is None:
        return 0

    # Rate range violated anywhere in the file rejects the whole file (M0 section 6).
    values = frame["value"].astype(float)
    if not values.between(0, 1, inclusive="right").all() or (values <= 0).any():
        bad = frame.loc[~values.between(0, 1, inclusive="right") | (values <= 0)]
        raise SourceValidationError(
            f"funnel_defaults.csv: {len(bad)} row(s) with value outside (0, 1]"
        )

    published = 0
    for row in frame.itertuples():
        upsert(
            session, FunnelDefault,
            natural_key={
                "indication_id": int(row.indication_id),
                "country_code": row.country_code if pd.notna(row.country_code) else None,
                "stage": row.stage,
            },
            values={
                "value": float(row.value),
                "value_low": float(row.value_low) if pd.notna(row.value_low) else None,
                "value_high": float(row.value_high) if pd.notna(row.value_high) else None,
                "source": row.source,
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    log.info("seed_published", extra={"file": "funnel_defaults.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- eligibility_criteria.csv


def publish_eligibility_criteria(session: Session) -> int:
    frame = _read("eligibility_criteria.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        factor = float(row.default_factor)
        if not (0 < factor <= 1):
            log.warning("seed_row_skipped", extra={"file": "eligibility_criteria.csv",
                                                     "reason": "default_factor out of range",
                                                     "criterion_code": row.criterion_code})
            continue
        upsert(
            session, EligibilityCriterion,
            natural_key={
                "indication_id": int(row.indication_id),
                "criterion_code": row.criterion_code,
            },
            values={
                "criterion_label": row.criterion_label,
                "criterion_type": row.criterion_type,
                "default_factor": factor,
                "factor_low": float(row.factor_low) if pd.notna(row.factor_low) else None,
                "factor_high": float(row.factor_high) if pd.notna(row.factor_high) else None,
                "source": row.source,
                "confidence_tier": row.confidence_tier,
                "correlated_with": _to_list(getattr(row, "correlated_with", None)),
            },
        )
        published += 1
    log.info("seed_published", extra={"file": "eligibility_criteria.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- auxiliary (no table of their own)


@dataclass(frozen=True)
class NdcMapping:
    ndc: str
    drug_id: int
    units_per_presentation: float
    presentations_per_year: float
    source: str
    # NADAC prices per mL; `drug_regimens.units_per_admin` is in the drug's
    # clinical dose unit (IU for insulin, mg for liraglutide) so that M5's
    # `unit_price x units_per_admin` is dimensionally consistent regardless of
    # which price_basis a run resolves to. This is the conversion between the
    # two: units (or mg) per mL, from the product's labelled concentration.
    concentration_per_ml: float
    dose_unit: str


def load_ndc_regimen_map() -> dict[str, NdcMapping]:
    """`ndc -> NdcMapping`. An NDC absent here is not published (M0 section 5.4)."""
    frame = _read("ndc_regimen_map.csv")
    if frame is None:
        return {}
    return {
        row.ndc: NdcMapping(
            ndc=row.ndc,
            drug_id=int(row.drug_id),
            units_per_presentation=float(row.units_per_presentation),
            presentations_per_year=float(row.presentations_per_year),
            source=row.source,
            concentration_per_ml=float(row.concentration_per_ml),
            dose_unit=row.dose_unit,
        )
        for row in frame.itertuples()
    }


def load_diabetes_cagr() -> dict[str, float]:
    """`country_code -> cagr`, for the diabetes forward projection (M0 section 5.3)."""
    frame = _read("diabetes_cagr.csv")
    if frame is None:
        return {}
    return {row.country_code: float(row.cagr) for row in frame.itertuples()}


def load_age_bands() -> dict[str, float]:
    """`country_code -> age_15_17_pct`, an observed override for the tier-B approximation."""
    frame = _read("age_bands.csv")
    if frame is None:
        return {}
    return {row.country_code: float(row.age_15_17_pct) for row in frame.itertuples()}


# --------------------------------------------------------------------------- adverse events (M13)


def publish_adverse_events(session: Session) -> int:
    """The event vocabulary. Shared across therapies and markets."""
    frame = _read("adverse_events.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        upsert(
            session, AdverseEvent,
            natural_key={"ae_code": row.ae_code},
            values={
                "ae_label": row.ae_label,
                "is_serious": _to_bool(row.is_serious),
                "meddra_pt": row.meddra_pt if pd.notna(row.meddra_pt) else None,
            },
        )
        published += 1
    log.info("seed_published", extra={"file": "adverse_events.csv", "rows": published})
    return published


def publish_adverse_event_costs(session: Session) -> int:
    """What managing one occurrence costs, per market."""
    frame = _read("adverse_event_costs.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        upsert(
            session, AdverseEventCost,
            natural_key={"ae_code": row.ae_code, "country_code": row.country_code},
            values={
                "unit_cost_local": row.unit_cost_local,
                "currency_code": row.currency_code,
                "cost_year": int(row.cost_year) if pd.notna(row.cost_year) else None,
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    log.info("seed_published", extra={"file": "adverse_event_costs.csv", "rows": published})
    return published


def publish_drug_adverse_events(session: Session) -> int:
    """Per-therapy incidences, each with the trial it was observed in.

    Rejected in full if any row lacks a source or a tier. An adverse-event
    incidence is the value in this system most likely to be repeated as fact
    (M13 section 5.1), so an unattributed one must not reach the database at
    all rather than arriving and being caught downstream.
    """
    frame = _read("drug_adverse_events.csv")
    if frame is None:
        return 0

    for row in frame.itertuples():
        if not str(row.source).strip() or not str(row.confidence_tier).strip():
            raise SourceValidationError(
                f"drug_adverse_events.csv: {row.drug_id}/{row.ae_code} has no source "
                "or no confidence tier; an unattributed incidence is not publishable"
            )

    published = 0
    for row in frame.itertuples():
        upsert(
            session, DrugAdverseEvent,
            natural_key={"drug_id": int(row.drug_id), "ae_code": row.ae_code},
            values={
                "incidence": row.incidence,
                "exposure_weeks": (
                    int(row.exposure_weeks) if pd.notna(row.exposure_weeks) else None
                ),
                "population": row.population if pd.notna(row.population) else None,
                "evidence_type": row.evidence_type,
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "vintage_year": (
                    int(row.vintage_year) if pd.notna(row.vintage_year) else None
                ),
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    log.info("seed_published", extra={"file": "drug_adverse_events.csv", "rows": published})
    return published


# ----------------------------------------------------- subgroups and outcomes (M16/M18)

#: The seeded subgroup shares are expected to partition the diagnosed
#: population. Floating-point CSV values will not sum to exactly 1, so the
#: check is against this tolerance — but it is a *rejection*, not a warning:
#: overlapping segments double-count patients and under-covering ones drop
#: them, and either is silently wrong all the way to the headline figure.
SUBGROUP_SHARE_TOLERANCE = 1e-6


def publish_disease_subgroups(session: Session) -> int:
    """M18. One disease, its clinically distinct populations.

    The share check is conditional on `is_overlapping`, and that is the point of
    the flag. A *partition* — segments assigned hierarchically so no patient is
    in two — must sum to 1, and a file that does not is silently dropping or
    double-counting patients. **Overlapping** subgroups must not: the WHO-derived
    obesity subgroups sum to roughly 1.5x the obese population precisely because
    a patient with diabetes and hypertension is in two of them, and rejecting
    that file would be rejecting the data for being correct.

    The default-population row is excluded from either check. It is the
    denominator the others are shares of, so counting it among them would double
    the total by construction.
    """
    frame = _read("disease_subgroups.csv")
    if frame is None:
        return 0

    partitioned: dict[int, float] = {}
    for row in frame.itertuples():
        if _to_bool(row.is_default_population) or _to_bool(row.is_overlapping):
            continue
        partitioned[int(row.indication_id)] = (
            partitioned.get(int(row.indication_id), 0.0) + float(row.share_of_diagnosed)
        )
    for indication_id, total in partitioned.items():
        if abs(total - 1.0) > SUBGROUP_SHARE_TOLERANCE:
            raise SourceValidationError(
                f"disease_subgroups.csv: indication {indication_id}'s "
                f"non-overlapping shares sum to {total:.6f}, not 1. A partition must "
                "cover the population exactly — overlapping segments double-count "
                "patients and gaps drop them. Mark the rows `is_overlapping` if they "
                "are alternative definitions rather than a partition."
            )

    published = 0
    for row in frame.itertuples():
        upsert(
            session, DiseaseSubgroup,
            natural_key={
                "indication_id": int(row.indication_id),
                "subgroup_code": row.subgroup_code,
            },
            values={
                "subgroup_label": row.subgroup_label,
                "description": row.description if pd.notna(row.description) else None,
                "share_of_diagnosed": row.share_of_diagnosed,
                "eligible_factor": row.eligible_factor,
                "uptake_multiplier": row.uptake_multiplier,
                "is_default_population": _to_bool(row.is_default_population),
                "is_overlapping": _to_bool(row.is_overlapping),
                "sort_order": int(row.sort_order),
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1

    # This file is the complete authority on which subgroups exist, so a row
    # that has left it must leave the database too. `upsert` only ever adds and
    # updates, which is right for a catalogue that grows — but a subgroup
    # dropped from the seed and left behind stays *selectable*, and a scenario
    # built on it would be modelled against a definition no longer in the
    # source. Deleted rather than deactivated: a subgroup nobody can choose and
    # nothing references has nothing to preserve.
    codes = {row.subgroup_code for row in frame.itertuples()}
    stale = [
        subgroup for subgroup in session.query(DiseaseSubgroup).all()
        if subgroup.subgroup_code not in codes
    ]
    for subgroup in stale:
        session.delete(subgroup)
    if stale:
        log.info("seed_pruned", extra={"file": "disease_subgroups.csv",
                                        "rows": len(stale),
                                        "codes": sorted(s.subgroup_code for s in stale)})
    session.flush()

    resync_sequence(session, "disease_subgroups", "subgroup_id")
    log.info("seed_published", extra={"file": "disease_subgroups.csv", "rows": published})
    return published


def publish_subgroup_country_rates(session: Session) -> int:
    """M18. Each subgroup's share and eligibility in each market.

    A comorbidity share is a property of the market, not of the disease: WHO
    puts hypertension prevalence at 34.0% in Brazil and 26.2% in France, and the
    hypertension subgroup's share of obese adults follows it. A market with no
    row here falls back to the global mean on `disease_subgroups`, which is a
    stated approximation rather than a measurement.
    """
    frame = _read("subgroup_country_rates.csv")
    if frame is None:
        return 0

    by_code = {
        subgroup.subgroup_code: subgroup.subgroup_id
        for subgroup in session.query(DiseaseSubgroup).all()
    }
    published = 0
    for row in frame.itertuples():
        subgroup_id = by_code.get(row.subgroup_code)
        if subgroup_id is None:
            raise SourceValidationError(
                f"subgroup_country_rates.csv: no subgroup {row.subgroup_code!r}"
            )
        if row.country_code not in TARGET_COUNTRIES:
            # The WHO source covers ten countries and this model covers ten,
            # and they are not the same ten. A market outside the model's set
            # is skipped rather than rejected: the file is a superset by
            # design, not an error.
            log.warning("seed_row_skipped",
                        extra={"file": "subgroup_country_rates.csv",
                               "country_code": row.country_code,
                               "reason": "not a target market"})
            continue
        upsert(
            session, SubgroupCountryRate,
            natural_key={"subgroup_id": subgroup_id, "country_code": row.country_code},
            values={
                "share_of_diagnosed": row.share_of_diagnosed,
                "eligible_factor": row.eligible_factor,
                "source": row.source,
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    resync_sequence(session, "subgroup_country_rates", "rate_id")
    log.info("seed_published",
             extra={"file": "subgroup_country_rates.csv", "rows": published})
    return published


def publish_country_health_indicators(session: Session) -> int:
    """WHO Global Health Observatory indicators, per market.

    Every numeric value is stored as a **fraction**, never a percentage
    (non-negotiable 5). The source file quotes percentages and the division
    happens once, in the transform that wrote `country_health_indicators.csv`.
    """
    frame = _read("country_health_indicators.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        if row.country_code not in TARGET_COUNTRIES:
            log.warning("seed_row_skipped",
                        extra={"file": "country_health_indicators.csv",
                               "country_code": row.country_code})
            continue
        upsert(
            session, CountryHealthIndicator,
            natural_key={"country_code": row.country_code, "indicator": row.indicator},
            values={
                "indicator_kind": row.indicator_kind,
                "value": row.value if pd.notna(row.value) else None,
                "label": row.label,
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "vintage_year": (
                    int(row.vintage_year) if pd.notna(row.vintage_year) else None
                ),
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    resync_sequence(session, "country_health_indicators", "indicator_id")
    log.info("seed_published",
             extra={"file": "country_health_indicators.csv", "rows": published})
    return published


def publish_subgroup_event_rates(session: Session) -> int:
    """M18. The baseline event rates a subgroup carries on current care.

    Keyed by `subgroup_code` in the CSV rather than by `subgroup_id`, so the
    file stays editable without knowing what surrogate key the database
    assigned. An unknown code is rejected rather than skipped: a silently
    dropped baseline rate means every avoided-event count for that segment
    comes out as zero, which reads as a finding.
    """
    frame = _read("subgroup_event_rates.csv")
    if frame is None:
        return 0

    by_code = {
        subgroup.subgroup_code: subgroup.subgroup_id
        for subgroup in session.query(DiseaseSubgroup).all()
    }
    published = 0
    for row in frame.itertuples():
        subgroup_id = by_code.get(row.subgroup_code)
        if subgroup_id is None:
            raise SourceValidationError(
                f"subgroup_event_rates.csv: no subgroup {row.subgroup_code!r}. "
                "A baseline rate with no segment to attach to would silently zero "
                "that segment's avoided events."
            )
        upsert(
            session, SubgroupEventRate,
            natural_key={"subgroup_id": subgroup_id, "event_class": row.event_class},
            values={
                "baseline_annual_rate": row.baseline_annual_rate,
                "rate_low": row.rate_low if pd.notna(row.rate_low) else None,
                "rate_high": row.rate_high if pd.notna(row.rate_high) else None,
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "vintage_year": (
                    int(row.vintage_year) if pd.notna(row.vintage_year) else None
                ),
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    resync_sequence(session, "subgroup_event_rates", "rate_id")
    log.info("seed_published",
             extra={"file": "subgroup_event_rates.csv", "rows": published})
    return published


def publish_treatment_effects(session: Session) -> int:
    """M16. Relative risk reductions, each naming the trial it rests on.

    Rejected in full if any row lacks a trial. M16's rule is that nothing is
    inferred — an effect with no trial behind it has nothing behind it, and
    admitting one would let a drug-class assumption enter the model looking
    exactly like an observation.
    """
    frame = _read("treatment_effects.csv")
    if frame is None:
        return 0

    for row in frame.itertuples():
        if not str(row.trial).strip() or not str(row.confidence_tier).strip():
            raise SourceValidationError(
                f"treatment_effects.csv: drug {row.drug_id}/{row.event_class} names no "
                "trial or no confidence tier; an unattributed effect size is not "
                "publishable"
            )

    published = 0
    for row in frame.itertuples():
        upsert(
            session, TreatmentEffect,
            natural_key={"drug_id": int(row.drug_id), "event_class": row.event_class},
            values={
                "relative_reduction": row.relative_reduction,
                "reduction_low": row.reduction_low if pd.notna(row.reduction_low) else None,
                "reduction_high": (
                    row.reduction_high if pd.notna(row.reduction_high) else None
                ),
                "observed_in_subgroup": (
                    row.observed_in_subgroup
                    if pd.notna(row.observed_in_subgroup) else None
                ),
                "trial": row.trial,
                "nct_id": row.nct_id if pd.notna(row.nct_id) else None,
                "follow_up_weeks": (
                    int(row.follow_up_weeks) if pd.notna(row.follow_up_weeks) else None
                ),
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "vintage_year": (
                    int(row.vintage_year) if pd.notna(row.vintage_year) else None
                ),
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    resync_sequence(session, "treatment_effects", "effect_id")
    log.info("seed_published", extra={"file": "treatment_effects.csv", "rows": published})
    return published


def publish_event_costs(session: Session) -> int:
    """M16. What one avoided event would have cost, per market.

    Only markets with a cited figure are seeded. The rest are derived at run
    time from the reference market through the same purchasing-power path M5
    uses for an unpriced therapy, and are labelled as derived — seeding
    placeholder costs for nine markets would pre-empt that with worse-sourced
    numbers.
    """
    frame = _read("event_costs.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        if row.country_code not in TARGET_COUNTRIES:
            log.warning("seed_row_skipped", extra={"file": "event_costs.csv",
                                                   "country_code": row.country_code})
            continue
        upsert(
            session, EventCost,
            natural_key={"event_class": row.event_class, "country_code": row.country_code},
            values={
                "unit_cost_local": row.unit_cost_local,
                "currency_code": row.currency_code,
                "cost_year": int(row.cost_year) if pd.notna(row.cost_year) else None,
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    resync_sequence(session, "event_costs", "event_cost_id")
    log.info("seed_published", extra={"file": "event_costs.csv", "rows": published})
    return published


def publish_response_profiles(session: Session) -> int:
    """M16. Responder share and mean weight loss, per therapy."""
    frame = _read("response_profiles.csv")
    if frame is None:
        return 0

    for row in frame.itertuples():
        if not str(row.trial).strip() or not str(row.confidence_tier).strip():
            raise SourceValidationError(
                f"response_profiles.csv: drug {row.drug_id} names no trial or no "
                "confidence tier"
            )

    published = 0
    for row in frame.itertuples():
        upsert(
            session, ResponseProfile,
            natural_key={"drug_id": int(row.drug_id), "threshold": row.threshold},
            values={
                "responder_share": row.responder_share,
                "responder_low": row.responder_low if pd.notna(row.responder_low) else None,
                "responder_high": (
                    row.responder_high if pd.notna(row.responder_high) else None
                ),
                "mean_weight_loss_pct": row.mean_weight_loss_pct,
                "regain_per_year": row.regain_per_year,
                "trial": row.trial,
                "nct_id": row.nct_id if pd.notna(row.nct_id) else None,
                "source": row.source,
                "source_url": row.source_url if pd.notna(row.source_url) else None,
                "vintage_year": (
                    int(row.vintage_year) if pd.notna(row.vintage_year) else None
                ),
                "confidence_tier": row.confidence_tier,
            },
        )
        published += 1
    resync_sequence(session, "response_profiles", "profile_id")
    log.info("seed_published", extra={"file": "response_profiles.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- fx_rates.csv


def publish_fx_rates(session: Session) -> int:
    """A dated FX baseline, so a first run can convert currencies offline.

    FX is otherwise supplied only by the live Frankfurter fetcher, which means
    a Docker first boot — `--seed-only`, deliberately offline so a machine with
    no internet can still start — left `fx_rates` empty. Every scenario
    reporting in anything but USD then failed with "no FX rate for reporting
    currency 'EUR'; available: []", which reads as a broken install rather than
    as data that was never loaded.

    These are real ECB reference rates, snapshotted on the date in the file
    rather than invented, and they are a floor and not a fixture: a live run
    publishes fresher rates under a new `fetched_date`, and because that date
    is half the natural key the newer set is added alongside rather than
    overwriting this one. M7 snapshots whichever set it used into the run, so a
    result always says which rates produced it.

    Validated on the same invariants the live fetcher enforces, because a seed
    that quietly omitted a currency would fail later, further from the cause.
    """
    frame = _read("fx_rates.csv")
    if frame is None:
        return 0

    seen: dict[str, float] = {}
    for row in frame.itertuples():
        rate = float(row.rate_per_usd)
        if rate <= 0:
            raise SourceValidationError(
                f"fx_rates.csv: non-positive rate for {row.currency_code}",
                currency=row.currency_code,
            )
        seen[str(row.currency_code)] = rate

    missing = REQUIRED_CURRENCIES - set(seen)
    if missing:
        raise SourceValidationError(
            f"fx_rates.csv: missing rates for {sorted(missing)}",
            missing=sorted(missing),
        )
    if len(seen) < MIN_FX_CURRENCIES:
        raise SourceValidationError(
            f"fx_rates.csv: only {len(seen)} currencies, need {MIN_FX_CURRENCIES}"
        )
    if seen.get(BASE_CURRENCY) != 1.0:
        # Without it, M7 has no pivot and every conversion needs a special case.
        raise SourceValidationError(
            f"fx_rates.csv: {BASE_CURRENCY} identity row must be exactly 1.0"
        )

    published = 0
    for row in frame.itertuples():
        upsert(
            session, FxRate,
            natural_key={
                "currency_code": row.currency_code,
                "fetched_date": date.fromisoformat(str(row.fetched_date)),
            },
            values={"rate_per_usd": float(row.rate_per_usd)},
        )
        published += 1
    log.info("seed_published", extra={"file": "fx_rates.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- country_economics.csv


def publish_country_economics(session: Session) -> int:
    """Population and economic indicators, so a first run can price offline.

    `country_economics` was populated only by the live World Bank fetch, which
    `--seed-only` deliberately skips. A container therefore started with the
    table empty, and an empty table is not a small loss: M5 derives a price for
    every market with no observed one by purchasing-power parity, and that
    derivation needs GDP per capita. Without it `_derive` returns None and the
    cell falls all the way through to "no price in any market this could be
    derived from" — 0.00 at tier D. Seven of eleven markets showed no price at
    all, and affordability had no capacity figure to position impact against.

    Real World Bank figures at their own vintages, one row per market per
    indicator. The vintage differs by indicator on purpose: population reaches
    2025 while health expenditure lags, and pinning them to one year would
    silently drop the lagging series.

    A later live run supersedes these by natural key, so this is a floor rather
    than a fixture.
    """
    frame = _read("country_economics.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        if row.country_code not in TARGET_COUNTRIES:
            log.warning("seed_row_skipped", extra={"file": "country_economics.csv",
                                                     "reason": "not a target market",
                                                     "country_code": row.country_code})
            continue
        upsert(
            session, CountryEconomics,
            natural_key={"country_code": row.country_code,
                         "indicator": row.indicator,
                         "year": int(row.year)},
            values={"value": float(row.value), "source": row.source,
                    "confidence_tier": row.confidence_tier},
        )
        published += 1

    # `countries.adult_share` is derived from the paediatric band by the live
    # publisher; deriving it here too keeps a seeded install and an ingested
    # one the same. WHO publishes prevalence for adults while World Bank
    # publishes all ages, so without this the diseased population carries the
    # paediatric share.
    age_bands = load_age_bands()
    for row in frame.itertuples():
        if row.indicator != "pop_0014_pct" or row.country_code not in TARGET_COUNTRIES:
            continue
        country = session.get(Country, row.country_code)
        if country is not None:
            country.adult_share = round(
                derive_adult_share(float(row.value), age_bands.get(row.country_code)), 4,
            )

    log.info("seed_published", extra={"file": "country_economics.csv", "rows": published})
    return published


# --------------------------------------------------------------------------- epidemiology.csv


def publish_epidemiology(session: Session) -> int:
    """Prevalence with WHO's own interval, so a first run can compute at all.

    `epidemiology` was populated only by the live WHO GHO fetch, which
    `--seed-only` skips. A container therefore started with the table empty and
    could not run a single scenario: `epidemiology.prevalence` resolved to
    nothing and every run failed with "no value for 'epidemiology.prevalence'
    in market 'USA' at any resolution level" before it reached the engine.

    `prevalence_low` and `prevalence_high` are WHO's published bounds and are
    seeded with the central value rather than dropped — M9 parameterises the
    PSA from them, and discarding them is a defect (see the model docstring).

    A live run supersedes these by natural key, so this is a floor rather than
    a fixture.
    """
    frame = _read("epidemiology.csv")
    if frame is None:
        return 0

    published = 0
    for row in frame.itertuples():
        if row.country_code not in TARGET_COUNTRIES:
            log.warning("seed_row_skipped", extra={"file": "epidemiology.csv",
                                                     "reason": "not a target market",
                                                     "country_code": row.country_code})
            continue
        upsert(
            session, Epidemiology,
            natural_key={
                "country_code": row.country_code,
                "indication_id": int(row.indication_id),
                "year": int(row.year),
                "age_group": row.age_group,
                "sex": row.sex,
            },
            values={
                "prevalence_pct": float(row.prevalence_pct),
                "prevalence_low": float(row.prevalence_low),
                "prevalence_high": float(row.prevalence_high),
                "source": row.source,
                "confidence_tier": row.confidence_tier,
                "is_projected": _to_bool(row.is_projected),
            },
        )
        published += 1

    published += _project_diabetes(session, frame)
    log.info("seed_published", extra={"file": "epidemiology.csv", "rows": published})
    return published


def _project_diabetes(session: Session, frame: pd.DataFrame) -> int:
    """Carry the 2014 diabetes observation forward, as the live publisher does.

    WHO's diabetes series stops in 2014. Left alone it is a decade stale, so
    the live path grows it at the market's own CAGR and marks the result
    projected; doing the same here keeps a seeded install and an ingested one
    from disagreeing about the same market.
    """
    cagr = load_diabetes_cagr()
    if not cagr:
        return 0

    diabetes = session.execute(
        select(Indication).filter_by(who_indicator_code="NCD_GLUC_04")
    ).scalar_one_or_none()
    if diabetes is None:
        return 0

    projected_year = datetime.now(UTC).year
    published = 0
    for row in frame.itertuples():
        if int(row.indication_id) != diabetes.indication_id:
            continue
        growth_rate = cagr.get(row.country_code)
        if growth_rate is None or int(row.year) >= projected_year:
            continue

        growth = (1 + growth_rate) ** (projected_year - int(row.year))
        upsert(
            session, Epidemiology,
            natural_key={
                "country_code": row.country_code,
                "indication_id": diabetes.indication_id,
                "year": projected_year,
                "age_group": row.age_group,
                "sex": row.sex,
            },
            values={
                "prevalence_pct": round(float(row.prevalence_pct) * growth, 4),
                "prevalence_low": round(float(row.prevalence_low) * growth, 4),
                "prevalence_high": round(float(row.prevalence_high) * growth, 4),
                "source": f"{row.source} projected to {projected_year} via "
                          f"data/seed/diabetes_cagr.csv (cagr={growth_rate})",
                "confidence_tier": "C",
                "is_projected": True,
            },
        )
        published += 1
    return published


# --------------------------------------------------------------------------- orchestration

#: Publish order matters: countries/indications before anything with a foreign
#: key to them; drugs before drug_regimens/drug_prices.
SEED_PUBLISHERS = (
    # No foreign keys, and every currency conversion depends on it.
    publish_fx_rates,
    publish_countries,
    # After countries: foreign key, and it writes countries.adult_share.
    publish_country_economics,
    publish_indications,
    # After countries and indications: foreign keys to both.
    publish_epidemiology,
    publish_drugs,
    publish_drug_regimens,
    publish_drug_prices,
    publish_funnel_defaults,
    publish_eligibility_criteria,
    # After drugs and countries: every one of these has a foreign key to one
    # or the other.
    publish_adverse_events,
    publish_adverse_event_costs,
    publish_drug_adverse_events,
    # M16/M18. Subgroups before their event rates; drugs and countries are
    # already published by the time either runs.
    publish_disease_subgroups,
    publish_subgroup_country_rates,
    publish_country_health_indicators,
    publish_subgroup_event_rates,
    publish_treatment_effects,
    publish_event_costs,
    publish_response_profiles,
)


def publish_seed_all(session: Session) -> dict[str, int]:
    return {fn.__name__: fn(session) for fn in SEED_PUBLISHERS}
