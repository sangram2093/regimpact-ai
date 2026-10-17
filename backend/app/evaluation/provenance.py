"""Git and SHA-256 provenance gates, with explicit limits of human attestations."""

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.evaluation.models import FreezeManifest, LabelSet, PredictionSet


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("Git provenance verification failed: " + result.stderr.decode().strip())
    return result.stdout


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Evaluation artifacts must be inside the selected repository") from exc


def _human_labels(labels: LabelSet) -> None:
    provenance = labels.provenance
    if provenance.origin != "HUMAN_INDEPENDENT" or labels.split not in {"dev", "test"}:
        raise ValueError("Blind evaluation requires independent human labels in a dev/test split")
    if not provenance.annotator or not provenance.annotator.strip():
        raise ValueError("A human annotator identity must be recorded")
    if not provenance.labeled_at or not provenance.independent_of_predictions:
        raise ValueError("Human label timestamp and independence attestation are required")


def freeze_labels(root: Path, labels_path: Path) -> FreezeManifest:
    content = labels_path.read_bytes()
    labels = LabelSet.model_validate_json(content)
    _human_labels(labels)
    relative = _relative(root, labels_path)
    committed = _git(root, "show", f"HEAD:{relative}")
    if sha256(committed) != sha256(content):
        raise ValueError("Commit the reviewed label file unchanged before freezing it")
    label_commit = _git(root, "log", "-1", "--format=%H", "--", relative).decode().strip()
    now = datetime.now(UTC)
    if labels.provenance.labeled_at and labels.provenance.labeled_at > now:
        raise ValueError("Human labeling timestamp cannot be in the future")
    return FreezeManifest(
        dataset_id=labels.dataset_id,
        split=labels.split,
        labels_path=relative,
        labels_sha256=sha256(content),
        labels_commit=label_commit,
        frozen_at=now,
        case_count=len(labels.cases),
    )


def verify_blind_run(
    root: Path, manifest_path: Path, predictions_path: Path
) -> tuple[LabelSet, PredictionSet, dict[str, Any]]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = FreezeManifest.model_validate_json(manifest_bytes)
    prediction_bytes = predictions_path.read_bytes()
    predictions = PredictionSet.model_validate_json(prediction_bytes)
    labels_path = root / manifest.labels_path
    _relative(root, labels_path)
    labels_bytes = labels_path.read_bytes()
    if sha256(labels_bytes) != manifest.labels_sha256:
        raise ValueError("Frozen labels changed after the manifest was created")
    labels = LabelSet.model_validate_json(labels_bytes)
    _human_labels(labels)
    if (labels.dataset_id, labels.split, len(labels.cases)) != (
        manifest.dataset_id,
        manifest.split,
        manifest.case_count,
    ):
        raise ValueError("Freeze manifest does not describe this label set")
    if predictions.execution_mode != "LIVE_AI" or not predictions.model:
        raise ValueError("Blind model evaluation requires a recorded live model run")
    if predictions.labels_manifest_sha256 != sha256(manifest_bytes):
        raise ValueError("Run did not pin this exact frozen manifest before prediction")
    commit = predictions.started_from_commit or ""
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Run start requires a full Git commit hash")
    _git(root, "merge-base", "--is-ancestor", manifest.labels_commit, commit)
    labeled_snapshot = _git(root, "show", f"{manifest.labels_commit}:{manifest.labels_path}")
    if sha256(labeled_snapshot) != manifest.labels_sha256:
        raise ValueError("Recorded label commit does not contain the frozen labels")
    manifest_relative = _relative(root, manifest_path)
    snapshot = _git(root, "show", f"{commit}:{manifest_relative}")
    if sha256(snapshot) != sha256(manifest_bytes):
        raise ValueError("Freeze manifest was not committed before this prediction run")
    frozen_labels = _git(root, "show", f"{commit}:{manifest.labels_path}")
    if sha256(frozen_labels) != manifest.labels_sha256:
        raise ValueError("Run-start commit contained different labels")
    commit_time = datetime.fromtimestamp(
        int(_git(root, "show", "-s", "--format=%ct", commit).strip()), UTC
    )
    if manifest.frozen_at > predictions.started_at or commit_time > predictions.started_at:
        raise ValueError("Recorded prediction time precedes committed label freeze")
    if labels.provenance.labeled_at and labels.provenance.labeled_at > manifest.frozen_at:
        raise ValueError("Labels were recorded after their freeze")
    if predictions.completed_at > datetime.now(UTC):
        raise ValueError("Recorded prediction completion cannot be in the future")
    return (
        labels,
        predictions,
        {
            "status": "HUMAN_LABELED_MODEL_EVALUATION",
            "labels_sha256": manifest.labels_sha256,
            "labels_commit": manifest.labels_commit,
            "manifest_sha256": sha256(manifest_bytes),
            "predictions_sha256": sha256(prediction_bytes),
            "run_start_commit": commit,
            "annotator": labels.provenance.annotator,
            "frozen_at": manifest.frozen_at.isoformat(),
            "independence_limit": "Git/timestamps verify recorded provenance; human independence "
            "and honest run capture remain reviewer attestations.",
            "split_caveat": "Dev results are tuning diagnostics, not held-out test performance."
            if labels.split == "dev"
            else "Do not tune against this frozen test split.",
        },
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
