"""Freeze independent labels or score a pinned run without fabricating blind results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--repo", type=Path, default=ROOT)
    actions = cli.add_subparsers(dest="action", required=True)
    freeze = actions.add_parser("freeze", help="Require human labels already committed to Git")
    freeze.add_argument("--labels", type=Path, required=True)
    freeze.add_argument("--manifest", type=Path, required=True)
    score = actions.add_parser(
        "score", help="Validate pre-run committed freeze and score live output"
    )
    score.add_argument("--manifest", type=Path, required=True)
    score.add_argument("--predictions", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    software = actions.add_parser(
        "software-test", help="Explicitly non-blind synthetic fixture run"
    )
    software.add_argument("--labels", type=Path, required=True)
    software.add_argument("--predictions", type=Path, required=True)
    software.add_argument("--output", type=Path, required=True)
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    # Support the repository CLI before an editable backend installation exists.
    sys.path.insert(0, str(ROOT / "backend"))
    from app.evaluation.models import LabelSet, PredictionSet
    from app.evaluation.provenance import freeze_labels, sha256, verify_blind_run, write_json
    from app.evaluation.reporting import render_markdown
    from app.evaluation.scoring import score_predictions

    try:
        if args.action == "freeze":
            if args.manifest.exists():
                raise ValueError("Freeze manifests are immutable; choose a new versioned path")
            manifest = freeze_labels(args.repo, args.labels)
            write_json(args.manifest, manifest.model_dump(mode="json"))
            print(f"Frozen labels: {manifest.labels_sha256}")
            print("Commit the manifest before starting predictions; pin its SHA-256 in the run.")
            return 0
        if args.action == "score":
            labels, predictions, provenance = verify_blind_run(
                args.repo, args.manifest, args.predictions
            )
        else:
            label_bytes = args.labels.read_bytes()
            prediction_bytes = args.predictions.read_bytes()
            labels = LabelSet.model_validate_json(label_bytes)
            predictions = PredictionSet.model_validate_json(prediction_bytes)
            if (
                labels.provenance.origin != "SYNTHETIC_SOFTWARE_TEST"
                or labels.split != "software-test"
                or predictions.execution_mode != "SYNTHETIC_SOFTWARE_TEST"
            ):
                raise ValueError("Software-test mode requires explicit synthetic-only provenance")
            provenance = {
                "status": "SOFTWARE_TEST_ONLY",
                "labels_sha256": sha256(label_bytes),
                "predictions_sha256": sha256(prediction_bytes),
                "warning": "Synthetic invariants are not blind model evaluation.",
            }
        report = score_predictions(labels, predictions)
        report["provenance"] = provenance
        args.output.mkdir(parents=True, exist_ok=True)
        json_path = args.output / "metrics.json"
        markdown_path = args.output / "report.md"
        if json_path.exists() or markdown_path.exists():
            raise ValueError("Reports are immutable; choose a new output directory")
        write_json(json_path, report)
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"{provenance['status']}: {json_path}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Evaluation refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
