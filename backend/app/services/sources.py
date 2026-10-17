"""Allowlisted public source ingestion with validated local/cloud metadata recovery."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.domain.errors import DomainError
from app.domain.ingestion import IngestedDocument, SourceDescriptor
from app.repositories.ports import ObjectStorage
from app.services.ingestion import IngestionService, PdfDocumentExtractor


class SourceService:
    def __init__(
        self, data_dir: Path, runtime_dir: Path, storage: ObjectStorage | None = None
    ) -> None:
        self.public_dir = data_dir / "public"
        self.output_dir = runtime_dir / "sources"
        self.storage = storage
        self.ingestion = IngestionService(PdfDocumentExtractor(), storage)
        self._cloud_documents: dict[str, IngestedDocument | None] = {}
        self._cloud_originals: set[str] = set()
        manifest = json.loads(
            (self.public_dir / "source-manifest.json").read_text(encoding="utf-8")
        )
        self.sources = {item["source_id"]: item for item in manifest["sources"]}
        for source_id in self.sources:
            self._descriptor(source_id)

    def _descriptor(self, source_id: str) -> SourceDescriptor:
        source = self.sources.get(source_id)
        if not source:
            raise DomainError("SOURCE_NOT_FOUND", "The requested public source was not found.", 404)
        return SourceDescriptor(
            source_id=source_id,
            title=source["title"],
            source_url=source["source_url"],
            publication_date=source["publication_date"],
            instrument_status=source["instrument_status"],
            document_kind="BASELINE"
            if source["instrument_status"] == "IN_FORCE"
            else "CHANGE_PROPOSAL",
            data_origin="PUBLIC_REGULATORY_SOURCE",
            expected_sha256=source.get("sha256"),
        )

    def _pdf_path(self, source_id: str) -> Path:
        self._descriptor(source_id)
        source = self.sources[source_id]
        path = (
            self.public_dir / (source.get("local_path") or f"downloads/{source_id}.pdf")
        ).resolve()
        if not path.is_relative_to((self.public_dir / "downloads").resolve()):
            raise DomainError(
                "INVALID_SOURCE_PATH", "Source must be inside the public download directory.", 422
            )
        return path

    def _validate_document(self, source_id: str, document: IngestedDocument) -> IngestedDocument:
        expected = self._descriptor(source_id)
        if document.source.model_dump(exclude={"expected_sha256"}) != expected.model_dump(
            exclude={"expected_sha256"}
        ) or (expected.expected_sha256 and document.sha256 != expected.expected_sha256):
            raise DomainError(
                "SOURCE_METADATA_MISMATCH",
                "Extracted metadata does not match the known source identity or checksum.",
                409,
            )
        return document

    def _local_document(self, source_id: str) -> IngestedDocument | None:
        self._descriptor(source_id)
        path = self.output_dir / f"{source_id}.json"
        if not path.exists():
            return None
        try:
            return self._validate_document(
                source_id, IngestedDocument.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except ValueError as exc:
            raise DomainError(
                "SOURCE_METADATA_INVALID",
                "Stored source metadata is invalid and requires reingestion.",
                409,
            ) from exc

    def document(self, source_id: str) -> IngestedDocument | None:
        """Synchronous validated cache; call refresh before reading cloud metadata."""
        self._descriptor(source_id)
        return (
            self._cloud_documents.get(source_id)
            if self.storage
            else self._local_document(source_id)
        )

    async def refresh(self, source_id: str | None = None) -> None:
        """Recover known immutable cloud records. Local mode performs no cloud access."""
        ids = (source_id,) if source_id is not None else tuple(self.sources)
        for selected in ids:
            descriptor = self._descriptor(selected)
            if self.storage is None:
                continue
            local = self._local_document(selected) if not descriptor.expected_sha256 else None
            digest = descriptor.expected_sha256 or (local.sha256 if local else None)
            self._cloud_documents[selected] = None
            self._cloud_originals.discard(selected)
            if not digest:
                continue
            key = f"sources/{selected}/{digest}/document-v1.json"
            try:
                content = await self.storage.read(key)
            except DomainError as exc:
                if exc.code == "STORAGE_OBJECT_NOT_FOUND":
                    exists = getattr(self.storage, "exists", None)
                    if exists is not None and await exists(
                        f"sources/{selected}/{digest}/original.pdf"
                    ):
                        self._cloud_originals.add(selected)
                    continue
                raise
            try:
                document = self._validate_document(
                    selected, IngestedDocument.model_validate_json(content)
                )
                if document.sha256 != digest:
                    raise ValueError("Cloud metadata key and source hash disagree")
            except ValueError as exc:
                raise DomainError(
                    "SOURCE_METADATA_INVALID", "Cloud source metadata failed validation.", 409
                ) from exc
            exists = getattr(self.storage, "exists", None)
            if exists is not None and await exists(f"sources/{selected}/{digest}/original.pdf"):
                self._cloud_originals.add(selected)
            self._save_local(document)
            self._cloud_documents[selected] = document

    def _save_local(self, document: IngestedDocument) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        target = self.output_dir / f"{document.source.source_id}.json"
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(document.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def source_view(self, source_id: str) -> dict:
        path = self._pdf_path(source_id)
        source = self.sources[source_id]
        document = self.document(source_id)
        can_ingest_cloud = source_id in self._cloud_originals
        return {
            "id": source_id,
            "title": source["title"],
            "source_url": source["source_url"],
            "regulator": "MAS",
            "publication_date": source["publication_date"],
            "legal_status": source["instrument_status"],
            "ingestion_status": f"EXTRACTED_{document.extraction_status}"
            if document
            else source.get("fetch_status", "NOT_FETCHED"),
            "sha256": document.sha256 if document else source.get("sha256"),
            "segment_count": len(document.segments) if document else 0,
            "retrieved_at": source.get("retrieved_at"),
            "verification_note": (
                "Extracted text requires specialist review; "
                "extraction does not establish legal currency."
                if document
                else source.get("fetch_error") or "Known public source; no extracted PDF yet."
            ),
            "can_ingest": path.is_file() or can_ingest_cloud,
        }

    def list_sources(self) -> dict:
        return {
            "sources": [self.source_view(source_id) for source_id in self.sources],
            "disclosures": [
                "Regulatory documents are public MAS sources. "
                "Enterprise catalog data is synthetic.",
                "The 2023 consultation is a historical proposal scenario, "
                "not a statement of current law.",
                "Curated source paraphrases are distinct from byte-verified extracted PDF text.",
            ],
        }

    async def ingest(self, source_id: str) -> dict:
        path = self._pdf_path(source_id)
        descriptor = self._descriptor(source_id)
        if path.is_file():
            if path.stat().st_size > 20 * 1024 * 1024:
                raise DomainError(
                    "SOURCE_TOO_LARGE", "The PDF exceeds the 20 MB source limit.", 422
                )
            document = await self.ingestion.ingest_bytes(
                await asyncio.to_thread(path.read_bytes), descriptor
            )
        elif self.storage is not None and descriptor.expected_sha256:
            key = f"sources/{source_id}/{descriptor.expected_sha256}/original.pdf"
            try:
                document = await self.ingestion.ingest_object(key, descriptor)
            except DomainError as exc:
                if exc.code != "STORAGE_OBJECT_NOT_FOUND":
                    raise
                raise DomainError(
                    "SOURCE_PDF_UNAVAILABLE",
                    "The known source PDF is not present in the configured bucket.",
                    409,
                ) from exc
        else:
            raise DomainError(
                "SOURCE_PDF_UNAVAILABLE",
                "The official PDF has not been downloaded. Run the source fetch script and retry; "
                "the endpoint may currently return a maintenance page.",
                409,
            )
        self._validate_document(source_id, document)
        self._save_local(document)
        if self.storage:
            self._cloud_documents[source_id] = document
            self._cloud_originals.add(source_id)
        return self.source_view(source_id)
