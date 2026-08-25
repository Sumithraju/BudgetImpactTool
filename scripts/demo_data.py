#!/usr/bin/env python
"""Placeholder dataset for demonstrating BIET end to end.

**Everything this script writes is invented.** Not estimated, not derived from
an analogue — invented, so that every screen in the tool has something to show.
It exists because a discovered comparator arrives without a price or a regimen
(M11 section 5.7), and a demo that stops at "7 therapies need pricing" does not
show what the tool does with them.

Three things keep invented data from being mistaken for evidence:

1. **Every row is tier D.** The resolution layer already raises
   `TIER_D_INPUT` for those, M15 ranks them critical, and they appear as
   placeholders in the assumption register of every export.
2. **Every `source` string starts with `DEMO PLACEHOLDER`.** It is visible in
   the interface, in the register, and in the PDF — anywhere the value goes.
3. **`purge` removes exactly what `load` wrote**, matched on that prefix, so
   the database returns to seeded-and-cited data with one command.

Usage:

    python scripts/demo_data.py status     # what is demo, what is real
    python scripts/demo_data.py load
    python scripts/demo_data.py purge

Numbers are plausible rather than random — a $12,000 GLP-1 is the right order
of magnitude — because an obviously silly number makes a demo useless, and a
plausible one that is *labelled* is honest. Do not cite any of it.
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parent.parent / "backend" / "src"
if str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

from biet_api.dal.session import session_scope
from biet_api.models import (
    AdverseEventCost,
    ComparatorAsset,
    Country,
    Drug,
    DrugAdverseEvent,
    DrugPrice,
    DrugRegimen,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session

#: The marker. Every string this script writes into a `source` column begins
#: with it, and `purge` matches on it. Changing it orphans existing demo rows.
TAG = "DEMO PLACEHOLDER"

TIER_D = "D"
OBESITY = 1
DIABETES = 2

#: Prices are seeded for the reference market only. M5 derives the other nine
#: through purchasing-power parity and labels them derived — which is the
#: honest treatment and the one every seeded therapy already gets. Seeding a
#: made-up price in ten markets would replace a labelled derivation with an
#: unlabelled fabrication.
REFERENCE_MARKET = "USA"


class DemoDrug:
    """One placeholder therapy, and the annual cost it should come out at."""

    def __init__(
        self, *, name: str, generic: str, company: str, source_id: str,
        stage: str, klass: str, annual_usd: float, admins_per_year: float,
        persistence: float, route: str = "subcutaneous",
        drug_class: str = "GLP-1 receptor agonist", indication_id: int = OBESITY,
        entry_year: int | None = None, terminal_pct: float | None = None,
    ) -> None:
        self.name = name
        self.generic = generic
        self.company = company
        self.source_id = source_id
        self.stage = stage
        self.klass = klass
        self.annual_usd = annual_usd
        self.admins_per_year = admins_per_year
        self.persistence = persistence
        self.route = route
        self.drug_class = drug_class
        self.indication_id = indication_id
        self.entry_year = entry_year
        self.terminal_pct = terminal_pct

    @property
    def unit_price(self) -> float:
        """One unit, priced so the annual acquisition lands on target."""
        return round(self.annual_usd / self.admins_per_year, 6)


#: The GLP1R comparators discovery returns that this system cannot yet price.
#: ChEMBL ids are real — taken from the live Open Targets response — so
#: registering these is idempotent with what discovery finds.
DEMO_DRUGS: tuple[DemoDrug, ...] = (
    # --- marketed, so they belong in the world-without today
    DemoDrug(
        name="Byetta (exenatide)", generic="exenatide", company="AstraZeneca",
        source_id="CHEMBL414357", stage="APPROVAL", klass="direct",
        annual_usd=9_600.0, admins_per_year=730.0, persistence=0.38,
    ),
    DemoDrug(
        name="Adlyxin (lixisenatide)", generic="lixisenatide", company="Sanofi",
        source_id="CHEMBL2108336", stage="APPROVAL", klass="direct",
        annual_usd=3_400.0, admins_per_year=365.0, persistence=0.41,
    ),
    DemoDrug(
        name="Tanzeum (albiglutide)", generic="albiglutide", company="GSK",
        source_id="CHEMBL2107841", stage="APPROVAL", klass="direct",
        annual_usd=6_200.0, admins_per_year=52.0, persistence=0.44,
    ),
    # --- pipeline: modellable only when the launch-year landscape is projected
    DemoDrug(
        name="Retatrutide", generic="retatrutide", company="Eli Lilly",
        source_id="CHEMBL5095485", stage="PHASE_3", klass="pipeline",
        annual_usd=13_800.0, admins_per_year=52.0, persistence=0.62,
        drug_class="GIP/GLP-1/glucagon receptor triple agonist",
        entry_year=2, terminal_pct=0.18,
    ),
    DemoDrug(
        name="Survodutide", generic="survodutide", company="Boehringer Ingelheim",
        source_id="CHEMBL5314776", stage="PHASE_3", klass="pipeline",
        annual_usd=12_900.0, admins_per_year=52.0, persistence=0.60,
        drug_class="GLP-1/glucagon receptor dual agonist",
        entry_year=2, terminal_pct=0.12,
    ),
    DemoDrug(
        name="Danuglipron", generic="danuglipron", company="Pfizer",
        source_id="CHEMBL4518483", stage="PHASE_2", klass="pipeline",
        annual_usd=8_400.0, admins_per_year=730.0, persistence=0.55,
        route="oral", drug_class="Oral GLP-1 receptor agonist",
        entry_year=3, terminal_pct=0.08,
    ),
    DemoDrug(
        name="Efinopegdutide", generic="efinopegdutide", company="Merck",
        source_id="CHEMBL4297576", stage="PHASE_2", klass="pipeline",
        annual_usd=11_500.0, admins_per_year=52.0, persistence=0.58,
        drug_class="GLP-1/glucagon receptor dual agonist",
        entry_year=3, terminal_pct=0.06,
    ),
)

#: Per-event management cost in each market's own currency. Scaled from the
#: seeded USA figures by nothing more principled than a round factor per
#: market — which is why they are tier D and say so.
AE_UNIT_COSTS: dict[str, dict[str, float]] = {
    "GBR": {"nausea": 42.0, "vomiting": 51.0, "diarrhoea": 33.0, "constipation": 22.0},
    "DEU": {"nausea": 48.0, "vomiting": 58.0, "diarrhoea": 38.0, "constipation": 26.0},
    "FRA": {"nausea": 44.0, "vomiting": 53.0, "diarrhoea": 35.0, "constipation": 24.0},
    "ITA": {"nausea": 40.0, "vomiting": 48.0, "diarrhoea": 32.0, "constipation": 21.0},
    "ESP": {"nausea": 38.0, "vomiting": 46.0, "diarrhoea": 30.0, "constipation": 20.0},
    "JPN": {"nausea": 5_400.0, "vomiting": 6_600.0, "diarrhoea": 4_200.0,
            "constipation": 2_900.0},
    "CHN": {"nausea": 180.0, "vomiting": 220.0, "diarrhoea": 140.0, "constipation": 95.0},
    "BRA": {"nausea": 120.0, "vomiting": 145.0, "diarrhoea": 95.0, "constipation": 65.0},
    "IND": {"nausea": 900.0, "vomiting": 1_100.0, "diarrhoea": 720.0,
            "constipation": 480.0},
}

#: Incidence by therapy, so that no market ends up with some therapies priced
#: for adverse events and others silently at zero — the asymmetry M13 warns
#: about. Invented, and in the same range as the seeded trial figures so the
#: comparison is not distorted by the placeholders themselves.
AE_INCIDENCE: dict[str, dict[str, float]] = {
    "exenatide": {"nausea": 0.44, "vomiting": 0.13, "diarrhoea": 0.13,
                  "constipation": 0.10},
    "lixisenatide": {"nausea": 0.26, "vomiting": 0.10, "diarrhoea": 0.08,
                     "constipation": 0.07},
    "albiglutide": {"nausea": 0.11, "vomiting": 0.05, "diarrhoea": 0.13,
                    "constipation": 0.05},
    "retatrutide": {"nausea": 0.34, "vomiting": 0.16, "diarrhoea": 0.27,
                    "constipation": 0.14},
    "survodutide": {"nausea": 0.39, "vomiting": 0.24, "diarrhoea": 0.20,
                    "constipation": 0.16},
    "danuglipron": {"nausea": 0.32, "vomiting": 0.19, "diarrhoea": 0.14,
                    "constipation": 0.09},
    "efinopegdutide": {"nausea": 0.36, "vomiting": 0.21, "diarrhoea": 0.18,
                       "constipation": 0.11},
    # Existing seeded therapies with no profile. Without these, M13's
    # asymmetry warning fires on every obesity run — which is correct, and
    # unhelpful in a demo where the point is the comparison itself.
    "orlistat": {"diarrhoea": 0.27, "constipation": 0.03, "nausea": 0.04,
                 "vomiting": 0.02},
}

#: Trial windows the placeholder incidences are notionally observed over, so
#: M13's annualisation has something to do rather than passing them through.
AE_EXPOSURE_WEEKS = 68


def _source(what: str) -> str:
    return f"{TAG} — invented for demonstration, not an observed {what}. Do not cite."


# --------------------------------------------------------------------------- load


def _upsert_drug(session: Session, demo: DemoDrug) -> Drug:
    existing = session.scalars(
        select(Drug).where(Drug.drug_name == demo.name)
    ).one_or_none()
    if existing is not None:
        return existing

    drug = Drug(
        drug_name=demo.name, generic_name=demo.generic, company=demo.company,
        drug_class=demo.drug_class, route=demo.route,
        indication_id=demo.indication_id, is_comparator=True,
    )
    session.add(drug)
    session.flush()
    return drug


def _write_regimen(session: Session, drug: Drug, demo: DemoDrug) -> None:
    existing = session.scalars(
        select(DrugRegimen).where(DrugRegimen.drug_id == drug.drug_id)
    ).one_or_none()
    if existing is not None:
        return
    session.add(DrugRegimen(
        drug_id=drug.drug_id,
        dose_amount=Decimal(1), dose_unit="dose",
        units_per_admin=Decimal(1),
        admins_per_year=Decimal(str(demo.admins_per_year)),
        wastage_pct=Decimal(0),
        persistence_12m=Decimal(str(demo.persistence)),
        source=_source("regimen or persistence figure"),
        confidence_tier=TIER_D,
    ))


def _write_price(session: Session, drug: Drug, demo: DemoDrug) -> None:
    existing = session.scalars(
        select(DrugPrice)
        .where(DrugPrice.drug_id == drug.drug_id)
        .where(DrugPrice.country_code == REFERENCE_MARKET)
    ).first()
    if existing is not None:
        return
    session.add(DrugPrice(
        drug_id=drug.drug_id, country_code=REFERENCE_MARKET,
        price_local=Decimal(str(demo.unit_price)), currency_code="USD",
        price_basis="list", annual_cost_usd=Decimal(str(demo.annual_usd)),
        source=_source(f"price — set so annual acquisition lands near ${demo.annual_usd:,.0f}"),
        confidence_tier=TIER_D,
    ))


def _write_asset(session: Session, drug: Drug, demo: DemoDrug) -> None:
    existing = session.scalars(
        select(ComparatorAsset)
        .where(ComparatorAsset.source_id == demo.source_id)
        .where(ComparatorAsset.indication_id == demo.indication_id)
    ).one_or_none()
    if existing is not None:
        existing.drug_id = drug.drug_id
        return
    session.add(ComparatorAsset(
        source_id=demo.source_id, asset_name=demo.name,
        indication_id=demo.indication_id, target_symbol="GLP1R",
        target_id="ENSG00000112164", mechanism_of_action=demo.drug_class,
        action_type="AGONIST", pathway_ids=["R-HSA-420092"],
        drug_type="Small molecule" if demo.route == "oral" else "Protein",
        max_clinical_stage=demo.stage, competitor_class=demo.klass,
        relevance=Decimal("0.85"),
        rationale=f"{TAG} — registered by the demo loader, not by discovery",
        manufacturer=demo.company, route=demo.route, sponsor=demo.company,
        expected_entry_year=demo.entry_year,
        assumed_terminal_pct=(
            Decimal(str(demo.terminal_pct)) if demo.terminal_pct is not None else None
        ),
        drug_id=drug.drug_id, source=_source("registry record"),
        confidence_tier=TIER_D,
    ))


def _write_ae_costs(session: Session) -> int:
    written = 0
    for code, events in AE_UNIT_COSTS.items():
        country = session.get(Country, code)
        if country is None:
            continue
        for ae_code, amount in events.items():
            existing = session.scalars(
                select(AdverseEventCost)
                .where(AdverseEventCost.ae_code == ae_code)
                .where(AdverseEventCost.country_code == code)
            ).one_or_none()
            if existing is not None:
                continue
            session.add(AdverseEventCost(
                ae_code=ae_code, country_code=code,
                unit_cost_local=Decimal(str(amount)),
                currency_code=country.currency_code, cost_year=2026,
                source=_source("management cost"), confidence_tier=TIER_D,
            ))
            written += 1
    return written


def _write_ae_incidences(session: Session) -> int:
    written = 0
    for generic, events in AE_INCIDENCE.items():
        drug = session.scalars(
            select(Drug).where(Drug.generic_name.ilike(f"{generic}%"))
        ).first()
        if drug is None:
            drug = session.scalars(
                select(Drug).where(Drug.drug_name.ilike(f"%{generic}%"))
            ).first()
        if drug is None:
            continue

        for ae_code, incidence in events.items():
            existing = session.scalars(
                select(DrugAdverseEvent)
                .where(DrugAdverseEvent.drug_id == drug.drug_id)
                .where(DrugAdverseEvent.ae_code == ae_code)
            ).one_or_none()
            if existing is not None:
                continue
            session.add(DrugAdverseEvent(
                drug_id=drug.drug_id, ae_code=ae_code,
                incidence=Decimal(str(incidence)),
                exposure_weeks=AE_EXPOSURE_WEEKS,
                population=f"{TAG} — no real population; invented for demonstration",
                evidence_type="literature",
                source=_source("adverse-event incidence"),
                vintage_year=2026, confidence_tier=TIER_D,
            ))
            written += 1
    return written


def load() -> None:
    with session_scope() as session:
        drugs = 0
        for demo in DEMO_DRUGS:
            drug = _upsert_drug(session, demo)
            _write_regimen(session, drug, demo)
            _write_price(session, drug, demo)
            _write_asset(session, drug, demo)
            drugs += 1
        session.flush()

        costs = _write_ae_costs(session)
        incidences = _write_ae_incidences(session)

    print(f"loaded  {drugs} therapies (regimen + reference price + registry record)")
    print(f"        {costs} adverse-event unit costs")
    print(f"        {incidences} adverse-event incidences")
    print(f"\nEvery row is tier D and carries '{TAG}' in its source.")
    print("Run `python scripts/demo_data.py purge` to remove all of it.")


# --------------------------------------------------------------------------- purge


def purge() -> None:
    """Remove exactly what `load` wrote, matched on the source prefix.

    Order matters: children before the `drugs` rows they reference, and
    `comparator_assets.drug_id` cleared before those rows go, since it is a
    foreign key without a cascade.
    """
    like = f"{TAG}%"
    with session_scope() as session:
        drug_ids = [
            row[0] for row in session.execute(
                text("SELECT drug_id FROM drug_prices WHERE source LIKE :p"), {"p": like}
            )
        ]
        removed: dict[str, int] = {}
        for table in ("drug_adverse_events", "adverse_event_costs",
                      "drug_prices", "drug_regimens"):
            result = session.execute(
                text(f"DELETE FROM {table} WHERE source LIKE :p"), {"p": like},
            )
            removed[table] = result.rowcount or 0

        session.execute(
            text("DELETE FROM comparator_approvals WHERE asset_id IN "
                 "(SELECT asset_id FROM comparator_assets WHERE source LIKE :p)"),
            {"p": like},
        )
        result = session.execute(
            text("DELETE FROM comparator_assets WHERE source LIKE :p"), {"p": like},
        )
        removed["comparator_assets"] = result.rowcount or 0

        if drug_ids:
            binds = {f"d{i}": v for i, v in enumerate(drug_ids)}
            keys = ", ".join(f":{k}" for k in binds)
            session.execute(
                text(f"UPDATE comparator_assets SET drug_id = NULL "
                     f"WHERE drug_id IN ({keys})"), binds,
            )
            result = session.execute(
                text(f"DELETE FROM drugs WHERE drug_id IN ({keys})"), binds,
            )
            removed["drugs"] = result.rowcount or 0

    for table, count in removed.items():
        print(f"removed {count:>4} from {table}")


# --------------------------------------------------------------------------- status


def status() -> None:
    like = f"{TAG}%"
    with session_scope() as session:
        print(f"{'table':24} {'demo':>6} {'total':>7}")
        for table in ("drugs", "drug_regimens", "drug_prices",
                      "drug_adverse_events", "adverse_event_costs",
                      "comparator_assets"):
            total = session.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            if table == "drugs":
                demo = session.execute(text(
                    "SELECT count(*) FROM drugs WHERE drug_id IN "
                    "(SELECT drug_id FROM drug_prices WHERE source LIKE :p)"
                ), {"p": like}).scalar()
            else:
                demo = session.execute(
                    text(f"SELECT count(*) FROM {table} WHERE source LIKE :p"),
                    {"p": like},
                ).scalar()
            print(f"{table:24} {demo:>6} {total:>7}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("load", "purge", "status"))
    args = parser.parse_args()
    {"load": load, "purge": purge, "status": status}[args.command]()


if __name__ == "__main__":
    main()
