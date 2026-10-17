"""Human decisions are prospective session records, never baseline mutations."""

from typing import Literal

from app.domain.models import Classification, FrozenModel


class ChangeReview(FrozenModel):
    change_id: str
    previous_classification: Classification
    classification: Classification
    reviewer: str
    role: Literal["Regulatory Specialist"]
    rationale: str
    evidence_ids: tuple[str, ...]
    reviewed_at: str


class PolicyMappingReview(FrozenModel):
    mandate_id: str
    policy_id: str
    decision: Literal["APPROVE", "REJECT"]
    reviewer: str
    role: Literal["Policy Owner"]
    rationale: str
    reviewed_at: str
    candidate_ids: tuple[str, ...]
    retrieval_run_id: str
    previous_status: str = "HUMAN_REVIEW_REQUIRED"
    scope: Literal["PROSPECTIVE_SCENARIO_ONLY"] = "PROSPECTIVE_SCENARIO_ONLY"
