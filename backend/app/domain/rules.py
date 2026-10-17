"""Conservative, deterministic scenario decisions. No API or SDK imports."""

from .models import (
    AssessmentStatus,
    Classification,
    ReviewMetrics,
    SafetyChecks,
    ScenarioMappingAssessment,
)


def carry_forward_eligible(classification: Classification, checks: SafetyChecks) -> bool:
    return (
        classification == Classification.UNCHANGED
        and not checks.high_confidence_pcs_target
        and not checks.applicable_global_overlay
        and checks.no_effect_result == "NO_EFFECT_SUPPORTED"
        and checks.human_change_confirmed
    )


def review_metrics(
    assessments: tuple[ScenarioMappingAssessment, ...], new_obligations: int
) -> ReviewMetrics:
    existing = len(assessments)
    candidates = sum(a.eligible_for_carry_forward for a in assessments)
    acknowledged = sum(
        a.eligible_for_carry_forward and a.status == AssessmentStatus.SCENARIO_ACKNOWLEDGED
        for a in assessments
    )
    rechecks = existing - candidates
    completed = sum(
        not a.eligible_for_carry_forward
        and a.classification != Classification.UNRESOLVED
        and a.status in {AssessmentStatus.SCENARIO_APPROVED, AssessmentStatus.SCENARIO_REJECTED}
        for a in assessments
    )
    unresolved = sum(a.classification == Classification.UNRESOLVED for a in assessments)
    bulk_actions = int(acknowledged > 0)
    # Candidates save effort only after the required bulk acknowledgement.
    # Unresolved mappings always count toward individual rechecks.
    estimate = max(0.0, (candidates - int(candidates > 0)) / existing * 100) if existing else None
    actual = max(0.0, (acknowledged - bulk_actions) / existing * 100) if acknowledged else None
    return ReviewMetrics(
        existing_mapping_items=existing,
        carry_forward_candidates=candidates,
        acknowledged_mappings=acknowledged,
        individual_rechecks=rechecks,
        completed_rechecks=completed,
        unresolved_items=unresolved,
        bulk_ack_actions=bulk_actions,
        estimated_review_reduction=round(estimate, 1) if estimate is not None else None,
        review_reduction=round(actual, 1) if actual is not None else None,
        carry_forward_rate=round(acknowledged / existing * 100, 1) if existing else None,
        new_obligations=new_obligations,
    )
