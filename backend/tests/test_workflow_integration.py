import json

from fastapi.testclient import TestClient

from app.ai.transport import ModelResponse
from app.services.ai_workflows import BoundedWorkflowService


class MappingTransport:
    model = "injected-test-model"

    def __init__(self, no_suitable: bool = False):
        self.context = None
        self.no_suitable = no_suitable

    async def complete(self, **kwargs):
        self.context = kwargs["context"]
        return ModelResponse(
            json.dumps(
                {
                    "decision": "NO_SUITABLE_CANDIDATE" if self.no_suitable else "RECOMMEND",
                    "candidate_id": None if self.no_suitable else "PR-CONSENT-01",
                    "alternative_ids": [],
                    "reason": "Policy addresses permission before marketing contact.",
                    "evidence": [
                        {
                            "source_id": "MAS-P002-2023",
                            "segment_id": "SEG-CP-CONSENT",
                            "excerpt": None,
                        }
                    ],
                }
            ),
            100,
            20,
            "injected-test-model-v1",
        )


def test_ai_recommendation_reaches_mapping_review_and_preserves_run(
    client: TestClient, session_headers: dict
):
    transport = MappingTransport()
    client.app.state.workflows = BoundedWorkflowService(transport)
    result = client.post(
        "/api/v1/workflows/policy-map/run",
        json={"mandate_id": "M-INTENT-CONSENT"},
        headers=session_headers,
    )
    assert result.status_code == 200
    run = result.json()["data"]
    assert run["status"] == "SUCCEEDED"
    candidate = client.get(
        "/api/v1/mandates/M-INTENT-CONSENT/policy-candidates", headers=session_headers
    ).json()["data"]
    assert len(candidate["candidates"]) == 1
    assert candidate["candidates"][0]["id"] == "PR-CONSENT-01"
    assert candidate["run"]["id"] == run["id"]
    assert not candidate["mapping_allowed"]
    runs = client.get("/api/v1/workflows/runs", headers=session_headers).json()["data"]["runs"]
    assert len({r["id"] for r in runs}) == len(runs)
    detail = client.get(f"/api/v1/workflows/runs/{run['id']}", headers=session_headers).json()[
        "data"
    ]
    assert detail["output"]["candidate_id"] == "PR-CONSENT-01"
    assert len(transport.context["candidates"]) <= 8


def test_no_suitable_recommendation_keeps_gap_without_selectable_alternatives(
    client: TestClient, session_headers: dict
):
    client.app.state.workflows = BoundedWorkflowService(MappingTransport(no_suitable=True))
    client.post(
        "/api/v1/workflows/policy-map/run",
        json={"mandate_id": "M-INTENT-CONSENT"},
        headers=session_headers,
    )
    data = client.get(
        "/api/v1/mandates/M-INTENT-CONSENT/policy-candidates", headers=session_headers
    ).json()["data"]
    assert data["candidates"] == []
    assert not data["mapping_allowed"]
    assert data["review_status"] == "NO_SUITABLE_CANDIDATE"


def test_live_interpretation_cannot_use_curated_paraphrases_as_pdf(
    client: TestClient, session_headers: dict
):
    transport = MappingTransport()
    client.app.state.workflows = BoundedWorkflowService(transport)
    result = client.post("/api/v1/workflows/interpret/run", json={}, headers=session_headers)
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "SOURCE_EXTRACTION_REQUIRED"
    assert transport.context is None
