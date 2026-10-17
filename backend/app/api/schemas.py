from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Meta(BaseModel):
    request_id: str
    mode: Literal["local", "gcp"] = "local"
    data_origin: str = "SEED / GOLDEN_LABELS"


class Envelope[T](BaseModel):
    data: T
    meta: Meta


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorMeta(BaseModel):
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    meta: ErrorMeta


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["APPROVE", "REJECT"]
    reviewer: str = Field(min_length=2, max_length=120)
    role: Literal["Policy Owner", "Risk Steward"]
    rationale: str = Field(min_length=10, max_length=2000)


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reviewer: str = Field(min_length=2, max_length=120)
    role: Literal["Regulatory Specialist"]


class ResetResponse(BaseModel):
    reset: Literal[True] = True


class ClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    classification: Literal["UNCHANGED", "MODIFIED", "NEW", "REMOVED"]
    reviewer: str = Field(min_length=2, max_length=120)
    role: Literal["Regulatory Specialist"]
    rationale: str = Field(min_length=10, max_length=2000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=50)


class PolicyMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    policy_id: str = Field(min_length=1, max_length=120)
    decision: Literal["APPROVE", "REJECT"]
    reviewer: str = Field(min_length=2, max_length=120)
    role: Literal["Policy Owner"]
    rationale: str = Field(min_length=10, max_length=2000)


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mandate_id: str | None = Field(default=None, max_length=120)
    change_id: str | None = Field(default=None, max_length=120)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=1500)
    scenario_id: str = Field(default="SCENARIO-MAS-2023", max_length=120)
