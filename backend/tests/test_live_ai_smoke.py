"""Offline smoke-harness tests. No ADC, real provider or public HTTP is used."""

import asyncio
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from app.ai.transport import ModelResponse

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "live_ai_smoke.py"
SPEC = importlib.util.spec_from_file_location("regimpact_live_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def direct_config(**kwargs):
    return smoke.SmokeConfig(
        project="regimpact-ai",
        checks="direct",
        vertex_location="global",
        model="explicit-test-model",
        embedding_model="explicit-test-embedding",
        allow_ai_calls=True,
        **kwargs,
    )


def api_config(**kwargs):
    return smoke.SmokeConfig(
        project="regimpact-ai",
        checks="api",
        api_url="https://smoke.test",
        expected_api_mode="local",
        **kwargs,
    )


def test_plan_has_no_network_and_unauthorized_project_is_rejected():
    def forbidden(*args):
        raise AssertionError("Plan must never construct a live client")

    report = asyncio.run(
        smoke.run(smoke.SmokeConfig(project="regimpact-ai"), vertex_client_factory=forbidden)
    )
    assert report["status"] == "NOT_RUN" and report["maximum_ai_requests"] == 0
    with pytest.raises(smoke.SmokeFailure, match="UNAUTHORIZED_PROJECT"):
        asyncio.run(smoke.run(smoke.SmokeConfig(project="unrelated-project")))


def test_live_calls_require_explicit_permissions_and_complete_model_configuration():
    with pytest.raises(smoke.SmokeFailure, match="EXPLICIT_AI_PERMISSION"):
        replace(direct_config(), allow_ai_calls=False).validate()
    with pytest.raises(smoke.SmokeFailure, match="EXPLICIT_AI_PERMISSION"):
        asyncio.run(smoke.direct_smoke(smoke.SmokeConfig(project="regimpact-ai")))
    with pytest.raises(smoke.SmokeFailure, match="MODELS_AND_DEMO_WRITE"):
        api_config(allow_ai_calls=True, model="explicit", allow_demo_writes=True).validate()
    with pytest.raises(smoke.SmokeFailure, match="MODEL_ARMOR_PROJECT_MISMATCH"):
        direct_config(armor_template="projects/unrelated/locations/global/templates/a").validate()
    with pytest.raises(smoke.SmokeFailure, match="EXPLICIT_HTTPS_API_ORIGIN"):
        replace(api_config(), api_url="https://user:credential@smoke.test").validate()


def test_api_two_session_idempotency_reset_and_baseline_provenance(client):
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="https://smoke.test"
        ) as http:
            return await smoke.run(api_config(allow_demo_writes=True), api_client=http)

    report = asyncio.run(exercise())
    assert report["status"] == "PASSED", report
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["api_two_session_reset"]["baseline_unchanged"]
    assert checks["api_two_session_reset"]["idempotent"]
    assert checks["api_health_lineage"]["mode"] == "local"
    assert len(checks["api_request_correlation"]["request_ids"]) >= 15
    assert report["maximum_ai_requests"] == 0


def test_api_readonly_mode_never_writes_or_calls_models(client):
    paths = []

    class TrackingClient:
        def __init__(self, http):
            self.http = http

        async def request(self, method, path, **kwargs):
            paths.append((method, path))
            return await self.http.request(method, path, **kwargs)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="https://smoke.test"
        ) as http:
            return await smoke.run(api_config(), api_client=TrackingClient(http))

    report = asyncio.run(exercise())
    assert report["status"] == "PASSED"
    assert all(method == "GET" for method, _ in paths)
    assert not any("policy-candidates" in path or path.endswith("/ask") for _, path in paths)
    assert (
        next(c for c in report["checks"] if c["name"] == "api_two_session_reset")["status"]
        == "NOT_RUN"
    )


def test_api_failure_preserves_partial_evidence_and_attempts_fresh_session_cleanup(client):
    reset_sessions = []
    review_count = 0

    class FailingClient:
        def __init__(self, http):
            self.http = http

        async def request(self, method, path, **kwargs):
            nonlocal review_count
            if path.endswith("/review") and method == "POST":
                review_count += 1
                if review_count == 2:
                    raise RuntimeError("Bearer secret-credential must never be printed")
            if path.endswith("/demo/reset"):
                reset_sessions.append(kwargs["headers"]["X-Demo-Session"])
                return httpx.Response(503)
            return await self.http.request(method, path, **kwargs)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="https://smoke.test"
        ) as http:
            return await smoke.run(
                api_config(allow_demo_writes=True), api_client=FailingClient(http)
            )

    report = asyncio.run(exercise())
    assert report["status"] == "FAILED"
    checks = {c["name"]: c for c in report["checks"]}
    assert checks["api_health_lineage"]["status"] == "PASSED"
    assert checks["api_session_cleanup"]["status"] == "FAILED"
    assert len(reset_sessions) == 1 and UUID(reset_sessions[0]).version == 4
    assert checks["api_session_cleanup"]["session_id"] == reset_sessions[0]
    assert checks["api_request_correlation"]["request_ids"]
    assert checks["api_e2e"]["code"] == "API_CHECK_FAILED"
    assert "secret-credential" not in json.dumps(report)


def test_api_rejects_silent_local_mode_substitution(client):
    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="https://smoke.test"
        ) as http:
            return await smoke.run(replace(api_config(), expected_api_mode="gcp"), api_client=http)

    report = asyncio.run(exercise())
    assert report["status"] == "FAILED"
    assert report["checks"][-1]["code"] == "API_MODE_MISMATCH"


@pytest.mark.parametrize("provider_version", ["actual-injected-version", None])
def test_direct_uses_explicit_models_real_validators_and_sanitized_provenance(
    monkeypatch, provider_version
):
    from app.ai import adk_ask

    calls = []
    closed = []

    async def embed_content(**kwargs):
        calls.append(("embedding", kwargs))
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.25] * 768)])

    async def generate_content(**kwargs):
        calls.append(("structured", kwargs))
        context = json.loads(kwargs["contents"])["data"]
        segment = context["evidence"][0]
        return SimpleNamespace(
            text=json.dumps(
                {
                    "decision": "RECOMMEND",
                    "candidate_id": context["candidates"][0]["id"],
                    "alternative_ids": [],
                    "reason": "Injected test recommendation, never a live model claim.",
                    "evidence": [{"segment_id": segment["id"], "source_id": segment["source_id"]}],
                }
            ),
            usage_metadata=None,
            model_version=provider_version,
        )

    async def close():
        closed.append(True)

    def factory(project, location):
        assert (project, location) == ("regimpact-ai", "global")
        return SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    embed_content=embed_content, generate_content=generate_content
                ),
                aclose=close,
            )
        )

    class AskTransport:
        def __init__(self, *, client, model):
            self.model = model

        async def select_facts(self, question, tools):
            result = tools.get_change_impact("CHANGE-GIFT")
            return ModelResponse(
                json.dumps({"fact_ids": [f["fact_id"] for f in result["facts"]]}),
                model_version=provider_version,
                model_calls=2,
            )

    monkeypatch.setattr(adk_ask, "AdkAskTransport", AskTransport)
    report = asyncio.run(smoke.run(direct_config(), vertex_client_factory=factory))
    assert report["status"] == ("PASSED" if provider_version else "PARTIAL"), report
    assert closed == [True] and len(calls) == 2
    assert calls[0][1]["model"] == "explicit-test-embedding"
    assert calls[0][1]["config"].output_dimensionality == 768
    assert calls[1][1]["model"] == "explicit-test-model"
    assert report["maximum_ai_requests"] == 7
    assert report["checks"][1]["provider_model_version"] == provider_version
    assert report["checks"][2]["verified_references"] > 0
    assert "Injected test recommendation" not in json.dumps(report)
    assert "input_tokens" not in json.dumps(report)


def test_provider_failure_is_sanitized_with_no_substitute():
    def factory(project, location):
        raise RuntimeError("private credential and provider response")

    report = asyncio.run(smoke.run(direct_config(), vertex_client_factory=factory))
    assert report["status"] == "FAILED"
    assert len(report["checks"]) == 1
    assert report["checks"][0]["code"] == "PROVIDER_CHECK_FAILED"
    assert "private credential" not in json.dumps(report)


def test_existing_report_is_rejected_before_any_operation(tmp_path, monkeypatch):
    output = tmp_path / "existing.json"
    output.write_text("preserve", encoding="utf-8")

    async def forbidden(*args):
        raise AssertionError("No checks may run after an output path conflict")

    monkeypatch.setattr(smoke, "run", forbidden)
    with pytest.raises(SystemExit):
        smoke.main(["--project", "regimpact-ai", "--output", str(output)])
    assert output.read_text(encoding="utf-8") == "preserve"
