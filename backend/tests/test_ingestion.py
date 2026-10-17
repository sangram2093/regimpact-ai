import asyncio
import hashlib
import io
import json

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.domain.errors import DomainError
from app.domain.ingestion import SourceDescriptor
from app.services.ingestion import IngestionService, PdfDocumentExtractor


@pytest.fixture
def source() -> SourceDescriptor:
    return SourceDescriptor(
        source_id="SYNTHETIC-PDF-TEST",
        title="Synthetic parser fixture",
        source_url="https://example.test/parser.pdf",
        publication_date="2026-10-17",
        instrument_status="SYNTHETIC",
        document_kind="SYNTHETIC",
        data_origin="SYNTHETIC_HACKATHON",
    )


def pdf(*pages: str, encrypted: bool = False) -> bytes:
    """Tiny actual PDFs, created solely as synthetic parser fixtures."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        if text:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): writer._add_object(font)}
                    )
                }
            )
            stream = DecodedStreamObject()
            lines = [
                line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                for line in text.splitlines()
            ]
            commands = (
                "BT /F1 12 Tf 50 750 Td 14 TL "
                + " ".join(f"({line}) Tj T*" for line in lines)
                + " ET"
            )
            stream.set_data(commands.encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("fixture-password")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_real_pdf_text_hash_and_stable_page_anchors(source):
    content = pdf(
        "Safeguard 2\n2.2.18 A synthetic gift clause",
        "Continued synthetic clause\n2.2.19 Next clause",
    )
    extractor = PdfDocumentExtractor()
    result = extractor.extract(content, source)
    again = extractor.extract(content, source)
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.segments == again.segments
    assert result.page_count == 2
    assert result.extraction_status == "COMPLETE"
    assert result.segments[1].paragraph_ref == "2.2.18"
    assert result.segments[1].text == "2.2.18 A synthetic gift clause"
    continuation = result.segments[2]
    assert continuation.page == 2 and continuation.paragraph_ref == "2.2.18"
    assert continuation.continued_from_previous_page
    assert len({item.segment_id for item in result.segments}) == len(result.segments)
    assert all(
        item.verification_status == "EXTRACTED_UNREVIEWED" and item.text_kind == "EXTRACTED_TEXT"
        for item in result.segments
    )


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"<html>maintenance</html>", "INVALID_PDF"),
        (b"%PDF-1.7\nbroken", "PDF_EXTRACTION_FAILED"),
        (b"", "SOURCE_SIZE_LIMIT"),
    ],
)
def test_reject_non_pdf_and_broken_sources(source, content, code):
    with pytest.raises(DomainError) as caught:
        PdfDocumentExtractor().extract(content, source)
    assert caught.value.code == code


def test_hash_mismatch_encryption_and_ocr_are_explicit(source):
    cases = [
        (
            pdf("Test"),
            source.model_copy(update={"expected_sha256": "0" * 64}),
            "SOURCE_HASH_MISMATCH",
        ),
        (pdf("Test", encrypted=True), source, "ENCRYPTED_PDF"),
        (pdf(""), source, "OCR_REQUIRED"),
    ]
    for content, descriptor, expected in cases:
        with pytest.raises(DomainError) as caught:
            PdfDocumentExtractor().extract(content, descriptor)
        assert caught.value.code == expected


def test_missing_text_never_implies_complete_extraction(source):
    result = PdfDocumentExtractor().extract(pdf("2.1 First", "", "Continuation unknown"), source)
    assert result.extraction_status == "PARTIAL"
    assert result.pages_without_text == (2,)
    assert result.warnings
    assert result.segments[-1].paragraph_ref == "page-3"
    assert not result.segments[-1].continued_from_previous_page


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"max_bytes": 10}, "SOURCE_SIZE_LIMIT"),
        ({"max_pages": 1}, "SOURCE_PAGE_LIMIT"),
        ({"max_text_characters": 1}, "SOURCE_TEXT_LIMIT"),
        ({"max_page_stream_bytes": 1}, "SOURCE_STREAM_LIMIT"),
    ],
)
def test_pdf_limits_fail_closed(source, options, expected):
    with pytest.raises(DomainError) as caught:
        PdfDocumentExtractor(**options).extract(pdf("2.1 First", "Second"), source)
    assert caught.value.code == expected


def test_storage_records_only_actual_bytes_and_deterministic_metadata(source):
    class Storage:
        def __init__(self):
            self.objects = {}

        async def write(self, key, content, content_type):
            if key in self.objects:
                if self.objects[key] != (content, content_type):
                    raise DomainError("SOURCE_OBJECT_CONFLICT", "test", 409)
            self.objects[key] = content, content_type
            return "gs://synthetic-test/" + key

        async def read(self, key):
            return self.objects[key][0]

    storage = Storage()
    service = IngestionService(PdfDocumentExtractor(), storage)
    content = pdf("2.1 Synthetic extraction fixture")
    first = asyncio.run(service.ingest_bytes(content, source))
    again = asyncio.run(service.ingest_bytes(content, source))
    assert first.extraction_uri == again.extraction_uri
    assert first.extracted_at == again.extracted_at
    assert len(storage.objects) == 3
    original = next(value for key, value in storage.objects.items() if key.endswith(".pdf"))
    assert original == (content, "application/pdf")
    metadata = json.loads(
        next(
            value[0] for key, value in storage.objects.items() if key.endswith("extraction-v1.json")
        )
    )
    assert metadata["sha256"] == first.sha256
    assert "extracted_at" not in metadata  # Hash-addressed bytes cannot vary on retries.
    assert metadata["segments"][0]["text_kind"] == "EXTRACTED_TEXT"
    # Pinning a previously unpinned descriptor does not change the source bytes or provenance.
    pinned = source.model_copy(update={"expected_sha256": first.sha256})
    assert asyncio.run(service.ingest_bytes(content, pinned)).extracted_at == first.extracted_at


def test_mime_and_source_status_are_checked_before_extraction(source):
    with pytest.raises(DomainError) as caught:
        asyncio.run(
            IngestionService(PdfDocumentExtractor()).ingest_bytes(
                pdf("Test"), source, content_type="text/html"
            )
        )
    assert caught.value.code == "UNSUPPORTED_SOURCE_TYPE"
    with pytest.raises(ValueError):
        SourceDescriptor.model_validate({**source.model_dump(), "instrument_status": "IN_FORCE"})
