"""Final-instrument TRM scenario: computed safe reuse, routing and mode-specific wording."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.adapters.local_json import LocalJsonRepository
from app.config.scenarios import TRM_2021
from app.config.settings import Settings
from app.main import create_server

TRM = {"X-RegImpact-Scenario": "trm-2021"}


@pytest.fixture
def server(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(
        create_server(Settings(mode="local", enable_live_ai=False, runtime_dir=tmp_path))
    ) as test_client:
        yield test_client


def headers(**extra: str) -> dict[str, str]:
    return {"X-Demo-Session": str(uuid4()), **TRM, **extra}


def test_trm_bundle_is_a_final_instrument_scenario() -> None:
    bundle = LocalJsonRepository(Settings().data_dir, TRM_2021).snapshot()
    assert bundle.scenario.status == "FINAL"
    assert all(not change.is_proposal for change in bundle.changes)
    assert {e.text_kind for e in bundle.evidence} == {"VERIFIED_EXCERPT"}
    counts = {
        label: sum(c.classification == label for c in bundle.changes)
        for label in ("UNCHANGED", "MODIFIED", "REMOVED", "NEW")
    }
    assert counts == {"UNCHANGED": 19, "MODIFIED": 14, "REMOVED": 1, "NEW": 2}
    # A one-word strengthening must never be treated as unchanged.
    strengthened = next(c for c in bundle.changes if c.id == "CHANGE-TRM-13-4-1")
    assert strengthened.classification == "MODIFIED"
    assert "STRENGTHENED" in strengthened.change_nature


def test_router_defaults_to_mas_and_rejects_unknown_scenarios(server: TestClient) -> None:
    assert server.get("/api/v1/dashboard").json()["data"]["scenario"]["id"] == "SCENARIO-MAS-2023"
    trm = server.get("/api/v1/dashboard", headers=TRM).json()["data"]
    assert trm["scenario"]["id"] == "SCENARIO-TRM-2021"
    unknown = server.get("/api/v1/dashboard", headers={"X-RegImpact-Scenario": "nope"})
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "SCENARIO_NOT_FOUND"
    listing = server.get("/api/v1/scenarios").json()["data"]
    assert [item["key"] for item in listing] == ["mas-2023", "trm-2021"]


def test_safe_reuse_is_computed_then_confirmed_by_bulk_acknowledgement(
    server: TestClient,
) -> None:
    request = headers()
    path = "/api/v1/changes/SCENARIO-TRM-2021/delta-review"
    metrics = server.get(path, headers=request).json()["data"]["metrics"]
    assert metrics["existing_mapping_items"] == 102
    assert metrics["carry_forward_candidates"] == 57
    assert metrics["individual_rechecks"] == 45
    assert metrics["new_obligations"] == 2
    assert metrics["estimated_review_reduction"] == 54.9
    assert metrics["review_reduction"] is None
    response = server.post(
        "/api/v1/changes/SCENARIO-TRM-2021/acknowledge-carry-forward",
        headers=request,
        json={"reviewer": "Demo reviewer", "role": "Regulatory Specialist"},
    )
    assert response.status_code == 200
    confirmed = response.json()["data"]["metrics"]
    assert confirmed["acknowledged_mappings"] == 57
    assert confirmed["review_reduction"] == 54.9
    # The MAS scenario in the same browser session is unaffected.
    mas = server.get(
        "/api/v1/changes/SCENARIO-MAS-2023/delta-review",
        headers={"X-Demo-Session": request["X-Demo-Session"]},
    ).json()["data"]["metrics"]
    assert mas["carry_forward_candidates"] == 0


def test_final_mode_change_detail_and_ask_do_not_use_proposal_wording(
    server: TestClient,
) -> None:
    detail = server.get("/api/v1/changes/CHANGE-TRM-13-4-1", headers=headers()).json()["data"]
    assert detail["scenario_status"] == "FINAL"
    assert detail["legal_force_after"] == "GUIDANCE"
    assert detail["legal_force_note"].startswith("Both texts are MAS guidelines")
    assert [e["paragraph_ref"] for e in detail["proposal_evidence"]] == ["13.4.1"]
    config = server.get("/api/v1/ask/config", headers=headers()).json()["data"]
    assert any("adversarial" in q for q in config["suggested_questions"])
