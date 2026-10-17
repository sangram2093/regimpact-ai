from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app


def confirmation(client: TestClient, change: str, classification: str) -> dict:
    data = client.get(f"/api/v1/changes/{change}").json()["data"]
    return {
        "classification": classification,
        "role": "Regulatory Specialist",
        "reviewer": "Scenario specialist",
        "rationale": "Reviewed baseline and proposal evidence; "
        "prospective interpretation confirmed.",
        "evidence_ids": [e["id"] for e in data["baseline_evidence"] + data["proposal_evidence"]],
    }


def test_sources_do_not_claim_missing_pdf_is_extracted(
    client: TestClient, session_headers: dict
) -> None:
    sources = client.get("/api/v1/sources").json()["data"]["sources"]
    assert {s["legal_status"] for s in sources} == {"IN_FORCE", "PROPOSED"}
    for source in sources:
        if not source["can_ingest"]:
            result = client.post(f"/api/v1/sources/{source['id']}/ingest", headers=session_headers)
            assert result.status_code == 409
            assert result.json()["error"]["code"] == "SOURCE_PDF_UNAVAILABLE"
            # A pinned expected checksum does not mean PDF bytes were extracted.
            assert not source["ingestion_status"].startswith("EXTRACTED_")
            assert source["segment_count"] == 0


def test_specialist_resolves_unknown_without_mutating_baseline(
    client: TestClient, session_headers: dict
) -> None:
    before = client.app.state.repository.snapshot().model_dump_json()
    payload = confirmation(client, "CHANGE-IDENTITY", "MODIFIED")
    result = client.post(
        "/api/v1/changes/CHANGE-IDENTITY/classify", headers=session_headers, json=payload
    )
    assert result.status_code == 200
    assert result.json()["data"]["classification"] == "MODIFIED"
    assert result.json()["data"]["safety_checks"]["human_change_confirmed"]
    metrics = client.get(
        "/api/v1/changes/SCENARIO-MAS-2023/delta-review", headers=session_headers
    ).json()["data"]["metrics"]
    assert metrics["unresolved_items"] == 0
    assert metrics["carry_forward_candidates"] == 0
    assert client.app.state.repository.snapshot().model_dump_json() == before
    assert (
        client.get("/api/v1/changes/CHANGE-IDENTITY").json()["data"]["classification"]
        == "UNRESOLVED"
    )
    assert (
        client.post(
            "/api/v1/changes/CHANGE-IDENTITY/classify", headers=session_headers, json=payload
        ).json()["data"]
        == result.json()["data"]
    )


@pytest.mark.parametrize(
    "classification,code", [("UNCHANGED", "UNSAFE_UNCHANGED"), ("NEW", "INVALID_CLASSIFICATION")]
)
def test_human_cannot_bypass_carry_forward_or_baseline_identity(
    client: TestClient, session_headers: dict, classification: str, code: str
) -> None:
    payload = confirmation(client, "CHANGE-GIFT", classification)
    result = client.post(
        "/api/v1/changes/CHANGE-GIFT/classify", headers=session_headers, json=payload
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == code


def test_classification_requires_all_evidence_and_specialist(
    client: TestClient, session_headers: dict
) -> None:
    payload = confirmation(client, "CHANGE-GIFT", "MODIFIED")
    incomplete = payload | {"evidence_ids": ["EV-UNKNOWN"]}
    assert (
        client.post(
            "/api/v1/changes/CHANGE-GIFT/classify", headers=session_headers, json=incomplete
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/changes/CHANGE-GIFT/classify",
            headers=session_headers,
            json=payload | {"role": "Policy Owner"},
        ).status_code
        == 422
    )


def test_removed_obligation_cannot_receive_new_policy_mapping(
    client: TestClient, session_headers: dict
) -> None:
    payload = confirmation(client, "CHANGE-GIFT", "REMOVED")
    result = client.post(
        "/api/v1/changes/CHANGE-GIFT/classify", headers=session_headers, json=payload
    )
    assert result.status_code == 200
    base = "/api/v1/mandates/M-GIFT"
    candidates = client.get(base + "/policy-candidates", headers=session_headers).json()["data"]
    assert not candidates["mapping_allowed"]
    assert "retirement" in candidates["mapping_block_reason"]
    result = client.post(
        base + "/policy-mapping",
        headers=session_headers,
        json={
            "policy_id": "PR-GIFT-01",
            "decision": "APPROVE",
            "reviewer": "Policy owner",
            "role": "Policy Owner",
            "rationale": "Review retirement while preserving baseline history.",
        },
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "RETIREMENT_REVIEW_REQUIRED"


def test_control_review_freezes_its_change_interpretation(
    client: TestClient, session_headers: dict
) -> None:
    assessments = client.get(
        "/api/v1/changes/CHANGE-GIFT/impact-assessments", headers=session_headers
    ).json()["data"]["assessments"]
    result = client.post(
        f"/api/v1/impact-assessments/{assessments[0]['id']}/review",
        headers=session_headers,
        json={
            "decision": "APPROVE",
            "role": "Policy Owner",
            "reviewer": "Owner",
            "rationale": "Confirmed the prospective gift control scope.",
        },
    )
    assert result.status_code == 200
    result = client.post(
        "/api/v1/changes/CHANGE-GIFT/classify",
        headers=session_headers,
        json=confirmation(client, "CHANGE-GIFT", "REMOVED"),
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "MAPPING_ALREADY_REVIEWED"
    assert (
        client.get("/api/v1/changes/CHANGE-GIFT", headers=session_headers).json()["data"][
            "classification"
        ]
        == "MODIFIED"
    )


def test_new_mapping_is_session_scoped_human_gated_and_prospective(
    client: TestClient, session_headers: dict
) -> None:
    before = client.app.state.repository.snapshot().model_dump_json()
    base = "/api/v1/mandates/M-INTENT-CONSENT"
    mapping = {
        "policy_id": "PR-CONSENT-01",
        "decision": "APPROVE",
        "reviewer": "Policy owner",
        "role": "Policy Owner",
        "rationale": "Prospective policy is relevant; a control objective remains required.",
    }
    result = client.get(base + "/policy-candidates", headers=session_headers).json()["data"]
    assert not result["mapping_allowed"]
    assert all(c["vector_rank"] is None for c in result["candidates"])
    assert (
        client.post(base + "/policy-mapping", json=mapping, headers=session_headers).status_code
        == 409
    )
    payload = confirmation(client, "CHANGE-INTENT-CONSENT", "NEW")
    assert (
        client.post(
            "/api/v1/changes/CHANGE-INTENT-CONSENT/classify", json=payload, headers=session_headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            base + "/policy-mapping",
            json=mapping | {"policy_id": "MADE-UP"},
            headers=session_headers,
        ).status_code
        == 422
    )
    result = client.post(base + "/policy-mapping", json=mapping, headers=session_headers)
    assert result.status_code == 200
    assert result.json()["data"]["review_status"] == "SCENARIO_APPROVED"
    assert not result.json()["data"]["mapping_allowed"]
    impact_path = "/api/v1/changes/CHANGE-INTENT-CONSENT/impact"
    assert (
        client.get(impact_path, headers=session_headers).json()["data"]["coverage"]
        == "NO_POLICY_MAPPING"
    )
    prospective = client.get(
        impact_path + "?include_scenario=true", headers=session_headers
    ).json()["data"]
    assert prospective["coverage"] == "PARTIAL"
    assert len(prospective["controls"]) == 0
    assert prospective["edges"][0]["status"] == "SCENARIO_APPROVED"
    explanation = client.get(
        "/api/v1/edges/SCENARIO-MAPPING-M-INTENT-CONSENT/explain", headers=session_headers
    ).json()["data"]
    assert explanation["provenance"]["decision_source"] == "HUMAN_REVIEW"
    assert explanation["provenance"]["agent_run_id"]
    assert client.get("/api/v1/edges/SCENARIO-MAPPING-M-INTENT-CONSENT/explain").status_code == 404
    assert client.app.state.repository.snapshot().model_dump_json() == before
    metrics = client.get("/api/v1/dashboard", headers=session_headers).json()["data"]["metrics"]
    assert metrics["existing_mapping_items"] == 6
    client.post("/api/v1/demo/reset", headers=session_headers)
    assert (
        client.get(impact_path + "?include_scenario=true", headers=session_headers).json()["data"][
            "coverage"
        ]
        == "NO_POLICY_MAPPING"
    )


def test_workflows_do_not_invent_live_results_and_runs_are_private(
    client: TestClient, session_headers: dict
) -> None:
    result = client.post("/api/v1/workflows/interpret/run", json={}, headers=session_headers)
    assert result.status_code == 200
    run = result.json()["data"]
    assert run["status"] == "BLOCKED"
    assert run["model"] is None and run["attempts"] == 0
    detail = client.get(f"/api/v1/workflows/runs/{run['id']}", headers=session_headers).json()[
        "data"
    ]
    assert detail["output"] is None
    assert detail["status"] == "AI_NOT_CONFIGURED"
    assert client.get(f"/api/v1/workflows/runs/{run['id']}").status_code == 404


def test_ask_grounded_answer_and_unsupported_question(
    client: TestClient, session_headers: dict
) -> None:
    config = client.get("/api/v1/ask/config").json()["data"]
    result = client.post(
        "/api/v1/ask", json={"question": config["suggested_questions"][0]}, headers=session_headers
    ).json()["data"]
    assert result["grounded"]
    assert result["verified_references"] == result["total_references"] > 0
    assert result["run"]["kind"] == "LOCAL_DETERMINISTIC"
    assert result["run"]["model"] is None
    assert "PROPOSED" in result["answer"].upper()
    assert result["citations"]
    unknown = client.post(
        "/api/v1/ask",
        json={"question": "Predict tomorrow's stock market prices"},
        headers=session_headers,
    ).json()["data"]
    assert not unknown["grounded"]


def test_budget_survives_demo_reset_and_reserved_id_is_rejected(tmp_path: Path) -> None:
    settings = Settings(mode="local", ai_calls_per_minute=1, session_db=tmp_path / "sessions.db")
    headers = {"X-Demo-Session": str(uuid4())}
    with TestClient(create_app(settings)) as client:
        assert (
            client.post(
                "/api/v1/ask", json={"question": "Explain the gift proposal"}, headers=headers
            ).status_code
            == 200
        )
        client.post("/api/v1/demo/reset", headers=headers)
        assert (
            client.post(
                "/api/v1/ask", json={"question": "Explain the gift proposal"}, headers=headers
            ).status_code
            == 429
        )
        assert (
            client.post(
                "/api/v1/demo/reset",
                headers={"X-Demo-Session": "00000000-0000-0000-0000-000000000000"},
            ).status_code
            == 422
        )
    with TestClient(create_app(settings)) as restarted:
        assert (
            restarted.post(
                "/api/v1/ask", json={"question": "Explain the gift proposal"}, headers=headers
            ).status_code
            == 429
        )


def test_classification_persists_across_local_restart(tmp_path: Path) -> None:
    settings = Settings(mode="local", session_db=tmp_path / "sessions.db")
    headers = {"X-Demo-Session": str(uuid4())}
    with TestClient(create_app(settings)) as client:
        payload = confirmation(client, "CHANGE-IDENTITY", "MODIFIED")
        client.post("/api/v1/changes/CHANGE-IDENTITY/classify", json=payload, headers=headers)
    with TestClient(create_app(settings)) as client:
        assert (
            client.get("/api/v1/changes/CHANGE-IDENTITY", headers=headers).json()["data"][
                "classification"
            ]
            == "MODIFIED"
        )
