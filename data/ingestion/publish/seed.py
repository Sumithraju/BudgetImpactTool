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
from pathlib import Path
from typing import Any

import pandas as pd
from biet_api.models import (
    AdverseEvent,
    AdverseEventCost,
    Country,
    Drug,
    DrugPrice,
    DrugAdverseEvent,
    DrugRegimen,
    EligibilityCriterion,
    FunnelDefault,
    Indication,
)
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import COUNTRY_CURRENCY, TARGET_COUNTRIES
from ..errors import SourceValidationError
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


# --------------------------------------------------------------------------- orchestration

#: Publish order matters: countries/indications before anything with a foreign
#: key to them; drugs before drug_regimens/drug_prices.
SEED_PUBLISHERS = (
    publish_countries,
    publish_indications,
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
)


def publish_seed_all(session: Session) -> dict[str, int]:
    return {fn.__name__: fn(session) for fn in SEED_PUBLISHERS}
