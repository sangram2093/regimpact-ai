"""Synthetic software checks only; no test here claims blind model accuracy."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.evaluation.models import GoldCase, LabelSet, PredictionSet
from app.evaluation.provenance import freeze_labels, sha256, verify_blind_run, write_json
from app.evaluation.reporting import render_markdown
from app.evaluation.scoring import ask_is_grounded, score_predictions


def labels_payload(origin: str = "SYNTHETIC_SOFTWARE_TEST") -> dict:
    return {
        "dataset_id": "synthetic-scoring-test",
        "split": "software-test",
        "provenance": {
            "origin": origin,
            "annotator": "Synthetic test author",
            "labeled_at": "2026-01-01T00:00:00Z",
            "independent_of_predictions": False,
            "notes": "Software fixture only; not a regulatory label.",
        },
        "cases": [
            {
                "id": "CASE-1",
                "input_reference": "synthetic fixture",
                "expected_mandate_ids": ["M-A", "M-B"],
                "acceptable_policy_ids": {"M-A": ["P-A"], "M-B": ["P-B"], "M-C": []},
                "expected_changes": {"M-A": "MODIFIED", "M-B": "NEW", "M-C": "UNCHANGED"},
                "carry_forward_allowed": {"M-A": False, "M-C": True},
                "source_segments": [
                    {
                        "id": "S-1",
                        "source_id": "DOC-1",
                        "text": "Synthetic source sentence about gift review.",
                        "artifact_sha256": "a" * 64,
                    }
                ],
                "evaluate_ask": True,
                "ask_allowed_facts": [
                    {"text": "This is proposed.", "entity_ids": ["M-A"], "legal_status": "PROPOSED"}
                ],
            }
        ],
    }


def output_payload() -> dict:
    fact = {"text": "This is proposed.", "entity_ids": ["M-A"], "legal_status": "PROPOSED"}
    return {
        "mandate_ids": ["M-A"],
        "evidence": [
            {"source_id": "DOC-1", "segment_id": "S-1", "excerpt": "gift review"},
            {"source_id": "DOC-1", "segment_id": "S-1", "excerpt": "invented excerpt"},
        ],
        "mapping_candidates": {"M-A": ["P-A"], "M-B": ["P-X", "P-B"], "M-C": []},
        "changes": {"M-A": "MODIFIED", "M-B": "MODIFIED", "M-C": "UNCHANGED"},
        "carry_forward_ids": ["M-A", "M-C"],
        "ask": {
            "run_id": "ASK-1",
            "answer": "This is proposed. [M-A]",
            "tool_results": [{"run_id": "ASK-1", "tool": "get_lineage", "facts": [fact]}],
            "claims": [fact],
        },
    }


def predictions_payload(output: dict | str | None = None) -> dict:
    now = datetime.now(UTC)
    return {
        "dataset_id": "synthetic-scoring-test",
        "run_id": "SOFTWARE-TEST-1",
        "execution_mode": "SYNTHETIC_SOFTWARE_TEST",
        "model": None,
        "started_at": now.isoformat(),
        "completed_at": now.isoformat(),
        "started_from_commit": None,
        "labels_manifest_sha256": None,
        "cases": [
            {"id": "CASE-1", "raw_output": output if output is not None else output_payload()}
        ],
    }


def test_raw_numerators_and_denominators_are_independently_computed() -> None:
    report = score_predictions(
        LabelSet.model_validate(labels_payload()),
        PredictionSet.model_validate(predictions_payload()),
    )
    counts = {
        name: (value["numerator"], value["denominator"])
        for name, value in report["metrics"].items()
    }
    assert counts == {
        "mandate_recall": (1, 2),
        "mandate_precision": (1, 1),
        "evidence_validity": (1, 2),
        "schema_validity": (1, 1),
        "mapping_top1": (1, 2),
        "mapping_top3": (2, 2),
        "mapping_abstention_accuracy": (1, 1),
        "change_recall": (2, 2),
        "change_classification": (2, 3),
        "false_carry_forward": (1, 2),
        "ask_grounding": (1, 1),
    }


def test_invalid_schema_still_counts_all_expected_cases_without_perfect_empty_rates() -> None:
    report = score_predictions(
        LabelSet.model_validate(labels_payload()),
        PredictionSet.model_validate(predictions_payload("not JSON")),
    )
    assert report["metrics"]["schema_validity"]["rate"] == 0
    assert report["metrics"]["mandate_recall"]["denominator"] == 2
    assert report["metrics"]["false_carry_forward"]["rate"] is None
    assert report["metrics"]["evidence_validity"]["rate"] is None
    assert report["schema_errors"][0]["case_id"] == "CASE-1"


@pytest.mark.parametrize(
    "tamper", ["cross_run", "unsupported_text", "wrong_legal_force", "extra_prose"]
)
def test_ask_rejects_membership_only_and_cross_run_grounding(tamper: str) -> None:
    from app.evaluation.models import AskTrace

    output = output_payload()["ask"]
    if tamper == "cross_run":
        output["tool_results"][0]["run_id"] = "OTHER-RUN"
    elif tamper == "unsupported_text":
        output["claims"][0] = {**output["claims"][0], "text": "This is now mandatory."}
        output["answer"] = "This is now mandatory. [M-A]"
    elif tamper == "wrong_legal_force":
        output["claims"][0] = {**output["claims"][0], "legal_status": "BASELINE_GUIDANCE"}
    else:
        output["answer"] += " All controls must change immediately."
    gold = GoldCase.model_validate(labels_payload()["cases"][0])
    assert not ask_is_grounded(AskTrace.model_validate(output), gold)


def test_unknown_carry_forward_id_is_an_error_not_ignored() -> None:
    output = output_payload()
    output["carry_forward_ids"] = ["HALLUCINATED-MANDATE"]
    report = score_predictions(
        LabelSet.model_validate(labels_payload()),
        PredictionSet.model_validate(predictions_payload(output)),
    )
    assert report["metrics"]["false_carry_forward"] == {
        "numerator": 1,
        "denominator": 1,
        "rate": 1,
    }


def test_missing_prediction_case_is_refused() -> None:
    predictions = predictions_payload()
    predictions["cases"][0]["id"] = "CHERRY-PICKED"
    with pytest.raises(ValueError, match="every frozen case"):
        score_predictions(
            LabelSet.model_validate(labels_payload()), PredictionSet.model_validate(predictions)
        )


def git(root: Path, *args: str) -> str:
    return (
        subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL)
        .decode()
        .strip()
    )


def commit_file(root: Path, path: str, message: str) -> str:
    git(root, "add", "--", path)
    git(
        root,
        "-c",
        "user.name=Evaluation Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        message,
    )
    return git(root, "rev-parse", "HEAD")


def setup_frozen_repo(root: Path) -> tuple[Path, Path, Path]:
    git(root, "init")
    # Human origin here is deliberately simulated only inside an isolated temporary test repo.
    labels = labels_payload("HUMAN_INDEPENDENT")
    labels["split"] = "test"
    labels["provenance"]["independent_of_predictions"] = True
    labels_path = root / "labels.json"
    write_json(labels_path, labels)
    commit_file(root, "labels.json", "test: labels fixture")
    manifest_path = root / "freeze.json"
    manifest = freeze_labels(root, labels_path)
    write_json(manifest_path, manifest.model_dump(mode="json"))
    commit = commit_file(root, "freeze.json", "test: freeze fixture")
    predictions = predictions_payload()
    predictions.update(
        execution_mode="LIVE_AI",
        model="synthetic-test-model",
        started_from_commit=commit,
        labels_manifest_sha256=sha256(manifest_path.read_bytes()),
    )
    predictions_path = root / "predictions.json"
    write_json(predictions_path, predictions)
    return labels_path, manifest_path, predictions_path


def test_valid_recorded_commit_order_and_hashes_are_verified(tmp_path: Path) -> None:
    _, manifest_path, predictions_path = setup_frozen_repo(tmp_path)
    labels, predictions, provenance = verify_blind_run(tmp_path, manifest_path, predictions_path)
    assert labels.split == "test"
    assert predictions.model == "synthetic-test-model"
    assert len(provenance["predictions_sha256"]) == 64


@pytest.mark.parametrize("origin", ["UNLABELED", "MODEL_GENERATED", "SYNTHETIC_SOFTWARE_TEST"])
def test_nonhuman_labels_cannot_be_frozen(tmp_path: Path, origin: str) -> None:
    path = tmp_path / "labels.json"
    write_json(path, labels_payload(origin))
    with pytest.raises(ValueError, match="independent human labels"):
        freeze_labels(tmp_path, path)


def test_changed_label_content_is_refused(tmp_path: Path) -> None:
    labels_path, manifest_path, predictions_path = setup_frozen_repo(tmp_path)
    labels_path.write_text(labels_path.read_text() + " ")
    with pytest.raises(ValueError, match="Frozen labels changed"):
        verify_blind_run(tmp_path, manifest_path, predictions_path)


def test_run_before_freeze_and_uncommitted_manifest_are_refused(tmp_path: Path) -> None:
    _, manifest_path, predictions_path = setup_frozen_repo(tmp_path)
    predictions = json.loads(predictions_path.read_text())
    predictions["started_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    write_json(predictions_path, predictions)
    with pytest.raises(ValueError, match="precedes committed label freeze"):
        verify_blind_run(tmp_path, manifest_path, predictions_path)
    predictions["started_at"] = datetime.now(UTC).isoformat()
    predictions["completed_at"] = datetime.now(UTC).isoformat()
    manifest = json.loads(manifest_path.read_text())
    manifest["frozen_at"] = datetime.now(UTC).isoformat()
    write_json(manifest_path, manifest)
    predictions["labels_manifest_sha256"] = sha256(manifest_path.read_bytes())
    write_json(predictions_path, predictions)
    with pytest.raises(ValueError, match="not committed before"):
        verify_blind_run(tmp_path, manifest_path, predictions_path)


def test_report_labels_software_fixtures_without_blind_accuracy_claim() -> None:
    report = score_predictions(
        LabelSet.model_validate(labels_payload()),
        PredictionSet.model_validate(predictions_payload()),
    )
    report["provenance"] = {"status": "SOFTWARE_TEST_ONLY"}
    markdown = render_markdown(report)
    assert "not blind model accuracy" in markdown
    assert "| false_carry_forward | 1 | 2 | 50.00% |" in markdown


def test_local_runs_cannot_be_reported_as_blind_model_evaluation(tmp_path: Path) -> None:
    _, manifest_path, predictions_path = setup_frozen_repo(tmp_path)
    predictions = json.loads(predictions_path.read_text())
    predictions["execution_mode"] = "LOCAL_DETERMINISTIC"
    write_json(predictions_path, predictions)
    with pytest.raises(ValueError, match="recorded live model run"):
        verify_blind_run(tmp_path, manifest_path, predictions_path)


def test_software_cli_produces_explicit_nonblind_report_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    labels_path = tmp_path / "labels.json"
    predictions_path = tmp_path / "predictions.json"
    output_path = tmp_path / "report"
    write_json(labels_path, labels_payload())
    write_json(predictions_path, predictions_payload())
    command = [
        sys.executable,
        str(root / "scripts" / "evaluate.py"),
        "software-test",
        "--labels",
        str(labels_path),
        "--predictions",
        str(predictions_path),
        "--output",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads((output_path / "metrics.json").read_text())
    assert report["provenance"]["status"] == "SOFTWARE_TEST_ONLY"
    repeated = subprocess.run(command, capture_output=True, text=True, check=False)
    assert repeated.returncode == 2
    assert "Reports are immutable" in repeated.stderr
