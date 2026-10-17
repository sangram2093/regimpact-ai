"""Composition root. GCP mode reads real stores and never falls back to local data."""

from dataclasses import dataclass
from typing import Any

from app.adapters.local_json import LocalJsonRepository
from app.adapters.sqlite_sessions import SQLiteSessionBackend
from app.config.settings import Settings
from app.repositories.ports import GraphRepository, RegulatoryRepository
from app.repositories.sessions import SessionBackend


@dataclass
class Adapters:
    repository: RegulatoryRepository
    graph: GraphRepository
    session_backend: SessionBackend | None = None
    search: Any = None
    embeddings: Any = None
    transport: Any = None
    ask_transport: Any = None
    screen: Any = None
    vertex_client: Any = None
    storage: Any = None


def create_adapters(settings: Settings) -> Adapters:
    if settings.mode == "local":
        repository = LocalJsonRepository(settings.data_dir)
        backend = (
            SQLiteSessionBackend(
                settings.session_db, settings.session_ttl_seconds, settings.max_sessions
            )
            if settings.session_db
            else None
        )
        return Adapters(repository=repository, graph=repository, session_backend=backend)
    required = (
        settings.gcp_project_id,
        settings.vertex_location,
        settings.spanner_instance,
        settings.spanner_database,
        settings.gcs_bucket,
    )
    if not all(required):
        raise RuntimeError(
            "GCP mode requires project, Vertex location, Spanner instance/database and bucket; "
            "it will not silently substitute local fixtures."
        )
    from app.adapters.gcp.common import make_database
    from app.adapters.gcp.repository import SpannerRegulatoryRepository
    from app.adapters.gcp.search import SpannerSearchRepository
    from app.adapters.gcp.sessions import SpannerSessionBackend
    from app.adapters.gcp.storage import GCSObjectStorage

    database = make_database(
        settings.gcp_project_id, settings.spanner_instance, settings.spanner_database
    )
    repository = SpannerRegulatoryRepository(database, "SCENARIO-MAS-2023")
    repository.snapshot()  # Require an explicitly imported, validated corpus before startup.
    result = Adapters(
        repository=repository,
        graph=repository,
        session_backend=SpannerSessionBackend(
            database, settings.session_ttl_seconds, settings.max_sessions
        ),
        storage=GCSObjectStorage.from_project(settings.gcp_project_id, settings.gcs_bucket),
    )
    if settings.enable_live_ai:
        from app.ai.adk_ask import AdkAskTransport
        from app.ai.armor import ModelArmorScreen
        from app.ai.google_client import (
            GoogleGenAITransport,
            VertexEmbeddingClient,
            create_vertex_client,
        )

        client = create_vertex_client(settings.gcp_project_id, settings.vertex_location)
        result.vertex_client = client
        result.transport = GoogleGenAITransport(client=client, model=settings.gemini_model)
        result.ask_transport = AdkAskTransport(client=client, model=settings.gemini_model)
        result.embeddings = VertexEmbeddingClient(client=client, model=settings.embedding_model)
        result.search = SpannerSearchRepository(
            database, "SCENARIO-MAS-2023", embedding_model=settings.embedding_model
        )
        if settings.model_armor_template:
            result.screen = ModelArmorScreen(settings.model_armor_template)
    return result
