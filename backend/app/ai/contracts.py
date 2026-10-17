from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

WorkflowName = Literal[
    "interpret", "risk-map", "policy-map", "pcs-extract", "change-effect", "impact-explain"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunStep(StrictModel):
    name: str
    status: str
    detail: str


class WorkflowRun(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow: str
    kind: Literal["LOCAL_DETERMINISTIC", "LIVE_AI", "SEED"]
    status: Literal["SUCCEEDED", "MANUAL_REVIEW_REQUIRED", "BLOCKED"]
    model: str | None = None
    prompt_version: str | None = None
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: float = 0
    label: str
    validation_status: Literal["PASSED", "FAILED", "NOT_RUN"]
    steps: tuple[RunStep, ...] = ()
    attempts: int = 0
    model_calls: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    input_sha256: str | None = None
    output_sha256: str | None = None
    thinking_level: str | None = None
    candidate_ids: tuple[str, ...] = ()
    candidate_details: tuple[dict[str, Any], ...] = ()
    provider_model_version: str | None = None
    change_id: str | None = None
    mandate_id: str | None = None
    source_id: str | None = None


class WorkflowResult(StrictModel):
    run: WorkflowRun
    output: dict[str, Any] | None = None
    status: Literal["HUMAN_REVIEW_REQUIRED", "MANUAL_REVIEW_REQUIRED", "AI_NOT_CONFIGURED"]
    validation_errors: tuple[str, ...] = ()


class EvidenceReference(StrictModel):
    source_id: str
    segment_id: str
    excerpt: str | None = Field(default=None, max_length=1500)


class MandateDraft(StrictModel):
    text: str = Field(min_length=10, max_length=3000)
    applicability: str = Field(min_length=1, max_length=1000)
    legal_force: Literal["GUIDANCE", "PROPOSED_BINDING", "UNKNOWN"]
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=12)


class InterpretationOutput(StrictModel):
    mandates: list[MandateDraft] = Field(min_length=1, max_length=30)


class RiskMappingOutput(StrictModel):
    selected_risk_type_id: str | None
    selected_risk_driver_ids: list[str] = Field(max_length=5)
    reason: str = Field(min_length=10, max_length=3000)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=12)


class PolicyMappingOutput(StrictModel):
    decision: Literal["RECOMMEND", "NO_SUITABLE_CANDIDATE"]
    candidate_id: str | None
    alternative_ids: list[str] = Field(max_length=2)
    reason: str = Field(min_length=10, max_length=3000)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def decision_matches_candidate(self) -> Self:
        if (self.decision == "RECOMMEND") != (self.candidate_id is not None):
            raise ValueError("RECOMMEND needs a candidate; NO_SUITABLE_CANDIDATE needs null")
        if self.decision == "NO_SUITABLE_CANDIDATE" and self.alternative_ids:
            raise ValueError("NO_SUITABLE_CANDIDATE cannot retain recommended alternatives")
        ids = [i for i in [self.candidate_id, *self.alternative_ids] if i is not None]
        if len(set(ids)) != len(ids):
            raise ValueError("Candidate IDs must be distinct")
        return self


class ProposedStatement(StrictModel):
    text: str = Field(min_length=10, max_length=3000)
    target_mandate_ids: list[str] = Field(max_length=30)
    instrument_wide: bool
    legal_force_after: Literal["PROPOSED_BINDING", "GUIDANCE", "UNKNOWN"]
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=12)


class ProposedChangesOutput(StrictModel):
    statements: list[ProposedStatement] = Field(min_length=1, max_length=30)


class ChangeEffectOutput(StrictModel):
    classification: Literal["UNCHANGED", "MODIFIED", "NEW", "REMOVED", "UNRESOLVED"]
    no_effect_result: Literal["NO_EFFECT_SUPPORTED", "EFFECT_POSSIBLE", "AMBIGUOUS_SOURCE"]
    reason: str = Field(min_length=10, max_length=3000)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=12)


class NarrativeClaim(StrictModel):
    text: str = Field(min_length=10, max_length=2000)
    entity_ids: list[str] = Field(min_length=1, max_length=20)
    legal_status: Literal["BASELINE_GUIDANCE", "PROPOSED"]
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=12)


class ImpactNarrativeOutput(StrictModel):
    claims: list[NarrativeClaim] = Field(min_length=1, max_length=12)


OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "interpret": InterpretationOutput,
    "risk-map": RiskMappingOutput,
    "policy-map": PolicyMappingOutput,
    "pcs-extract": ProposedChangesOutput,
    "change-effect": ChangeEffectOutput,
    "impact-explain": ImpactNarrativeOutput,
}


class Candidate(StrictModel):
    id: str
    title: str
    text: str
    type: str
    vector_rank: int | None
    lexical_rank: int | None
    rrf_rank: int | None
    rrf_score: float | None
    reason: str
    origin: Literal["RETRIEVAL", "APPROVED_BASELINE"] = "RETRIEVAL"


class CandidateResult(StrictModel):
    mandate_id: str
    candidates: tuple[Candidate, ...]
    run: WorkflowRun
    review_status: str = "HUMAN_REVIEW_REQUIRED"
    selected_policy_id: str | None = None
    retrieval_mode: Literal["LEXICAL_LOCAL", "HYBRID"]
    embedding_model: str | None = None


class AskCitation(StrictModel):
    id: str
    label: str
    type: str
    excerpt: str | None = None
    source_url: str | None = None


class AskToolCall(StrictModel):
    name: str
    status: Literal["SUCCEEDED", "FAILED"]
    summary: str


class AskResponse(StrictModel):
    answer: str
    grounded: bool
    verified_references: int
    total_references: int
    citations: tuple[AskCitation, ...]
    tool_calls: tuple[AskToolCall, ...]
    run: WorkflowRun


class AskConfig(StrictModel):
    mode: Literal["LOCAL_DETERMINISTIC", "LIVE_AI"]
    label: str
    suggested_questions: tuple[str, ...]
    available: bool
    reason: str | None = None


class AskSelection(StrictModel):
    fact_ids: list[str] = Field(min_length=1, max_length=12)
