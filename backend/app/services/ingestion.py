"""Deterministic PDF parsing. No fetching URLs, OCR, model calls or legal promotion."""

import asyncio
import hashlib
import io
import json
import re
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Protocol

from app.domain.errors import DomainError
from app.domain.ingestion import ExtractedSourceSegment, IngestedDocument, SourceDescriptor
from app.repositories.ports import ObjectStorage

PARAGRAPH = re.compile(r"^\s*(?P<ref>\d+(?:\.\d+){1,4})(?:\s|$)")
SAFEGUARD = re.compile(r"^\s*(Safeguard\s+\d+)\s*$", re.IGNORECASE)


class DocumentExtractor(Protocol):
    def extract(self, content: bytes, source: SourceDescriptor) -> IngestedDocument: ...


class PdfDocumentExtractor:
    def __init__(
        self,
        *,
        max_bytes: int = 20 * 1024 * 1024,
        max_pages: int = 200,
        max_text_characters: int = 2_000_000,
        max_page_stream_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_pages = max_pages
        self.max_text_characters = max_text_characters
        self.max_page_stream_bytes = max_page_stream_bytes

    def extract(self, content: bytes, source: SourceDescriptor) -> IngestedDocument:
        if not content or len(content) > self.max_bytes:
            raise DomainError(
                "SOURCE_SIZE_LIMIT", "PDF is empty or exceeds the source size limit.", 413
            )
        if not content.startswith(b"%PDF-"):
            raise DomainError(
                "INVALID_PDF", "Source bytes are not a PDF (HTML is not accepted).", 422
            )
        digest = hashlib.sha256(content).hexdigest()
        if source.expected_sha256 and source.expected_sha256 != digest:
            raise DomainError(
                "SOURCE_HASH_MISMATCH", "Source bytes differ from the pinned hash.", 409
            )
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise DomainError(
                "PDF_DEPENDENCY_MISSING", "Install the pypdf ingestion dependency.", 503
            ) from exc
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise DomainError(
                    "ENCRYPTED_PDF", "Encrypted sources require an unlocked PDF.", 422
                )
            if not 0 < len(reader.pages) <= self.max_pages:
                raise DomainError(
                    "SOURCE_PAGE_LIMIT", "PDF page count exceeds the extraction limit.", 413
                )
            pages = []
            total_chars = 0
            for page in reader.pages:
                stream = page.get_contents()
                if stream is not None and len(stream.get_data()) > self.max_page_stream_bytes:
                    raise DomainError("SOURCE_STREAM_LIMIT", "PDF page content is too large.", 413)
                text = (page.extract_text(extraction_mode="plain") or "").replace("\r\n", "\n")
                total_chars += len(text)
                if total_chars > self.max_text_characters:
                    raise DomainError(
                        "SOURCE_TEXT_LIMIT", "Extracted text exceeds the size limit.", 413
                    )
                pages.append(text)
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "PDF_EXTRACTION_FAILED", "PDF could not be parsed safely.", 422
            ) from exc
        segments = self._segment(tuple(pages), source, digest)
        if not segments:
            raise DomainError(
                "OCR_REQUIRED", "PDF has no extractable text; OCR/manual review is required.", 422
            )
        empty_pages = tuple(i for i, text in enumerate(pages, 1) if not text.strip())
        return IngestedDocument(
            source=source,
            sha256=digest,
            byte_length=len(content),
            page_count=len(pages),
            extracted_at=datetime.now(UTC),
            extraction_method=f"pypdf/{version('pypdf')}:plain:v1",
            extraction_status="PARTIAL" if empty_pages else "COMPLETE",
            segments=segments,
            pages_without_text=empty_pages,
            warnings=(
                ("Some pages have no text. Do not infer no regulatory effect from missing text.",)
                if empty_pages
                else ()
            ),
        )

    @staticmethod
    def _segment(
        pages: tuple[str, ...],
        source: SourceDescriptor,
        digest: str,
    ) -> tuple[ExtractedSourceSegment, ...]:
        result = []
        stable_prefix = hashlib.sha256(f"{source.source_id}:{digest}".encode()).hexdigest()[:16]
        last_ref: str | None = None
        section = "Document"
        for page_number, text in enumerate(pages, 1):
            if not text.strip():
                last_ref = None  # Never guess continuity across an unreadable page.
                continue
            chunks: list[tuple[str, str, bool, str]] = []
            lines: list[str] = []
            active_ref = last_ref or f"page-{page_number}"
            continued = last_ref is not None
            active_section = section
            for line in text.splitlines():
                paragraph = PARAGRAPH.match(line)
                safeguard = SAFEGUARD.match(line)
                if paragraph or safeguard:
                    if "\n".join(lines).strip():
                        chunks.append(
                            (active_ref, "\n".join(lines).strip(), continued, active_section)
                        )
                    active_ref = paragraph.group("ref") if paragraph else safeguard.group(1)
                    if safeguard:
                        section = active_ref
                    active_section = section
                    continued = False
                    lines = []
                lines.append(line)
            if "\n".join(lines).strip():
                chunks.append((active_ref, "\n".join(lines).strip(), continued, active_section))
            for ordinal, (ref, chunk, continuation, section_path) in enumerate(chunks, 1):
                result.append(
                    ExtractedSourceSegment(
                        segment_id=f"SEG-{stable_prefix}-P{page_number:04}-S{ordinal:04}",
                        source_id=source.source_id,
                        source_sha256=digest,
                        page=page_number,
                        paragraph_ref=ref,
                        section_path=section_path,
                        text=chunk,
                        continued_from_previous_page=continuation,
                        source_url=source.source_url,
                        data_origin=source.data_origin,
                    )
                )
            last_ref = active_ref if not active_ref.startswith("page-") else None
        return tuple(result)


class IngestionService:
    def __init__(self, extractor: DocumentExtractor, storage: ObjectStorage | None = None) -> None:
        self.extractor = extractor
        self.storage = storage

    async def ingest_bytes(
        self,
        content: bytes,
        source: SourceDescriptor,
        *,
        content_type: str = "application/pdf",
    ) -> IngestedDocument:
        if content_type.split(";", 1)[0].strip().lower() != "application/pdf":
            raise DomainError("UNSUPPORTED_SOURCE_TYPE", "Only application/pdf is supported.", 415)
        document = await asyncio.to_thread(self.extractor.extract, content, source)
        if self.storage is None:
            return document
        original_key = f"sources/{source.source_id}/{document.sha256}/original.pdf"
        original_uri = await self.storage.write(original_key, content, "application/pdf")
        # The content-addressed extraction is deterministic. Runtime timestamp is outside the
        # persisted payload so retries of the same PDF do not conflict with immutable storage.
        payload = document.model_dump(
            mode="json",
            exclude={"extracted_at": True, "extraction_uri": True, "source": {"expected_sha256"}},
        )
        payload["original_uri"] = original_uri
        extraction_uri = await self.storage.write(
            f"sources/{source.source_id}/{document.sha256}/extraction-v1.json",
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode(),
            "application/json",
        )
        stored = document.model_copy(
            update={"original_uri": original_uri, "extraction_uri": extraction_uri}
        )
        record_key = f"sources/{source.source_id}/{document.sha256}/document-v1.json"
        try:
            await self.storage.write(
                record_key, stored.model_dump_json().encode(), "application/json"
            )
        except DomainError as exc:
            if exc.code != "SOURCE_OBJECT_CONFLICT":
                raise
            # Preserve the first successful extraction timestamp on an idempotent retry.
            try:
                previous = IngestedDocument.model_validate_json(await self.storage.read(record_key))
                stable_fields = {"extracted_at": True, "source": {"expected_sha256"}}
                if previous.model_dump(exclude=stable_fields) != stored.model_dump(
                    exclude=stable_fields
                ):
                    raise ValueError("Existing source metadata differs")
            except (ValueError, TypeError) as invalid:
                raise DomainError(
                    "SOURCE_METADATA_CONFLICT",
                    "Existing source metadata does not match this PDF.",
                    409,
                ) from invalid
            return previous
        return stored

    async def ingest_object(self, object_key: str, source: SourceDescriptor) -> IngestedDocument:
        if self.storage is None:
            raise DomainError(
                "STORAGE_NOT_CONFIGURED", "Source object storage is unavailable.", 503
            )
        return await self.ingest_bytes(await self.storage.read(object_key), source)
