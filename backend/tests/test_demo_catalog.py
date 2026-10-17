from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.domain.errors import DomainError
from app.services.demo_catalog import DemoCatalogService


def test_local_catalog_preserves_proposal_status(client: TestClient) -> None:
    response = client.get("/api/v1/demo-catalog")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["origin"] == "LOCAL_SEED"
    assert "not a claim about current binding law" in data["catalog"]["notice"]
    assert len(data["catalog"]["steps"]) == 5


def test_firestore_read_never_silently_falls_back_to_local() -> None:
    service = DemoCatalogService(
        mode="gcp", data_dir=Settings().data_dir, project="example", database="(default)"
    )
    with patch("google.auth.default", side_effect=RuntimeError("credentials unavailable")):
        with pytest.raises(DomainError) as failure:
            service.read()
    assert failure.value.code == "DEMO_CATALOG_UNAVAILABLE"
    assert failure.value.status_code == 503


def test_firestore_catalog_is_validated_and_read_is_bounded() -> None:
    settings = Settings()
    local = DemoCatalogService(
        mode="local", data_dir=settings.data_dir, project="", database="(default)"
    ).read()

    def encode(value):
        if isinstance(value, str):
            return {"stringValue": value}
        if isinstance(value, list):
            return {"arrayValue": {"values": [encode(item) for item in value]}}
        return {"mapValue": {"fields": {key: encode(item) for key, item in value.items()}}}

    response = MagicMock()
    response.json.return_value = encode(local.catalog.model_dump())["mapValue"]
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value = response
    service = DemoCatalogService(
        mode="gcp", data_dir=settings.data_dir, project="example", database="(default)"
    )
    with (
        patch("google.auth.default", return_value=(MagicMock(), "example")),
        patch("google.auth.transport.requests.AuthorizedSession", return_value=session),
    ):
        assert service.read().origin == "FIRESTORE"
    assert session.get.call_args.kwargs == {"timeout": 8, "max_allowed_time": 12}
