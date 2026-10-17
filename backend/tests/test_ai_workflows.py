import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from app.ai.contracts import OUTPUT_SCHEMAS
from app.ai.google_client import GoogleGenAITransport, VertexEmbeddingClient, create_vertex_client
from app.ai.transport import ModelResponse
from app.domain.errors import DomainError
from app.services.ai_workflows import BoundedWorkflowService


def context() -> dict:
    return {
        "sources": [{"id": "SOURCE-1"}],
        "segments": [
            {
                "id": "SEGMENT-1",
                "source_id": "SOURCE-1",
                "text": "Gift offers should not unduly influence customers.",
                "text_kind": "VERIFIED_EXCERPT",
            }
        ],
        "candidates": [{"id": "PR-1", "type": "POLICY_REQUIREMENT"}],
        "mandates": [{"id": "M-1"}],
        "entity_ids": ["M-1", "PR-1"],
        "high_confidence_pcs_target": False,
        "applicable_global_overlay": False,
    }


def evidence() -> list[dict]:
    return [{"source_id": "SOURCE-1", "segment_id": "SEGMENT-1", "excerpt": "Gift offers"}]


def policy() -> dict:
    return {
        "decision": "RECOMMEND",
        "candidate_id": "PR-1",
        "alternative_ids": [],
        "reason": "This policy addresses the gift safeguard.",
        "evidence": evidence(),
    }


class FakeTransport:
    model = "injected-test-model"

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = list(responses)
        self.calls = []

    async def complete(self, **kwargs) -> ModelResponse:
        self.calls.append(kwargs)
        output = self.responses.pop(0)
        if isinstance(output, Exception):
            raise output
        return ModelResponse(output, 20, 10, "injected-test-version")


def test_bounded_workflow_success_records_provenance_and_never_approves() -> None:
    transport = FakeTransport([json.dumps(policy())])
    result = asyncio.run(BoundedWorkflowService(transport).run("policy-map", context()))
    assert result.status == "HUMAN_REVIEW_REQUIRED"
    assert result.run.attempts == 1
    assert result.run.model == "injected-test-model"
    assert result.run.provider_model_version == "injected-test-version"
    assert result.run.prompt_version == "policy-map-v1"
    assert result.run.input_tokens == 20 and result.run.output_tokens == 10
    assert len(result.run.input_sha256) == 64 and len(result.run.output_sha256) == 64
    assert result.run.candidate_ids == ("PR-1",)
    assert "approved" not in result.output


def test_one_repair_receives_validation_errors_then_succeeds() -> None:
    transport = FakeTransport(["not JSON", json.dumps(policy())])
    result = asyncio.run(BoundedWorkflowService(transport).run("policy-map", context()))
    assert result.status == "HUMAN_REVIEW_REQUIRED"
    assert len(transport.calls) == 2
    assert transport.calls[0]["repair_errors"] == ()
    assert transport.calls[1]["repair_errors"]
    assert result.run.input_tokens == 40


@pytest.mark.parametrize(
    "mutation",
    [
        lambda output: output.update(candidate_id="INVENTED"),
        lambda output: output["evidence"][0].update(source_id="INVENTED"),
        lambda output: output["evidence"][0].update(segment_id="INVENTED"),
        lambda output: output["evidence"][0].update(excerpt="This is already binding"),
        lambda output: output.update(alternative_ids=["PR-1"]),
    ],
)
def test_invalid_mapping_or_evidence_fails_after_exactly_one_repair(mutation) -> None:
    output = policy()
    mutation(output)
    transport = FakeTransport([json.dumps(output), json.dumps(output), json.dumps(policy())])
    result = asyncio.run(BoundedWorkflowService(transport).run("policy-map", context()))
    assert result.status == "MANUAL_REVIEW_REQUIRED"
    assert result.output is None
    assert len(transport.calls) == 2
    assert len(transport.responses) == 1


def test_source_must_exist_separately_from_segment() -> None:
    inputs = context()
    inputs["sources"] = []
    transport = FakeTransport([json.dumps(policy())] * 2)
    result = asyncio.run(BoundedWorkflowService(transport).run("policy-map", inputs))
    assert result.status == "MANUAL_REVIEW_REQUIRED"


def test_paraphrase_can_be_referenced_but_not_quoted() -> None:
    inputs = context()
    inputs["segments"][0]["text_kind"] = "PARAPHRASE"
    transport = FakeTransport([json.dumps(policy())] * 2)
    assert asyncio.run(BoundedWorkflowService(transport).run("policy-map", inputs)).output is None
    output = policy()
    output["evidence"][0]["excerpt"] = None
    transport = FakeTransport([json.dumps(output)])
    assert (
        asyncio.run(BoundedWorkflowService(transport).run("policy-map", inputs)).output is not None
    )


def test_unchanged_cannot_bypass_global_scope_or_missing_blocker_check() -> None:
    output = {
        "classification": "UNCHANGED",
        "no_effect_result": "NO_EFFECT_SUPPORTED",
        "reason": "The content appears unchanged in this test.",
        "evidence": evidence(),
    }
    for blocker in (True, None):
        inputs = context()
        if blocker is None:
            del inputs["applicable_global_overlay"]
        else:
            inputs["applicable_global_overlay"] = blocker
        result = asyncio.run(
            BoundedWorkflowService(FakeTransport([json.dumps(output)] * 2)).run(
                "change-effect", inputs
            )
        )
        assert result.status == "MANUAL_REVIEW_REQUIRED"


def test_transport_failure_is_not_retried_or_replaced_by_fixture() -> None:
    transport = FakeTransport([TimeoutError("sensitive internal message")])
    result = asyncio.run(BoundedWorkflowService(transport).run("policy-map", context()))
    assert result.output is None
    assert len(transport.calls) == 1
    assert "sensitive internal" not in result.model_dump_json()


def test_no_transport_honestly_reports_no_inference() -> None:
    result = asyncio.run(BoundedWorkflowService().run("interpret", context()))
    assert result.status == "AI_NOT_CONFIGURED"
    assert result.run.model is None and result.run.attempts == 0
    assert result.output is None


def test_all_six_structured_contracts_are_executable() -> None:
    outputs = {
        "interpret": {
            "mandates": [
                {
                    "text": "Prevent gifts from unduly influencing purchases.",
                    "applicability": "Public prospecting",
                    "legal_force": "GUIDANCE",
                    "evidence": evidence(),
                }
            ]
        },
        "risk-map": {
            "selected_risk_type_id": None,
            "selected_risk_driver_ids": [],
            "reason": "No risk catalog candidates are suitable.",
            "evidence": evidence(),
        },
        "policy-map": policy(),
        "pcs-extract": {
            "statements": [
                {
                    "text": "A prospective gift safeguard is proposed.",
                    "target_mandate_ids": ["M-1"],
                    "instrument_wide": False,
                    "legal_force_after": "PROPOSED_BINDING",
                    "evidence": evidence(),
                }
            ]
        },
        "change-effect": {
            "classification": "MODIFIED",
            "no_effect_result": "EFFECT_POSSIBLE",
            "reason": "The proposal alters the scope of the safeguard.",
            "evidence": evidence(),
        },
        "impact-explain": {
            "claims": [
                {
                    "text": "This proposed change may affect the mapped policy.",
                    "entity_ids": ["M-1", "PR-1"],
                    "legal_status": "PROPOSED",
                    "evidence": evidence(),
                }
            ]
        },
    }
    assert set(outputs) == set(OUTPUT_SCHEMAS)
    for name, output in outputs.items():
        inputs = context()
        if name == "impact-explain":
            inputs["allowed_claims"] = output["claims"]
        result = asyncio.run(
            BoundedWorkflowService(FakeTransport([json.dumps(output)])).run(name, inputs)
        )
        assert result.status == "HUMAN_REVIEW_REQUIRED", name


def test_unknown_workflow_and_unbounded_candidates_rejected_before_model() -> None:
    service = BoundedWorkflowService(FakeTransport([]))
    with pytest.raises(DomainError, match="Unknown bounded"):
        asyncio.run(service.run("approve", context()))
    inputs = context()
    inputs["candidates"] *= 9
    with pytest.raises(DomainError, match="at most eight"):
        asyncio.run(service.run("policy-map", inputs))


def test_google_sdk_real_config_and_injected_async_transport() -> None:
    calls = []

    async def generate_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            text=json.dumps(policy()),
            model_version="sdk-test-version",
            usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=5),
        )

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    transport = GoogleGenAITransport(client=client, model="configured-test-model")
    result = asyncio.run(BoundedWorkflowService(transport).run("policy-map", context()))
    assert result.output["candidate_id"] == "PR-1"
    config = calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema["type"] == "object"
    assert config.automatic_function_calling.disable
    assert config.automatic_continuation is False
    assert config.max_output_tokens == 8192
    assert config.thinking_config.thinking_level == "LOW"
    original_schema = json.loads(calls[0]["contents"])["output_validation_schema"]
    assert original_schema["properties"]["reason"]["maxLength"] == 3000
    assert "maxLength" not in config.response_json_schema["properties"]["reason"]
    assert config.tools is None


def test_vertex_client_factory_uses_current_sdk_config_without_network(monkeypatch) -> None:
    from google import genai

    captured = {}

    def construct(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(genai, "Client", construct)
    create_vertex_client("project-id", "us-central1")
    assert captured["vertexai"] is True
    assert captured["http_options"].api_version == "v1"
    assert captured["http_options"].retry_options.attempts == 1


def test_provider_grammar_does_not_weaken_application_length_validation() -> None:
    async def generate_content(**kwargs):
        assert "maxLength" not in kwargs["config"].response_json_schema["properties"]["reason"]
        invalid = policy() | {"reason": "x" * 3001}
        return SimpleNamespace(
            text=json.dumps(invalid), model_version="test", usage_metadata=None
        )

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    result = asyncio.run(
        BoundedWorkflowService(
            GoogleGenAITransport(client=client, model="configured-test-model")
        ).run("policy-map", context())
    )
    assert result.run.attempts == 2
    assert result.run.validation_status == "FAILED"
    assert result.output is None
    assert any("3000" in error for error in result.validation_errors)


def test_vertex_embeddings_enforce_768_and_task_type_without_paid_calls() -> None:
    calls = []

    async def embed_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1] * 768)])

    client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))
    )
    adapter = VertexEmbeddingClient(client=client)
    result = asyncio.run(adapter.embed(("bounded query", "another query")))
    assert len(result) == 2 and len(result[0]) == 768
    assert all(call["config"].output_dimensionality == 768 for call in calls)
    assert calls[0]["config"].task_type == "RETRIEVAL_QUERY"
    assert calls[0]["config"].auto_truncate is False
    with pytest.raises(ValueError):
        VertexEmbeddingClient(client=client, dimensions=3072)


def test_impact_claim_support_requires_exact_supplied_fact_when_available() -> None:
    inputs = context()
    inputs["allowed_claims"] = [
        {"text": "This remains a proposal.", "legal_status": "PROPOSED", "entity_ids": ["M-1"]}
    ]
    output = {
        "claims": [
            {
                "text": "This is already an in-force binding requirement.",
                "legal_status": "PROPOSED",
                "entity_ids": ["M-1"],
                "evidence": evidence(),
            }
        ]
    }
    transport = FakeTransport([json.dumps(copy.deepcopy(output))] * 2)
    result = asyncio.run(BoundedWorkflowService(transport).run("impact-explain", inputs))
    assert result.output is None


def test_no_suitable_candidate_cannot_present_an_alternative() -> None:
    output = policy()
    output.update(decision="NO_SUITABLE_CANDIDATE", candidate_id=None, alternative_ids=["PR-1"])
    result = asyncio.run(
        BoundedWorkflowService(FakeTransport([json.dumps(output)] * 2)).run("policy-map", context())
    )
    assert result.output is None


@pytest.mark.parametrize("text_kind", [None, "PARAPHRASE", "UNVERIFIED"])
def test_excerpts_require_explicit_raw_or_verified_text_kind(text_kind) -> None:
    inputs = context()
    inputs["segments"][0]["text_kind"] = text_kind
    result = asyncio.run(
        BoundedWorkflowService(FakeTransport([json.dumps(policy())] * 2)).run("policy-map", inputs)
    )
    assert result.output is None


def test_guideline_evidence_cannot_be_promoted_to_proposed_binding() -> None:
    inputs = context()
    inputs["sources"][0]["legal_force"] = "GUIDANCE"
    output = {
        "mandates": [
            {
                "text": "Prevent gifts from unduly influencing purchases.",
                "applicability": "Public prospecting",
                "legal_force": "PROPOSED_BINDING",
                "evidence": evidence(),
            }
        ]
    }
    result = asyncio.run(
        BoundedWorkflowService(FakeTransport([json.dumps(output)] * 2)).run("interpret", inputs)
    )
    assert result.output is None


def test_impact_narrative_fails_closed_without_deterministic_claims() -> None:
    output = {
        "claims": [
            {
                "text": "This proposed change affects a policy.",
                "legal_status": "PROPOSED",
                "entity_ids": ["M-1"],
                "evidence": evidence(),
            }
        ]
    }
    result = asyncio.run(
        BoundedWorkflowService(FakeTransport([json.dumps(output)] * 2)).run(
            "impact-explain", context()
        )
    )
    assert result.output is None
