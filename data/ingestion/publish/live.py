"""Publishers for the six live sources — the counterpart to `.seed`.

Each function takes the already-`transform()`-ed frame from a `Fetcher` and
writes it to the database. Every source also lands its transformed rows in
`staging_extracts`, which is the second half of the audit trail described in
`biet_api.models.staging` (the first half is the untouched payload under
`data/raw/`).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from biet_api.models import (
    Country,
    CountryEconomics,
    DrugPrice,
    Epidemiology,
    FxRate,
    Indication,
    StagingExtract,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import STALE_VINTAGE_YEARS, WHO_INDICATORS
from .seed import NdcMapping
from .upsert import upsert
from ..sources.worldbank import SOURCE_LABEL as WORLD_BANK_LABEL
from ..sources.worldbank import derive_adult_share

log = logging.getLogger(__name__)

_WHO_CODE_BY_INDICATOR: dict[str, str] = {v: k for k, v in WHO_INDICATORS.items()}


def _json_safe(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, (pd.Timestamp, date, datetime)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def stage_frame(session: Session, source_id: str, frame: pd.DataFrame) -> None:
    """Persist every published row for audit, keyed by source and row index."""
    fetched_at = datetime.now(UTC)
    for index, row in enumerate(frame.to_dict(orient="records")):
        payload = {k: _json_safe(v) for k, v in row.items()}
        payload = {k: v for k, v in payload.items() if v is not None}
        upsert(
            session, StagingExtract,
            natural_key={"source_id": source_id, "row_index": index},
            values={"payload": payload, "fetched_at": fetched_at},
        )


# --------------------------------------------------------------------------- World Bank


def publish_worldbank(
    session: Session, frame: pd.DataFrame, age_bands: dict[str, float]
) -> int:
    """`country_economics`, plus `countries.adult_share` derived from it."""
    published = 0
    for row in frame.itertuples():
        upsert(
            session, CountryEconomics,
            natural_key={
                "country_code": row.country_code,
                "indicator": row.indicator,
                "year": int(row.year),
            },
            values={"value": row.value, "source": row.source,
                    "confidence_tier": row.confidence_tier},
        )
        published += 1

    paediatric = frame[frame["indicator"] == "pop_0014_pct"]
    for row in paediatric.itertuples():
        country = session.execute(
            select(Country).filter_by(country_code=row.country_code)
        ).scalar_one_or_none()
        if country is None:
            log.warning("live_row_skipped", extra={"source": "worldbank",
                                                     "reason": "country not seeded yet",
                                                     "country_code": row.country_code})
            continue

        override = age_bands.get(row.country_code)
        country.adult_share = round(derive_adult_share(row.value, override), 4)
        country.adult_share_confidence_tier = "A" if override is not None else "B"
        country.adult_share_source = (
            f"{WORLD_BANK_LABEL} SP.POP.0014.TO.ZS {row.year}, "
            + (
                "observed 15-17 share from data/seed/age_bands.csv"
                if override is not None
                else "less an approximated 15-17 cohort"
            )
        )
    return published


# --------------------------------------------------------------------------- WHO GHO


def publish_who_gho(
    session: Session, frame: pd.DataFrame, diabetes_cagr: dict[str, float]
) -> int:
    """`epidemiology`, plus a forward-projected diabetes row per M0 section 5.3.

    `overweight_prevalence` (NCD_BMI_25A) has no home in `epidemiology` — the two
    launch indications are obesity and type 2 diabetes, not "overweight" — so it
    is staged for context only and never published to a reference table.
    """
    published = 0
    diabetes_2014: dict[str, tuple[float, float | None, float | None, str]] = {}

    for row in frame.itertuples():
        if row.indicator == "overweight_prevalence":
            continue

        who_code = _WHO_CODE_BY_INDICATOR[row.indicator]
        indication = session.execute(
            select(Indication).filter_by(who_indicator_code=who_code)
        ).scalar_one_or_none()
        if indication is None:
            log.warning("live_row_skipped", extra={"source": "who_gho",
                                                     "reason": "indication not seeded yet",
                                                     "indicator": row.indicator})
            continue

        upsert(
            session, Epidemiology,
            natural_key={
                "country_code": row.country_code,
                "indication_id": indication.indication_id,
                "year": int(row.year),
                "age_group": row.age_group,
                "sex": row.sex,
            },
            values={
                "prevalence_pct": row.prevalence_pct,
                "prevalence_low": row.prevalence_low,
                "prevalence_high": row.prevalence_high,
                "source": row.source,
                "confidence_tier": row.confidence_tier,
                "is_projected": False,
            },
        )
        published += 1

        if row.indicator == "diabetes_prevalence":
            diabetes_2014[row.country_code] = (
                row.prevalence_pct, row.prevalence_low, row.prevalence_high, row.source,
            )

    if not diabetes_2014:
        return published

    diabetes_indication = session.execute(
        select(Indication).filter_by(who_indicator_code="NCD_GLUC_04")
    ).scalar_one_or_none()
    if diabetes_indication is None:
        return published

    base_year = 2014
    projected_year = date.today().year
    for country_code, (pct, low, high, source) in diabetes_2014.items():
        cagr = diabetes_cagr.get(country_code)
        if cagr is None:
            log.warning("live_row_skipped", extra={"source": "who_gho",
                                                     "reason": "no diabetes_cagr for market; "
                                                               "stale 2014 value only",
                                                     "country_code": country_code})
            continue

        growth = (1 + cagr) ** (projected_year - base_year)
        upsert(
            session, Epidemiology,
            natural_key={
                "country_code": country_code,
                "indication_id": diabetes_indication.indication_id,
                "year": projected_year,
                "age_group": "AGEGROUP_YEARS18-PLUS",
                "sex": "SEX_BTSX",
            },
            values={
                "prevalence_pct": round(pct * growth, 4),
                "prevalence_low": round(low * growth, 4) if low is not None else None,
                "prevalence_high": round(high * growth, 4) if high is not None else None,
                "source": f"{source} projected to {projected_year} via "
                          f"data/seed/diabetes_cagr.csv (cagr={cagr})",
                "confidence_tier": "C",
                "is_projected": True,
            },
        )
        published += 1

    stale = projected_year - base_year > STALE_VINTAGE_YEARS
    log.info("diabetes_projected", extra={"base_year": base_year,
                                           "projected_year": projected_year,
                                           "stale": stale})
    return published


# --------------------------------------------------------------------------- Frankfurter


def publish_frankfurter(session: Session, frame: pd.DataFrame) -> int:
    published = 0
    for row in frame.itertuples():
        fetched_date = (
            row.fetched_date
            if isinstance(row.fetched_date, date)
            else date.fromisoformat(str(row.fetched_date))
        )
        upsert(
            session, FxRate,
            natural_key={"currency_code": row.currency_code,
                         "fetched_date": fetched_date},
            values={"rate_per_usd": row.rate_per_usd},
        )
        published += 1
    return published


# --------------------------------------------------------------------------- NADAC


def publish_nadac(
    session: Session, frame: pd.DataFrame, ndc_map: dict[str, NdcMapping]
) -> int:
    """Converts mapped NDCs into `drug_prices` rows with `price_basis = nadac`.

    NADAC reports a per-mL price. `price_local` is stored per clinical dose unit
    instead — IU for insulin, mg for liraglutide — dividing by the product's
    labelled concentration (`concentration_per_ml`). `drug_regimens` has one row
    per drug regardless of how many price bases exist for it, so every basis for
    a drug must share one unit convention; per-mL would only be consistent for
    NADAC-priced rows and break the moment a per-mg branded price is added for
    the same drug_id.

    `annual_cost_usd` is a convenience figure computed straight from the raw
    per-mL price and the NDC-specific packaging in `ndc_regimen_map.csv`, per
    the M0 section 5.4 formula — a separate, informational conversion.

    An NDC absent from `ndc_map` is not published (M0 section 5.4).
    """
    published = 0
    for row in frame.itertuples():
        mapping = ndc_map.get(str(row.ndc))
        if mapping is None:
            log.warning("live_row_skipped", extra={"source": "nadac",
                                                     "reason": "no ndc_regimen_map entry",
                                                     "ndc": row.ndc})
            continue

        annual_cost = (
            row.nadac_per_unit * mapping.units_per_presentation
            * mapping.presentations_per_year
        )
        effective_date = (
            row.effective_date.date()
            if isinstance(row.effective_date, pd.Timestamp) and pd.notna(row.effective_date)
            else None
        )
        upsert(
            session, DrugPrice,
            natural_key={"drug_id": mapping.drug_id, "country_code": "USA",
                         "price_basis": "nadac"},
            values={
                "price_local": round(row.nadac_per_unit / mapping.concentration_per_ml, 6),
                "currency_code": "USD",
                "annual_cost_usd": round(annual_cost, 2),
                "gross_to_net_pct": None,
                "effective_date": effective_date,
                "source": f"{row.source}, converted from $/mL to $/{mapping.dose_unit} "
                          f"at {mapping.concentration_per_ml} {mapping.dose_unit}/mL "
                          f"per the product label",
                "source_url": "https://data.medicaid.gov",
                "confidence_tier": "A",
            },
        )
        published += 1
    return published
