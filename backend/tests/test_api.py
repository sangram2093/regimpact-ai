from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import create_app

SCENARIO_PATH = "/api/v1/changes/SCENARIO-MAS-2023"
REVIEW_PATH = "/api/v1/assessments/ASSESS-E-GIFT-POLICY/review"
REVIEW = {
    "decision": "APPROVE",
    "reviewer": "Demo reviewer",
    "role": "Policy Owner",
    "rationale": "Prospective mapping remains relevant; channel scope needs assessment.",
}


def test_health_is_honest_and_has_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    payload = response.json()
    assert response.status_code == 200
    assert payload["data"]["ai_status"] == "NOT_CONNECTED_SEED_MODE"
    assert payload["meta"]["mode"] == "local"
    assert payload["meta"]["request_id"] == response.headers["X-Request-ID"]
    UUID(payload["meta"]["request_id"])
    assert response.headers["Cache-Control"] == "no-store"


def test_dashboard_counts_real_edges_and_preserves_proposal(client: TestClient) -> None:
    dashboard = client.get("/api/v1/dashboard").json()["data"]
    metrics = dashboard["metrics"]
    assert metrics["existing_mapping_items"] == 6
    assert metrics["individual_rechecks"] == 6
    assert metrics["unresolved_items"] == 3
    assert metrics["carry_forward_candidates"] == 0
    assert metrics["new_obligations"] == 1
    assert metrics["review_reduction"] is None
    assert dashboard["run"]["model"] is None
    assert dashboard["scenario"]["status"] == "PROPOSED"
    assert dashboard["impact_summary"]["controls"] == 3
    assert dashboard["impact_summary"]["coverage_gaps"] == 1


def test_gift_evidence_and_direct_impact_path(client: TestClient) -> None:
    change = client.get("/api/v1/changes/CHANGE-GIFT").json()["data"]
    assert change["classification"] == "MODIFIED"
    assert change["baseline_evidence"][0]["text_kind"] == "PARAPHRASE"
    assert change["baseline_evidence"][0]["verification_status"] == "VERIFIED_PRIMARY_SOURCE"
    assert "PROPOSED" in change["proposal_notice"]
    assert change["legal_force_after"] == "PROPOSED_BINDING"
    impact = client.get("/api/v1/changes/CHANGE-GIFT/impact").json()["data"]
    assert impact["coverage"] == "COMPLETE"
    assert {c["id"] for c in impact["controls"]} == {"CO-GIFT-01", "CO-GIFT-02"}
    assert not any(n["type"] in {"RISK_TYPE", "RISK_DRIVER"} for n in impact["nodes"])
    assert "CO-IDENTITY-01" not in {n["id"] for n in impact["nodes"]}
    assert "Conduct risk" in impact["risk_tags"]


def test_new_obligation_exposes_gap_without_implied_approval(client: TestClient) -> None:
    impact = client.get("/api/v1/changes/CHANGE-INTENT-CONSENT/impact").json()["data"]
    assert impact["coverage"] == "NO_POLICY_MAPPING"
    assert impact["controls"] == []
    assert impact["edges"] == []
    assert impact["nodes"][0]["status"] == "PROPOSED"
    assert impact["gap_reason"]


def test_explanation_has_no_invented_model_or_retrieval(client: TestClient) -> None:
    explanation = client.get("/api/v1/edges/E-GIFT-POLICY/explain").json()["data"]
    assert explanation["status"] == "APPROVED"
    assert explanation["provenance"]["decision_source"] == "GOLDEN_LABELS"
    for field in (
        "model",
        "prompt_version",
        "vector_rank",
        "lexical_rank",
        "rrf_score",
        "reviewed_at",
    ):
        assert explanation["provenance"][field] is None
    assert explanation["catalog_relationship"] is False
    catalog = client.get("/api/v1/edges/E-GIFT-CONTROL-01/explain").json()["data"]
    assert catalog["catalog_relationship"] is True
    assert catalog["evidence"] == []


def test_review_is_idempotent_session_isolated_and_baseline_immutable(
    client: TestClient, session_headers: dict[str, str]
) -> None:
    original = client.app.state.repository.snapshot().model_dump_json()
    response = client.post(REVIEW_PATH, json=REVIEW, headers=session_headers)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "SCENARIO_APPROVED"
    duplicate = client.post(REVIEW_PATH, json=REVIEW, headers=session_headers)
    assert duplicate.json()["data"] == response.json()["data"]
    other_headers = {"X-Demo-Session": str(uuid4())}
    other = client.get(SCENARIO_PATH + "/delta-review", headers=other_headers).json()["data"]
    assert other["metrics"]["completed_rechecks"] == 0
    own = client.get(SCENARIO_PATH + "/delta-review", headers=session_headers).json()["data"]
    assert own["metrics"]["completed_rechecks"] == 1
    assert own["metrics"]["review_reduction"] is None
    assert client.app.state.repository.snapshot().model_dump_json() == original
    explain = client.get("/api/v1/edges/E-GIFT-POLICY/explain", headers=session_headers).json()[
        "data"
    ]
    assert explain["status"] == "APPROVED"
    assert explain["scenario_status"] == "SCENARIO_APPROVED"


def test_reset_only_affects_requesting_session(
    client: TestClient, session_headers: dict[str, str]
) -> None:
    other = {"X-Demo-Session": str(uuid4())}
    client.post(REVIEW_PATH, json=REVIEW, headers=session_headers)
    client.post(REVIEW_PATH, json=REVIEW | {"decision": "REJECT"}, headers=other)
    assert client.post("/api/v1/demo/reset", headers=session_headers).json()["data"] == {
        "reset": True
    }
    assert (
        client.get(SCENARIO_PATH + "/delta-review", headers=session_headers).json()["data"][
            "metrics"
        ]["completed_rechecks"]
        == 0
    )
    assert (
        client.get(SCENARIO_PATH + "/delta-review", headers=other).json()["data"]["metrics"][
            "completed_rechecks"
        ]
        == 1
    )


def test_conflicting_review_fails(client: TestClient, session_headers: dict[str, str]) -> None:
    client.post(REVIEW_PATH, json=REVIEW, headers=session_headers)
    response = client.post(
        REVIEW_PATH, json=REVIEW | {"decision": "REJECT"}, headers=session_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DECISION_ALREADY_RECORDED"


def test_role_gate_is_relationship_specific(
    client: TestClient, session_headers: dict[str, str]
) -> None:
    risk_path = "/api/v1/assessments/ASSESS-E-GIFT-RISK/review"
    wrong = client.post(risk_path, json=REVIEW, headers=session_headers)
    assert wrong.status_code == 403
    assert wrong.json()["error"]["code"] == "REVIEW_ROLE_MISMATCH"
    correct = client.post(
        risk_path, json=REVIEW | {"role": "Risk Steward"}, headers=session_headers
    )
    assert correct.status_code == 200
    assert correct.json()["data"]["required_role"] == "Risk Steward"


def test_unresolved_change_cannot_be_approved_as_a_mapping(
    client: TestClient, session_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/assessments/ASSESS-E-IDENTITY-POLICY/review", json=REVIEW, headers=session_headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHANGE_REVIEW_REQUIRED"


def test_no_unsafe_carry_forward_even_with_specialist_role(
    client: TestClient, session_headers: dict[str, str]
) -> None:
    response = client.post(
        SCENARIO_PATH + "/acknowledge-carry-forward",
        headers=session_headers,
        json={"reviewer": "Specialist", "role": "Regulatory Specialist"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_ELIGIBLE_CARRY_FORWARD"


@pytest.mark.parametrize("path", [REVIEW_PATH, "/api/v1/demo/reset"])
def test_writes_require_session(client: TestClient, path: str) -> None:
    response = client.post(path, json=REVIEW if path == REVIEW_PATH else None)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SESSION_REQUIRED"


def test_invalid_header_and_body_are_typed(
    client: TestClient, session_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/dashboard", headers={"X-Demo-Session": "malformed"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SESSION"
    response = client.post(REVIEW_PATH, json=REVIEW | {"rationale": "   "}, headers=session_headers)
    assert response.status_code == 422
    assert response.json()["error"]["details"]
    assert response.json()["meta"]["request_id"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/changes/unknown",
        "/api/v1/edges/unknown/explain",
        "/api/v1/changes/unknown/impact",
        "/api/v1/not-a-route",
    ],
)
def test_missing_entities_are_typed_errors(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"]
    assert "Traceback" not in response.text


def test_cloud_mode_fails_without_serving_seed() -> None:
    with pytest.raises(RuntimeError, match="will not silently substitute local fixtures"):
        create_app(Settings(mode="gcp"))


def test_openapi_contains_typed_envelopes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "RegImpact AI"
    operation = schema["paths"][REVIEW_PATH.replace("ASSESS-E-GIFT-POLICY", "{assessment_id}")][
        "post"
    ]
    assert "403" in operation["responses"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "ReviewRequest"
    )


def test_session_validation_also_applies_to_stateless_routes(client: TestClient) -> None:
    response = client.get("/api/v1/changes/CHANGE-GIFT/impact", headers={"X-Demo-Session": "bad"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SESSION"


def test_unhandled_failure_does_not_leak_details(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(Settings(mode="local"))

    def failing_dashboard(session_id: str | None):
        raise RuntimeError("private diagnostic content")

    monkeypatch.setattr(app.state.scenarios, "dashboard", failing_dashboard)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/v1/dashboard")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.headers["X-Request-ID"] == response.json()["meta"]["request_id"]
    assert "private diagnostic" not in response.text
