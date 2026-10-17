from types import SimpleNamespace

import pytest

from app import bootstrap
from app.config.settings import Settings
from app.domain.errors import DomainError


def configured(**overrides):
    return Settings(
        mode="gcp",
        GCP_PROJECT_ID="synthetic-project",
        SPANNER_INSTANCE="synthetic-instance",
        SPANNER_DATABASE="synthetic-database",
        GCS_BUCKET="synthetic-bucket",
        VERTEX_LOCATION="synthetic-location",
        **overrides,
    )


@pytest.fixture
def cloud_stubs(monkeypatch, bundle):
    from app.adapters.gcp import common, repository, storage
    from app.ai import google_client

    database = object()
    bucket = object()
    client = object()
    calls = []

    class Repository:
        def __init__(self, passed_database, scenario_id):
            assert passed_database is database
            assert scenario_id == "SCENARIO-MAS-2023"
            self.reads = 0

        def snapshot(self):
            self.reads += 1
            return bundle

    def make_database(project, instance, name):
        calls.append((project, instance, name))
        return database

    def create_client(project, location):
        calls.append((project, location))
        return client

    monkeypatch.setattr(common, "make_database", make_database)
    monkeypatch.setattr(repository, "SpannerRegulatoryRepository", Repository)
    monkeypatch.setattr(storage.GCSObjectStorage, "from_project", lambda project, name: bucket)
    monkeypatch.setattr(google_client, "create_vertex_client", create_client)
    return SimpleNamespace(database=database, storage=bucket, client=client, calls=calls)


def test_gcp_bootstrap_uses_real_adapter_types_with_injected_clients_and_no_ai_calls(cloud_stubs):
    adapters = bootstrap.create_adapters(configured(enable_live_ai=False))
    assert adapters.repository.snapshot().scenario.id == "SCENARIO-MAS-2023"
    assert adapters.repository is adapters.graph
    assert adapters.session_backend.database is cloud_stubs.database
    assert adapters.storage is cloud_stubs.storage
    assert adapters.transport is None and adapters.embeddings is None and adapters.search is None
    assert cloud_stubs.calls == [("synthetic-project", "synthetic-instance", "synthetic-database")]


def test_gcp_bootstrap_imports_optional_ai_path_without_network_or_model_substitution(cloud_stubs):
    adapters = bootstrap.create_adapters(
        configured(
            enable_live_ai=True,
            GEMINI_MODEL="explicit-test-model",
            MODEL_ARMOR_TEMPLATE="projects/synthetic-project/locations/us-central1/templates/test",
        )
    )
    assert adapters.transport.client is cloud_stubs.client
    assert adapters.transport.model == "explicit-test-model"
    assert adapters.ask_transport.client is cloud_stubs.client
    assert adapters.ask_transport.model == "explicit-test-model"
    assert adapters.embeddings.task_type == "RETRIEVAL_QUERY"
    assert adapters.search.database is cloud_stubs.database
    assert adapters.screen.session is None  # No ADC or HTTP session was created.
    assert adapters.vertex_client is cloud_stubs.client


def test_cloud_configuration_or_snapshot_failure_never_falls_back(monkeypatch, cloud_stubs):
    with pytest.raises(RuntimeError):
        bootstrap.create_adapters(Settings(mode="gcp", GCP_PROJECT_ID="", SPANNER_INSTANCE=""))
    from app.adapters.gcp import repository

    class BrokenRepository:
        def __init__(self, *args):
            pass

        def snapshot(self):
            raise DomainError("CLOUD_DATA_MISSING", "synthetic failure", 503)

    monkeypatch.setattr(repository, "SpannerRegulatoryRepository", BrokenRepository)
    with pytest.raises(DomainError) as caught:
        bootstrap.create_adapters(configured())
    assert caught.value.code == "CLOUD_DATA_MISSING"


def test_local_bootstrap_never_constructs_cloud_clients(monkeypatch):
    from app.adapters.gcp import common

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected cloud client")

    monkeypatch.setattr(common, "make_database", forbidden)
    adapters = bootstrap.create_adapters(Settings(mode="local"))
    assert adapters.repository.snapshot().scenario.id == "SCENARIO-MAS-2023"
    assert adapters.storage is None and adapters.vertex_client is None
