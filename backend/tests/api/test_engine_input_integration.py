"""End-to-end: persisted scenario -> EngineInput -> budget impact.

These are the only tests in the suite that need a live database, so they
skip cleanly without one rather than failing — every other test stays
offline (M0's `conftest.py` blocks sockets outright). What they cover is the
seam nothing else can: that the reference tables M0 populates actually
satisfy the contract M2-M9 expect, which unit tests with hand-built fixtures
cannot prove.

Every test rolls back. Nothing here writes to the database permanently.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from biet_api.dal import session_factory
from biet_api.models.scenario import Scenario
from biet_api.services.engine_input import EngineInputBuilder
from biet_engine.constants import PriceBasis
from biet_engine.impact import compute_budget_impact


def _database_available() -> bool:
    try:
        with session_factory() as probe:
            probe.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(),
    reason="needs the local PostgreSQL instance (see STATUS.md section 5.1)",
)


@pytest.fixture
def session() -> Iterator[Session]:
    """A session that always rolls back, so these tests never leave rows."""
    db = session_factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def scenario(session: Session) -> Scenario:
    row = Scenario(
        name="integration fixture",
        indication_id=1,                      # obesity
        asset_name="Test Asset",
        launch_year=2028,
        horizon_years=3,
        reporting_currency="EUR",
        country_codes=["DEU", "USA"],
    )
    session.add(row)
    session.flush()
    return row


def test_engine_input_builds_from_seeded_reference_data(
    session: Session, scenario: Scenario,
) -> None:
    engine_input, _ = EngineInputBuilder(session).build(scenario)

    assert [c.country_code for c in engine_input.countries] == ["DEU", "USA"]
    assert engine_input.horizon_years == 3
    assert engine_input.reporting_currency == "EUR"
    # The USD identity row plus the six quoted currencies (M0 section 5.5).
    assert len(engine_input.fx_rates) >= 7
    assert engine_input.fx_snapshot_date is not None


def test_every_resolved_value_carries_provenance(
    session: Session, scenario: Scenario,
) -> None:
    """Non-negotiable 8. A value that reached the engine without provenance
    would be untraceable in the export, which is the whole audit trail."""
    engine_input, _ = EngineInputBuilder(session).build(scenario)

    for country in engine_input.countries:
        for valued in (
            country.population_total, country.prevalence, country.gdp_pc_ppp,
            country.funnel.diagnosis_rate, country.funnel.treatment_rate,
            country.funnel.access_rate,
        ):
            assert valued.provenance.source
            assert valued.provenance.confidence_tier
            assert valued.provenance.resolution_level


def test_unpriced_market_falls_back_to_ppp_derivation(
    session: Session,
) -> None:
    """A market with no seeded price must derive one, and must say so — a
    derived price is a modelling assumption, not an observation (M5 5.3).

    USA, DEU and GBR now carry observed prices, so Japan is the market that
    exercises this path. If Japanese prices are ever seeded, move this to
    another unpriced market rather than deleting it.
    """
    row = Scenario(
        name="ppp fixture", indication_id=1, asset_name="Test Asset",
        launch_year=2028, horizon_years=3, reporting_currency="EUR",
        country_codes=["USA", "JPN"],
    )
    session.add(row)
    session.flush()

    engine_input, _ = EngineInputBuilder(session).build(row)
    by_code = {c.country_code: c for c in engine_input.countries}

    assert by_code["USA"].new_therapy.price_basis is not PriceBasis.PPP_DERIVED
    assert by_code["JPN"].new_therapy.price_basis is PriceBasis.PPP_DERIVED
    assert "parity" in by_code["JPN"].new_therapy.price_provenance.source.lower()


def test_observed_price_beats_derivation_where_one_is_seeded(
    session: Session, scenario: Scenario,
) -> None:
    """Germany now has an observed list price, so it should not be deriving
    one. (The UK likewise, but this fixture's markets are DEU and USA.)"""
    engine_input, _ = EngineInputBuilder(session).build(scenario)
    by_code = {c.country_code: c for c in engine_input.countries}

    assert by_code["DEU"].new_therapy.price_basis is PriceBasis.LIST


def test_market_mixing_observed_and_derived_prices_is_flagged(
    session: Session, scenario: Scenario,
) -> None:
    """The comparison stops being like-for-like the moment one therapy in a
    market is observed and another is derived: the derived side inherits the
    reference market's price level, and the impact can flip sign. The result
    still stands, but the reader has to be told."""
    _, warnings = EngineInputBuilder(session).build(scenario)

    flagged = {
        w.country_code for w in warnings if w.code == "MIXED_PRICE_BASIS"
    }
    # DEU has an observed Wegovy price but PPP-derived comparators.
    assert "DEU" in flagged
    # The USA is observed throughout, so there is nothing to flag.
    assert "USA" not in flagged


def test_default_criterion_stack_has_no_enabled_correlated_pair(
    session: Session, scenario: Scenario,
) -> None:
    """M3 section 5.4: enabling both halves of a correlated pair raises in
    strict mode, so the default stack must not do it."""
    engine_input, _ = EngineInputBuilder(session).build(scenario)

    for country in engine_input.countries:
        enabled = {c.code for c in country.criteria if c.enabled}
        for criterion in country.criteria:
            if criterion.enabled:
                assert not (set(criterion.correlated_with) & enabled)
        # The disabled half is still present as an available choice.
        assert len(country.criteria) > len(enabled)


def test_full_chain_produces_a_budget_impact(
    session: Session, scenario: Scenario,
) -> None:
    """The whole point: persisted rows through to an incremental number."""
    engine_input, _ = EngineInputBuilder(session).build(scenario)
    result = compute_budget_impact(engine_input)

    assert result.reporting_currency == "EUR"
    assert len(result.countries) == 2
    assert len(result.totals.by_year) == 3
    assert result.totals.cumulative.currency == "EUR"
    # A launch into an established class costs money; a zero here would mean
    # the funnel or the uptake collapsed to nothing.
    assert result.totals.cumulative.amount > 0


def test_budget_impact_is_incremental_not_gross(
    session: Session, scenario: Scenario,
) -> None:
    """CLAUDE.md's most important rule. The impact must be world-with minus
    world-without, so it has to come out strictly below the gross cost of
    treating those patients — the difference being the displaced care."""
    engine_input, _ = EngineInputBuilder(session).build(scenario)
    result = compute_budget_impact(engine_input)

    for country_result in result.countries:
        country = next(
            c for c in engine_input.countries
            if c.country_code == country_result.country_code
        )
        annual_gross = (
            country.new_therapy.unit_price.amount
            * country.new_therapy.regimen.units_per_admin.value
            * country.new_therapy.regimen.admins_per_year.value
        )
        for year in country_result.years:
            gross = annual_gross * year.patients_on_new
            assert year.budget_impact.amount < gross


def test_funnel_is_monotonic_on_real_data(
    session: Session, scenario: Scenario,
) -> None:
    engine_input, _ = EngineInputBuilder(session).build(scenario)
    result = compute_budget_impact(engine_input)

    for country_result in result.countries:
        values = [stage.value for stage in country_result.funnel.stages]
        assert all(values[i] >= values[i + 1] for i in range(len(values) - 1))
