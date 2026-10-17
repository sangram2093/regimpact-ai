"""Publish an explicitly built image; preserve submission assets and roll back on failure.

Authentication comes from ADC / GitHub OIDC. This does not provision databases,
change IAM, import a corpus or invoke a model. Production is changed only after
the candidate API passes real-store checks.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "regimpact-ai"
REGION = "asia-south1"
SERVICE = "regimpact-api"
SITE = "regimpact-ai"
HOSTING = "https://regimpact-ai.web.app"
MANIFEST = ROOT / "infra/firebase/submission-assets.json"
IMAGE_PATTERN = re.compile(
    r"asia-south1-docker\.pkg\.dev/regimpact-ai/regimpact/regimpact-api@sha256:[a-f0-9]{64}"
)


def cli(*args: str, as_json: bool = False) -> Any:
    command = list(args)
    if command[0] == "gcloud":
        command += [f"--project={PROJECT}", "--quiet"]
        if as_json:
            command.append("--format=json")
    executable = shutil.which(command[0])
    if not executable:
        raise RuntimeError(f"Required deployment command is unavailable: {command[0]}")
    command[0] = executable
    result = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
    )
    if result.returncode:
        # Provider logs can contain signed URLs. Keep raw output out of public CI logs.
        raise RuntimeError(
            f"{args[0]} {args[1]} failed with exit code {result.returncode}"
        )
    return json.loads(result.stdout) if as_json else result.stdout


def restore_assets(manifest: dict, storage_client: Any, destination: Path) -> None:
    if manifest["bucket"] != "regimpact-ai-builds-61760046387":
        raise ValueError("Submission assets must use the reviewed private bucket")
    prefix = manifest["prefix"]
    if not prefix.startswith("submission-assets/") or ".." in prefix.split("/"):
        raise ValueError("Unapproved submission asset prefix")
    verified = []
    for item in manifest["files"]:
        name = item["name"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Submission asset names must be plain filenames")
        content = (
            storage_client.bucket(manifest["bucket"])
            .blob(f"{prefix.rstrip('/')}/{name}")
            .download_as_bytes(timeout=30)
        )
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError(f"Submission asset checksum mismatch: {name}")
        verified.append((name, content))
    # Verify the whole set before writing any publishable artifact.
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in verified:
        (destination / name).write_bytes(content)


def verify_api(base: str, client: httpx.Client) -> None:
    def data(path: str) -> dict:
        response = client.get(base.rstrip("/") + "/api/v1/" + path)
        response.raise_for_status()
        return response.json()["data"]

    health = data("health")
    if health.get("status") != "ok" or health.get("mode") != "gcp":
        raise ValueError("The candidate did not start in healthy GCP mode")
    if data("demo-catalog").get("origin") != "FIRESTORE":
        raise ValueError("The deployed Firestore registry is not available")
    sources = {item["id"]: item for item in data("sources")["sources"]}
    for identifier in ("MAS-FSG-G02-2016", "MAS-P002-2023"):
        source = sources.get(identifier, {})
        if source.get("ingestion_status") != "EXTRACTED_COMPLETE":
            raise ValueError(f"Required source is not ready: {identifier}")
        if source.get("segment_count", 0) <= 0 or not re.fullmatch(
            r"[a-f0-9]{64}", source.get("sha256") or ""
        ):
            raise ValueError(f"Required source evidence is incomplete: {identifier}")
    if not data("dashboard"):
        raise ValueError("The real-store dashboard is unavailable")


def verify_hosting(manifest: dict, client: httpx.Client) -> None:
    verify_api(HOSTING, client)
    for path in ("/dashboard", "/delta-review", "/ask", "/submission/"):
        response = client.get(HOSTING + path)
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            raise ValueError(f"Hosting deep link is unavailable: {path}")
    response = client.get(HOSTING + "/api/v1/nonexistent-deployment-probe")
    if response.status_code != 404 or "application/json" not in response.headers.get(
        "content-type", ""
    ):
        raise ValueError("The Hosting API rewrite returned a SPA instead of a JSON 404")
    for item in manifest["files"]:
        response = client.get(HOSTING + "/submission/" + item["name"])
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != item["sha256"]:
            raise ValueError(f"Published submission artifact mismatch: {item['name']}")


def firebase_request(session: Any, method: str, path: str, **kwargs: Any) -> dict:
    response = session.request(
        method,
        "https://firebasehosting.googleapis.com/v1beta1/" + path,
        timeout=30,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if not IMAGE_PATTERN.fullmatch(args.image) or not re.fullmatch(
        r"[a-f0-9]{40}", args.commit
    ):
        parser.error(
            "A reviewed repository image digest and full commit SHA are required"
        )

    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    from google.cloud import storage

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    restore_assets(
        manifest, storage.Client(project=PROJECT), ROOT / "frontend/dist/submission"
    )
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    with (
        AuthorizedSession(credentials) as session,
        httpx.Client(timeout=55, follow_redirects=True) as client,
    ):
        current = cli(
            "gcloud",
            "run",
            "services",
            "describe",
            SERVICE,
            f"--region={REGION}",
            as_json=True,
        )
        previous_traffic = {
            entry["revisionName"]: entry["percent"]
            for entry in current["status"]["traffic"]
            if entry.get("percent", 0) > 0
        }
        releases = firebase_request(session, "GET", f"sites/{SITE}/releases?pageSize=1")
        previous_version = releases["releases"][0]["version"]["name"]
        print("Previous production revision and Hosting version captured.", flush=True)

        candidate = cli(
            "gcloud",
            "run",
            "deploy",
            SERVICE,
            f"--region={REGION}",
            f"--image={args.image}",
            "--service-account=regimpact-runtime@regimpact-ai.iam.gserviceaccount.com",
            "--env-vars-file=infra/cloudrun/regimpact-env.yaml",
            "--min-instances=0",
            "--max-instances=2",
            "--cpu=1",
            "--memory=1Gi",
            "--concurrency=8",
            "--timeout=60",
            "--no-traffic",
            "--tag=cd-candidate",
            as_json=True,
        )
        revision = candidate["status"]["latestReadyRevisionName"]
        candidate_url = next(
            entry["url"]
            for entry in candidate["status"]["traffic"]
            if entry.get("tag") == "cd-candidate"
        )
        verify_api(candidate_url, client)
        print(f"Candidate real-store verification passed: {revision}", flush=True)
        promotion_attempted = False
        try:
            # A client failure can occur after the server changed traffic.
            promotion_attempted = True
            cli(
                "gcloud",
                "run",
                "services",
                "update-traffic",
                SERVICE,
                f"--region={REGION}",
                f"--to-revisions={revision}=100",
            )
            cli(
                "firebase",
                "deploy",
                "--only",
                "hosting",
                "--project",
                PROJECT,
                "--config",
                "firebase.json",
                "--non-interactive",
            )
            verify_hosting(manifest, client)
        except Exception:
            if promotion_attempted:
                print(
                    "Publication verification failed; restoring the previous release.",
                    flush=True,
                )
                rollback_errors = []
                try:
                    firebase_request(
                        session,
                        "POST",
                        f"sites/{SITE}/releases",
                        params={"versionName": previous_version},
                        json={"message": f"Automatic rollback of {args.commit[:12]}"},
                    )
                except Exception as exc:
                    rollback_errors.append(type(exc).__name__)
                try:
                    traffic = ",".join(
                        f"{name}={percent}"
                        for name, percent in previous_traffic.items()
                    )
                    cli(
                        "gcloud",
                        "run",
                        "services",
                        "update-traffic",
                        SERVICE,
                        f"--region={REGION}",
                        f"--to-revisions={traffic}",
                    )
                except Exception as exc:
                    rollback_errors.append(type(exc).__name__)
                if rollback_errors:
                    raise RuntimeError(
                        "Automatic rollback requires operator attention"
                    ) from None
            raise
        summary = (
            f"### Verified deployment\n\nCommit: `{args.commit}`\n\n"
            f"Cloud Run revision: `{revision}`\n\n"
            f"Image: `{args.image}`\n\n[Live prototype]({HOSTING}) · "
            f"[Submission artifacts]({HOSTING}/submission/)\n\n"
            "Candidate GCP/Firestore/source/dashboard checks and post-release "
            "Hosting/artifact checks passed. No AI calls or data migrations were run.\n"
        )
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open(
                "a", encoding="utf-8"
            ) as stream:
                stream.write(summary)
        print(
            f"Deployment verified: {revision}; submission assets preserved.", flush=True
        )


if __name__ == "__main__":
    main()
