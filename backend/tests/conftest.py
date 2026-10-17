from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.adapters.local_json import LocalJsonRepository
from app.config.settings import Settings
from app.domain.graph import approved_control_paths
from app.domain.models import Classification, SafetyChecks, SeedBundle
from app.main import create_app
from app.repositories.sessions import SessionRepository
from app.services.impact import ImpactService
from app.services.scenarios import ScenarioService


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    # Developer-ingested sources must not leak into tests of missing-source guards.
    with TestClient(
        create_app(Settings(mode="local", enable_live_ai=False, runtime_dir=tmp_path))
    ) as test_client:
        yield test_client


@pytest.fixture
def session_headers() -> dict[str, str]:
    return {"X-Demo-Session": str(uuid4())}


@pytest.fixture
def bundle() -> SeedBundle:
    return LocalJsonRepository(Settings().data_dir).snapshot()


@pytest.fixture
def safe_checks() -> SafetyChecks:
    # Explicitly synthetic TEST scenario. These claims do not describe MAS P002-2023.
    return SafetyChecks(
        high_confidence_pcs_target=False,
        applicable_global_overlay=False,
        no_effect_result="NO_EFFECT_SUPPORTED",
        human_change_confirmed=True,
        scope_basis="SYNTHETIC TEST ONLY: no applicable scope or legal-force change.",
    )


class MemoryRepository:
    def __init__(self, bundle: SeedBundle) -> None:
        self.bundle = bundle

    def snapshot(self) -> SeedBundle:
        return self.bundle

    def approved_outgoing(self, node_id: str):
        return tuple(
            e for e in self.bundle.edges if e.source_id == node_id and e.status == "APPROVED"
        )

    def approved_control_paths(self, mandate_id: str):
        return approved_control_paths(self.bundle, mandate_id)


@pytest.fixture
def synthetic_safe_service(bundle: SeedBundle, safe_checks: SafetyChecks) -> ScenarioService:
    data = bundle.model_dump()
    for change in data["changes"]:
        if change["mandate_id"] == "M-IDENTITY":
            change["classification"] = Classification.UNCHANGED
            change["safety_checks"] = safe_checks.model_dump()
    data["proposed_change_statements"] = tuple(
        pcs for pcs in data["proposed_change_statements"] if pcs["id"] != "PCS-LEGAL-FORCE"
    )
    synthetic = SeedBundle.model_validate(data)
    repository = MemoryRepository(synthetic)
    return ScenarioService(
        repository, SessionRepository(300, 10), ImpactService(synthetic, repository)
    )
