"Human confirmation and prospective mappings, isolated from the approved catalog."

from datetime import UTC, datetime

from app.domain.errors import DomainError
from app.domain.models import Classification, EdgeProvenance, Relationship
from app.domain.reviews import ChangeReview, PolicyMappingReview
from app.domain.rules import carry_forward_eligible
from app.domain.views import ControlImpact, EdgeExplanation, ImpactEdge, ImpactNode, ImpactResponse
from app.repositories.sessions import SessionState
from app.services.scenarios import ScenarioService


class HumanReviewService:
    def __init__(self, scenarios: ScenarioService) -> None:
        self.scenarios = scenarios
        self.sessions = scenarios.sessions

    def mandates(self, session_id: str | None) -> dict:
        state = self.sessions.snapshot(session_id)
        rows = []
        for mandate in self.scenarios.bundle.mandates:
            change = self.scenarios.by_mandate.get(mandate.id)
            review = state.classifications.get(change.id) if change else None
            evidence = [self.scenarios.impact.evidence[i] for i in mandate.evidence_ids]
            if change:
                ids = dict.fromkeys(change.baseline_evidence_ids + change.proposal_evidence_ids)
                evidence = [self.scenarios.impact.evidence[i] for i in ids]
            rows.append(
                {
                    "id": mandate.id,
                    "title": mandate.title,
                    "text": change.summary if change else mandate.title,
                    "status": mandate.status,
                    "source_id": evidence[0].source_id if evidence else None,
                    "change_id": change.id if change else None,
                    "classification": review.classification
                    if review
                    else change.classification
                    if change
                    else None,
                    "review_status": "HUMAN_CONFIRMED" if review else "HUMAN_REVIEW_REQUIRED",
                    "evidence": evidence,
                    "reviewed_by": review.reviewer if review else None,
                    "rationale": review.rationale if review else None,
                    "classification_confirmed": review is not None,
                }
            )
        return {"mandates": rows}

    def classify(
        self,
        change_id: str,
        session_id: str,
        classification: Classification,
        reviewer: str,
        rationale: str,
        evidence_ids: tuple[str, ...],
    ) -> None:
        if classification == Classification.UNRESOLVED:
            raise DomainError(
                "INVALID_CLASSIFICATION", "Unresolved is not a confirmed interpretation.", 409
            )
        change = self.scenarios.changes.get(change_id)
        if not change:
            raise DomainError("CHANGE_NOT_FOUND", "The requested change was not found.", 404)
        required = set(change.baseline_evidence_ids + change.proposal_evidence_ids)
        if not required or set(evidence_ids) != required:
            raise DomainError(
                "EVIDENCE_REVIEW_REQUIRED",
                "Review every displayed baseline and proposal evidence segment before confirming.",
                409,
            )
        baseline = change.mandate_id in self.scenarios.bundle.scenario.baseline_mandate_ids
        if (classification == Classification.NEW) == baseline:
            raise DomainError(
                "INVALID_CLASSIFICATION",
                (
                    "NEW must describe an obligation without a baseline mapping; "
                    "existing obligations retain baseline lineage."
                ),
                409,
            )
        if classification == Classification.UNCHANGED:
            safety = self.scenarios.safety_checks(change).model_copy(
                update={"human_change_confirmed": True}
            )
            if not carry_forward_eligible(classification, safety):
                raise DomainError(
                    "UNSAFE_UNCHANGED",
                    (
                        "Unchanged cannot be confirmed while a PCS target, global "
                        "scope/legal-force effect, or missing semantic No-Effect check "
                        "remains unresolved."
                    ),
                    409,
                )

        def apply(state: SessionState) -> None:
            old = state.classifications.get(change_id)
            if old:
                if (old.classification, old.reviewer, old.rationale, set(old.evidence_ids)) == (
                    classification,
                    reviewer,
                    rationale,
                    set(evidence_ids),
                ):
                    return
                raise DomainError(
                    "DECISION_ALREADY_RECORDED",
                    "Change interpretation is already confirmed. Reset this demo to reconsider it.",
                    409,
                )
            edge_ids = {
                f"ASSESS-{e.id}"
                for e in self.scenarios.bundle.edges
                if e.source_id == change.mandate_id
            }
            if (
                edge_ids.intersection(state.decisions)
                or change.mandate_id in state.mappings
                or any(review.change_id == change_id for review in state.impact_reviews.values())
            ):
                raise DomainError(
                    "MAPPING_ALREADY_REVIEWED",
                    "Reset the demo before changing an interpretation "
                    "with recorded mapping or control-impact decisions.",
                    409,
                )
            state.classifications[change_id] = ChangeReview(
                change_id=change_id,
                previous_classification=change.classification,
                classification=classification,
                reviewer=reviewer,
                role="Regulatory Specialist",
                rationale=rationale,
                evidence_ids=tuple(sorted(required)),
                reviewed_at=datetime.now(UTC).isoformat(),
            )

        self.sessions.transact(session_id, apply)

    def prospective_impact(self, change_id: str, session_id: str | None) -> ImpactResponse:
        impact = self.scenarios.impact.change_impact(change_id)
        change = self.scenarios.changes[change_id]
        review = self.sessions.snapshot(session_id).mappings.get(change.mandate_id)
        if not review or review.decision != "APPROVE":
            return impact
        policy = self.scenarios.impact.catalog[review.policy_id]
        nodes = {n.id: n for n in impact.nodes}
        nodes.setdefault(
            policy.id,
            ImpactNode(
                id=policy.id, label=policy.title, type=policy.type, status="SCENARIO_APPROVED"
            ),
        )
        edges = {e.id: e for e in impact.edges}
        edge_id = f"SCENARIO-MAPPING-{change.mandate_id}"
        edges[edge_id] = ImpactEdge(
            id=edge_id,
            source=change.mandate_id,
            target=policy.id,
            label="PROSPECTIVE_ADDRESSED_BY",
            status="SCENARIO_APPROVED",
        )
        controls = {c.id: c for c in impact.controls}
        downstream = [
            e
            for e in self.scenarios.impact.graph.approved_outgoing(policy.id)
            if e.relationship == Relationship.IMPLEMENTED_BY
        ]
        for edge in downstream:
            control = self.scenarios.impact.catalog[edge.target_id]
            nodes[control.id] = ImpactNode(
                id=control.id, label=control.title, type=control.type, status="APPROVED"
            )
            edges[edge.id] = self.scenarios.impact._edge_view(edge)
            controls[control.id] = ControlImpact(id=control.id, title=control.title)
        complete = bool(downstream) and impact.coverage != "PARTIAL"
        return impact.model_copy(
            update={
                "nodes": tuple(nodes.values()),
                "edges": tuple(edges.values()),
                "controls": tuple(controls.values()),
                "coverage": "COMPLETE" if complete else "PARTIAL",
                "gap_reason": None
                if complete
                else (
                    "The prospective policy mapping is approved in this session, but "
                    "an approved control relationship is still missing."
                ),
            }
        )

    def explain_mapping(self, edge_id: str, session_id: str | None) -> EdgeExplanation:
        state = self.sessions.snapshot(session_id)
        review = next(
            (v for v in state.mappings.values() if f"SCENARIO-MAPPING-{v.mandate_id}" == edge_id),
            None,
        )
        if not review or review.decision != "APPROVE":
            raise DomainError(
                "EDGE_NOT_FOUND", "The prospective mapping was not found in this session.", 404
            )
        run = (
            state.runs.get(f"recommendations:{review.mandate_id}")
            or state.runs[f"candidates:{review.mandate_id}"]
        )
        candidate = next(c for c in run["candidates"] if c["id"] == review.policy_id)
        change = self.scenarios.by_mandate[review.mandate_id]
        return EdgeExplanation(
            id=edge_id,
            source_id=review.mandate_id,
            target_id=review.policy_id,
            relationship="PROSPECTIVE_ADDRESSED_BY",
            status="SCENARIO_APPROVED",
            evidence=tuple(self.scenarios.impact.evidence[i] for i in change.proposal_evidence_ids),
            provenance=EdgeProvenance(
                proposed_by="AI"
                if run["run"]["workflow"] == "policy-map"
                else "DETERMINISTIC_RETRIEVAL",
                decision_source="HUMAN_REVIEW",
                model=run["run"].get("model"),
                prompt_version=run["run"].get("prompt_version"),
                reviewer=review.reviewer,
                reviewed_at=review.reviewed_at,
                reason=review.rationale,
                vector_rank=candidate["vector_rank"],
                lexical_rank=candidate["lexical_rank"],
                rrf_rank=candidate["rrf_rank"],
                rrf_score=candidate["rrf_score"],
                agent_run_id=review.retrieval_run_id,
            ),
            data_origin="SYNTHETIC_HACKATHON",
            catalog_relationship=False,
        )

    def review_mapping(
        self,
        mandate_id: str,
        session_id: str,
        policy_id: str,
        decision: str,
        reviewer: str,
        rationale: str,
    ) -> None:
        change = self.scenarios.by_mandate.get(mandate_id)
        if not change:
            raise DomainError("MANDATE_NOT_FOUND", "No scenario mandate was found.", 404)

        def apply(state: SessionState) -> None:
            confirmed = state.classifications.get(change.id)
            if not confirmed or confirmed.classification == Classification.UNRESOLVED:
                raise DomainError(
                    "CHANGE_REVIEW_REQUIRED",
                    "A Regulatory Specialist must confirm the change "
                    "interpretation before mapping it.",
                    409,
                )
            if confirmed.classification == Classification.REMOVED:
                raise DomainError(
                    "RETIREMENT_REVIEW_REQUIRED",
                    "Removed obligations require retirement review in Delta Review, "
                    "not a new prospective policy mapping.",
                    409,
                )
            candidate_run = state.runs.get(f"recommendations:{mandate_id}") or state.runs.get(
                f"candidates:{mandate_id}"
            )
            if not candidate_run:
                raise DomainError(
                    "CANDIDATE_RETRIEVAL_REQUIRED",
                    "Retrieve candidates in this session before reviewing a mapping.",
                    409,
                )
            allowed = tuple(c["id"] for c in candidate_run["candidates"][:3])
            if policy_id not in allowed:
                raise DomainError(
                    "INVALID_CANDIDATE",
                    "The policy must be one of the retrieved candidates for this mandate.",
                    422,
                )
            existing = state.mappings.get(mandate_id)
            if existing:
                if (
                    existing.policy_id,
                    existing.decision,
                    existing.reviewer,
                    existing.rationale,
                ) == (policy_id, decision, reviewer, rationale):
                    return
                raise DomainError(
                    "DECISION_ALREADY_RECORDED",
                    "This prospective mapping is already reviewed. "
                    "Reset this demo to reconsider it.",
                    409,
                )
            state.mappings[mandate_id] = PolicyMappingReview(
                mandate_id=mandate_id,
                policy_id=policy_id,
                decision=decision,
                reviewer=reviewer,
                role="Policy Owner",
                rationale=rationale,
                reviewed_at=datetime.now(UTC).isoformat(),
                candidate_ids=allowed,
                retrieval_run_id=candidate_run["run"]["id"],
            )

        self.sessions.transact(session_id, apply)
