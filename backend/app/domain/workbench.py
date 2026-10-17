from pydantic import BaseModel

from app.ai.contracts import CandidateResult, WorkflowRun
from app.domain.models import Evidence


class SourceView(BaseModel):
    id: str
    title: str
    source_url: str
    regulator: str
    publication_date: str
    legal_status: str
    ingestion_status: str
    sha256: str | None
    segment_count: int
    retrieved_at: str | None
    verification_note: str
    can_ingest: bool


class SourcesView(BaseModel):
    sources: tuple[SourceView, ...]
    disclosures: tuple[str, ...]


class MandateReviewView(BaseModel):
    id: str
    title: str
    text: str
    status: str
    source_id: str | None
    change_id: str | None
    classification: str | None
    review_status: str
    evidence: tuple[Evidence, ...]
    reviewed_by: str | None
    rationale: str | None
    classification_confirmed: bool


class MandatesView(BaseModel):
    mandates: tuple[MandateReviewView, ...]


class PolicyReviewView(CandidateResult):
    rationale: str | None = None
    reviewed_by: str | None = None
    mapping_allowed: bool = False
    mapping_block_reason: str | None = None


class RunsView(BaseModel):
    runs: tuple[WorkflowRun, ...]
