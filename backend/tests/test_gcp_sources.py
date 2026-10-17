import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_ingestion import pdf

from app.domain.errors import DomainError
from app.services.sources import SourceService


class Storage:
    def __init__(self):
        self.objects = {}
        self.reads = []
        self.inspections = []

    async def read(self, key):
        self.reads.append(key)
        if key not in self.objects:
            raise DomainError("STORAGE_OBJECT_NOT_FOUND", "test missing object", 404)
        return self.objects[key]

    async def exists(self, key):
        self.inspections.append(key)
        return key in self.objects

    async def write(self, key, content, content_type):
        if key in self.objects and self.objects[key] != content:
            raise DomainError("SOURCE_OBJECT_CONFLICT", "test immutable conflict", 409)
        self.objects[key] = content
        return "gs://test-only/" + key


@pytest.fixture
def source_files(tmp_path: Path):
    data = tmp_path / "data"
    public = data / "public"
    downloads = public / "downloads"
    downloads.mkdir(parents=True)
    content = pdf("2.1 Synthetic fixture text for ingestion integration tests")
    digest = hashlib.sha256(content).hexdigest()
    item = {
        "source_id": "TEST-SOURCE",
        "title": "Synthetic fixture for the public-source adapter",
        "source_url": "https://example.test/test-source.pdf",
        "publication_date": "2026-10-17",
        "instrument_status": "IN_FORCE",
        "sha256": digest,
        "local_path": "downloads/TEST-SOURCE.pdf",
        "fetch_status": "DOWNLOADED",
        "retrieved_at": "2026-10-17T00:00:00+00:00",
    }
    (public / "source-manifest.json").write_text(json.dumps({"sources": [item]}), encoding="utf-8")
    path = downloads / "TEST-SOURCE.pdf"
    path.write_bytes(content)
    return data, path, content, digest


def test_cloud_ingestion_survives_fresh_runtime_and_retains_first_timestamp(source_files, tmp_path):
    data, path, _, digest = source_files
    storage = Storage()
    first = SourceService(data, tmp_path / "first", storage)
    view = asyncio.run(first.ingest("TEST-SOURCE"))
    assert view["ingestion_status"] == "EXTRACTED_COMPLETE"
    assert len(storage.objects) == 3
    original = first.document("TEST-SOURCE")
    asyncio.run(first.ingest("TEST-SOURCE"))
    assert first.document("TEST-SOURCE").extracted_at == original.extracted_at
    path.unlink()
    restarted = SourceService(data, tmp_path / "fresh", storage)
    assert restarted.document("TEST-SOURCE") is None
    asyncio.run(restarted.refresh())
    assert restarted.document("TEST-SOURCE") == original
    assert restarted.list_sources()["sources"][0]["can_ingest"]
    assert storage.reads[-1] == f"sources/TEST-SOURCE/{digest}/document-v1.json"
    # Reingestion can use the pinned original object after the local PDF is removed.
    asyncio.run(restarted.ingest("TEST-SOURCE"))
    assert restarted.document("TEST-SOURCE").sha256 == digest


def test_cloud_missing_objects_and_unknown_checksums_do_not_claim_availability(
    source_files, tmp_path
):
    data, path, _, _ = source_files
    path.unlink()
    storage = Storage()
    service = SourceService(data, tmp_path / "state", storage)
    asyncio.run(service.refresh())
    assert service.document("TEST-SOURCE") is None
    assert not service.source_view("TEST-SOURCE")["can_ingest"]
    with pytest.raises(DomainError) as caught:
        asyncio.run(service.ingest("TEST-SOURCE"))
    assert caught.value.code == "SOURCE_PDF_UNAVAILABLE"
    service.sources["TEST-SOURCE"]["sha256"] = None
    storage.reads.clear()
    storage.inspections.clear()
    asyncio.run(service.refresh())
    assert storage.reads == [] and storage.inspections == []


def test_metadata_and_pdf_hash_tampering_fail_before_use(source_files, tmp_path):
    data, path, _, digest = source_files
    storage = Storage()
    service = SourceService(data, tmp_path / "state", storage)
    asyncio.run(service.ingest("TEST-SOURCE"))
    key = f"sources/TEST-SOURCE/{digest}/document-v1.json"
    metadata = json.loads(storage.objects[key])
    metadata["segments"][0]["source_sha256"] = "0" * 64
    storage.objects[key] = json.dumps(metadata).encode()
    with pytest.raises(DomainError) as caught:
        asyncio.run(SourceService(data, tmp_path / "restart", storage).refresh())
    assert caught.value.code == "SOURCE_METADATA_INVALID"
    path.write_bytes(pdf("2.1 A different fixture"))
    with pytest.raises(DomainError) as caught:
        asyncio.run(service.ingest("TEST-SOURCE"))
    assert caught.value.code == "SOURCE_HASH_MISMATCH"


def test_cloud_provider_failure_does_not_use_local_metadata_fallback(source_files, tmp_path):
    data, _, _, _ = source_files
    storage = Storage()
    service = SourceService(data, tmp_path / "state", storage)
    asyncio.run(service.ingest("TEST-SOURCE"))

    async def unavailable(key):
        raise DomainError("STORAGE_READ_FAILED", "test unavailable", 503)

    storage.read = unavailable
    with pytest.raises(DomainError) as caught:
        asyncio.run(service.refresh())
    assert caught.value.code == "STORAGE_READ_FAILED"
    assert service.document("TEST-SOURCE") is None


def test_local_mode_recovery_and_path_boundaries(source_files, tmp_path):
    data, _, _, _ = source_files
    service = SourceService(data, tmp_path / "state")
    asyncio.run(service.refresh())
    asyncio.run(service.ingest("TEST-SOURCE"))
    restarted = SourceService(data, tmp_path / "state")
    assert restarted.document("TEST-SOURCE").segments[0].text.startswith("2.1 Synthetic")
    service.sources["TEST-SOURCE"]["local_path"] = "../../outside.pdf"
    with pytest.raises(DomainError) as caught:
        asyncio.run(service.ingest("TEST-SOURCE"))
    assert caught.value.code == "INVALID_SOURCE_PATH"
    with pytest.raises(DomainError) as caught:
        asyncio.run(service.ingest("https://untrusted.test/file.pdf"))
    assert caught.value.code == "SOURCE_NOT_FOUND"


def test_api_routes_use_async_ingestion_and_durable_refresh(
    client: TestClient, session_headers, source_files, tmp_path
):
    data, path, _, digest = source_files
    storage = Storage()
    client.app.state.sources = SourceService(data, tmp_path / "first", storage)
    response = client.post("/api/v1/sources/TEST-SOURCE/ingest", headers=session_headers)
    assert response.status_code == 200
    assert response.json()["data"]["sha256"] == digest
    assert response.json()["data"]["ingestion_status"] == "EXTRACTED_COMPLETE"
    path.unlink()
    client.app.state.sources = SourceService(data, tmp_path / "new-worker", storage)
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    assert response.json()["data"]["sources"][0]["segment_count"] == 1
    assert client.app.state.sources.document("TEST-SOURCE") is not None
