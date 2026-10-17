"""Explicit bundle/index operations against an existing database; never provisions."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def run(args, settings) -> dict:
    from app.adapters.gcp.common import make_database
    from app.adapters.gcp.repository import SpannerRegulatoryRepository
    from app.adapters.gcp.search import SearchEntity, SpannerSearchRepository
    from app.adapters.local_json import LocalJsonRepository

    local_bundle = LocalJsonRepository(settings.data_dir).snapshot()
    scenario_id = args.scenario_id or local_bundle.scenario.id
    if args.action == "plan":
        return {
            "action": "PLAN_ONLY",
            "scenario_id": scenario_id,
            "cloud_calls": "NOT_RUN",
            "schema": str(ROOT / "sql" / "spanner" / "001_schema.sql"),
        }
    if not all(
        (settings.gcp_project_id, settings.spanner_instance, settings.spanner_database)
    ):
        raise ValueError(
            "Explicit project, instance and database configuration is required"
        )
    database = make_database(
        settings.gcp_project_id, settings.spanner_instance, settings.spanner_database
    )
    repository = SpannerRegulatoryRepository(database, scenario_id)
    if args.action == "import-seed":
        repository.import_bundle(local_bundle)
        return {
            "action": "IMPORT_SEED",
            "status": "SUCCEEDED",
            "scenario_id": scenario_id,
            "notice": "Public-source paraphrases and synthetic enterprise fixtures retained; "
            "no model or PDF extraction is claimed.",
        }
    bundle = repository.snapshot()
    nodes = tuple(node for node in bundle.catalog if node.type != "MANDATE")
    texts = tuple(f"{node.title} {node.text}".strip() for node in nodes)
    vectors: tuple = (None,) * len(nodes)
    if args.action == "index-embeddings":
        from app.ai.google_client import VertexEmbeddingClient, create_vertex_client

        client = create_vertex_client(settings.gcp_project_id, settings.vertex_location)
        embeddings = VertexEmbeddingClient(
            client=client,
            model=settings.embedding_model,
            dimensions=768,
            task_type="RETRIEVAL_DOCUMENT",
        )
        collected = []
        try:
            for offset in range(0, len(nodes), 30):
                collected.extend(await embeddings.embed(texts[offset : offset + 30]))
        finally:
            await client.aio.aclose()
        vectors = tuple(collected)
    entities = tuple(
        SearchEntity(node.id, node.type, text, embedding)
        for node, text, embedding in zip(nodes, texts, vectors, strict=True)
    )
    SpannerSearchRepository(
        database, scenario_id, embedding_model=settings.embedding_model
    ).index_entities(entities)
    return {
        "action": args.action,
        "status": "SUCCEEDED",
        "scenario_id": scenario_id,
        "entity_count": len(entities),
        "embedding_model": settings.embedding_model
        if args.action == "index-embeddings"
        else None,
        "notice": "Lexical-only indexing replaces this catalog's previous vectors with NULL."
        if args.action == "index-lexical"
        else "Model-generated document vectors; no mapping approvals were changed.",
    }


def main() -> int:
    from app.config.settings import Settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action",
        choices=("plan", "import-seed", "index-lexical", "index-embeddings"),
        default="plan",
    )
    parser.add_argument("--scenario-id")
    parser.add_argument("--allow-cloud-writes", action="store_true")
    parser.add_argument("--allow-ai-calls", action="store_true")
    args = parser.parse_args()
    if args.action != "plan" and not args.allow_cloud_writes:
        parser.error(
            "This action writes existing resources; explicitly pass --allow-cloud-writes"
        )
    if args.action == "index-embeddings" and not args.allow_ai_calls:
        parser.error(
            "Embedding generation calls Vertex AI; explicitly pass --allow-ai-calls"
        )
    try:
        result = asyncio.run(run(args, Settings()))
    except Exception as exc:  # noqa: BLE001 -- sanitize provider failures at the CLI boundary
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "code": getattr(exc, "code", "ADMIN_OPERATION_FAILED")
                    if isinstance(getattr(exc, "code", None), str)
                    else "ADMIN_OPERATION_FAILED",
                }
            )
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
