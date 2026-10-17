"""Explicit Cloud Build release command used only by the deployment job."""

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "regimpact-ai"


def gcloud(*args: str) -> dict:
    result = subprocess.run(
        ["gcloud", *args, f"--project={PROJECT}", "--format=json", "--quiet"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        parser.error("A full commit SHA is required")
    tag = f"{args.commit}-{os.environ.get('GITHUB_RUN_ID', 'manual')}"
    build = gcloud(
        "builds",
        "submit",
        ".",
        "--config=infra/cloudbuild/cloudbuild.yaml",
        "--gcs-source-staging-dir=gs://regimpact-ai-builds-61760046387/source",
        "--service-account=projects/regimpact-ai/serviceAccounts/"
        "regimpact-builder@regimpact-ai.iam.gserviceaccount.com",
        f"--substitutions=_TAG={tag}",
        "--async",
    )
    identifier = build["id"]
    print(f"Cloud Build: {identifier}", flush=True)
    deadline = time.monotonic() + 1250
    previous = None
    while time.monotonic() < deadline:
        build = gcloud("builds", "describe", identifier)
        status = build["status"]
        if status != previous:
            print(f"Build status: {status}", flush=True)
            previous = status
        if status == "SUCCESS":
            digest = build["results"]["images"][0]["digest"]
            image = (
                f"asia-south1-docker.pkg.dev/{PROJECT}/regimpact/regimpact-api@{digest}"
            )
            output = os.environ.get("GITHUB_OUTPUT")
            if output:
                with Path(output).open("a", encoding="utf-8") as stream:
                    stream.write(f"image={image}\nbuild_id={identifier}\n")
            print(f"Verified image: {image}", flush=True)
            return
        if status not in {"QUEUED", "WORKING", "PENDING"}:
            raise RuntimeError(f"Cloud Build {identifier} ended with {status}")
        time.sleep(10)
    raise TimeoutError(f"Cloud Build {identifier} exceeded the release deadline")


if __name__ == "__main__":
    main()
