"""The criterion reference endpoint, and the rule it duplicates.

`GET /reference/criteria` recomputes the default-enabled stack rather than
importing it from `EngineInputBuilder._build_criteria`, so that the endpoint
stays a plain read of reference data. That duplication is the thing worth
testing: the two must not drift, or the interface would offer a stack the
engine does not build, and every funnel figure would be explained by a
criterion set that never ran.
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
    not _database_available(), reason="needs the database"
)

OBESITY = 1


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def test_serves_the_seeded_stack_before_any_run(client: TestClient) -> None:
    """The point of the endpoint: criteria are choosable before a calculation.

    Read from the interface's position — nothing has been run, so nothing can
    be read out of a result."""
    rows = client.get(f"/api/v1/reference/criteria?indication_id={OBESITY}").json()
    assert rows, "obesity seeds a criterion stack"
    codes = {r["criterion_code"] for r in rows}
    assert {"bmi_ge_30", "bmi_ge_35", "cv_comorbidity"} <= codes

    for row in rows:
        assert 0.0 < row["default_factor"] <= 1.0
        assert row["confidence_tier"] in {"A", "B", "C", "D"}
        assert row["source"], "a factor without a source is not auditable"


def test_enabled_matches_what_the_engine_would_build(client: TestClient) -> None:
    """The duplication guard.

    A criterion is enabled unless it correlates with one already enabled, so
    two clinically overlapping restrictions are never multiplied together.
    Asserted as the invariant rather than against fixed codes, so it still
    holds when the seed adds a criterion."""
    rows = client.get(f"/api/v1/reference/criteria?indication_id={OBESITY}").json()

    enabled: set[str] = set()
    blocked: set[str] = set()
    for row in rows:  # rows arrive in criterion_id order, which the rule needs
        code = row["criterion_code"]
        expected = code not in blocked
        assert row["enabled"] is expected, (
            f"{code}: endpoint says enabled={row['enabled']}, the engine's rule "
            f"says {expected} — the two have drifted"
        )
        if expected:
            enabled.add(code)
            blocked.update(row["correlated_with"])

    assert enabled, "a stack with nothing enabled would narrow to zero"


def test_the_held_out_half_is_still_reported(client: TestClient) -> None:
    """A criterion the default stack skips stays in the payload.

    It is an available choice the scenario has not taken, and hiding it would
    make the interface look like the restriction does not exist."""
    rows = client.get(f"/api/v1/reference/criteria?indication_id={OBESITY}").json()
    correlated = [r for r in rows if r["correlated_with"]]
    assert correlated, "obesity seeds at least one correlated pair"
    assert any(not r["enabled"] for r in correlated), (
        "one half of a correlated pair must be held out, and still reported"
    )


def test_each_indication_gets_its_own_stack(client: TestClient) -> None:
    obesity = client.get(f"/api/v1/reference/criteria?indication_id={OBESITY}").json()
    diabetes = client.get("/api/v1/reference/criteria?indication_id=2").json()
    assert diabetes, "type 2 diabetes seeds its own criteria"
    assert {r["criterion_code"] for r in obesity} != {
        r["criterion_code"] for r in diabetes
    }, "two diseases sharing a criterion stack would be a seeding error"


# --------------------------------------------------------------- negative


def test_missing_indication_is_422_not_a_silent_default(client: TestClient) -> None:
    """Defaulting to a disease nobody asked for would be worse than refusing."""
    assert client.get("/api/v1/reference/criteria").status_code == 422


def test_non_numeric_indication_is_422(client: TestClient) -> None:
    assert (
        client.get("/api/v1/reference/criteria?indication_id=abc").status_code == 422
    )


@pytest.mark.parametrize("indication_id", [999, 0, -1])
def test_unknown_indication_is_an_empty_stack(
    client: TestClient, indication_id: int
) -> None:
    """Empty rather than 404, matching `/reference/subgroups`.

    An indication with no seeded criteria is a gap in the reference data, not
    a bad request — and the interface renders an empty section for it either
    way."""
    response = client.get(
        f"/api/v1/reference/criteria?indication_id={indication_id}"
    )
    assert response.status_code == 200
    assert response.json() == []


def test_a_factor_override_is_range_checked(client: TestClient) -> None:
    """The factor is a share. Outside (0, 1] it is not a narrowing at all —
    above 1 it would widen the funnel past its own denominator."""
    created = client.post(
        "/api/v1/scenarios",
        json={
            "name": "criterion range check",
            "indication_id": OBESITY,
            "asset_name": "test asset",
            "launch_year": 2028,
            "horizon_years": 3,
            "reporting_currency": "EUR",
            "country_codes": ["DEU"],
            "perspective": "health_system",
        },
    )
    assert created.status_code == 201, created.text
    sid = created.json()["scenario_id"]
    try:
        for bad in (1.5, 0, -0.2):
            rejected = client.put(
                f"/api/v1/scenarios/{sid}/overrides",
                json={
                    "overrides": [
                        {
                            "parameter_path": "criteria.bmi_ge_35.factor",
                            "value": bad,
                        }
                    ]
                },
            )
            assert rejected.status_code == 422, f"{bad} should be refused"

        accepted = client.put(
            f"/api/v1/scenarios/{sid}/overrides",
            json={
                "overrides": [
                    {"parameter_path": "criteria.bmi_ge_35.factor", "value": 0.2}
                ]
            },
        )
        assert accepted.status_code == 200, accepted.text
    finally:
        client.delete(f"/api/v1/scenarios/{sid}")


# ------------------------------------------- identifiers inside a path


def _scenario(client: TestClient, **kw: object) -> dict:
    body = {
        "name": "identifier check",
        "indication_id": OBESITY,
        "asset_name": "test asset",
        "launch_year": 2028,
        "horizon_years": 3,
        "reporting_currency": "EUR",
        "country_codes": ["DEU"],
        "perspective": "health_system",
        **kw,
    }
    return client.post("/api/v1/scenarios", json=body)


def test_unknown_subgroup_is_refused_not_silently_dropped(
    client: TestClient,
) -> None:
    """A segment code naming nothing used to be dropped, and the run then
    modelled the whole diagnosed population while the request asked for a
    subset — a wrong denominator reported as a correct answer."""
    refused = _scenario(client, subgroup_codes=["not_a_real_subgroup"])
    assert refused.status_code == 422, refused.text
    assert "not_a_real_subgroup" in refused.text


def test_a_real_subgroup_still_narrows(client: TestClient) -> None:
    created = _scenario(client, subgroup_codes=["diabesity"])
    assert created.status_code == 201, created.text
    sid = created.json()["scenario_id"]
    try:
        whole = _scenario(client)
        assert whole.status_code == 201
        wid = whole.json()["scenario_id"]
        try:
            narrowed = client.post(f"/api/v1/scenarios/{sid}/calculate", json={})
            everyone = client.post(f"/api/v1/scenarios/{wid}/calculate", json={})
            assert narrowed.status_code == 200, narrowed.text
            assert everyone.status_code == 200, everyone.text
            a = narrowed.json()["countries"][0]["funnel"][-1]["value"]
            b = everyone.json()["countries"][0]["funnel"][-1]["value"]
            assert a < b, "a subgroup must narrow the funnel, not reproduce it"
        finally:
            client.delete(f"/api/v1/scenarios/{wid}")
    finally:
        client.delete(f"/api/v1/scenarios/{sid}")


@pytest.mark.parametrize(
    "path",
    [
        "criteria.no_such_criterion.factor",
        "subgroup.no_such_subgroup.share",
        "therapy.999999.price_local",
    ],
)
def test_override_naming_a_missing_row_is_refused(
    client: TestClient, path: str
) -> None:
    """The path templates are regexes over `[A-Za-z0-9_]+`, so a misspelled
    identifier matched the vocabulary, stored, and was then skipped by the
    engine — which only iterates seeded rows. Accepted and inert is the worst
    of both."""
    created = _scenario(client)
    assert created.status_code == 201, created.text
    sid = created.json()["scenario_id"]
    try:
        refused = client.put(
            f"/api/v1/scenarios/{sid}/overrides",
            json={"overrides": [{"parameter_path": path, "value": 0.5}]},
        )
        assert refused.status_code == 422, f"{path} should be refused"
    finally:
        client.delete(f"/api/v1/scenarios/{sid}")


def test_substitution_naive_is_not_read_as_a_drug_id(client: TestClient) -> None:
    """`substitution.naive` shares its shape with `substitution.<drug_id>`.
    The literal must not be looked up as an identifier."""
    created = _scenario(client)
    assert created.status_code == 201, created.text
    sid = created.json()["scenario_id"]
    try:
        accepted = client.put(
            f"/api/v1/scenarios/{sid}/overrides",
            json={
                "overrides": [
                    {"parameter_path": "substitution.naive", "value": 0.4}
                ]
            },
        )
        assert accepted.status_code == 200, accepted.text
    finally:
        client.delete(f"/api/v1/scenarios/{sid}")
