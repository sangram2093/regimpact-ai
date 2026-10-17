import asyncio
import json
from time import perf_counter

from app.ai.adk_ask import AdkAskTransport
from app.ai.google_client import GoogleGenAITransport, VertexEmbeddingClient
from app.ai.transport import ModelResponse
from app.api import workbench


def test_total_workflow_deadline_includes_initial_call_and_one_repair(
    client,
    session_headers,
    monkeypatch,
):
    class Transport:
        model = "injected-timeout-model"
        calls = 0
        cancelled = False

        async def complete(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                await asyncio.sleep(0.035)
                return ModelResponse("malformed output")
            try:
                await asyncio.sleep(10)
            finally:
                self.cancelled = True

    transport = Transport()
    client.app.state.workflows.transport = transport
    monkeypatch.setattr(workbench, "OPERATION_DEADLINE_SECONDS", 0.09)
    started = perf_counter()
    response = client.post(
        "/api/v1/workflows/risk-map/run",
        headers=session_headers,
        json={"mandate_id": "M-GIFT", "change_id": "CHANGE-GIFT"},
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "OPERATION_TIMEOUT"
    assert transport.calls == 2 and transport.cancelled
    assert perf_counter() - started < 0.5
    assert client.app.state.sessions.snapshot(session_headers["X-Demo-Session"]).runs == {}


def test_ask_total_deadline_includes_input_agent_and_output_screening(
    client,
    session_headers,
    monkeypatch,
):
    class Screen:
        calls = 0
        cancelled = False

        async def allow(self, text, *, is_response=False):
            self.calls += 1
            try:
                await asyncio.sleep(0.035 if not is_response else 10)
                return True
            finally:
                if is_response:
                    self.cancelled = True

    class Transport:
        model = "injected-timeout-model"
        calls = 0

        async def select_facts(self, question, tools):
            self.calls += 1
            await asyncio.sleep(0.035)
            result = tools.get_change_impact("CHANGE-GIFT")
            return ModelResponse(json.dumps({"fact_ids": [f["fact_id"] for f in result["facts"]]}))

    screen, transport = Screen(), Transport()
    client.app.state.ask.screen = screen
    client.app.state.ask.transport = transport
    monkeypatch.setattr(workbench, "OPERATION_DEADLINE_SECONDS", 0.12)
    response = client.post(
        "/api/v1/ask",
        headers=session_headers,
        json={"question": "Explain gift impact", "scenario_id": "SCENARIO-MAS-2023"},
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "OPERATION_TIMEOUT"
    assert transport.calls == 1 and screen.calls == 2 and screen.cancelled
    assert client.app.state.sessions.snapshot(session_headers["X-Demo-Session"]).runs == {}


def test_retrieval_timeout_cancels_before_any_structured_model_call(
    client,
    session_headers,
    monkeypatch,
):
    class Candidates:
        embedding_client = object()
        cancelled = False

        async def retrieve(self, mandate_id):
            try:
                await asyncio.sleep(10)
            finally:
                self.cancelled = True

    class Transport:
        model = "injected-timeout-model"
        calls = 0

        async def complete(self, **kwargs):
            self.calls += 1
            raise AssertionError("Deadline should prevent model generation")

    retrieval, transport = Candidates(), Transport()
    client.app.state.candidates = retrieval
    client.app.state.workflows.transport = transport
    monkeypatch.setattr(workbench, "OPERATION_DEADLINE_SECONDS", 0.05)
    response = client.post(
        "/api/v1/workflows/policy-map/run",
        headers=session_headers,
        json={"mandate_id": "M-GIFT", "change_id": "CHANGE-GIFT"},
    )
    assert response.status_code == 504
    assert retrieval.cancelled and transport.calls == 0


def test_provider_and_agent_deadlines_leave_room_for_api_overhead():
    assert GoogleGenAITransport(client=None, model="explicit-model").timeout_seconds == 40
    assert VertexEmbeddingClient(client=None).timeout_seconds == 40
    assert AdkAskTransport(client=None, model="explicit-model").timeout_seconds == 40
    assert workbench.OPERATION_DEADLINE_SECONDS == 50
