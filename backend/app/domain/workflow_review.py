"""Session-only human decisions over immutable model output and control impact."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai.contracts import WorkflowResult

ReviewerRole = Literal["Regulatory Specialist", "Risk Steward", "Policy Owner"]
Decision = Literal["APPROVE", "REJECT", "MODIFY"]
REQUIRED_ROLES: dict[str, ReviewerRole] = {
    "interpret": "Regulatory Specialist",
    "pcs-extract": "Regulatory Specialist",
    "change-effect": "Regulatory Specialist",
    "risk-map": "Risk Steward",
    "policy-map": "Policy Owner",
    "impact-explain": "Policy Owner",
}


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Decision
    reviewer: str = Field(min_length=2, max_length=120)
    role: ReviewerRole
    rationale: str = Field(min_length=10, max_length=2000)
    final_output: dict[str, Any] | None = None

    @model_validator(mode="after")
    def modification_payload(self) -> "ReviewRequest":
        if (self.decision == "MODIFY") != (self.final_output is not None):
            raise ValueError("MODIFY requires final_output; other decisions cannot replace output")
        return self


class WorkflowReviewDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    workflow: str
    change_id: str | None = None
    mandate_id: str | None = None
    source_id: str | None = None
    decision: Decision
    reviewer: str
    role: ReviewerRole
    rationale: str
    reviewed_at: str
    previous_output: dict[str, Any]
    final_output: dict[str, Any] | None
    input_sha256: str
    output_sha256: str
    final_output_sha256: str | None = None


class WorkflowReviewView(WorkflowResult):
    required_role: ReviewerRole | None = None
    review_allowed: bool = False
    block_reason: str | None = None
    review: WorkflowReviewDecision | None = None


class ImpactReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Decision
    reviewer: str = Field(min_length=2, max_length=120)
    role: Literal["Policy Owner"]
    rationale: str = Field(min_length=10, max_length=2000)
    scope_note: str | None = Field(default=None, min_length=10, max_length=2000)

    @model_validator(mode="after")
    def modification_scope(self) -> "ImpactReviewRequest":
        if (self.decision == "MODIFY") != (self.scope_note is not None):
            raise ValueError("MODIFY requires scope_note; other decisions cannot replace scope")
        return self


class ImpactReviewDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    assessment_id: str
    change_id: str
    control_id: str
    decision: Decision
    reviewer: str
    role: Literal["Policy Owner"]
    rationale: str
    reviewed_at: str
    previous_output: dict[str, Any]
    final_output: dict[str, Any] | None


class ControlImpactReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    change_id: str
    control_id: str
    title: str
    status: Literal["PENDING_REVIEW", "APPROVED", "REJECTED", "MODIFIED"] = "PENDING_REVIEW"
    impact_type: Literal["PROSPECTIVE_REVIEW"] = "PROSPECTIVE_REVIEW"
    scope_note: str
    review: ImpactReviewDecision | None = None


class ImpactReviewList(BaseModel):
    assessments: tuple[ControlImpactReview, ...]
    required_role: Literal["Policy Owner"] = "Policy Owner"
