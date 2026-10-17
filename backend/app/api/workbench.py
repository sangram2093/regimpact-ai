"""Source, specialist review and bounded AI routes."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.ai.contracts import (
    AskConfig,
    AskResponse,
    CandidateResult,
    WorkflowName,
    WorkflowRun,
)
from app.api.dependencies import demo_session, respond, writable_session
from app.api.schemas import (
    AskRequest,
    ClassificationRequest,
    Envelope,
    PolicyMappingRequest,
    WorkflowRequest,
)
from app.domain.errors import DomainError
from app.domain.models import Classification, NodeType
from app.domain.views import ChangeDetail
from app.domain.workbench import MandatesView, PolicyReviewView, RunsView, SourcesView, SourceView
from app.domain.workflow_review import WorkflowReviewView
from app.repositories.sessions import SessionState
from app.services.human_review import HumanReviewService
from app.services.workflow_review import WorkflowReviewService

logger = logging.getLogger("regimpact.api")
Session = Annotated[str, Depends(writable_session)]
ReadSession = Annotated[str | None, Depends(demo_session)]
router = APIRouter(prefix="/api/v1")
OPERATION_DEADLINE_SECONDS = 50


def bounded_operation[**P, T](handler: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    @wraps(handler)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            async with asyncio.timeout(OPERATION_DEADLINE_SECONDS):
                return await handler(*args, **kwargs)
        except TimeoutError as exc:
            raise DomainError(
                "OPERATION_TIMEOUT",
                "The operation exceeded its total request deadline. "
                "No unvalidated output was accepted; inspect run history before retrying.",
                504,
            ) from exc

    return wrapped


def save_run(
    request: Request,
    session: str,
    payload: dict,
    key: str | None = None,
    unreviewed_mandate: str | None = None,
) -> None:
    def save(state: SessionState) -> None:
        if unreviewed_mandate and unreviewed_mandate in state.mappings:
            raise DomainError(
                "MAPPING_ALREADY_REVIEWED",
                "The mapping was reviewed while AI was running. "
                "Its recorded provenance is preserved.",
                409,
            )
        if key and key.startswith("candidates:") and key in state.runs:
            return
        # A bounded session history prevents long-lived demos growing without limit.
        if len(state.runs) >= 100:
            pinned = {review.retrieval_run_id for review in state.mappings.values()}
            pinned.update(getattr(state, "workflow_reviews", {}))
            oldest = next(
                (
                    k
                    for k, v in state.runs.items()
                    if not k.startswith(("candidates:", "recommendations:"))
                    and v["run"]["id"] not in pinned
                ),
                None,
            )
            if oldest:
                del state.runs[oldest]
            elif key not in state.runs:
                raise DomainError(
                    "RUN_HISTORY_FULL",
                    "Reviewed run history is full. "
                    "Reset this demo session before creating new runs.",
                    409,
                )
        state.runs[key or payload["run"]["id"]] = payload

    request.app.state.sessions.transact(session, save)
    run = payload["run"]
    import json

    logger.info(
        json.dumps(
            {
                "event": "workflow_complete",
                "request_id": request.state.request_id,
                "workflow_id": run["workflow"],
                "agent_run_id": run["id"],
                "model_id": run.get("model"),
                "prompt_version": run.get("prompt_version"),
                "latency_ms": run.get("duration_ms"),
                "input_tokens": run.get("input_tokens"),
                "output_tokens": run.get("output_tokens"),
                "validation_status": run.get("validation_status"),
                "status": run["status"],
            }
        )
    )


def review_view(request: Request, session: str, result: CandidateResult) -> PolicyReviewView:
    state = request.app.state.sessions.snapshot(session)
    change = request.app.state.scenarios.by_mandate[result.mandate_id]
    confirmed = change.id in state.classifications
    removed = (
        confirmed and state.classifications[change.id].classification == Classification.REMOVED
    )
    decision = state.mappings.get(result.mandate_id)
    values = result.model_dump()
    values["candidates"] = values["candidates"][:3]
    if decision:
        status = "APPROVED" if decision.decision == "APPROVE" else "REJECTED"
        values.update(
            review_status=f"SCENARIO_{status}",
            selected_policy_id=decision.policy_id,
        )
    return PolicyReviewView(
        **values,
        rationale=decision.rationale if decision else None,
        reviewed_by=decision.reviewer if decision else None,
        mapping_allowed=confirmed and not removed and decision is None and bool(result.candidates),
        mapping_block_reason="This prospective decision is already recorded."
        if decision
        else "This obligation was classified as removed; review its retirement in Delta Review."
        if removed
        else "A Regulatory Specialist must confirm this change before mapping."
        if not confirmed
        else "No suitable candidate was retrieved; retain the coverage gap."
        if not result.candidates
        else None,
    )


@router.get("/sources", response_model=Envelope[SourcesView])
@bounded_operation
async def sources(request: Request) -> Envelope[SourcesView]:
    await request.app.state.sources.refresh()
    return respond(request, SourcesView.model_validate(request.app.state.sources.list_sources()))


@router.post("/sources/{source_id}/ingest", response_model=Envelope[SourceView])
@bounded_operation
async def ingest(source_id: str, request: Request, session: Session) -> Envelope[SourceView]:
    await asyncio.to_thread(request.app.state.limiter.acquire)
    result = await request.app.state.sources.ingest(source_id)
    return respond(request, SourceView.model_validate(result))


@router.get("/mandates", response_model=Envelope[MandatesView])
def mandates(request: Request, session: ReadSession) -> Envelope[MandatesView]:
    service = HumanReviewService(request.app.state.scenarios)
    return respond(request, MandatesView.model_validate(service.mandates(session)))


@router.post("/changes/{change_id}/classify", response_model=Envelope[ChangeDetail])
def classify(
    change_id: str, body: ClassificationRequest, request: Request, session: Session
) -> Envelope[ChangeDetail]:
    HumanReviewService(request.app.state.scenarios).classify(
        change_id,
        session,
        Classification(body.classification),
        body.reviewer,
        body.rationale,
        body.evidence_ids,
    )
    return respond(request, request.app.state.scenarios.change_detail(change_id, session))


@router.get("/mandates/{mandate_id}/policy-candidates", response_model=Envelope[PolicyReviewView])
@bounded_operation
async def candidates(
    mandate_id: str, request: Request, session: Session
) -> Envelope[PolicyReviewView]:
    state = await asyncio.to_thread(request.app.state.sessions.snapshot, session)
    cached = state.runs.get(f"recommendations:{mandate_id}") or state.runs.get(
        f"candidates:{mandate_id}"
    )
    if cached:
        result = CandidateResult.model_validate(cached)
    else:
        if request.app.state.candidates.embedding_client:
            await asyncio.to_thread(request.app.state.limiter.acquire)
        result = await request.app.state.candidates.retrieve(mandate_id)
        await asyncio.to_thread(
            save_run, request, session, result.model_dump(mode="json"), f"candidates:{mandate_id}"
        )
        state = await asyncio.to_thread(request.app.state.sessions.snapshot, session)
        result = CandidateResult.model_validate(state.runs[f"candidates:{mandate_id}"])
    return respond(request, await asyncio.to_thread(review_view, request, session, result))


@router.post("/mandates/{mandate_id}/policy-mapping", response_model=Envelope[PolicyReviewView])
def mapping(
    mandate_id: str, body: PolicyMappingRequest, request: Request, session: Session
) -> Envelope[PolicyReviewView]:
    HumanReviewService(request.app.state.scenarios).review_mapping(
        mandate_id, session, body.policy_id, body.decision, body.reviewer, body.rationale
    )
    state = request.app.state.sessions.snapshot(session)
    cached = (
        state.runs.get(f"recommendations:{mandate_id}") or state.runs[f"candidates:{mandate_id}"]
    )
    return respond(request, review_view(request, session, CandidateResult.model_validate(cached)))


@router.get("/workflows/runs", response_model=Envelope[RunsView])
def runs(request: Request, session: ReadSession) -> Envelope[RunsView]:
    stored = request.app.state.sessions.snapshot(session).runs.values()
    unique = {v["run"]["id"]: v for v in stored}
    return respond(
        request,
        RunsView(
            runs=tuple(
                WorkflowRun.model_validate(v["run"]) for v in reversed(list(unique.values()))
            )
        ),
    )


@router.get("/workflows/runs/{run_id}", response_model=Envelope[WorkflowReviewView])
def run_detail(run_id: str, request: Request, session: ReadSession) -> Envelope[WorkflowReviewView]:
    return respond(
        request, WorkflowReviewService(request.app.state.scenarios).detail(run_id, session)
    )


@router.post("/workflows/{workflow}/run", response_model=Envelope[WorkflowRun])
@bounded_operation
async def workflow_run(
    workflow: WorkflowName, body: WorkflowRequest, request: Request, session: Session
) -> Envelope[WorkflowRun]:
    app = request.app.state
    source_id = None
    bundle = app.scenarios.bundle
    change = app.scenarios.changes.get(body.change_id) if body.change_id else None
    if body.change_id and not change:
        raise DomainError("CHANGE_NOT_FOUND", "The requested change was not found.", 404)
    mandate_id = body.mandate_id or (change.mandate_id if change else None)
    if mandate_id and not any(m.id == mandate_id for m in bundle.mandates):
        raise DomainError("MANDATE_NOT_FOUND", "The requested mandate was not found.", 404)
    if change and mandate_id != change.mandate_id:
        raise DomainError("CONTEXT_MISMATCH", "Select a mandate belonging to this change.", 422)
    if workflow in {"risk-map", "policy-map"} and not mandate_id:
        raise DomainError("MANDATE_REQUIRED", "Select a mandate for this workflow.", 422)
    context = {
        "sources": [
            i.model_dump(mode="json")
            | {"legal_force": "GUIDANCE" if i.status == "IN_FORCE" else "PROPOSED_BINDING"}
            for i in bundle.instruments
        ],
        "evidence": [e.model_dump(mode="json") for e in bundle.evidence],
        "mandates": [m.model_dump(mode="json") for m in bundle.mandates],
        "mandate_ids": [m.id for m in bundle.mandates],
        "entity_ids": [m.id for m in bundle.mandates] + [n.id for n in bundle.catalog],
        "proposal_notice": bundle.scenario.proposal_notice,
        "proposed_change_statements": [
            p.model_dump(mode="json") for p in bundle.proposed_change_statements
        ],
    }
    if workflow in {"interpret", "pcs-extract"}:
        source_id = (
            bundle.versions[0].instrument_id
            if workflow == "interpret"
            else bundle.proposals[0].source_id
        )
        await app.sources.refresh(source_id)
        document = app.sources.document(source_id)
        if app.workflows.transport and (
            document is None or document.extraction_status != "COMPLETE"
        ):
            raise DomainError(
                "SOURCE_EXTRACTION_REQUIRED",
                "Complete PDF extraction is required before interpreting a source. "
                "Curated paraphrases cannot replace the original document.",
                409,
            )
        if document:
            context["evidence"] = [s.model_dump(mode="json") for s in document.segments]
            context["source_sha256"] = document.sha256
    if app.workflows.transport:
        await asyncio.to_thread(app.limiter.acquire)
    if mandate_id:
        context["selected_mandate_id"] = mandate_id
    if workflow == "policy-map":
        if not mandate_id:
            raise DomainError("MANDATE_REQUIRED", "Select a mandate for policy mapping.", 422)
        state = await asyncio.to_thread(app.sessions.snapshot, session)
        if mandate_id in state.mappings:
            raise DomainError(
                "MAPPING_ALREADY_REVIEWED",
                "Reset this demo before proposing another mapping for a reviewed mandate.",
                409,
            )
        await candidates(mandate_id, request, session)
        state = await asyncio.to_thread(app.sessions.snapshot, session)
        retrieved = CandidateResult.model_validate(state.runs[f"candidates:{mandate_id}"])
        context["candidates"] = [c.model_dump(mode="json") for c in retrieved.candidates]
    elif workflow == "risk-map":
        context["candidates"] = [
            n.model_dump(mode="json")
            for n in bundle.catalog
            if n.type in {NodeType.RISK_TYPE, NodeType.RISK_DRIVER}
        ]
    if workflow in {"change-effect", "impact-explain"}:
        if not change:
            raise DomainError("CHANGE_REQUIRED", "Select a change for this workflow.", 422)
        state = await asyncio.to_thread(app.sessions.snapshot, session)
        effective_change = app.scenarios.effective_change(change, state)
        context.update(app.scenarios.safety_checks(effective_change).model_dump(mode="json"))
        context["change"] = change.model_dump(mode="json")
        impact = await asyncio.to_thread(app.scenarios.impact.change_impact, change.id)
        context["impact"] = impact.model_dump(mode="json")
        if workflow == "impact-explain":
            context["allowed_claims"] = [
                {
                    "text": f"If adopted, review control {c['title']} "
                    "through approved mandate-policy-control lineage.",
                    "entity_ids": [change.mandate_id, c["id"]],
                    "legal_status": "PROPOSED",
                }
                for c in context["impact"]["controls"]
            ] or [
                {
                    "text": "The proposed obligation has no approved mandate-policy-control path.",
                    "entity_ids": [change.mandate_id],
                    "legal_status": "PROPOSED",
                }
            ]
    result = await app.workflows.run(workflow, context)
    result = result.model_copy(
        update={
            "run": result.run.model_copy(
                update={
                    "change_id": change.id if change else None,
                    "mandate_id": mandate_id,
                    "source_id": source_id,
                }
            )
        }
    )
    await asyncio.to_thread(
        save_run, request, session, result.model_dump(mode="json") | {"_context": context}
    )
    if workflow == "policy-map" and result.output is not None:
        output = result.output
        selected_ids = [i for i in [output["candidate_id"], *output["alternative_ids"]] if i]
        selected = tuple(
            next(c for c in retrieved.candidates if c.id == i).model_copy(
                update={
                    "reason": output["reason"]
                    if i == output["candidate_id"]
                    else "Alternative selected by Gemini for specialist comparison; not approved."
                }
            )
            for i in selected_ids
        )
        recommendation = retrieved.model_copy(
            update={
                "candidates": selected,
                "run": result.run,
                "review_status": "NO_SUITABLE_CANDIDATE"
                if output["decision"] == "NO_SUITABLE_CANDIDATE"
                else "HUMAN_REVIEW_REQUIRED",
            }
        )
        await asyncio.to_thread(
            save_run,
            request,
            session,
            recommendation.model_dump(mode="json"),
            f"recommendations:{mandate_id}",
            unreviewed_mandate=mandate_id,
        )
    return respond(request, result.run)


@router.get("/ask/config", response_model=Envelope[AskConfig])
def ask_config(request: Request) -> Envelope[AskConfig]:
    return respond(request, request.app.state.ask.config())


@router.post("/ask", response_model=Envelope[AskResponse])
@bounded_operation
async def ask(body: AskRequest, request: Request, session: Session) -> Envelope[AskResponse]:
    await asyncio.to_thread(request.app.state.limiter.acquire)
    result = await request.app.state.ask.ask(body.question, body.scenario_id)
    await asyncio.to_thread(save_run, request, session, result.model_dump(mode="json"))
    return respond(request, result)
