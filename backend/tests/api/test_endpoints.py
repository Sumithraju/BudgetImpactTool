"""API contract tests — M1 section 10's "API" class.

These run against the real app with a real database, since the endpoints
exist to expose data the fixtures cannot fake. They skip without one, like
the other integration tests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from biet_api.dal import session_factory
from biet_api.main import create_app


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

VALID = {
    "name": "test scenario", "indication_id": 1, "asset_name": "Test Asset",
    "launch_year": 2028, "horizon_years": 3, "reporting_currency": "EUR",
    "country_codes": ["USA", "DEU"],
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def scenario_id(client: TestClient) -> Iterator[str]:
    created = client.post("/api/v1/scenarios", json=VALID)
    assert created.status_code == 201, created.text
    sid = created.json()["scenario_id"]
    yield sid
    client.delete(f"/api/v1/scenarios/{sid}")      # archive, never hard-delete


def test_health(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_reference_endpoints_serve_the_seeded_data(client: TestClient) -> None:
    assert len(client.get("/api/v1/reference/countries").json()) == 10
    assert len(client.get("/api/v1/reference/indications").json()) == 2
    assert client.get("/api/v1/reference/parameter-paths").json()


def test_create_returns_201_with_a_location_header(client: TestClient) -> None:
    r = client.post("/api/v1/scenarios", json=VALID)
    assert r.status_code == 201
    assert r.headers["Location"].endswith(r.json()["scenario_id"])
    client.delete(f"/api/v1/scenarios/{r.json()['scenario_id']}")


def test_unknown_market_is_422_naming_the_offender(client: TestClient) -> None:
    r = client.post("/api/v1/scenarios", json={**VALID, "country_codes": ["ZZZ"]})
    assert r.status_code == 422
    assert "ZZZ" in r.text


def test_unknown_indication_is_422(client: TestClient) -> None:
    r = client.post("/api/v1/scenarios", json={**VALID, "indication_id": 999})
    assert r.status_code == 422


def test_override_outside_its_range_is_422_naming_the_path(client: TestClient) -> None:
    r = client.post("/api/v1/scenarios", json={
        **VALID,
        "overrides": [{"parameter_path": "funnel.diagnosis_rate", "value": 5.0}],
    })
    assert r.status_code == 422
    assert "funnel.diagnosis_rate" in r.text


def test_unknown_parameter_path_is_422(client: TestClient) -> None:
    r = client.post("/api/v1/scenarios", json={
        **VALID, "overrides": [{"parameter_path": "funnel.invented", "value": 0.5}],
    })
    assert r.status_code == 422
    assert "funnel.invented" in r.text


def test_missing_scenario_is_404(client: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/scenarios/{missing}").status_code == 404


def test_every_error_carries_the_envelope_and_a_request_id(client: TestClient) -> None:
    r = client.get("/api/v1/scenarios/00000000-0000-0000-0000-000000000000")
    body = r.json()
    assert body["error"]["code"] and body["error"]["message"]
    assert body["request_id"]
    assert r.headers["X-Request-ID"]


def test_calculate_returns_an_incremental_result(client: TestClient, scenario_id: str) -> None:
    r = client.post(f"/api/v1/scenarios/{scenario_id}/calculate")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["totals"]["currency"] == "EUR"
    assert body["totals"]["cumulative"] > 0
    assert len(body["countries"]) == 2
    assert len(body["totals"]["by_year"]) == 3
    # Persisted by default, so the run stays reproducible.
    assert body["run_id"]


def test_calculate_carries_provenance_on_every_funnel_stage(
    client: TestClient, scenario_id: str,
) -> None:
    body = client.post(f"/api/v1/scenarios/{scenario_id}/calculate").json()
    for country in body["countries"]:
        for stage in country["funnel"]:
            assert stage["provenance"]["source"]
            assert stage["provenance"]["confidence_tier"]


def test_calculate_can_skip_persistence(client: TestClient, scenario_id: str) -> None:
    body = client.post(
        f"/api/v1/scenarios/{scenario_id}/calculate", params={"persist": False},
    ).json()
    assert body["run_id"] is None


def test_owsa_bars_bracket_the_base_case(client: TestClient, scenario_id: str) -> None:
    body = client.get(f"/api/v1/scenarios/{scenario_id}/owsa").json()
    for entry in body["entries"]:
        low, high = sorted((entry["result_at_low"], entry["result_at_high"]))
        assert low <= body["base_result"] <= high


def test_psa_returns_a_binned_histogram(client: TestClient, scenario_id: str) -> None:
    body = client.get(
        f"/api/v1/scenarios/{scenario_id}/psa", params={"iterations": 500},
    ).json()
    assert body["iterations"] == 500
    assert sum(body["histogram"]) == 500
    assert body["p2_5"] <= body["median"] <= body["p97_5"]


def test_clone_copies_overrides_and_sets_the_parent(client: TestClient) -> None:
    created = client.post("/api/v1/scenarios", json={
        **VALID,
        "overrides": [{"parameter_path": "funnel.diagnosis_rate", "value": 0.42}],
    }).json()
    clone = client.post(
        f"/api/v1/scenarios/{created['scenario_id']}/clone", json={},
    ).json()

    assert clone["parent_scenario_id"] == created["scenario_id"]
    assert clone["name"].endswith("(copy)")
    assert clone["is_baseline"] is False
    assert [o["parameter_path"] for o in clone["overrides"]] == ["funnel.diagnosis_rate"]

    for sid in (created["scenario_id"], clone["scenario_id"]):
        client.delete(f"/api/v1/scenarios/{sid}")


def test_baseline_is_exclusive_within_an_indication(client: TestClient) -> None:
    first = client.post("/api/v1/scenarios", json=VALID).json()
    second = client.post("/api/v1/scenarios", json=VALID).json()

    client.post(f"/api/v1/scenarios/{first['scenario_id']}/baseline")
    client.post(f"/api/v1/scenarios/{second['scenario_id']}/baseline")

    assert client.get(f"/api/v1/scenarios/{first['scenario_id']}").json()["is_baseline"] is False
    assert client.get(f"/api/v1/scenarios/{second['scenario_id']}").json()["is_baseline"] is True

    for s in (first, second):
        client.delete(f"/api/v1/scenarios/{s['scenario_id']}")


def test_archive_is_soft_and_leaves_the_row_readable(client: TestClient) -> None:
    created = client.post("/api/v1/scenarios", json=VALID).json()
    assert client.delete(f"/api/v1/scenarios/{created['scenario_id']}").status_code == 204

    # Still readable — archived, not deleted (M1 section 12).
    after = client.get(f"/api/v1/scenarios/{created['scenario_id']}")
    assert after.status_code == 200
    assert after.json()["is_archived"] is True


def test_replacing_overrides_swaps_the_whole_set(client: TestClient, scenario_id: str) -> None:
    client.put(f"/api/v1/scenarios/{scenario_id}/overrides", json={
        "overrides": [{"parameter_path": "funnel.access_rate", "value": 0.5}],
    })
    body = client.put(f"/api/v1/scenarios/{scenario_id}/overrides", json={
        "overrides": [{"parameter_path": "uptake.year_1", "value": 0.09}],
    }).json()

    # Replaced, not merged — the first override is gone.
    assert [o["parameter_path"] for o in body["overrides"]] == ["uptake.year_1"]


def test_an_override_actually_changes_the_answer(client: TestClient, scenario_id: str) -> None:
    before = client.post(
        f"/api/v1/scenarios/{scenario_id}/calculate", params={"persist": False},
    ).json()["totals"]["cumulative"]

    client.put(f"/api/v1/scenarios/{scenario_id}/overrides", json={
        "overrides": [{"parameter_path": "funnel.treatment_rate", "value": 0.46}],
    })
    after = client.post(
        f"/api/v1/scenarios/{scenario_id}/calculate", params={"persist": False},
    ).json()["totals"]["cumulative"]

    # Doubling the treatment rate roughly doubles the addressable population.
    assert after > before * 1.5


def test_runs_history_and_snapshot_are_retrievable(
    client: TestClient, scenario_id: str,
) -> None:
    client.post(f"/api/v1/scenarios/{scenario_id}/calculate")
    runs = client.get(f"/api/v1/scenarios/{scenario_id}/runs").json()
    assert runs and runs[0]["run_type"] == "forward"

    detail = client.get(f"/api/v1/runs/{runs[0]['run_id']}").json()
    # The snapshot is what makes a run reproducible — resolved inputs, the
    # FX set they were converted with, and the results they produced.
    assert detail["input_snapshot"]["countries"]
    assert detail["fx_snapshot"]["date"]
    assert detail["results"]["totals"]["cumulative"] > 0


def test_solver_reports_the_binding_market(client: TestClient, scenario_id: str) -> None:
    body = client.post(
        f"/api/v1/scenarios/{scenario_id}/solve", json={"target_ratio": 0.01},
    ).json()

    assert body["binding_market"]
    assert body["entries"]
    # The corridor is only as wide as its narrowest market, so the global
    # ceiling equals the binding market's own ceiling.
    binding = next(
        e for e in body["entries"] if e["country_code"] == body["binding_market"]
    )
    assert body["single_global_price_ceiling_usd"] == pytest.approx(
        binding["max_unit_price_usd"]
    )
    for entry in body["entries"]:
        if entry["feasible"] and entry["max_unit_price_usd"] is not None:
            assert entry["max_unit_price_usd"] >= body["single_global_price_ceiling_usd"]


def test_compare_diffs_only_what_actually_differs(client: TestClient) -> None:
    plain = client.post("/api/v1/scenarios", json=VALID).json()
    varied = client.post("/api/v1/scenarios", json={
        **VALID,
        "overrides": [{"parameter_path": "funnel.treatment_rate", "value": 0.40}],
    }).json()

    body = client.post("/api/v1/scenarios/compare", json={
        "scenario_ids": [plain["scenario_id"], varied["scenario_id"]],
    }).json()

    assert len(body["results"]) == 2
    # Only the one differing assumption is reported; listing every identical
    # one would bury the handful that matter.
    assert [d["parameter_path"] for d in body["diff"]] == ["funnel.treatment_rate"]
    # A higher treatment rate must produce a larger impact.
    assert body["results"][1]["totals"]["cumulative"] > body["results"][0]["totals"]["cumulative"]

    for s in (plain, varied):
        client.delete(f"/api/v1/scenarios/{s['scenario_id']}")


def test_compare_rejects_a_single_scenario(client: TestClient, scenario_id: str) -> None:
    r = client.post("/api/v1/scenarios/compare", json={"scenario_ids": [scenario_id]})
    assert r.status_code == 422


def test_compare_rejects_mixed_indications(client: TestClient) -> None:
    obesity = client.post("/api/v1/scenarios", json=VALID).json()
    diabetes = client.post("/api/v1/scenarios", json={
        **VALID, "indication_id": 2, "name": "diabetes scenario",
    }).json()

    r = client.post("/api/v1/scenarios/compare", json={
        "scenario_ids": [obesity["scenario_id"], diabetes["scenario_id"]],
    })
    assert r.status_code == 409          # a conflict, not a validation failure

    for s in (obesity, diabetes):
        client.delete(f"/api/v1/scenarios/{s['scenario_id']}")
