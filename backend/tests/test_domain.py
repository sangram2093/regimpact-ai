from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from app.domain.errors import DomainError
from app.domain.models import Classification, SafetyChecks, SeedBundle
from app.domain.rules import carry_forward_eligible, review_metrics
from app.repositories.sessions import SessionRepository
from app.services.grounding import (
    SourceSegment,
    SupportedClaim,
    validate_answer_references,
    validate_candidate_id,
    validate_excerpt,
    validate_supported_claims,
)
from app.services.retrieval import reciprocal_rank_fusion
from app.services.scenarios import ScenarioService


@pytest.mark.parametrize(
    "blocker",
    [
        {"high_confidence_pcs_target": True},
        {"applicable_global_overlay": True},
        {"no_effect_result": "EFFECT_POSSIBLE"},
        {"no_effect_result": "NOT_RUN"},
        {"human_change_confirmed": False},
    ],
)
def test_every_carry_forward_gate_is_required(safe_checks: SafetyChecks, blocker: dict) -> None:
    assert carry_forward_eligible(Classification.UNCHANGED, safe_checks)
    assert not carry_forward_eligible(
        Classification.UNCHANGED, safe_checks.model_copy(update=blocker)
    )


@pytest.mark.parametrize("classification", ["MODIFIED", "NEW", "REMOVED", "UNRESOLVED"])
def test_only_unchanged_can_be_reused(safe_checks: SafetyChecks, classification: str) -> None:
    assert not carry_forward_eligible(Classification(classification), safe_checks)


def test_safe_bulk_acknowledgement_idempotent_and_metrics_consistent(
    synthetic_safe_service: ScenarioService,
) -> None:
    service = synthetic_safe_service
    scenario_id = service.bundle.scenario.id
    baseline = service.bundle.model_dump_json()
    before = service.delta_review(scenario_id, "session-a").metrics
    assert before.existing_mapping_items == 6  # Catalog edges excluded; new obligation separate.
    assert before.carry_forward_candidates == 3
    assert before.individual_rechecks == 3
    assert before.estimated_review_reduction == pytest.approx(33.3)
    assert before.review_reduction is None
    after = service.acknowledge(scenario_id, "session-a", "Synthetic reviewer")
    assert after.metrics.bulk_ack_actions == 1
    assert after.metrics.acknowledged_mappings == 3
    assert after.metrics.review_reduction == pytest.approx(33.3)
    assert after.metrics.carry_forward_rate == 50
    assert service.acknowledge(scenario_id, "session-a", "Duplicate reviewer") == after
    assert service.delta_review(scenario_id, "session-b").metrics.acknowledged_mappings == 0
    assert service.bundle.model_dump_json() == baseline


def test_zero_denominator_never_claims_savings() -> None:
    metrics = review_metrics((), new_obligations=2)
    assert metrics.review_reduction is None
    assert metrics.estimated_review_reduction is None
    assert metrics.carry_forward_rate is None
    assert metrics.new_obligations == 2


def test_one_safe_item_does_not_save_an_action(synthetic_safe_service: ScenarioService) -> None:
    service = synthetic_safe_service
    result = service.acknowledge(service.bundle.scenario.id, "a", "Reviewer")
    reused = tuple(a for a in result.assessments if a.eligible_for_carry_forward)[:1]
    assert review_metrics(reused, 0).review_reduction == 0


def test_seed_is_frozen_and_rejects_invalid_relationships(bundle: SeedBundle) -> None:
    with pytest.raises(ValidationError):
        bundle.edges[0].status = "REJECTED"
    data = bundle.model_dump()
    data["edges"][0]["target_id"] = "RT-CONDUCT"
    with pytest.raises(ValidationError, match="Invalid lineage relationship"):
        SeedBundle.model_validate(data)


def test_seed_rejects_unknown_evidence(bundle: SeedBundle) -> None:
    data = bundle.model_dump()
    data["edges"][0]["evidence_ids"] = ("invented",)
    with pytest.raises(ValidationError, match="Unknown evidence reference"):
        SeedBundle.model_validate(data)


def test_rrf_uses_both_rankings_and_stable_ties() -> None:
    result = reciprocal_rank_fusion(("A", "B", "C"), ("B", "A", "D"))
    assert [candidate.id for candidate in result] == ["A", "B", "C", "D"]
    assert result[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert result[0].vector_rank == 1
    assert result[0].lexical_rank == 2
    assert result[0].rrf_rank == 1
    with pytest.raises(FrozenInstanceError):
        result[0].score = 9


def test_rrf_deduplicates_and_bounds_candidates() -> None:
    result = reciprocal_rank_fusion(("A", "A", "B"), ("B",), limit=1)
    assert len(result) == 1 and result[0].id == "B"
    assert reciprocal_rank_fusion((), ()) == ()
    with pytest.raises(ValueError):
        reciprocal_rank_fusion(("A",), (), k=0)


def test_excerpt_grounding_checks_source_segment_and_exact_text() -> None:
    sources = frozenset({"source-a", "source-b"})
    segments = {
        "seg-a": SourceSegment("seg-a", "source-a", "Gift offers should not unduly influence.")
    }
    assert validate_excerpt(
        "source-a", "seg-a", "not unduly influence", sources=sources, segments=segments
    )
    assert not validate_excerpt(
        "source-b", "seg-a", "not unduly influence", sources=sources, segments=segments
    )
    assert not validate_excerpt("source-a", "missing", "Gift", sources=sources, segments=segments)
    assert not validate_excerpt(
        "source-a", "seg-a", "Binding now", sources=sources, segments=segments
    )
    assert not validate_excerpt("source-a", "seg-a", "", sources=sources, segments=segments)


def test_candidate_selection_cannot_invent_ids() -> None:
    assert validate_candidate_id("PR-1", frozenset({"PR-1"}))
    assert validate_candidate_id(None, frozenset())  # No suitable candidate is valid.
    assert not validate_candidate_id("INVENTED", frozenset({"PR-1"}))


def test_reference_membership_is_not_claim_support() -> None:
    assert validate_answer_references("Proposed [M-1]", frozenset({"M-1"}))
    assert not validate_answer_references("Proposed [M-2]", frozenset({"M-1"}))
    assert not validate_answer_references("No references", frozenset({"M-1"}))
    fact = SupportedClaim("A proposed safeguard", ("M-1",), "PROPOSED")
    false_claim = SupportedClaim("A binding safeguard", ("M-1",), "IN_FORCE")
    assert validate_supported_claims((fact,), (fact,))
    assert not validate_supported_claims((false_claim,), (fact,))
    assert not validate_supported_claims((), (fact,))


def test_sessions_have_bounded_capacity_and_atomic_failed_transactions() -> None:
    sessions = SessionRepository(300, 1)
    sessions.transact("a", lambda state: None)
    with pytest.raises(DomainError, match="capacity"):
        sessions.transact("b", lambda state: None)
    sessions.reset("a")

    def failing(state):
        state.decisions["partial"] = None
        raise ValueError("rollback")

    with pytest.raises(ValueError):
        sessions.transact("b", failing)
    assert sessions.decisions("b") == {}
    sessions.transact("c", lambda state: None)


def test_expired_sessions_are_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.repositories.sessions.monotonic", lambda: 10)
    sessions = SessionRepository(60, 1)
    sessions.transact("a", lambda state: None)
    monkeypatch.setattr("app.repositories.sessions.monotonic", lambda: 71)
    sessions.transact("b", lambda state: None)
    assert sessions.decisions("a") == {}


def test_known_pcs_target_overrides_incorrect_no_effect_flags(
    synthetic_safe_service: ScenarioService, safe_checks: SafetyChecks
) -> None:
    service = synthetic_safe_service
    gift = service.by_mandate["M-GIFT"]
    service.by_mandate["M-GIFT"] = gift.model_copy(
        update={
            "classification": Classification.UNCHANGED,
            "safety_checks": safe_checks,
        }
    )
    # The real gift PCS still targets this mandate in repository data.
    gift_assessments = [a for a in service.assessments(None) if a.mandate_id == "M-GIFT"]
    assert gift_assessments
    assert all(not a.eligible_for_carry_forward for a in gift_assessments)
