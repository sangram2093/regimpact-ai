"""Deployment regression checks: real-store readiness, artifact integrity and rollback."""

import hashlib
import importlib.util
import sys
from contextlib import nullcontext
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "regimpact_deployment", ROOT / "scripts/deploy_release.py"
)
assert SPEC is not None and SPEC.loader is not None
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)


def test_readiness_rejects_non_firestore_registry_without_calling_models() -> None:
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        data = (
            {"status": "ok", "mode": "gcp"}
            if request.url.path.endswith("health")
            else {"origin": "LOCAL_SEED"}
        )
        return httpx.Response(200, json={"data": data})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Firestore"):
            deployment.verify_api("https://candidate.example", client)
    assert paths == ["/api/v1/health", "/api/v1/demo-catalog"]


@pytest.mark.parametrize("failure", ["checksum", "path"])
def test_corrupt_or_unsafe_submission_assets_never_reach_publish_directory(
    tmp_path: Path, failure: str
) -> None:
    class Blob:
        def download_as_bytes(self, **kwargs):
            return b"verified asset"

    class Bucket:
        def blob(self, path):
            return Blob()

    class Storage:
        def bucket(self, name):
            return Bucket()

    manifest = {
        "bucket": "regimpact-ai-builds-61760046387",
        "prefix": "submission-assets/test",
        "files": [
            {"name": "first.mp4", "sha256": hashlib.sha256(b"verified asset").hexdigest()},
            {"name": "../escape.pptx" if failure == "path" else "deck.pptx", "sha256": "0" * 64},
        ],
    }
    destination = tmp_path / "publish"
    with pytest.raises(ValueError):
        deployment.restore_assets(manifest, Storage(), destination)
    assert not destination.exists()
    assert not (tmp_path / "escape.pptx").exists()


@pytest.mark.parametrize("failure_stage", ["candidate", "hosting"])
def test_failed_release_preserves_or_restores_previous_production(
    monkeypatch: pytest.MonkeyPatch, failure_stage: str, tmp_path: Path
) -> None:
    import google.auth
    from google.auth.transport import requests
    from google.cloud import storage

    manifest_path = tmp_path / "assets.json"
    manifest_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(deployment, "MANIFEST", manifest_path)
    commands = []
    firebase_calls = []

    def cli(*args, **kwargs):
        commands.append(args)
        if args[:4] == ("gcloud", "run", "services", "describe"):
            return {"status": {"traffic": [{"revisionName": "old", "percent": 100}]}}
        if args[:3] == ("gcloud", "run", "deploy"):
            return {
                "status": {
                    "latestReadyRevisionName": "new",
                    "traffic": [{"tag": "cd-candidate", "url": "https://candidate.example"}],
                }
            }
        return ""

    def firebase(session, method, path, **kwargs):
        firebase_calls.append((method, kwargs))
        return {"releases": [{"version": {"name": "sites/regimpact-ai/versions/old"}}]}

    def fail(*args):
        raise ValueError("Release readiness failed")

    monkeypatch.setattr(deployment, "cli", cli)
    monkeypatch.setattr(deployment, "firebase_request", firebase)
    monkeypatch.setattr(deployment, "restore_assets", lambda *args: None)
    monkeypatch.setattr(google.auth, "default", lambda **kwargs: (object(), None))
    monkeypatch.setattr(storage, "Client", lambda **kwargs: object())
    monkeypatch.setattr(requests, "AuthorizedSession", lambda *args: nullcontext(object()))
    monkeypatch.setattr(
        deployment, "verify_api", fail if failure_stage == "candidate" else lambda *a: None
    )
    monkeypatch.setattr(deployment, "verify_hosting", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy_release.py",
            "--commit",
            "a" * 40,
            "--image",
            "asia-south1-docker.pkg.dev/regimpact-ai/regimpact/regimpact-api@sha256:" + "b" * 64,
        ],
    )
    with pytest.raises(ValueError, match="readiness"):
        deployment.main()
    traffic_updates = [args[-1] for args in commands if "update-traffic" in args]
    if failure_stage == "candidate":
        assert traffic_updates == []
        assert not any(method == "POST" for method, _ in firebase_calls)
    else:
        assert traffic_updates == ["--to-revisions=new=100", "--to-revisions=old=100"]
        assert firebase_calls[-1][0] == "POST"
        assert firebase_calls[-1][1]["params"]["versionName"] == "sites/regimpact-ai/versions/old"
