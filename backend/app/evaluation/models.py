"""Evaluation interchange format. Software fixtures cannot be blind labels."""

from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Classification = Literal["UNCHANGED", "MODIFIED", "NEW", "REMOVED", "UNRESOLVED"]
LabelOrigin = Literal[
    "HUMAN_INDEPENDENT", "UNLABELED", "MODEL_GENERATED", "SYNTHETIC_SOFTWARE_TEST"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LabelProvenance(StrictModel):
    origin: LabelOrigin
    annotator: str | None
    labeled_at: AwareDatetime | None
    independent_of_predictions: bool
    notes: str


class SourceSegment(StrictModel):
    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Fact(StrictModel):
    text: str = Field(min_length=1)
    entity_ids: list[str] = Field(min_length=1)
    legal_status: Literal["BASELINE_GUIDANCE", "PROPOSED"]


class GoldCase(StrictModel):
    id: str = Field(min_length=1)
    input_reference: str = Field(min_length=1)
    expected_mandate_ids: list[str]
    acceptable_policy_ids: dict[str, list[str]]
    expected_changes: dict[str, Classification]
    carry_forward_allowed: dict[str, bool]
    source_segments: list[SourceSegment]
    evaluate_ask: bool = False
    ask_allowed_facts: list[Fact] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(set(self.expected_mandate_ids)) != len(self.expected_mandate_ids):
            raise ValueError("Expected mandate IDs must be unique")
        segment_ids = [segment.id for segment in self.source_segments]
        if len(set(segment_ids)) != len(segment_ids):
            raise ValueError("Source segment IDs must be unique within a case")
        if self.evaluate_ask and not self.ask_allowed_facts:
            raise ValueError("Ask evaluation needs independently supported facts")
        return self


class LabelSet(StrictModel):
    dataset_id: str = Field(min_length=1)
    split: Literal["dev", "test", "software-test"]
    provenance: LabelProvenance
    cases: list[GoldCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        ids = [case.id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("Label case IDs must be unique")
        return self


class EvidenceClaim(StrictModel):
    source_id: str
    segment_id: str
    excerpt: str


class ToolFacts(StrictModel):
    run_id: str
    tool: str
    facts: list[Fact]


class AskTrace(StrictModel):
    run_id: str
    answer: str
    tool_results: list[ToolFacts]
    claims: list[Fact]


class EvaluationOutput(StrictModel):
    """Normalized prediction export, validated here rather than trusting success flags."""

    mandate_ids: list[str]
    evidence: list[EvidenceClaim]
    mapping_candidates: dict[str, list[str]]
    changes: dict[str, Classification]
    carry_forward_ids: list[str]
    ask: AskTrace | None = None

    @model_validator(mode="after")
    def unique_rankings(self) -> Self:
        sequences = [self.mandate_ids, self.carry_forward_ids, *self.mapping_candidates.values()]
        if any(len(set(items)) != len(items) for items in sequences):
            raise ValueError("Predicted IDs and ordered candidate lists must be unique")
        return self


class PredictionCase(StrictModel):
    id: str
    raw_output: Any


class PredictionSet(StrictModel):
    dataset_id: str
    run_id: str = Field(min_length=1)
    execution_mode: Literal["LIVE_AI", "LOCAL_DETERMINISTIC", "SYNTHETIC_SOFTWARE_TEST"]
    model: str | None
    started_at: AwareDatetime
    completed_at: AwareDatetime
    started_from_commit: str | None
    labels_manifest_sha256: str | None
    cases: list[PredictionCase] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent_run(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("Run completion cannot precede start")
        ids = [case.id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("Prediction case IDs must be unique")
        return self


class FreezeManifest(StrictModel):
    version: Literal[1] = 1
    dataset_id: str
    split: Literal["dev", "test"]
    labels_path: str
    labels_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    labels_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    frozen_at: AwareDatetime
    case_count: int = Field(gt=0)
    label_origin: Literal["HUMAN_INDEPENDENT"] = "HUMAN_INDEPENDENT"
