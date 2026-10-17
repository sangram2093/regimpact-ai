import asyncio
from types import SimpleNamespace

import pytest

from app.adapters.gcp.storage import GCSObjectStorage
from app.domain.errors import DomainError


class Conflict(Exception):
    code = 412


class Missing(Exception):
    code = 404


class Blob:
    def __init__(self):
        self.content = None
        self.size = None
        self.generation = 7
        self.upload_options = None
        self.download_options = None

    def reload(self, **kwargs):
        if self.content is None:
            raise Missing("not found")
        self.size = len(self.content)

    def download_as_bytes(self, **kwargs):
        self.download_options = kwargs
        return self.content

    def upload_from_string(self, content, **kwargs):
        self.upload_options = kwargs
        if self.content is not None:
            raise Conflict()
        self.content = content


@pytest.fixture
def storage():
    blobs = {}
    bucket = SimpleNamespace(blob=lambda key: blobs.setdefault(key, Blob()))
    result = GCSObjectStorage(
        SimpleNamespace(bucket=lambda name: bucket), "synthetic-test", max_bytes=20
    )
    return result, blobs


def test_gcs_create_only_write_generation_pinned_read_and_idempotency(storage):
    adapter, blobs = storage
    assert (
        asyncio.run(adapter.write("sources/test.pdf", b"%PDF-fixture", "application/pdf"))
        == "gs://synthetic-test/sources/test.pdf"
    )
    assert blobs["sources/test.pdf"].upload_options["if_generation_match"] == 0
    asyncio.run(adapter.write("sources/test.pdf", b"%PDF-fixture", "application/pdf"))
    assert asyncio.run(adapter.read("sources/test.pdf")) == b"%PDF-fixture"
    assert blobs["sources/test.pdf"].download_options["if_generation_match"] == 7
    with pytest.raises(DomainError) as caught:
        asyncio.run(adapter.write("sources/test.pdf", b"different", "application/pdf"))
    assert caught.value.code == "SOURCE_OBJECT_CONFLICT"
    assert blobs["sources/test.pdf"].content == b"%PDF-fixture"


@pytest.mark.parametrize(
    "key", ["../secret", "/absolute", "sources//file", "gs://other/file", "sources/./file"]
)
def test_gcs_rejects_unsafe_keys_without_network(storage, key):
    adapter, blobs = storage
    with pytest.raises(DomainError):
        asyncio.run(adapter.write(key, b"data", "application/json"))
    assert not blobs


def test_gcs_size_type_and_provider_errors_fail_closed(storage):
    adapter, blobs = storage
    with pytest.raises(DomainError):
        asyncio.run(adapter.write("large", b"a" * 21, "application/pdf"))
    with pytest.raises(DomainError):
        asyncio.run(adapter.write("html", b"data", "text/html"))
    blob = Blob()
    blob.content = b"a" * 21
    blobs["large"] = blob
    with pytest.raises(DomainError):
        asyncio.run(adapter.read("large"))
    assert blob.download_options is None
    with pytest.raises(DomainError) as caught:
        asyncio.run(adapter.read("missing"))
    assert caught.value.code == "STORAGE_OBJECT_NOT_FOUND"


def test_gcs_availability_checks_metadata_without_downloading(storage):
    adapter, blobs = storage
    assert not asyncio.run(adapter.exists("missing"))
    asyncio.run(adapter.write("sources/test.pdf", b"%PDF-fixture", "application/pdf"))
    assert asyncio.run(adapter.exists("sources/test.pdf"))
    assert blobs["sources/test.pdf"].download_options is None
