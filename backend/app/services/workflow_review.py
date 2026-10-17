"""Human review gates for bounded output; approvals never rewrite baseline data."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.ai.contracts import OUTPUT_SCHEMAS, Candidate, CandidateResult, WorkflowRun
from app.domain.errors import DomainError
from app.domain.models import Classification
from app.domain.reviews import ChangeReview
from app.domain.workflow_review import (
    REQUIRED_ROLES,
    ControlImpactReview,
    ImpactReviewDecision,
    ImpactReviewList,
    ImpactReviewRequest,
    ReviewRequest,
    WorkflowReviewDecision,
    WorkflowReviewView,
)
from app.repositories.sessions import SessionState
from app.services.ai_workflows import _ground_output
from app.services.human_review import HumanReviewService
from app.services.scenarios import ScenarioService


class WorkflowReviewService:
    def __init__(self, scenarios: ScenarioService) -> None:
        self.scenarios = scenarios
        self.sessions = scenarios.sessions

    @staticmethod
    def _stored(run_id: str, state: SessionState) -> dict[str, Any]:
        matches = [v for v in state.runs.values() if v.get("run", {}).get("id") == run_id]
        if not matches:
            raise DomainError("RUN_NOT_FOUND", "This run is unavailable in this demo session.", 404)
        # A recommendation cache may share the same run ID; prefer the actual workflow output.
        return next((v for v in matches if "output" in v), matches[0])

    @staticmethod
    def _block_reason(stored: dict[str, Any]) -> str | None:
        run = WorkflowRun.model_validate(stored["run"])
        if run.workflow not in REQUIRED_ROLES:
            return "This record is a read-only retrieval or answer, not a reviewable workflow."
        if (
            run.kind != "LIVE_AI"
            or run.status != "SUCCEEDED"
            or run.validation_status != "PASSED"
            or not isinstance(stored.get("output"), dict)
        ):
            return "Only a successfully validated bounded workflow output can be reviewed."
        if not isinstance(stored.get("_context"), dict):
            return "The original deterministic context is unavailable; run this workflow again."
        if not run.input_sha256 or not run.output_sha256:
            return "The original input/output hashes are unavailable; run this workflow again."
        return None

    def detail(self, run_id: str, session_id: str | None) -> WorkflowReviewView:
        state = self.sessions.snapshot(session_id)
        stored = self._stored(run_id, state)
        run = WorkflowRun.model_validate(stored["run"])
        review = state.workflow_reviews.get(run_id)
        reason = self._block_reason(stored)
        if review:
            reason = "A human decision is recorded. Reset this demo to make a new decision."
        output = stored.get("output")
        if "output" not in stored:
            output = {k: v for k, v in stored.items() if k != "run" and not k.startswith("_")}
        status = stored.get("status", "HUMAN_REVIEW_REQUIRED")
        if status not in {"HUMAN_REVIEW_REQUIRED", "MANUAL_REVIEW_REQUIRED", "AI_NOT_CONFIGURED"}:
            status = "MANUAL_REVIEW_REQUIRED"
        return WorkflowReviewView(
            run=run,
            output=deepcopy(output),
            status=status,
            validation_errors=tuple(stored.get("validation_errors", ())),
            required_role=REQUIRED_ROLES.get(run.workflow),
            review_allowed=reason is None,
            block_reason=reason,
            review=review,
        )

    @staticmethod
    def _validated_output(stored: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
        run = WorkflowRun.model_validate(stored["run"])
        context = stored["_context"]
        actual_input_hash = hashlib.sha256(
            json.dumps(context, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        schema = OUTPUT_SCHEMAS[run.workflow]
        try:
            original = schema.model_validate(stored["output"])
            original_hash = hashlib.sha256(original.model_dump_json().encode()).hexdigest()
            if actual_input_hash != run.input_sha256 or original_hash != run.output_sha256:
                raise ValueError("Stored workflow provenance does not match its original hashes")
            parsed = schema.model_validate(value)
            result = parsed.model_dump(mode="json")
            _ground_output(result, context)
            return result
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            raise DomainError(
                "WORKFLOW_REVIEW_INVALID",
                "The reviewed output failed schema, evidence, candidate or provenance validation.",
                422,
            ) from exc

    def review(self, run_id: str, session_id: str, body: ReviewRequest) -> WorkflowReviewView:
        def apply(state: SessionState) -> None:
            stored = self._stored(run_id, state)
            run = WorkflowRun.model_validate(stored["run"])
            required_role = REQUIRED_ROLES.get(run.workflow)
            if body.role != required_role:
                raise DomainError(
                    "REVIEW_ROLE_MISMATCH", f"This output requires {required_role}.", 403
                )
            reason = self._block_reason(stored)
            if reason:
                raise DomainError("WORKFLOW_REVIEW_UNAVAILABLE", reason, 409)
            final = (
                self._validated_output(
                    stored,
                    body.final_output if body.decision == "MODIFY" else stored["output"],
                )
                if body.decision != "REJECT"
                else None
            )
            existing = state.workflow_reviews.get(run_id)
            if existing:
                if (
                    existing.decision,
                    existing.reviewer,
                    existing.role,
                    existing.rationale,
                    existing.final_output,
                ) == (body.decision, body.reviewer, body.role, body.rationale, final):
                    return
                raise DomainError(
                    "DECISION_ALREADY_RECORDED", "Reset before changing this review.", 409
                )
            accepted = body.decision != "REJECT"
            if accepted:
                self._validate_subject(run, stored["_context"])
            if (
                accepted
                and run.workflow == "pcs-extract"
                and (state.decisions or state.mappings or state.impact_reviews)
            ):
                raise DomainError(
                    "SCENARIO_ALREADY_REVIEWED",
                    "Reset before accepting new PCS evidence after downstream decisions.",
                    409,
                )
            timestamp = datetime.now(UTC).isoformat()
            if accepted and run.workflow == "change-effect":
                self._authorize_change(run, final, body, state, timestamp)
            if run.workflow == "policy-map":
                self._sync_policy(run, final, stored, state)
            state.workflow_reviews[run_id] = WorkflowReviewDecision(
                run_id=run.id,
                workflow=run.workflow,
                change_id=run.change_id,
                mandate_id=run.mandate_id,
                source_id=run.source_id,
                decision=body.decision,
                reviewer=body.reviewer,
                role=body.role,
                rationale=body.rationale,
                reviewed_at=timestamp,
                previous_output=deepcopy(stored["output"]),
                final_output=deepcopy(final),
                input_sha256=run.input_sha256,
                output_sha256=run.output_sha256,
                final_output_sha256=hashlib.sha256(
                    OUTPUT_SCHEMAS[run.workflow].model_validate(final).model_dump_json().encode()
                ).hexdigest()
                if final is not None
                else None,
            )

        self.sessions.transact(session_id, apply)
        return self.detail(run_id, session_id)

    @staticmethod
    def _sync_policy(
        run: WorkflowRun,
        final: dict[str, Any] | None,
        stored: dict[str, Any],
        state: SessionState,
    ) -> None:
        if run.mandate_id in state.mappings:
            raise DomainError(
                "MAPPING_ALREADY_REVIEWED", "Reset before revising a mapped recommendation.", 409
            )
        original = state.runs.get(f"candidates:{run.mandate_id}")
        if original is None:
            raise DomainError(
                "CANDIDATE_RETRIEVAL_REQUIRED",
                "The original candidate retrieval is unavailable.",
                409,
            )
        retrieval = CandidateResult.model_validate(original)
        selected_ids = (
            []
            if final is None
            else [i for i in [final["candidate_id"], *final["alternative_ids"]] if i is not None]
        )
        allowed = {c["id"]: Candidate.model_validate(c) for c in stored["_context"]["candidates"]}
        selected = tuple(
            allowed[candidate_id].model_copy(
                update={
                    "reason": final["reason"]
                    if candidate_id == final["candidate_id"]
                    else "Alternative retained in the human-reviewed recommendation draft.",
                }
            )
            for candidate_id in selected_ids
        )
        recommendation = retrieval.model_copy(
            update={
                "candidates": selected,
                "run": run,
                "review_status": "REJECTED"
                if final is None
                else "NO_SUITABLE_CANDIDATE"
                if not selected
                else "HUMAN_REVIEW_REQUIRED",
            }
        )
        state.runs[f"recommendations:{run.mandate_id}"] = recommendation.model_dump(mode="json")

    def _validate_subject(self, run: WorkflowRun, context: dict[str, Any]) -> None:
        if run.workflow in {"interpret", "pcs-extract"}:
            expected = (
                self.scenarios.bundle.versions[0].instrument_id
                if run.workflow == "interpret"
                else self.scenarios.bundle.proposals[0].source_id
            )
            if run.source_id != expected:
                raise DomainError(
                    "WORKFLOW_SUBJECT_INVALID",
                    "The reviewed source does not match this workflow.",
                    422,
                )
        elif run.workflow in {"risk-map", "policy-map"}:
            if (
                run.mandate_id not in self.scenarios.impact.mandates
                or context.get("selected_mandate_id") != run.mandate_id
            ):
                raise DomainError(
                    "WORKFLOW_SUBJECT_INVALID", "The reviewed mandate does not match this run.", 422
                )
        elif run.workflow in {"change-effect", "impact-explain"}:
            change = self.scenarios.changes.get(run.change_id)
            if (
                change is None
                or run.mandate_id != change.mandate_id
                or context.get("change", {}).get("id") != change.id
            ):
                raise DomainError(
                    "WORKFLOW_SUBJECT_INVALID", "The reviewed change does not match this run.", 422
                )

    def _authorize_change(
        self,
        run: WorkflowRun,
        final: dict[str, Any],
        body: ReviewRequest,
        state: SessionState,
        timestamp: str,
    ) -> None:
        change = self.scenarios.changes.get(run.change_id)
        if change is None or run.mandate_id != change.mandate_id:
            raise DomainError("WORKFLOW_SUBJECT_INVALID", "Change/run subject does not match.", 422)
        if change.id in state.classifications:
            raise DomainError(
                "DECISION_ALREADY_RECORDED", "This change already has a specialist decision.", 409
            )
        if (
            change.mandate_id in state.mappings
            or any(
                self.scenarios.edges.get(key.removeprefix("ASSESS-"), None)
                and self.scenarios.edges[key.removeprefix("ASSESS-")].source_id == change.mandate_id
                for key in state.decisions
            )
            or any(r.change_id == change.id for r in state.impact_reviews.values())
        ):
            raise DomainError(
                "SCENARIO_ALREADY_REVIEWED", "Reset before revising reviewed change effects.", 409
            )
        classification = Classification(final["classification"])
        if classification == Classification.UNRESOLVED:
            raise DomainError(
                "CHANGE_UNRESOLVED", "Resolve ambiguity before approving change analysis.", 409
            )
        baseline = change.mandate_id in self.scenarios.bundle.scenario.baseline_mandate_ids
        if (classification == Classification.NEW) == baseline:
            raise DomainError(
                "CLASSIFICATION_INVALID", "Classification conflicts with baseline membership.", 422
            )
        evidence_ids = tuple(dict.fromkeys(item["segment_id"] for item in final["evidence"]))
        required = set(change.baseline_evidence_ids + change.proposal_evidence_ids)
        if not required <= set(evidence_ids):
            raise DomainError(
                "CHANGE_EVIDENCE_REQUIRED",
                "Include every displayed baseline/proposal evidence reference "
                "in the reviewed output.",
                422,
            )
        checks = self.scenarios.safety_checks(self.scenarios.effective_change(change, state))
        if classification == Classification.UNCHANGED and (
            final["no_effect_result"] != "NO_EFFECT_SUPPORTED"
            or checks.high_confidence_pcs_target
            or checks.applicable_global_overlay
        ):
            raise DomainError(
                "UNSAFE_CARRY_FORWARD", "PCS or scope blockers prevent unchanged approval.", 409
            )
        state.classifications[change.id] = ChangeReview(
            change_id=change.id,
            classification=classification,
            previous_classification=change.classification,
            reviewer=body.reviewer,
            role="Regulatory Specialist",
            rationale=body.rationale,
            reviewed_at=timestamp,
            evidence_ids=evidence_ids,
        )

    def impact_assessments(self, change_id: str, session_id: str | None) -> ImpactReviewList:
        impact = HumanReviewService(self.scenarios).prospective_impact(change_id, session_id)
        state = self.sessions.snapshot(session_id)
        values = []
        for control in impact.controls:
            assessment_id = f"IMPACT-{change_id}-{control.id}"
            review = state.impact_reviews.get(assessment_id)
            scope = (
                f"If adopted, review {control.title} for this proposal's scope and implementation."
            )
            if review and review.final_output:
                scope = review.final_output["scope_note"]
            values.append(
                ControlImpactReview(
                    id=assessment_id,
                    change_id=change_id,
                    control_id=control.id,
                    title=control.title,
                    scope_note=scope,
                    review=review,
                    status={"APPROVE": "APPROVED", "REJECT": "REJECTED", "MODIFY": "MODIFIED"}[
                        review.decision
                    ]
                    if review
                    else "PENDING_REVIEW",
                )
            )
        return ImpactReviewList(assessments=tuple(values))

    def review_impact(
        self,
        assessment_id: str,
        session_id: str,
        body: ImpactReviewRequest,
    ) -> ControlImpactReview:
        assessment = next(
            (
                item
                for change in self.scenarios.bundle.changes
                for item in self.impact_assessments(change.id, session_id).assessments
                if item.id == assessment_id
            ),
            None,
        )
        if assessment is None:
            raise DomainError(
                "IMPACT_ASSESSMENT_NOT_FOUND", "No approved path supports this assessment.", 404
            )
        base_scope = (
            f"If adopted, review {assessment.title} for this proposal's scope and implementation."
        )
        previous = {"impact_type": "PROSPECTIVE_REVIEW", "scope_note": base_scope}
        final = (
            None
            if body.decision == "REJECT"
            else {
                "impact_type": "PROSPECTIVE_REVIEW",
                "scope_note": body.scope_note or base_scope,
            }
        )

        def apply(state: SessionState) -> None:
            # Re-evaluate against this transaction's mappings to reject stale/reset paths.
            control_exists = any(
                c.id == assessment.control_id
                for c in self.scenarios.impact.change_impact(assessment.change_id).controls
            )
            change = self.scenarios.changes[assessment.change_id]
            mapping = state.mappings.get(change.mandate_id)
            if mapping and mapping.decision == "APPROVE":
                control_exists |= any(
                    edge.source_id == mapping.policy_id
                    and edge.target_id == assessment.control_id
                    and edge.relationship == "IMPLEMENTED_BY"
                    and edge.status == "APPROVED"
                    for edge in self.scenarios.bundle.edges
                )
            if not control_exists:
                raise DomainError(
                    "IMPACT_PATH_CHANGED", "Refresh the prospective impact before review.", 409
                )
            existing = state.impact_reviews.get(assessment_id)
            if existing:
                if (
                    existing.decision,
                    existing.reviewer,
                    existing.rationale,
                    existing.final_output,
                ) == (
                    body.decision,
                    body.reviewer,
                    body.rationale,
                    final,
                ):
                    return
                raise DomainError(
                    "DECISION_ALREADY_RECORDED", "Reset before changing this assessment.", 409
                )
            state.impact_reviews[assessment_id] = ImpactReviewDecision(
                assessment_id=assessment_id,
                change_id=assessment.change_id,
                control_id=assessment.control_id,
                decision=body.decision,
                reviewer=body.reviewer,
                role=body.role,
                rationale=body.rationale,
                reviewed_at=datetime.now(UTC).isoformat(),
                previous_output=previous,
                final_output=deepcopy(final),
            )

        self.sessions.transact(session_id, apply)
        return next(
            a
            for a in self.impact_assessments(assessment.change_id, session_id).assessments
            if a.id == assessment_id
        )
