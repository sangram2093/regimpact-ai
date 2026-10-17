from datetime import UTC, datetime
from typing import Literal

from app.domain.errors import DomainError
from app.domain.models import (
    MANDATE_RELATIONSHIPS,
    AgentRun,
    AssessmentStatus,
    ChangeItem,
    Classification,
    Relationship,
    ReviewDecision,
    SafetyChecks,
    ScenarioMappingAssessment,
)
from app.domain.rules import carry_forward_eligible, review_metrics
from app.domain.views import (
    AssessmentView,
    ChangeDetail,
    ChangeSummary,
    Dashboard,
    DeltaReview,
    ImpactSummary,
    MandateSummary,
)
from app.repositories.ports import RegulatoryRepository
from app.repositories.sessions import SessionRepository, SessionState
from app.services.impact import ImpactService


class ScenarioService:
    def __init__(
        self, repository: RegulatoryRepository, sessions: SessionRepository, impact: ImpactService
    ) -> None:
        self.bundle = repository.snapshot()
        self.sessions = sessions
        self.impact = impact
        self.changes = {change.id: change for change in self.bundle.changes}
        self.by_mandate = {change.mandate_id: change for change in self.bundle.changes}
        self.edges = {edge.id: edge for edge in self.bundle.edges}

    def safety_checks(self, change: ChangeItem) -> SafetyChecks:
        # Recompute PCS blockers from graph data. A mislabeled fixture flag must
        # never bypass a known target or instrument-wide overlay.
        pcs = self.bundle.proposed_change_statements
        return change.safety_checks.model_copy(
            update={
                "high_confidence_pcs_target": change.safety_checks.high_confidence_pcs_target
                or any(change.mandate_id in item.target_mandate_ids for item in pcs),
                "applicable_global_overlay": change.safety_checks.applicable_global_overlay
                or any(item.global_scope for item in pcs),
            }
        )

    def effective_change(self, change: ChangeItem, state: SessionState) -> ChangeItem:
        review = state.classifications.get(change.id)
        safety = change.safety_checks.model_dump()
        for workflow_review in state.workflow_reviews.values():
            output = workflow_review.final_output
            if workflow_review.decision == "REJECT" or output is None:
                continue
            if (
                workflow_review.workflow == "pcs-extract"
                and workflow_review.source_id == self.bundle.proposals[0].source_id
            ):
                for statement in output.get("statements", []):
                    safety["high_confidence_pcs_target"] |= (
                        change.mandate_id in statement["target_mandate_ids"]
                    )
                    safety["applicable_global_overlay"] |= statement["instrument_wide"]
            if (
                workflow_review.workflow == "change-effect"
                and workflow_review.change_id == change.id
                and workflow_review.mandate_id == change.mandate_id
                and review is not None
                and workflow_review.role == "Regulatory Specialist"
                and output.get("classification") == review.classification
            ):
                safety["no_effect_result"] = (
                    output["no_effect_result"]
                    if output["no_effect_result"] in {"NO_EFFECT_SUPPORTED", "EFFECT_POSSIBLE"}
                    else "NOT_RUN"
                )
                safety["scope_basis"] = (
                    "Human-reviewed bounded change analysis: " + workflow_review.run_id
                )
        if review:
            safety["human_change_confirmed"] = True
        return change.model_copy(
            update={
                "classification": review.classification if review else change.classification,
                "safety_checks": SafetyChecks.model_validate(safety),
            }
        )

    def _base_assessments(
        self, state: SessionState | None = None
    ) -> tuple[ScenarioMappingAssessment, ...]:
        assessments = []
        for edge in self.bundle.edges:
            if (
                edge.status != "APPROVED"
                or edge.relationship not in MANDATE_RELATIONSHIPS
                or edge.source_id not in self.bundle.scenario.baseline_mandate_ids
            ):
                continue
            change = self.by_mandate.get(edge.source_id)
            if change and state:
                change = self.effective_change(change, state)
            classification = change.classification if change else Classification.UNRESOLVED
            eligible = bool(
                change and carry_forward_eligible(classification, self.safety_checks(change))
            )
            if eligible:
                status = AssessmentStatus.CARRY_FORWARD_PENDING_ACK
                recommendation = "Acknowledge prospective reuse"
            elif classification == Classification.UNRESOLVED:
                status = AssessmentStatus.MANUAL_REVIEW_REQUIRED
                recommendation = "Confirm change effect before mapping review"
            else:
                status = AssessmentStatus.RE_REVIEW_REQUIRED
                recommendation = (
                    "Review prospective retirement"
                    if classification == Classification.REMOVED
                    else "Review prospective mapping individually"
                )
            assessments.append(
                ScenarioMappingAssessment(
                    id=f"ASSESS-{edge.id}",
                    scenario_id=self.bundle.scenario.id,
                    baseline_edge_id=edge.id,
                    mandate_id=edge.source_id,
                    classification=classification,
                    status=status,
                    recommendation=recommendation,
                    reason="Approval authorizes prospective retirement in this scenario only; "
                    "the approved baseline remains unchanged."
                    if classification == Classification.REMOVED
                    else change.safety_checks.scope_basis
                    if change
                    else "No change analysis available.",
                    eligible_for_carry_forward=eligible,
                )
            )
        return tuple(assessments)

    def assessments(self, session_id: str | None) -> tuple[AssessmentView, ...]:
        state = self.sessions.snapshot(session_id)
        return self._apply_decisions(state.decisions, state)

    def _apply_decisions(
        self, decisions: dict[str, ReviewDecision], state: SessionState | None = None
    ) -> tuple[AssessmentView, ...]:
        views = []
        status_for = {
            "ACKNOWLEDGE": AssessmentStatus.SCENARIO_ACKNOWLEDGED,
            "APPROVE": AssessmentStatus.SCENARIO_APPROVED,
            "REJECT": AssessmentStatus.SCENARIO_REJECTED,
        }
        for assessment in self._base_assessments(state):
            decision = decisions.get(assessment.id)
            edge = self.edges[assessment.baseline_edge_id]
            values = assessment.model_dump()
            if decision:
                values.update(
                    status=status_for[decision.decision],
                    reviewed_by=decision.reviewer,
                    rationale=decision.rationale,
                    reviewed_at=decision.reviewed_at,
                )
            views.append(
                AssessmentView(
                    **values,
                    mandate_title=self.impact.mandates[assessment.mandate_id].title,
                    target_id=edge.target_id,
                    target_label=self.impact.catalog[edge.target_id].title,
                    relationship=edge.relationship,
                    required_role=(
                        "Policy Owner"
                        if edge.relationship == Relationship.ADDRESSED_BY
                        else "Risk Steward"
                    ),
                )
            )
        return tuple(views)

    def _require_scenario(self, scenario_id: str) -> None:
        if scenario_id != self.bundle.scenario.id:
            raise DomainError("SCENARIO_NOT_FOUND", "The requested scenario was not found.", 404)

    def delta_review(self, scenario_id: str, session_id: str | None) -> DeltaReview:
        self._require_scenario(scenario_id)
        assessments = self.assessments(session_id)
        new_count = sum(
            change.classification == Classification.NEW for change in self.bundle.changes
        )
        return DeltaReview(
            scenario_id=scenario_id,
            assessments=assessments,
            metrics=review_metrics(assessments, new_count),
        )

    def _summary(
        self, change: ChangeItem, assessments: tuple[AssessmentView, ...]
    ) -> ChangeSummary:
        relevant = [a for a in assessments if a.mandate_id == change.mandate_id]
        if change.classification == Classification.NEW:
            state = "NO_POLICY_MAPPING"
        elif relevant and len({a.status for a in relevant}) == 1:
            state = relevant[0].status
        else:
            state = "REVIEW_IN_PROGRESS"
        return ChangeSummary(
            id=change.id,
            title=change.title,
            classification=change.classification,
            change_nature=change.change_nature,
            summary=change.summary,
            mandate_id=change.mandate_id,
            impacted_controls=len(self.impact.change_impact(change.id).controls),
            review_status=state,
        )

    def dashboard(self, session_id: str | None) -> Dashboard:
        delta = self.delta_review(self.bundle.scenario.id, session_id)
        state = self.sessions.snapshot(session_id)
        impacts = [self.impact.change_impact(change.id) for change in self.bundle.changes]
        return Dashboard(
            scenario=self.bundle.scenario,
            metrics=delta.metrics,
            changes=tuple(
                self._summary(self.effective_change(change, state), delta.assessments)
                for change in self.bundle.changes
            ),
            impact_summary=ImpactSummary(
                policies=len(
                    {
                        node.id
                        for impact in impacts
                        for node in impact.nodes
                        if node.type == "POLICY_REQUIREMENT"
                    }
                ),
                controls=len({control.id for impact in impacts for control in impact.controls}),
                coverage_gaps=sum(impact.coverage != "COMPLETE" for impact in impacts),
                review_needed=delta.metrics.individual_rechecks - delta.metrics.completed_rechecks,
            ),
            run=AgentRun(),
        )

    def change_detail(self, change_id: str, session_id: str | None) -> ChangeDetail:
        change = self.changes.get(change_id)
        if change is None:
            raise DomainError("CHANGE_NOT_FOUND", "The requested change was not found.", 404)
        change = self.effective_change(change, self.sessions.snapshot(session_id))
        mandate = self.impact.mandates[change.mandate_id]
        return ChangeDetail(
            **self._summary(change, self.assessments(session_id)).model_dump(),
            classification_review=self.sessions.snapshot(session_id).classifications.get(change_id),
            scenario_id=self.bundle.scenario.id,
            baseline_evidence=tuple(self.impact.evidence[i] for i in change.baseline_evidence_ids),
            proposal_evidence=tuple(self.impact.evidence[i] for i in change.proposal_evidence_ids),
            mandate=MandateSummary(id=mandate.id, title=mandate.title),
            risk_tags=self.impact.risk_tags(mandate.id),
            safety_checks=self.safety_checks(change),
            proposal_notice=self.bundle.scenario.proposal_notice,
            legal_force_note=(
                "Proposed Notices apply to investment products and long-term accident "
                "and health policies. Other products retain guideline treatment."
            ),
        )

    def acknowledge(self, scenario_id: str, session_id: str, reviewer: str) -> DeltaReview:
        self._require_scenario(scenario_id)
        eligible = tuple(
            a
            for a in self._base_assessments(self.sessions.snapshot(session_id))
            if a.eligible_for_carry_forward
        )
        if not eligible:
            raise DomainError(
                "NO_ELIGIBLE_CARRY_FORWARD",
                "No mappings meet all carry-forward safeguards. "
                "Review scope and legal-force effects.",
                409,
            )

        def apply(state: SessionState) -> None:
            current_eligible = tuple(
                a for a in self._base_assessments(state) if a.eligible_for_carry_forward
            )
            if not current_eligible:
                raise DomainError(
                    "NO_ELIGIBLE_CARRY_FORWARD",
                    "Eligibility changed; refresh the review before acknowledging.",
                    409,
                )
            for assessment in current_eligible:
                if assessment.id not in state.decisions:
                    state.decisions[assessment.id] = ReviewDecision(
                        assessment_id=assessment.id,
                        decision="ACKNOWLEDGE",
                        reviewer=reviewer,
                        role="Regulatory Specialist",
                        rationale="Acknowledged prospective reuse.",
                        reviewed_at=datetime.now(UTC).isoformat(),
                    )

        self.sessions.transact(session_id, apply)
        return self.delta_review(scenario_id, session_id)

    def review(
        self,
        assessment_id: str,
        session_id: str,
        decision: Literal["APPROVE", "REJECT"],
        reviewer: str,
        rationale: str,
        role: Literal["Policy Owner", "Risk Steward"],
    ) -> AssessmentView:
        assessment = next(
            (
                a
                for a in self._base_assessments(self.sessions.snapshot(session_id))
                if a.id == assessment_id
            ),
            None,
        )
        if assessment is None:
            raise DomainError(
                "ASSESSMENT_NOT_FOUND", "The requested assessment was not found.", 404
            )
        edge = self.edges[assessment.baseline_edge_id]
        required_role = (
            "Policy Owner" if edge.relationship == Relationship.ADDRESSED_BY else "Risk Steward"
        )
        if role != required_role:
            raise DomainError(
                "REVIEW_ROLE_MISMATCH", f"This mapping requires a {required_role} review.", 403
            )
        if assessment.eligible_for_carry_forward:
            raise DomainError(
                "BULK_ACK_REQUIRED", "Use the specialist carry-forward acknowledgement.", 409
            )
        if assessment.classification == Classification.UNRESOLVED:
            raise DomainError(
                "CHANGE_REVIEW_REQUIRED",
                "Resolve the change effect before reviewing its mapping.",
                409,
            )

        def apply(state: SessionState) -> None:
            current = next(
                (a for a in self._base_assessments(state) if a.id == assessment_id), None
            )
            if current is None:
                raise DomainError("ASSESSMENT_NOT_FOUND", "The assessment is unavailable.", 404)
            if current.eligible_for_carry_forward:
                raise DomainError(
                    "BULK_ACK_REQUIRED", "Use the specialist carry-forward acknowledgement.", 409
                )
            if current.classification == Classification.UNRESOLVED:
                raise DomainError(
                    "CHANGE_REVIEW_REQUIRED",
                    "Resolve the change before reviewing its mapping.",
                    409,
                )
            current_edge = self.edges[current.baseline_edge_id]
            current_role = (
                "Policy Owner"
                if current_edge.relationship == Relationship.ADDRESSED_BY
                else "Risk Steward"
            )
            if role != current_role:
                raise DomainError(
                    "REVIEW_ROLE_MISMATCH", f"This mapping requires a {current_role} review.", 403
                )
            existing = state.decisions.get(assessment_id)
            if existing:
                if (existing.decision, existing.reviewer, existing.rationale) == (
                    decision,
                    reviewer,
                    rationale,
                ):
                    return
                raise DomainError(
                    "DECISION_ALREADY_RECORDED",
                    "This scenario assessment is already reviewed. "
                    "Reset this demo to review it again.",
                    409,
                )
            state.decisions[assessment_id] = ReviewDecision(
                assessment_id=assessment_id,
                decision=decision,
                reviewer=reviewer,
                role=role,
                rationale=rationale,
                reviewed_at=datetime.now(UTC).isoformat(),
            )

        self.sessions.transact(session_id, apply)
        return next(a for a in self.assessments(session_id) if a.id == assessment_id)
