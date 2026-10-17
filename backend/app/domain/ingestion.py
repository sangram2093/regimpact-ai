"""Source identity and extraction records, separate from reviewed legal assertions."""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    title: str = Field(min_length=1, max_length=500)
    source_url: str = Field(max_length=2048)
    publication_date: date
    instrument_status: Literal["IN_FORCE", "PROPOSED", "SYNTHETIC"]
    document_kind: Literal["BASELINE", "CHANGE_PROPOSAL", "SYNTHETIC"]
    data_origin: Literal["PUBLIC_REGULATORY_SOURCE", "SYNTHETIC_HACKATHON"]
    expected_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("source_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Source URL must be HTTPS without embedded credentials")
        return value

    @model_validator(mode="after")
    def preserve_status(self) -> Self:
        expected = {"BASELINE": "IN_FORCE", "CHANGE_PROPOSAL": "PROPOSED", "SYNTHETIC": "SYNTHETIC"}
        if self.instrument_status != expected[self.document_kind]:
            raise ValueError("Document kind and declared instrument status disagree")
        if (self.document_kind == "SYNTHETIC") != (self.data_origin == "SYNTHETIC_HACKATHON"):
            raise ValueError("Synthetic sources must retain their synthetic origin")
        return self


class ExtractedSourceSegment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    segment_id: str
    source_id: str
    source_sha256: str
    page: int = Field(ge=1)
    paragraph_ref: str
    section_path: str
    text: str
    continued_from_previous_page: bool = False
    source_url: str
    data_origin: Literal["PUBLIC_REGULATORY_SOURCE", "SYNTHETIC_HACKATHON"]
    text_kind: Literal["EXTRACTED_TEXT"] = "EXTRACTED_TEXT"
    verification_status: Literal["EXTRACTED_UNREVIEWED"] = "EXTRACTED_UNREVIEWED"


class IngestedDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceDescriptor
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_length: int = Field(gt=0)
    page_count: int = Field(gt=0)
    extracted_at: datetime
    extraction_method: str
    extraction_status: Literal["COMPLETE", "PARTIAL"]
    segments: tuple[ExtractedSourceSegment, ...]
    pages_without_text: tuple[int, ...] = ()
    original_uri: str | None = None
    extraction_uri: str | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def verify_provenance(self) -> Self:
        if not self.segments:
            raise ValueError("An extracted document must contain source text")
        if self.source.expected_sha256 and self.source.expected_sha256 != self.sha256:
            raise ValueError("The extracted document hash differs from the pinned source hash")
        if len({segment.segment_id for segment in self.segments}) != len(self.segments):
            raise ValueError("Source segment IDs must be unique")
        for segment in self.segments:
            if (
                segment.source_id != self.source.source_id
                or segment.source_sha256 != self.sha256
                or segment.source_url != self.source.source_url
                or segment.data_origin != self.source.data_origin
                or segment.page > self.page_count
                or not segment.text.strip()
            ):
                raise ValueError("Segment provenance does not match its extracted document")
        if any(page < 1 or page > self.page_count for page in self.pages_without_text):
            raise ValueError("Missing-text page is outside the source document")
        if self.extraction_status == "COMPLETE" and self.pages_without_text:
            raise ValueError("A document with missing text pages cannot be complete")
        return self
