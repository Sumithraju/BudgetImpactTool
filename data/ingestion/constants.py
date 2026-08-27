"""Reference constants for the ingestion pipeline.

No literal country code, indicator code, URL or threshold appears anywhere else
in this package. See the `biet-backend` skill, section 4.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# --------------------------------------------------------------------------- markets

TARGET_COUNTRIES: Final[tuple[str, ...]] = (
    "USA", "GBR", "DEU", "FRA", "ITA", "ESP", "IND", "CHN", "BRA", "JPN", "DNK",
)

COUNTRY_CURRENCY: Final[dict[str, str]] = {
    "USA": "USD", "GBR": "GBP", "DEU": "EUR", "FRA": "EUR", "ITA": "EUR",
    "ESP": "EUR", "IND": "INR", "CHN": "CNY", "BRA": "BRL", "JPN": "JPY",
    "DNK": "DKK",
}

REQUIRED_CURRENCIES: Final[frozenset[str]] = frozenset(COUNTRY_CURRENCY.values())
BASE_CURRENCY: Final[str] = "USD"
REFERENCE_COUNTRY: Final[str] = "USA"

# --------------------------------------------------------------------------- sources


class SourceId(StrEnum):
    WORLD_BANK = "worldbank"
    WHO_GHO = "who_gho"
    NADAC = "nadac"
    OPENFDA = "openfda"
    CLINICALTRIALS = "clinicaltrials"
    FRANKFURTER = "frankfurter"


# --------------------------------------------------------------------------- World Bank

WORLD_BANK_BASE_URL: Final[str] = "https://api.worldbank.org/v2"

WORLD_BANK_INDICATORS: Final[dict[str, str]] = {
    "SP.POP.TOTL": "population_total",
    "NY.GDP.PCAP.PP.CD": "gdp_pc_ppp",
    "SH.XPD.CHEX.PC.CD": "health_exp_pc_usd",
    "SH.XPD.OOPC.CH.ZS": "oop_health_pct",
    "SP.POP.0014.TO.ZS": "pop_0014_pct",
}

WORLD_BANK_DATE_RANGE: Final[str] = "2018:2026"
WORLD_BANK_PAGE_SIZE: Final[int] = 500

# --------------------------------------------------------------------------- WHO GHO

WHO_GHO_BASE_URL: Final[str] = "https://ghoapi.azureedge.net/api"

WHO_INDICATORS: Final[dict[str, str]] = {
    "NCD_BMI_30A": "obesity_prevalence",
    "NCD_BMI_25A": "overweight_prevalence",
    "NCD_GLUC_04": "diabetes_prevalence",
}

# Filters that MUST be applied to every WHO extract. Omitting the spatial-dimension
# filter loads World Bank income groups and WHO regions as if they were markets.
WHO_SPATIAL_DIM_TYPE: Final[str] = "COUNTRY"
WHO_SEX_BOTH: Final[str] = "SEX_BTSX"
WHO_AGE_GROUP_ADULT: Final[str] = "AGEGROUP_YEARS18-PLUS"

# --------------------------------------------------------------------------- NADAC

NADAC_DATASET_URL: Final[str] = (
    "https://download.medicaid.gov/data/"
    "nadac-national-average-drug-acquisition-cost-{date}.csv"
)
NADAC_FALLBACK_WEEKS: Final[int] = 8
NADAC_CHUNK_SIZE: Final[int] = 100_000

NADAC_MOLECULES: Final[tuple[str, ...]] = (
    "semaglutide", "tirzepatide", "liraglutide", "dulaglutide",
    "orforglipron", "insulin",
)

# --------------------------------------------------------------------------- other sources

OPENFDA_URL: Final[str] = "https://api.fda.gov/drug/drugsfda.json"
CLINICALTRIALS_URL: Final[str] = "https://clinicaltrials.gov/api/v2/studies"
FRANKFURTER_URL: Final[str] = "https://api.frankfurter.dev/v1/latest"

GLP1_GENERICS: Final[tuple[str, ...]] = (
    "semaglutide", "tirzepatide", "liraglutide", "dulaglutide", "orforglipron",
)

# --------------------------------------------------------------------------- validation

PREVALENCE_MIN_PCT: Final[float] = 0.0
PREVALENCE_MAX_PCT: Final[float] = 100.0
ADULT_SHARE_MIN: Final[float] = 0.50
ADULT_SHARE_MAX: Final[float] = 0.95

# WHO prevalence is published for ages 18+, but the World Bank publishes a 0-14
# band, so "not 0-14" is a 15+ share and overstates the adult denominator by the
# 15-17 cohort. Assuming roughly uniform single-year cohorts within 0-14, that
# band is 3/15 of it. Crude, but explicit, and it removes a 3-6% inflation of the
# diseased population. Overridable per market from data/seed/age_bands.csv.
ADOLESCENT_BAND_RATIO: Final[float] = 3.0 / 15.0
RATE_MIN: Final[float] = 0.0
RATE_MAX: Final[float] = 1.0
MIN_FX_CURRENCIES: Final[int] = 8          # seven quoted plus the USD identity row
STALE_VINTAGE_YEARS: Final[int] = 5

# --------------------------------------------------------------------------- confidence


class ConfidenceTier(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
