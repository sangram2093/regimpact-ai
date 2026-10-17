"""Lazy SDK construction: importing this package never authenticates or provisions."""

import json
from typing import Any

from app.adapters.gcp.timeouts import configure_rpc_deadlines
from app.domain.errors import DomainError


def make_database(project: str, instance: str, database: str) -> Any:
    if not all((project, instance, database)):
        raise DomainError(
            "GCP_CONFIGURATION_REQUIRED",
            "Explicit Spanner project, instance and database are required.",
            503,
        )
    try:
        from google.cloud import spanner
    except ImportError as exc:
        raise DomainError(
            "GCP_DEPENDENCY_MISSING", "Install the gcp dependency extra to use Spanner.", 503
        ) from exc
    # The optional SDK metrics exporter has emitted malformed Monitoring resource
    # labels with the pinned version. Keep database operations independent of it;
    # application logs and server-side Spanner metrics remain available.
    result = (
        spanner.Client(project=project, disable_builtin_metrics=True)
        .instance(instance)
        .database(database)
    )
    configure_rpc_deadlines(result.spanner_api)
    return result


def sql_types() -> Any:
    try:
        from google.cloud.spanner_v1 import param_types
    except ImportError as exc:
        raise DomainError(
            "GCP_DEPENDENCY_MISSING", "Install the gcp dependency extra to use Spanner.", 503
        ) from exc
    return param_types


def json_value(value: Any) -> dict[str, Any]:
    result = json.loads(value) if isinstance(value, str) else dict(value)
    if not isinstance(result, dict):
        raise ValueError("Stored JSON must be an object")
    # A detached plain JSON object prevents state aliasing across session callbacks.
    return json.loads(json.dumps(result, allow_nan=False))


def spanner_json(value: dict[str, Any]) -> Any:
    from google.cloud.spanner_v1.data_types import JsonObject

    return JsonObject(json_value(value))
