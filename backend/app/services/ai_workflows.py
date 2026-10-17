import hashlib
import json
from collections.abc import Callable
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.contracts import OUTPUT_SCHEMAS, RunStep, WorkflowResult, WorkflowRun
from app.ai.prompts import load_prompt
from app.ai.transport import StructuredTransport
from app.domain.errors import DomainError


def _ground_output(output: dict[str, Any], context: dict[str, Any]) -> None:
    sources = {
        source.get("id", source.get("source_id")): source for source in context.get("sources", [])
    }
    source_ids = set(context.get("source_ids", [])) | {
        source.get("id", source.get("source_id")) for source in context.get("sources", [])
    }
    segments = {
        segment.get("id", segment.get("segment_id")): segment
        for segment in context.get("evidence", context.get("segments", []))
    }
    candidates = {candidate["id"]: candidate for candidate in context.get("candidates", [])}
    mandate_ids = set(context.get("mandate_ids", [])) | {
        mandate["id"] for mandate in context.get("mandates", [])
    }
    entity_ids = set(context.get("entity_ids", []))

    def check(value: Any) -> None:
        if isinstance(value, dict):
            references = value.get("evidence", [])
            if isinstance(references, list) and references:
                forces = {
                    sources.get(reference.get("source_id"), {}).get("legal_force")
                    for reference in references
                    if isinstance(reference, dict)
                }
                if forces == {"GUIDANCE"} and any(
                    value.get(key) == "PROPOSED_BINDING"
                    for key in ("legal_force", "legal_force_after")
                ):
                    raise ValueError(
                        "Guideline-only evidence cannot establish proposed binding treatment"
                    )
            if "segment_id" in value and "source_id" in value:
                segment = segments.get(value["segment_id"])
                if (
                    segment is None
                    or segment.get("source_id") != value["source_id"]
                    or value["source_id"] not in source_ids
                ):
                    raise ValueError("Evidence reference is not in the supplied source context")
                excerpt = value.get("excerpt")
                if excerpt is not None and (
                    not excerpt.strip()
                    or excerpt not in segment["text"]
                    or segment.get("text_kind") not in {"EXTRACTED_TEXT", "VERIFIED_EXCERPT"}
                ):
                    raise ValueError(
                        "Quoted evidence must be an exact excerpt from a source segment"
                    )
            for key, item in value.items():
                selected: list[str] = []
                if key in {"candidate_id", "selected_risk_type_id"} and item is not None:
                    selected = [item]
                elif key in {"alternative_ids", "selected_risk_driver_ids"}:
                    selected = item
                if any(candidate not in candidates for candidate in selected):
                    raise ValueError("Selected candidate ID was not supplied to this run")
                if key in {"candidate_id", "alternative_ids"}:
                    if any(candidates[i].get("type") != "POLICY_REQUIREMENT" for i in selected):
                        raise ValueError("Policy mapping selected a non-policy candidate")
                if key == "selected_risk_type_id" and item is not None:
                    if candidates[item].get("type") != "RISK_TYPE":
                        raise ValueError("Risk type selection has the wrong catalog type")
                if key == "selected_risk_driver_ids":
                    if any(candidates[i].get("type") != "RISK_DRIVER" for i in item):
                        raise ValueError("Risk driver selection has the wrong catalog type")
                if key == "target_mandate_ids" and not set(item) <= mandate_ids:
                    raise ValueError("Proposed change references an unknown mandate")
                if key == "entity_ids" and not set(item) <= entity_ids:
                    raise ValueError("Narrative references entities absent from this run")
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(output)
    if output.get("classification") == "UNCHANGED":
        if (
            output.get("no_effect_result") != "NO_EFFECT_SUPPORTED"
            or context.get("high_confidence_pcs_target", True)
            or context.get("applicable_global_overlay", True)
        ):
            raise ValueError(
                "Unchanged analysis cannot bypass PCS, global scope or no-effect checks"
            )
    if "claims" in output:
        allowed = context.get("allowed_claims", [])
        for claim in output["claims"]:
            if not any(
                claim["text"] == fact["text"]
                and claim["legal_status"] == fact["legal_status"]
                and set(claim["entity_ids"]) == set(fact["entity_ids"])
                for fact in allowed
            ):
                raise ValueError(
                    "Narrative claim is not supported by a supplied deterministic fact"
                )


class BoundedWorkflowService:
    """At most two model calls, neither of which has tools or write capabilities."""

    def __init__(self, transport: StructuredTransport | None = None) -> None:
        self.transport = transport

    async def run(
        self,
        workflow: str,
        context: dict[str, Any],
        validator: Callable[[BaseModel], None] | None = None,
    ) -> WorkflowResult:
        if workflow not in OUTPUT_SCHEMAS:
            raise DomainError("WORKFLOW_NOT_FOUND", "Unknown bounded workflow.", 404)
        context_json = json.dumps(context, sort_keys=True, ensure_ascii=False)
        if len(context_json) > 120000:
            raise DomainError(
                "CONTEXT_TOO_LARGE", "The bounded context exceeds the allowed size.", 422
            )
        if workflow in {"policy-map", "risk-map"} and len(context.get("candidates", [])) > 8:
            raise DomainError(
                "CANDIDATE_LIMIT", "Pass at most eight deterministically ranked candidates.", 422
            )
        started = perf_counter()
        version = f"{workflow}-v2" if workflow in {"interpret", "pcs-extract"} else f"{workflow}-v1"
        run = WorkflowRun(
            workflow=workflow,
            kind="LIVE_AI" if self.transport else "LOCAL_DETERMINISTIC",
            model=self.transport.model if self.transport else None,
            prompt_version=version,
            status="BLOCKED",
            validation_status="NOT_RUN",
            label="Bounded Gemini recommendation — human review required"
            if self.transport
            else "Live AI is not configured — no inference was performed",
            input_sha256=hashlib.sha256(context_json.encode("utf-8")).hexdigest(),
            thinking_level=getattr(self.transport, "thinking_level", None),
            candidate_ids=tuple(candidate["id"] for candidate in context.get("candidates", [])),
            candidate_details=tuple(context.get("candidates", [])),
        )
        if self.transport is None:
            return WorkflowResult(
                run=run,
                status="AI_NOT_CONFIGURED",
                validation_errors=("Configure a live Vertex AI transport to run this workflow.",),
            )
        schema = OUTPUT_SCHEMAS[workflow]
        errors: tuple[str, ...] = ()
        steps: list[RunStep] = []
        input_tokens = output_tokens = 0
        token_usage_available = False
        for attempt in (1, 2):
            try:
                response = await self.transport.complete(
                    system_instruction=load_prompt(version),
                    context=context,
                    response_schema=schema.model_json_schema(),
                    repair_errors=errors,
                )
            except Exception as exc:
                # Transport failures are not silently retried or replaced by fixture output.
                errors = (f"AI transport unavailable ({type(exc).__name__}).",)
                steps.append(RunStep(name="model-call", status="FAILED", detail=errors[0]))
                break
            input_tokens += response.input_tokens or 0
            output_tokens += response.output_tokens or 0
            token_usage_available |= response.input_tokens is not None
            try:
                parsed = schema.model_validate_json(response.text)
                output = parsed.model_dump(mode="json")
                _ground_output(output, context)
                if validator:
                    validator(parsed)
            except (ValidationError, ValueError, KeyError, TypeError) as exc:
                if isinstance(exc, ValidationError):
                    errors = tuple(
                        f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                        for item in exc.errors(include_input=False, include_url=False)
                    )[:12]
                else:
                    errors = (str(exc),)
                steps.append(
                    RunStep(
                        name=f"validate-attempt-{attempt}",
                        status="FAILED",
                        detail="Schema, evidence or candidate validation failed.",
                    )
                )
                continue
            steps.append(
                RunStep(
                    name="validate-output",
                    status="SUCCEEDED",
                    detail="Schema, evidence and ID checks passed; "
                    "semantic judgment requires human review.",
                )
            )
            return WorkflowResult(
                output=output,
                status="HUMAN_REVIEW_REQUIRED",
                run=run.model_copy(
                    update={
                        "status": "SUCCEEDED",
                        "validation_status": "PASSED",
                        "attempts": attempt,
                        "model_calls": attempt,
                        "duration_ms": round((perf_counter() - started) * 1000, 2),
                        "steps": tuple(steps),
                        "input_tokens": input_tokens if token_usage_available else None,
                        "output_tokens": output_tokens if token_usage_available else None,
                        "provider_model_version": response.model_version,
                        "output_sha256": hashlib.sha256(
                            parsed.model_dump_json().encode()
                        ).hexdigest(),
                    }
                ),
            )
        return WorkflowResult(
            status="MANUAL_REVIEW_REQUIRED",
            validation_errors=errors,
            run=run.model_copy(
                update={
                    "status": "MANUAL_REVIEW_REQUIRED",
                    "validation_status": "FAILED",
                    "attempts": attempt,
                    "model_calls": attempt,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                    "steps": tuple(steps),
                    "input_tokens": input_tokens if token_usage_available else None,
                    "output_tokens": output_tokens if token_usage_available else None,
                }
            ),
        )
