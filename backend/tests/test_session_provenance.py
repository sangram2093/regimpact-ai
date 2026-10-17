from types import SimpleNamespace

import pytest

from app.api.workbench import save_run
from app.domain.reviews import PolicyMappingReview
from app.repositories.sessions import SessionRepository, SessionState


def test_snapshot_and_failed_transaction_cannot_mutate_stored_run_provenance():
    sessions = SessionRepository(60, 10)

    def initial(state: SessionState):
        state.runs["RUN"] = {"output": {"candidate_ids": ["ORIGINAL"]}}

    sessions.transact("session", initial)
    snapshot = sessions.snapshot("session")
    snapshot.runs["RUN"]["output"]["candidate_ids"].append("FROM_SNAPSHOT")

    def failing(state: SessionState):
        state.runs["RUN"]["output"]["candidate_ids"].append("FAILED_WRITE")
        raise ValueError("rollback")

    with pytest.raises(ValueError):
        sessions.transact("session", failing)
    assert sessions.snapshot("session").runs == {"RUN": {"output": {"candidate_ids": ["ORIGINAL"]}}}


def test_history_bound_never_evicts_approved_mapping_provenance():
    sessions = SessionRepository(60, 10)

    def populate(state: SessionState):
        state.mappings["M-GIFT"] = PolicyMappingReview(
            mandate_id="M-GIFT",
            policy_id="PR-GIFT-01",
            decision="APPROVE",
            reviewer="Owner",
            role="Policy Owner",
            rationale="Reviewed prospective scope.",
            reviewed_at="2026-10-17T00:00:00Z",
            candidate_ids=("PR-GIFT-01",),
            retrieval_run_id="RUN-0",
        )
        for i in range(100):
            state.runs[f"RUN-{i}"] = {
                "run": {"id": f"RUN-{i}", "workflow": "policy-map", "status": "SUCCEEDED"},
                "output": {"provenance": i},
            }

    sessions.transact("session", populate)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(sessions=sessions)),
        state=SimpleNamespace(request_id="test-request"),
    )
    save_run(
        request, "session", {"run": {"id": "NEW", "workflow": "interpret", "status": "BLOCKED"}}
    )
    state = sessions.snapshot("session")
    assert len(state.runs) == 100
    assert state.runs["RUN-0"]["output"] == {"provenance": 0}
    assert "RUN-1" not in state.runs
    assert "NEW" in state.runs
