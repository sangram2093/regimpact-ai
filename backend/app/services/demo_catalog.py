"""Read-only demonstration registry, served from Firestore in the deployed app."""

from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from app.domain.errors import DomainError


class DemoStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)
    path: str = Field(pattern=r"^/(sources|delta-review|impact|ask|runs|changes/[A-Z0-9-]+)$")


class DemoCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(pattern=r"^SCENARIO-[A-Z0-9-]+$")
    title: str = Field(min_length=1, max_length=160)
    baseline: str = Field(min_length=1, max_length=200)
    comparison: str = Field(min_length=1, max_length=200)
    notice: str = Field(min_length=1, max_length=500)
    source_ids: list[str] = Field(min_length=2, max_length=2)
    steps: list[DemoStep] = Field(min_length=1, max_length=5)


class DemoCatalogView(BaseModel):
    origin: Literal["FIRESTORE", "LOCAL_SEED"]
    catalog: DemoCatalog


def decode_firestore(value: dict[str, Any]) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "arrayValue" in value:
        return [decode_firestore(item) for item in value["arrayValue"].get("values", [])]
    if "mapValue" in value:
        return {
            key: decode_firestore(item)
            for key, item in value["mapValue"].get("fields", {}).items()
        }
    raise ValueError("Unsupported demo catalog field type")


class DemoCatalogService:
    def __init__(
        self,
        *,
        mode: str,
        data_dir: Path,
        project: str,
        database: str,
        scenario_id: str = "SCENARIO-MAS-2023",
        local_file: str = "seed/demo_catalog.json",
    ) -> None:
        self.mode = mode
        self.data_dir = data_dir
        self.project = project
        self.database = database
        self.scenario_id = scenario_id
        self.local_file = local_file

    def read(self) -> DemoCatalogView:
        if self.mode != "gcp":
            catalog = DemoCatalog.model_validate_json(
                (self.data_dir / self.local_file).read_text(encoding="utf-8")
            )
            return DemoCatalogView(origin="LOCAL_SEED", catalog=catalog)
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/datastore"]
            )
            url = (
                "https://firestore.googleapis.com/v1/projects/"
                f"{quote(self.project, safe='')}/databases/{quote(self.database, safe='')}/"
                f"documents/demo_catalog/{quote(self.scenario_id, safe='')}"
            )
            with AuthorizedSession(credentials) as session:
                response = session.get(url, timeout=8, max_allowed_time=12)
                response.raise_for_status()
                body = response.json()
            catalog = DemoCatalog.model_validate(
                {key: decode_firestore(value) for key, value in body["fields"].items()}
            )
            if catalog.scenario_id != self.scenario_id:
                raise ValueError("Firestore guide belongs to another scenario")
            return DemoCatalogView(origin="FIRESTORE", catalog=catalog)
        except Exception as exc:
            # No silent local fallback: the UI must accurately report Firestore availability.
            raise DomainError(
                "DEMO_CATALOG_UNAVAILABLE",
                "The demonstration guide is temporarily unavailable. "
                "The review workspace remains available.",
                503,
            ) from exc
