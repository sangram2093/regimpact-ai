"""Application read models shared by services and transports."""

from typing import Literal

from pydantic import BaseModel

from app.domain.models import (
    AgentRun,
    AssessmentStatus,
    Classification,
    EdgeProvenance,
    Evidence,
    ImpactScenario,
    ReviewMetrics,
    SafetyChecks,
    ScenarioMappingAssessment,
)
from app.domain.reviews import ChangeReview


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["local", "gcp"] = "local"
    version: str = "0.2.0"
    ai_status: Literal["NOT_CONNECTED_SEED_MODE", "LIVE_AI_CONFIGURED_UNVERIFIED"] = (
        "NOT_CONNECTED_SEED_MODE"
    )


class ChangeSummary(BaseModel):
    id: str
    title: str
    classification: Classification
    change_nature: tuple[str, ...]
    summary: str
    mandate_id: str
    impacted_controls: int
    review_status: str
    is_proposal: Literal[True] = True


class MandateSummary(BaseModel):
    id: str
    title: str


class ChangeDetail(ChangeSummary):
    classification_review: ChangeReview | None = None
    scenario_id: str
    baseline_evidence: tuple[Evidence, ...]
    proposal_evidence: tuple[Evidence, ...]
    mandate: MandateSummary
    risk_tags: tuple[str, ...]
    safety_checks: SafetyChecks
    proposal_notice: str
    scenario_status: Literal["PROPOSED", "FINAL"] = "PROPOSED"
    legal_force_before: Literal["GUIDANCE"] = "GUIDANCE"
    legal_force_after: Literal["PROPOSED_BINDING", "GUIDANCE"] = "PROPOSED_BINDING"
    legal_force_note: str | None


class AssessmentView(ScenarioMappingAssessment):
    mandate_title: str
    target_id: str
    target_label: str
    relationship: str
    required_role: Literal["Policy Owner", "Risk Steward"]


class DeltaReview(BaseModel):
    scenario_id: str
    metrics: ReviewMetrics
    assessments: tuple[AssessmentView, ...]


class ImpactNode(BaseModel):
    id: str
    label: str
    type: str
    status: str


class ImpactEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    status: str


class ControlImpact(BaseModel):
    id: str
    title: str
    impact_type: Literal["PROSPECTIVE_REVIEW"] = "PROSPECTIVE_REVIEW"


class ImpactResponse(BaseModel):
    nodes: tuple[ImpactNode, ...]
    edges: tuple[ImpactEdge, ...]
    controls: tuple[ControlImpact, ...]
    coverage: Literal["COMPLETE", "PARTIAL", "NO_POLICY_MAPPING"]
    risk_tags: tuple[str, ...]
    gap_reason: str | None = None
    proposal_notice: str = "PROPOSED — NOT AN IN-FORCE REQUIREMENT"


class ImpactSummary(BaseModel):
    policies: int
    controls: int
    coverage_gaps: int
    review_needed: int


class Dashboard(BaseModel):
    scenario: ImpactScenario
    metrics: ReviewMetrics
    changes: tuple[ChangeSummary, ...]
    impact_summary: ImpactSummary
    run: AgentRun


class EdgeExplanation(BaseModel):
    id: str
    source_id: str
    target_id: str
    relationship: str
    status: str
    evidence: tuple[Evidence, ...]
    provenance: EdgeProvenance
    data_origin: str
    catalog_relationship: bool
    scenario_status: AssessmentStatus | None = None
