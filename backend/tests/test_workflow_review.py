import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import pytest

from app.ai.transport import ModelResponse
from app.domain.errors import DomainError
from app.domain.graph import approved_control_paths
from app.domain.models import Classification
from app.domain.workflow_review import ImpactReviewRequest, ReviewRequest
from app.repositories.sessions import SessionRepository
from app.services.ai_workflows import BoundedWorkflowService
from app.services.impact import ImpactService
from app.services.scenarios import ScenarioService
from app.services.workflow_review import WorkflowReviewService


class Repository:
    def __init__(self, bundle):
        self.bundle = bundle

    def snapshot(self):
        return self.bundle

    def approved_outgoing(self, node_id):
        return tuple(
            e for e in self.bundle.edges if e.source_id == node_id and e.status == "APPROVED"
        )

    def approved_control_paths(self, mandate_id):
        return approved_control_paths(self.bundle, mandate_id)


def create_service(bundle):
    repository = Repository(bundle)
    return WorkflowReviewService(
        ScenarioService(repository, SessionRepository(600, 20), ImpactService(bundle, repository))
    )


def body(decision="APPROVE", role="Regulatory Specialist", **kwargs):
    return ReviewRequest(
        decision=decision,
        role=role,
        reviewer="Independent specialist",
        rationale="Reviewed the exact source context and prospective scope.",
        **kwargs,
    )


def evidence(bundle, change_id="CHANGE-GIFT"):
    change = next(c for c in bundle.changes if c.id == change_id)
    ids = set(change.baseline_evidence_ids + change.proposal_evidence_ids)
    return [
        {"source_id": e.source_id, "segment_id": e.id, "excerpt": None}
        for e in bundle.evidence
        if e.id in ids
    ]


def interpretation(bundle):
    return {
        "mandates": [
            {
                "text": "Prevent gift offers from unduly influencing customer purchases.",
                "applicability": "Public prospecting within the source scope.",
                "legal_force": "GUIDANCE",
                "evidence": evidence(bundle)[:1],
            }
        ]
    }


def prepare(service, session, workflow, output, change_id="CHANGE-GIFT", *, override=None):
    bundle = service.scenarios.bundle
    change = service.scenarios.changes[change_id]
    context = {
        "sources": [i.model_dump(mode="json") for i in bundle.instruments],
        "evidence": [e.model_dump(mode="json") for e in bundle.evidence],
        "mandates": [m.model_dump(mode="json") for m in bundle.mandates],
        "entity_ids": [m.id for m in bundle.mandates],
        "candidates": [{"id": "PR-GIFT-01", "type": "POLICY_REQUIREMENT"}],
        "selected_mandate_id": change.mandate_id,
        "change": change.model_dump(mode="json"),
        **service.scenarios.safety_checks(change).model_dump(mode="json"),
        **(override or {}),
    }

    class Transport:
        model = "injected-test-model"

        async def complete(self, **kwargs):
            return ModelResponse(json.dumps(output))

    result = asyncio.run(BoundedWorkflowService(Transport()).run(workflow, context))
    assert result.output is not None, result.validation_errors
    source_id = (
        bundle.versions[0].instrument_id
        if workflow == "interpret"
        else bundle.proposals[0].source_id
    )
    result = result.model_copy(
        update={
            "run": result.run.model_copy(
                update={
                    "change_id": change.id,
                    "mandate_id": change.mandate_id,
                    "source_id": source_id,
                }
            )
        }
    )
    payload = result.model_dump(mode="json") | {"_context": context}
    service.sessions.transact(session, lambda state: state.runs.update({result.run.id: payload}))
    return result.run.id


def test_review_preserves_original_and_modified_draft_without_baseline_mutation(bundle):
    service, session = create_service(bundle), str(uuid4())
    baseline = bundle.model_dump_json()
    output = interpretation(bundle)
    run_id = prepare(service, session, "interpret", output)
    modified = deepcopy(output)
    modified["mandates"][0]["applicability"] = (
        "Public-place prospecting only, pending specialist adoption."
    )
    result = service.review(run_id, session, body("MODIFY", final_output=modified))
    assert result.review.decision == "MODIFY"
    assert result.review.previous_output == output
    assert result.review.final_output == modified
    assert result.review.final_output_sha256 != result.review.output_sha256
    assert not result.review_allowed
    assert bundle.model_dump_json() == baseline
    assert len(bundle.mandates) == len(service.scenarios.bundle.mandates)
    # Returning a nested dictionary never leaks the committed object.
    result.review.final_output["mandates"][0]["text"] = "tampered external view"
    assert service.detail(run_id, session).review.final_output == modified


def test_empty_modified_output_is_not_silently_replaced_by_original(bundle):
    service, session = create_service(bundle), str(uuid4())
    run_id = prepare(service, session, "interpret", interpretation(bundle))
    with pytest.raises(DomainError) as error:
        service.review(run_id, session, body("MODIFY", final_output={}))
    assert error.value.code == "WORKFLOW_REVIEW_INVALID"


def test_review_enforces_role_session_and_idempotency(bundle):
    service, session = create_service(bundle), str(uuid4())
    run_id = prepare(service, session, "interpret", interpretation(bundle))
    with pytest.raises(DomainError) as error:
        service.review(run_id, session, body(role="Policy Owner"))
    assert error.value.code == "REVIEW_ROLE_MISMATCH"
    with pytest.raises(DomainError) as error:
        service.review(run_id, str(uuid4()), body())
    assert error.value.code == "RUN_NOT_FOUND"
    first = service.review(run_id, session, body())
    second = service.review(run_id, session, body())
    assert first.review == second.review
    with pytest.raises(DomainError):
        service.review(run_id, session, body("REJECT"))
    service.sessions.reset(session)
    with pytest.raises(DomainError):
        service.detail(run_id, session)


@pytest.mark.parametrize("tamper", ["context", "output", "candidate", "evidence"])
def test_modified_review_revalidates_hashes_allowlists_and_evidence(bundle, tamper):
    service, session = create_service(bundle), str(uuid4())
    output = {
        "decision": "RECOMMEND",
        "candidate_id": "PR-GIFT-01",
        "alternative_ids": [],
        "reason": "This policy supports the gift safeguard.",
        "evidence": evidence(bundle),
    }
    run_id = prepare(service, session, "policy-map", output)
    if tamper in {"context", "output"}:

        def corrupt(state):
            if tamper == "context":
                state.runs[run_id]["_context"]["selected_mandate_id"] = "OTHER"
            else:
                state.runs[run_id]["output"]["reason"] = (
                    "A changed statement outside original provenance."
                )

        service.sessions.transact(session, corrupt)
    changed = deepcopy(output)
    if tamper == "candidate":
        changed["candidate_id"] = "INVENTED"
    if tamper == "evidence":
        changed["evidence"][0]["excerpt"] = "A quote that does not exist."
    with pytest.raises(DomainError) as error:
        service.review(run_id, session, body("MODIFY", "Policy Owner", final_output=changed))
    assert error.value.code == "WORKFLOW_REVIEW_INVALID"
    assert service.sessions.snapshot(session).workflow_reviews == {}


def test_accepted_change_effect_cannot_bypass_current_overlay(bundle):
    service, session = create_service(bundle), str(uuid4())
    output = {
        "classification": "UNCHANGED",
        "no_effect_result": "NO_EFFECT_SUPPORTED",
        "reason": "Injected test claims no applicable effects.",
        "evidence": evidence(bundle),
    }
    run_id = prepare(
        service,
        session,
        "change-effect",
        output,
        override={
            "high_confidence_pcs_target": False,
            "applicable_global_overlay": False,
        },
    )
    with pytest.raises(DomainError) as error:
        service.review(run_id, session, body())
    assert error.value.code == "UNSAFE_CARRY_FORWARD"
    assert not service.sessions.snapshot(session).classifications


def test_trusted_reviewed_no_effect_applies_only_to_matching_change(synthetic_safe_service):
    original = synthetic_safe_service.bundle
    identity = next(c for c in original.changes if c.id == "CHANGE-IDENTITY")
    identity = identity.model_copy(
        update={
            "classification": Classification.UNRESOLVED,
            "safety_checks": identity.safety_checks.model_copy(
                update={
                    "no_effect_result": "NOT_RUN",
                    "human_change_confirmed": False,
                }
            ),
        }
    )
    bundle = original.model_copy(
        update={"changes": tuple(identity if c.id == identity.id else c for c in original.changes)}
    )
    service, session = create_service(bundle), str(uuid4())
    output = {
        "classification": "UNCHANGED",
        "no_effect_result": "NO_EFFECT_SUPPORTED",
        "reason": "Synthetic test source scope supports no effect.",
        "evidence": evidence(bundle, identity.id),
    }
    run_id = prepare(service, session, "change-effect", output, identity.id)
    assert (
        service.scenarios.delta_review(bundle.scenario.id, session).metrics.carry_forward_candidates
        == 0
    )
    service.review(run_id, session, body())
    state = service.sessions.snapshot(session)
    effective = service.scenarios.effective_change(identity, state)
    assert effective.safety_checks.no_effect_result == "NO_EFFECT_SUPPORTED"
    assert effective.safety_checks.human_change_confirmed
    assert (
        service.scenarios.delta_review(bundle.scenario.id, session).metrics.carry_forward_candidates
        > 0
    )
    gift = service.scenarios.changes["CHANGE-GIFT"]
    assert (
        service.scenarios.effective_change(gift, state).safety_checks.no_effect_result
        == gift.safety_checks.no_effect_result
    )
    # A reset between preflight and commit must invalidate stale bulk eligibility.
    transact = service.sessions.transact

    def reset_before_commit(session_id, operation):
        service.sessions.reset(session_id)
        return transact(session_id, operation)

    service.sessions.transact = reset_before_commit
    with pytest.raises(DomainError) as error:
        service.scenarios.acknowledge(bundle.scenario.id, session, "Specialist")
    assert error.value.code == "NO_ELIGIBLE_CARRY_FORWARD"


def test_approved_pcs_adds_blocker_but_never_removes_baseline_blockers(synthetic_safe_service):
    service, session = WorkflowReviewService(synthetic_safe_service), str(uuid4())
    bundle = service.scenarios.bundle
    output = {
        "statements": [
            {
                "text": "Synthetic test proposes an instrument-wide scope change.",
                "target_mandate_ids": [],
                "instrument_wide": True,
                "legal_force_after": "PROPOSED_BINDING",
                "evidence": evidence(bundle),
            }
        ]
    }
    run_id = prepare(service, session, "pcs-extract", output)
    assert (
        service.scenarios.delta_review(bundle.scenario.id, session).metrics.carry_forward_candidates
        > 0
    )
    service.review(run_id, session, body())
    assert (
        service.scenarios.delta_review(bundle.scenario.id, session).metrics.carry_forward_candidates
        == 0
    )


def test_control_impact_review_is_separate_idempotent_and_session_scoped(bundle):
    service, session = create_service(bundle), str(uuid4())
    baseline = bundle.model_dump_json()
    assessment = service.impact_assessments("CHANGE-GIFT", session).assessments[0]
    request = ImpactReviewRequest(
        decision="MODIFY",
        reviewer="Policy reviewer",
        role="Policy Owner",
        rationale="Reviewed the control scope against the proposed channel extension.",
        scope_note="If adopted, assess the telemarketing channel within this control scope.",
    )
    first = service.review_impact(assessment.id, session, request)
    assert first.status == "MODIFIED"
    assert first.review.previous_output != first.review.final_output
    assert first.scope_note == request.scope_note
    assert service.review_impact(assessment.id, session, request) == first
    assert bundle.model_dump_json() == baseline
    assert service.impact_assessments("CHANGE-GIFT", None).assessments[0].status == "PENDING_REVIEW"
    service.sessions.reset(session)
    assert (
        service.impact_assessments("CHANGE-GIFT", session).assessments[0].status == "PENDING_REVIEW"
    )


def test_no_control_assessment_is_invented_for_unmapped_proposal(bundle):
    service = create_service(bundle)
    change = next(c for c in bundle.changes if c.classification == Classification.NEW)
    assert service.impact_assessments(change.id, None).assessments == ()


def test_review_endpoints_require_session_and_enforce_gate_role(client, session_headers):
    # The application router must expose real Gate 6 endpoints.
    response = client.get("/api/v1/changes/CHANGE-GIFT/impact-assessments")
    assert response.status_code == 200
    assessment_id = response.json()["data"]["assessments"][0]["id"]
    request = {
        "decision": "APPROVE",
        "reviewer": "Policy reviewer",
        "role": "Policy Owner",
        "rationale": "Reviewed prospective scope against public source evidence.",
    }
    path = f"/api/v1/impact-assessments/{assessment_id}/review"
    assert client.post(path, json=request).status_code == 400
    assert (
        client.post(
            path, headers=session_headers, json=request | {"role": "Risk Steward"}
        ).status_code
        == 422
    )
    response = client.post(path, headers=session_headers, json=request)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "APPROVED"


def test_reviewed_drafts_survive_sqlite_restart_without_mutable_aliases(bundle, tmp_path):
    from app.adapters.sqlite_sessions import SQLiteSessionBackend

    service, session = create_service(bundle), str(uuid4())
    backend = SQLiteSessionBackend(tmp_path / "reviews.db", 600, 20)
    service.scenarios.sessions = SessionRepository(600, 20, backend)
    service.sessions = service.scenarios.sessions
    run_id = prepare(service, session, "interpret", interpretation(bundle))
    service.review(run_id, session, body())
    detached = service.sessions.snapshot(session)
    detached.workflow_reviews[run_id].final_output["mandates"][0]["text"] = "Mutated detached view"
    restored = create_service(bundle)
    restored.scenarios.sessions = SessionRepository(
        600, 20, SQLiteSessionBackend(tmp_path / "reviews.db", 600, 20)
    )
    restored.sessions = restored.scenarios.sessions
    assert restored.detail(run_id, session).review.final_output == interpretation(bundle)


def test_mapping_assessment_rechecks_classification_inside_transaction(bundle):
    from app.domain.reviews import ChangeReview

    service, session = create_service(bundle), str(uuid4())
    identity = service.scenarios.changes["CHANGE-IDENTITY"]
    review = ChangeReview(
        change_id=identity.id,
        previous_classification=identity.classification,
        classification="MODIFIED",
        role="Regulatory Specialist",
        reviewer="Specialist",
        rationale="Synthetic review context for a reset race test.",
        evidence_ids=identity.baseline_evidence_ids + identity.proposal_evidence_ids,
        reviewed_at="2026-10-17T00:00:00+00:00",
    )
    service.sessions.transact(
        session, lambda state: state.classifications.update({identity.id: review})
    )
    assessment = next(
        a
        for a in service.scenarios.assessments(session)
        if a.mandate_id == identity.mandate_id and a.required_role == "Policy Owner"
    )
    transact = service.sessions.transact

    def reset_before_commit(session_id, operation):
        service.sessions.reset(session_id)
        return transact(session_id, operation)

    service.sessions.transact = reset_before_commit
    with pytest.raises(DomainError) as error:
        service.scenarios.review(
            assessment.id,
            session,
            "APPROVE",
            "Policy reviewer",
            "Review attempted across a concurrent reset.",
            "Policy Owner",
        )
    assert error.value.code == "CHANGE_REVIEW_REQUIRED"
    assert not service.sessions.snapshot(session).decisions


def test_workflow_api_returns_review_audit_but_not_internal_context(client, session_headers):
    service = WorkflowReviewService(client.app.state.scenarios)
    session = session_headers["X-Demo-Session"]
    run_id = prepare(service, session, "interpret", interpretation(service.scenarios.bundle))
    route = f"/api/v1/workflows/runs/{run_id}"
    before = client.get(route, headers=session_headers)
    assert before.status_code == 200
    assert before.json()["data"]["review_allowed"]
    assert "_context" not in before.json()["data"]
    result = client.post(route + "/review", headers=session_headers, json=body().model_dump())
    assert result.status_code == 200
    assert result.json()["data"]["review"]["decision"] == "APPROVE"
    assert result.json()["data"]["required_role"] == "Regulatory Specialist"
    assert not result.json()["data"]["review_allowed"]


@pytest.mark.parametrize("decision", ["MODIFY", "REJECT"])
def test_policy_workflow_review_synchronizes_candidate_choices(bundle, decision):
    from app.services.candidates import CandidateService

    service, session = create_service(bundle), str(uuid4())
    retrieval = asyncio.run(CandidateService(Repository(bundle)).retrieve("M-GIFT"))
    service.sessions.transact(
        session,
        lambda state: state.runs.update(
            {
                "candidates:M-GIFT": retrieval.model_dump(mode="json"),
            }
        ),
    )
    original = {
        "decision": "RECOMMEND",
        "candidate_id": "PR-GIFT-01",
        "alternative_ids": [],
        "reason": "Original recommendation for specialist review.",
        "evidence": evidence(bundle),
    }
    run_id = prepare(
        service,
        session,
        "policy-map",
        original,
        override={
            "candidates": [c.model_dump(mode="json") for c in retrieval.candidates],
        },
    )
    alternative = next(c.id for c in retrieval.candidates if c.id != "PR-GIFT-01")
    changed = original | {
        "candidate_id": alternative,
        "reason": "Human corrected recommendation after source review.",
    }
    request = body(
        decision, "Policy Owner", **({"final_output": changed} if decision == "MODIFY" else {})
    )
    service.review(run_id, session, request)
    cached = service.sessions.snapshot(session).runs["recommendations:M-GIFT"]
    assert cached["run"]["id"] == run_id
    if decision == "REJECT":
        assert cached["candidates"] == []
        assert cached["review_status"] == "REJECTED"
    else:
        assert [c["id"] for c in cached["candidates"]] == [alternative]
        assert cached["candidates"][0]["reason"] == changed["reason"]
    assert service.detail(run_id, session).output == original
