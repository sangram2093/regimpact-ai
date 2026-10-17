"""Explicit, bounded live checks. Default plan mode performs no network operations."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
AUTHORIZED_PROJECT = "regimpact-ai"


class SmokeFailure(Exception):
    """A fixed diagnostic code, never a provider response or credential-bearing message."""


@dataclass(frozen=True)
class SmokeConfig:
    project: str
    checks: str = "plan"
    vertex_location: str | None = None
    model: str | None = None
    embedding_model: str | None = None
    api_url: str | None = None
    allow_ai_calls: bool = False
    allow_demo_writes: bool = False
    expected_api_mode: str = "gcp"
    data_dir: Path = ROOT / "data"
    armor_template: str | None = None

    def validate(self) -> None:
        if self.project != AUTHORIZED_PROJECT:
            raise SmokeFailure("UNAUTHORIZED_PROJECT")
        if self.checks not in {"plan", "direct", "api", "all"}:
            raise SmokeFailure("INVALID_CHECK_SELECTION")
        if self.checks in {"direct", "all"} and (
            not self.allow_ai_calls
            or not all((self.vertex_location, self.model, self.embedding_model))
        ):
            raise SmokeFailure("EXPLICIT_AI_PERMISSION_AND_MODEL_CONFIGURATION_REQUIRED")
        if self.armor_template and not self.armor_template.startswith(f"projects/{self.project}/"):
            raise SmokeFailure("MODEL_ARMOR_PROJECT_MISMATCH")
        if self.checks in {"api", "all"}:
            url = urlsplit(self.api_url or "")
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
            ):
                raise SmokeFailure("EXPLICIT_HTTPS_API_ORIGIN_REQUIRED")
            if self.allow_ai_calls and (
                not self.allow_demo_writes or not self.model or not self.embedding_model
            ):
                raise SmokeFailure("API_AI_CHECKS_REQUIRE_MODELS_AND_DEMO_WRITE_PERMISSION")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def require(condition: bool, code: str) -> None:
    if not condition:
        raise SmokeFailure(code)


def run_provenance(run: dict, expected_model: str) -> dict:
    require(run.get("kind") == "LIVE_AI", "LIVE_MODEL_REQUIRED_NO_LOCAL_SUBSTITUTE")
    require(
        run.get("status") == "SUCCEEDED" and run.get("validation_status") == "PASSED",
        "MODEL_OUTPUT_NOT_VALIDATED",
    )
    require(run.get("model") == expected_model, "MODEL_ID_MISMATCH")
    require(
        all(
            re.fullmatch(r"[0-9a-f]{64}", run.get(key) or "")
            for key in ("input_sha256", "output_sha256")
        ),
        "RUN_HASH_MISSING",
    )
    provider_version = run.get("provider_model_version")
    if provider_version is not None:
        require(
            bool(re.fullmatch(r"[A-Za-z0-9._:/-]{1,160}", provider_version)), "MODEL_ID_INVALID"
        )
    require(str(UUID(run["id"])) == run["id"], "RUN_ID_INVALID")
    require(
        isinstance(run.get("prompt_version"), str)
        and bool(re.fullmatch(r"[a-zA-Z0-9._-]{1,100}", run["prompt_version"])),
        "PROMPT_VERSION_INVALID",
    )
    for key in ("attempts", "model_calls", "duration_ms"):
        require(run.get(key) is None or isinstance(run[key], (int, float)), "RUN_METRIC_INVALID")
    return {
        "run_id": run["id"],
        "requested_model": expected_model,
        "provider_model_version": provider_version,
        "model_identity_status": "RETURNED_BY_PROVIDER" if provider_version else "NOT_RETURNED",
        "prompt_version": run.get("prompt_version"),
        "input_sha256": run["input_sha256"],
        "output_sha256": run["output_sha256"],
        "attempts": run.get("attempts"),
        "model_calls": run.get("model_calls"),
        "duration_ms": run.get("duration_ms"),
    }


async def direct_smoke(
    config: SmokeConfig, client_factory=None, checks: list[dict] | None = None
) -> list[dict]:
    from app.adapters.local_json import LocalJsonRepository
    from app.ai.adk_ask import AdkAskTransport
    from app.ai.armor import ModelArmorScreen
    from app.ai.google_client import (
        GoogleGenAITransport,
        VertexEmbeddingClient,
        create_vertex_client,
    )
    from app.services.ai_workflows import BoundedWorkflowService
    from app.services.ask import AskService
    from app.services.candidates import CandidateService
    from app.services.impact import ImpactService

    config.validate()
    require(
        config.allow_ai_calls
        and all((config.model, config.embedding_model, config.vertex_location)),
        "EXPLICIT_AI_PERMISSION_AND_MODEL_CONFIGURATION_REQUIRED",
    )
    repository = LocalJsonRepository(config.data_dir)
    bundle = repository.snapshot()
    client = (client_factory or create_vertex_client)(config.project, config.vertex_location)
    checks = [] if checks is None else checks
    try:
        # A single embedding request: vectors never leave this process/report as raw values.
        started = perf_counter()
        embedding = await VertexEmbeddingClient(client=client, model=config.embedding_model).embed(
            ("Synthetic gifts policy: prevent undue influence during public prospecting.",)
        )
        require(len(embedding) == 1 and len(embedding[0]) == 768, "EMBEDDING_DIMENSIONS_INVALID")
        checks.append(
            {
                "name": "direct_embedding",
                "status": "PASSED",
                "dimensions": 768,
                "requested_model": config.embedding_model,
                "model_identity_status": "EXPLICIT_REQUEST_PARAMETER",
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            }
        )
        mandate = next(m for m in bundle.mandates if m.id == "M-GIFT")
        candidates = await CandidateService(repository).retrieve(mandate.id)
        context = {
            "sources": [
                i.model_dump(mode="json")
                | {"legal_force": "GUIDANCE" if i.status == "IN_FORCE" else "PROPOSED_BINDING"}
                for i in bundle.instruments
            ],
            "evidence": [e.model_dump(mode="json") for e in bundle.evidence],
            "mandates": [m.model_dump(mode="json") for m in bundle.mandates],
            "selected_mandate_id": mandate.id,
            "candidates": [c.model_dump(mode="json") for c in candidates.candidates],
            "proposal_notice": bundle.scenario.proposal_notice,
        }
        result = await BoundedWorkflowService(
            GoogleGenAITransport(
                client=client,
                model=config.model,
            )
        ).run("policy-map", context)
        provenance = run_provenance(result.run.model_dump(mode="json"), config.model)
        require(result.output is not None and result.run.attempts <= 2, "STRUCTURED_OUTPUT_MISSING")
        checks.append(
            {
                "name": "direct_structured_policy",
                "status": "PASSED",
                **provenance,
                "retrieval": "LOCAL_LEXICAL_FOR_THIS_PROVIDER_PROBE",
                "data": "PUBLIC_SOURCE_PARAPHRASES_AND_SYNTHETIC_CATALOG",
                "human_approval": "NOT_PERFORMED",
            }
        )
        screen = ModelArmorScreen(config.armor_template) if config.armor_template else None
        ask = AskService(
            bundle,
            ImpactService(bundle, repository),
            AdkAskTransport(client=client, model=config.model),
            screen,
        )
        result = await ask.ask(ask.config().suggested_questions[0], bundle.scenario.id)
        provenance = run_provenance(result.run.model_dump(mode="json"), config.model)
        require(
            result.grounded and result.verified_references == result.total_references > 0,
            "ASK_GROUNDING_FAILED",
        )
        require(bool(result.tool_calls), "ASK_TOOL_USE_MISSING")
        checks.append(
            {
                "name": "direct_adk_ask",
                "status": "PASSED",
                **provenance,
                "verified_references": result.verified_references,
                "tool_names": list(dict.fromkeys(c.name for c in result.tool_calls)),
                "model_armor": "CONFIGURED_AND_PASSED" if screen else "NOT_CONFIGURED",
            }
        )
    finally:
        await client.aio.aclose()
    return checks


class ApiProbe:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.request_ids: list[str] = []

    async def call(
        self,
        method: str,
        path: str,
        session: str | None = None,
        body: dict | None = None,
        expected: int = 200,
    ) -> dict:
        response = await self.client.request(
            method,
            "/api/v1" + path,
            headers={"X-Demo-Session": session} if session else {},
            json=body,
        )
        if response.status_code != expected:
            raise SmokeFailure(f"API_HTTP_{response.status_code}")
        payload = response.json()
        request_id = payload.get("meta", {}).get("request_id")
        require(
            isinstance(request_id, str)
            and bool(re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", request_id)),
            "API_REQUEST_ID_MISSING",
        )
        self.request_ids.append(request_id)
        return payload.get("data", {})


async def api_smoke(
    config: SmokeConfig, client: Any, checks: list[dict] | None = None
) -> list[dict]:
    """Only random fresh sessions are written/reset; no catalog or baseline writes."""
    config.validate()
    probe = ApiProbe(client)
    checks = [] if checks is None else checks
    sessions = [str(uuid4()), str(uuid4())]
    touched: list[str] = []
    try:
        health = await probe.call("GET", "/health")
        require(health.get("mode") == config.expected_api_mode, "API_MODE_MISMATCH")
        dashboard = await probe.call("GET", "/dashboard")
        scenario = dashboard["scenario"]["id"]
        delta_path = f"/changes/{scenario}/delta-review"
        before = [await probe.call("GET", delta_path, session) for session in sessions]
        require(before[0] == before[1], "FRESH_SESSION_STATE_MISMATCH")
        selected = next(
            (
                a
                for a in before[0]["assessments"]
                if not a["eligible_for_carry_forward"]
                and a["classification"] not in {"UNRESOLVED", "UNCHANGED"}
            ),
            None,
        )
        require(selected is not None, "NO_REVIEWABLE_SMOKE_ASSESSMENT")
        change = next(c for c in dashboard["changes"] if c["mandate_id"] == selected["mandate_id"])
        impact_path = f"/changes/{change['id']}/impact"
        baseline_hash = digest(await probe.call("GET", impact_path))
        edge = await probe.call("GET", f"/edges/{selected['baseline_edge_id']}/explain")
        require(
            bool(edge.get("evidence")) and bool(edge.get("provenance")), "EDGE_PROVENANCE_MISSING"
        )
        checks.append(
            {
                "name": "api_health_lineage",
                "status": "PASSED",
                "mode": health["mode"],
                "scenario_id": scenario,
                "baseline_impact_sha256": baseline_hash,
            }
        )
        if config.allow_demo_writes:
            review_body = {
                "decision": "REJECT",
                "role": selected["required_role"],
                "reviewer": "Synthetic smoke validation",
                "rationale": (
                    "Temporary synthetic smoke decision, reset after session isolation checks."
                ),
            }
            path = f"/assessments/{selected['id']}/review"
            touched.append(sessions[0])
            first = await probe.call("POST", path, sessions[0], review_body)
            second = await probe.call("POST", path, sessions[0], review_body)
            require(first == second, "REVIEW_NOT_IDEMPOTENT")
            require(
                await probe.call("GET", delta_path, sessions[1]) == before[1], "SESSION_WRITE_LEAK"
            )
            touched.append(sessions[1])
            await probe.call("POST", path, sessions[1], review_body)
            second_session = await probe.call("GET", delta_path, sessions[1])
            await probe.call("POST", "/demo/reset", sessions[0])
            require(await probe.call("GET", delta_path, sessions[0]) == before[0], "RESET_FAILED")
            require(
                await probe.call("GET", delta_path, sessions[1]) == second_session,
                "RESET_CROSSED_SESSIONS",
            )
            require(
                digest(await probe.call("GET", impact_path)) == baseline_hash, "BASELINE_MUTATION"
            )
            checks.append(
                {
                    "name": "api_two_session_reset",
                    "status": "PASSED",
                    "fresh_sessions": 2,
                    "idempotent": True,
                    "baseline_unchanged": True,
                }
            )
        else:
            checks.append(
                {
                    "name": "api_two_session_reset",
                    "status": "NOT_RUN",
                    "reason": "Requires --allow-demo-writes.",
                }
            )
        if config.allow_ai_calls:
            if sessions[0] not in touched:
                touched.append(sessions[0])
            candidates = await probe.call(
                "GET", f"/mandates/{change['mandate_id']}/policy-candidates", sessions[0]
            )
            require(candidates.get("retrieval_mode") == "HYBRID", "LIVE_HYBRID_RETRIEVAL_REQUIRED")
            require(
                candidates.get("embedding_model") == config.embedding_model,
                "EMBEDDING_MODEL_MISMATCH",
            )
            run = await probe.call(
                "POST",
                "/workflows/policy-map/run",
                sessions[0],
                {"change_id": change["id"], "mandate_id": change["mandate_id"]},
            )
            provenance = run_provenance(run, config.model)
            detail = await probe.call("GET", f"/workflows/runs/{run['id']}", sessions[0])
            require(
                detail.get("output") is not None and detail["run"] == run,
                "WORKFLOW_DETAIL_MISMATCH",
            )
            await probe.call("GET", f"/workflows/runs/{run['id']}", sessions[1], expected=404)
            require("_context" not in detail, "INTERNAL_CONTEXT_EXPOSED")
            checks.append(
                {
                    "name": "api_hybrid_policy_provenance",
                    "status": "PASSED",
                    **provenance,
                    "run_session_isolated": True,
                }
            )
            answer = await probe.call(
                "POST",
                "/ask",
                sessions[0],
                {
                    "question": "Which controls should we review for the gift proposal?",
                    "scenario_id": scenario,
                },
            )
            provenance = run_provenance(answer["run"], config.model)
            require(
                answer["grounded"]
                and answer["verified_references"] == answer["total_references"] > 0,
                "API_ASK_GROUNDING_FAILED",
            )
            require(bool(answer["tool_calls"]), "API_ASK_TOOL_USE_MISSING")
            checks.append(
                {
                    "name": "api_grounded_ask",
                    "status": "PASSED",
                    **provenance,
                    "verified_references": answer["verified_references"],
                }
            )
        require(digest(await probe.call("GET", impact_path)) == baseline_hash, "BASELINE_MUTATION")
    finally:
        for session in touched:
            try:
                await probe.call("POST", "/demo/reset", session)
            except Exception:
                checks.append(
                    {
                        "name": "api_session_cleanup",
                        "status": "FAILED",
                        "session_id": session,
                        "reason": "Retry reset for this smoke session only.",
                    }
                )
        checks.append(
            {
                "name": "api_request_correlation",
                "status": "PASSED",
                "request_ids": probe.request_ids,
            }
        )
    return checks


async def run(config: SmokeConfig, api_client=None, vertex_client_factory=None) -> dict:
    config.validate()
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "project": config.project,
        "mode": config.checks,
        "checks": [],
        "status": "NOT_RUN",
        "maximum_ai_requests": (7 if config.checks in {"direct", "all"} else 0)
        + (7 if config.checks in {"api", "all"} and config.allow_ai_calls else 0),
        "notes": [
            "No provisioning, source/catalog mutation, automatic retries or model substitution.",
            "These are smoke checks, not blind model-quality or legal-accuracy results.",
            "API project ownership must be established from the deployment URL; "
            "health is not an ownership attestation.",
        ],
    }
    if config.checks == "plan":
        return report
    if config.checks in {"direct", "all"}:
        try:
            await direct_smoke(config, vertex_client_factory, report["checks"])
        except Exception as exc:
            report["checks"].append(
                {
                    "name": "direct_ai",
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "code": str(exc) if isinstance(exc, SmokeFailure) else "PROVIDER_CHECK_FAILED",
                }
            )
    if config.checks in {"api", "all"}:
        try:
            if api_client is None:
                import httpx

                token = os.environ.get("REGIMPACT_SMOKE_ID_TOKEN")
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                async with httpx.AsyncClient(
                    base_url=config.api_url,
                    headers=headers,
                    timeout=httpx.Timeout(55, connect=10),
                    follow_redirects=False,
                ) as client:
                    await api_smoke(config, client, report["checks"])
            else:
                await api_smoke(config, api_client, report["checks"])
        except Exception as exc:
            report["checks"].append(
                {
                    "name": "api_e2e",
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "code": str(exc) if isinstance(exc, SmokeFailure) else "API_CHECK_FAILED",
                }
            )
    report["status"] = (
        "FAILED" if any(c["status"] == "FAILED" for c in report["checks"]) else "PASSED"
    )
    if report["status"] == "PASSED" and any(
        c.get("model_identity_status") == "NOT_RETURNED" for c in report["checks"]
    ):
        report["status"] = "PARTIAL"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, choices=[AUTHORIZED_PROJECT])
    parser.add_argument("--checks", choices=["plan", "direct", "api", "all"], default="plan")
    parser.add_argument("--vertex-location")
    parser.add_argument("--model")
    parser.add_argument("--embedding-model")
    parser.add_argument("--api-url")
    parser.add_argument("--allow-ai-calls", action="store_true")
    parser.add_argument("--allow-demo-writes", action="store_true")
    parser.add_argument("--armor-template")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    config = SmokeConfig(**{k: v for k, v in vars(args).items() if k != "output"})
    try:
        config.validate()
    except SmokeFailure as exc:
        parser.error(str(exc))
    if args.output and args.output.exists():
        parser.error("OUTPUT_ALREADY_EXISTS; choose a new report path before running checks")
    previous_log_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        report = asyncio.run(run(config))
    finally:
        logging.disable(previous_log_level)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            destination.write(rendered + "\n")
    print(rendered)
    return 0 if report["status"] in {"PASSED", "NOT_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
