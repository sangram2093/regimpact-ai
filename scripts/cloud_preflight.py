"""Offline configuration by default; optional read-only existing-resource capability checks."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def offline_report(settings) -> dict:
    packages = {}
    for package in (
        "google-cloud-spanner",
        "google-cloud-storage",
        "google-genai",
        "pypdf",
    ):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = "NOT_INSTALLED"
    required = {
        "GCP_PROJECT_ID": settings.gcp_project_id,
        "SPANNER_INSTANCE": settings.spanner_instance,
        "SPANNER_DATABASE": settings.spanner_database,
        "GCS_BUCKET": settings.gcs_bucket,
        "VERTEX_LOCATION": settings.vertex_location,
    }
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "mode": "OFFLINE",
        "cloud_capability_spike": "NOT_RUN",
        "configuration": {
            key: "SET" if value else "MISSING" for key, value in required.items()
        },
        "packages": packages,
        "notes": [
            "No credentials, cloud resources, source PDFs or models are inspected in offline mode.",
            "This command never provisions resources, enables APIs, "
            "upgrades trials or calls a model.",
        ],
    }


async def live_report(settings, scenario_id: str) -> dict:
    from app.adapters.gcp.common import make_database, sql_types
    from app.adapters.gcp.repository import SpannerRegulatoryRepository
    from app.adapters.gcp.search import SpannerSearchRepository
    from app.adapters.gcp.storage import GCSObjectStorage
    from app.services.retrieval import reciprocal_rank_fusion

    result = {"mode": "LIVE_READ_ONLY", "checks": {}}
    checks = result["checks"]
    database = make_database(
        settings.gcp_project_id, settings.spanner_instance, settings.spanner_database
    )
    repository = SpannerRegulatoryRepository(database, scenario_id)
    bundle = repository.snapshot()
    checks["relational_snapshot"] = {
        "status": "PASSED",
        "scenario_id": bundle.scenario.id,
    }
    with database.snapshot() as snapshot:
        vector_rows = list(
            snapshot.execute_sql(
                "SELECT EntityId, Embedding FROM SearchEntity "
                "WHERE BundleId = @bundle AND Kind = 'POLICY_REQUIREMENT' "
                "AND Status = 'ACTIVE' AND EmbeddingModel = @model AND Embedding IS NOT NULL "
                "ORDER BY EntityId LIMIT 1",
                params={"bundle": scenario_id, "model": settings.embedding_model},
                param_types={"bundle": sql_types().STRING, "model": sql_types().STRING},
            )
        )
    search = SpannerSearchRepository(
        database, scenario_id, embedding_model=settings.embedding_model
    )
    policy = next(
        (node for node in bundle.catalog if node.type == "POLICY_REQUIREMENT"), None
    )
    lexical = await search.lexical_search(policy.title if policy else "gift")
    checks["full_text"] = {
        "status": "PASSED" if lexical else "NO_RESULTS",
        "ids": lexical,
    }
    if vector_rows:
        vector = await search.vector_search(tuple(vector_rows[0][1]))
        checks["exact_knn"] = {
            "status": "PASSED" if vector_rows[0][0] in vector else "FAILED",
            "probe": "Stored document vector queried against its own catalog; "
            "not a relevance evaluation.",
            "ids": vector,
        }
        checks["rrf"] = {
            "status": "PASSED",
            "ids": [item.id for item in reciprocal_rank_fusion(vector, lexical)],
        }
    else:
        checks["exact_knn"] = {
            "status": "NOT_RUN",
            "reason": "No indexed document embeddings.",
        }
        checks["rrf"] = {
            "status": "NOT_RUN",
            "reason": "Exact KNN has no indexed embeddings.",
        }
    expected = {
        (edge.source_id, edge.target_id, control.target_id, edge.id, control.id)
        for edge in bundle.edges
        if edge.relationship == "ADDRESSED_BY" and edge.status == "APPROVED"
        for control in bundle.edges
        if control.relationship == "IMPLEMENTED_BY"
        and control.source_id == edge.target_id
        and control.status == "APPROVED"
        and any(
            m.id == edge.source_id and m.status == "BASELINE_APPROVED"
            for m in bundle.mandates
        )
    }
    paths = [
        path
        for mandate in bundle.mandates
        for path in repository.approved_control_paths(mandate.id)
    ]
    actual = {
        (
            p.mandate_id,
            p.policy_id,
            p.control_id,
            p.mandate_policy_edge_id,
            p.policy_control_edge_id,
        )
        for p in paths
    }
    checks["approved_graph"] = {
        "status": "PASSED" if expected == actual else "FAILED",
        "path_count": len(actual),
        "expected_count": len(expected),
        "risk_edges_excluded": True,
    }
    storage = GCSObjectStorage.from_project(
        settings.gcp_project_id, settings.gcs_bucket
    )
    storage.client.bucket(settings.gcs_bucket).reload(timeout=30)
    checks["gcs_metadata_read"] = {"status": "PASSED", "object_write": "NOT_RUN"}
    result["cloud_capability_spike"] = (
        "READ_ONLY_CHECKS_PASSED"
        if all(v["status"] == "PASSED" for v in checks.values())
        else "INCOMPLETE"
    )
    result["notes"] = [
        "No writes or model calls. Passing read checks does not validate IAM writes, "
        "model availability, source authenticity or legal conclusions."
    ]
    return result


def main() -> int:
    from app.config.settings import Settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-read-only",
        action="store_true",
        help="Query existing configured cloud resources using ADC; no provisioning or writes",
    )
    parser.add_argument(
        "--scenario-id", help="Explicit imported scenario ID required for live checks"
    )
    args = parser.parse_args()
    settings = Settings()
    report = offline_report(settings)
    if args.live_read_only:
        if not args.scenario_id:
            parser.error("--scenario-id is required with --live-read-only")
        if any(
            status == "MISSING"
            for name, status in report["configuration"].items()
            if name != "VERTEX_LOCATION"
        ):
            parser.error(
                "Live checks require GCP_PROJECT_ID, SPANNER_INSTANCE, "
                "SPANNER_DATABASE and GCS_BUCKET"
            )
        try:
            report.update(asyncio.run(live_report(settings, args.scenario_id)))
        except Exception as exc:  # noqa: BLE001 -- sanitize provider failures at the CLI boundary
            # Never print provider messages that may contain credentials, URLs or request payloads.
            report.update(
                mode="LIVE_READ_ONLY",
                cloud_capability_spike="FAILED",
                error_type=type(exc).__name__,
            )
    print(json.dumps(report, indent=2))
    return 1 if report["cloud_capability_spike"] in {"FAILED", "INCOMPLETE"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
