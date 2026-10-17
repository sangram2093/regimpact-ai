"""Counts from immutable labels; empty denominators are unavailable, not perfect."""

import re
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import ValidationError

from app.evaluation.models import (
    AskTrace,
    EvaluationOutput,
    Fact,
    GoldCase,
    LabelSet,
    PredictionSet,
)


@dataclass
class Metric:
    numerator: int = 0
    denominator: int = 0

    def result(self) -> dict[str, int | float | None]:
        return {
            **asdict(self),
            "rate": self.numerator / self.denominator if self.denominator else None,
        }


def _fact_key(fact: Fact) -> tuple[str, tuple[str, ...], str]:
    return fact.text, tuple(sorted(fact.entity_ids)), fact.legal_status


def ask_is_grounded(trace: AskTrace | None, gold: GoldCase) -> bool:
    """Conservative exact-fact support, same-run membership and complete-answer checking.

    Tool logs alone are not a support oracle: each claim must also match a human
    supported fact frozen with the evaluation case. No semantic judge is inferred.
    """
    if trace is None or not trace.claims:
        return False
    allowed = {_fact_key(fact) for fact in gold.ask_allowed_facts}
    same_run = {
        _fact_key(fact)
        for result in trace.tool_results
        if result.run_id == trace.run_id
        for fact in result.facts
    }
    if any(_fact_key(claim) not in allowed & same_run for claim in trace.claims):
        return False
    expected = "\n".join(
        claim.text + " " + " ".join(f"[{entity_id}]" for entity_id in claim.entity_ids)
        for claim in trace.claims
    )
    # Reject added uncited prose or legal-force changes, even with valid referenced IDs.
    return re.sub(r"\s+", " ", trace.answer).strip() == re.sub(r"\s+", " ", expected).strip()


def score_predictions(labels: LabelSet, predictions: PredictionSet) -> dict[str, Any]:
    """Compute metrics only. Provenance validation is mandatory in the public CLI."""
    if labels.dataset_id != predictions.dataset_id:
        raise ValueError("Predictions target a different dataset")
    expected_ids = {case.id for case in labels.cases}
    by_id = {case.id: case for case in predictions.cases}
    if set(by_id) != expected_ids:
        raise ValueError(
            "Predictions must contain every frozen case exactly once; no cherry-picking"
        )
    metrics = {
        name: Metric()
        for name in (
            "mandate_recall",
            "mandate_precision",
            "evidence_validity",
            "schema_validity",
            "mapping_top1",
            "mapping_top3",
            "mapping_abstention_accuracy",
            "change_recall",
            "change_classification",
            "false_carry_forward",
            "ask_grounding",
        )
    }
    errors: list[dict[str, Any]] = []
    for gold in labels.cases:
        raw = by_id[gold.id].raw_output
        metrics["schema_validity"].denominator += 1
        try:
            output = (
                EvaluationOutput.model_validate_json(raw)
                if isinstance(raw, str)
                else EvaluationOutput.model_validate(raw)
            )
            metrics["schema_validity"].numerator += 1
        except (ValidationError, ValueError) as exc:
            errors.append({"case_id": gold.id, "error": str(exc)})
            output = EvaluationOutput(
                mandate_ids=[], evidence=[], mapping_candidates={}, changes={}, carry_forward_ids=[]
            )
        mandates = set(output.mandate_ids)
        overlap = len(mandates & set(gold.expected_mandate_ids))
        metrics["mandate_recall"].numerator += overlap
        metrics["mandate_recall"].denominator += len(gold.expected_mandate_ids)
        metrics["mandate_precision"].numerator += overlap
        metrics["mandate_precision"].denominator += len(mandates)
        segments = {segment.id: segment for segment in gold.source_segments}
        for evidence in output.evidence:
            segment = segments.get(evidence.segment_id)
            valid = bool(
                segment
                and segment.source_id == evidence.source_id
                and evidence.excerpt.strip()
                and evidence.excerpt in segment.text
            )
            metrics["evidence_validity"].denominator += 1
            metrics["evidence_validity"].numerator += int(valid)
        for mandate_id, accepted in gold.acceptable_policy_ids.items():
            candidates = output.mapping_candidates.get(mandate_id, [])
            if accepted:
                for name, limit in (("mapping_top1", 1), ("mapping_top3", 3)):
                    metrics[name].denominator += 1
                    metrics[name].numerator += int(bool(set(candidates[:limit]) & set(accepted)))
            else:
                metrics["mapping_abstention_accuracy"].denominator += 1
                # Missing results are not counted as a correct, explicit abstention.
                metrics["mapping_abstention_accuracy"].numerator += int(
                    mandate_id in output.mapping_candidates and not candidates
                )
        for mandate_id, classification in gold.expected_changes.items():
            predicted = output.changes.get(mandate_id)
            metrics["change_classification"].denominator += 1
            metrics["change_classification"].numerator += int(predicted == classification)
            if classification in {"MODIFIED", "NEW", "REMOVED"}:
                metrics["change_recall"].denominator += 1
                metrics["change_recall"].numerator += int(
                    predicted in {"MODIFIED", "NEW", "REMOVED"}
                )
        for mandate_id in output.carry_forward_ids:
            metrics["false_carry_forward"].denominator += 1
            metrics["false_carry_forward"].numerator += int(
                not gold.carry_forward_allowed.get(mandate_id, False)
            )
        if gold.evaluate_ask:
            metrics["ask_grounding"].denominator += 1
            metrics["ask_grounding"].numerator += int(ask_is_grounded(output.ask, gold))
    return {
        "dataset_id": labels.dataset_id,
        "split": labels.split,
        "run_id": predictions.run_id,
        "case_count": len(labels.cases),
        "model": predictions.model,
        "execution_mode": predictions.execution_mode,
        "metrics": {name: metric.result() for name, metric in metrics.items()},
        "schema_errors": errors,
        "limitations": [
            "Rates use micro-aggregated raw counts; null rates have zero denominator.",
            "Schema validity measures the normalized evaluation export, not semantic correctness.",
            "Evidence validity measures exact nonempty substrings in frozen source segments.",
            "Mandate IDs require independent human alignment before normalized prediction export.",
            "Ask support is conservative exact-fact support, not general semantic entailment.",
            "Zero false carry-forward with zero proposed reuse does not demonstrate safe reuse.",
        ],
    }
