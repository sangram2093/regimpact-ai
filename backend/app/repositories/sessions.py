from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from time import monotonic
from typing import Any, Protocol, TypeVar

from app.domain.errors import DomainError
from app.domain.models import ReviewDecision
from app.domain.reviews import ChangeReview, PolicyMappingReview
from app.domain.workflow_review import ImpactReviewDecision, WorkflowReviewDecision

T = TypeVar("T")


@dataclass
class SessionState:
    touched_at: float
    decisions: dict[str, ReviewDecision] = field(default_factory=dict)
    classifications: dict[str, ChangeReview] = field(default_factory=dict)
    mappings: dict[str, PolicyMappingReview] = field(default_factory=dict)
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    workflow_reviews: dict[str, WorkflowReviewDecision] = field(default_factory=dict)
    impact_reviews: dict[str, ImpactReviewDecision] = field(default_factory=dict)

    def serialize(self) -> dict[str, Any]:
        return {
            "decisions": {k: v.model_dump(mode="json") for k, v in self.decisions.items()},
            "classifications": {
                k: v.model_dump(mode="json") for k, v in self.classifications.items()
            },
            "mappings": {k: v.model_dump(mode="json") for k, v in self.mappings.items()},
            "runs": deepcopy(self.runs),
            "workflow_reviews": {
                k: deepcopy(v.model_dump(mode="json")) for k, v in self.workflow_reviews.items()
            },
            "impact_reviews": {
                k: deepcopy(v.model_dump(mode="json")) for k, v in self.impact_reviews.items()
            },
        }

    @classmethod
    def deserialize(cls, value: dict[str, Any]) -> "SessionState":
        return cls(
            touched_at=monotonic(),
            decisions={
                k: ReviewDecision.model_validate(v) for k, v in value.get("decisions", {}).items()
            },
            classifications={
                k: ChangeReview.model_validate(v)
                for k, v in value.get("classifications", {}).items()
            },
            mappings={
                k: PolicyMappingReview.model_validate(v)
                for k, v in value.get("mappings", {}).items()
            },
            runs=deepcopy(value.get("runs", {})),
            workflow_reviews={
                k: WorkflowReviewDecision.model_validate(deepcopy(v))
                for k, v in value.get("workflow_reviews", {}).items()
            },
            impact_reviews={
                k: ImpactReviewDecision.model_validate(deepcopy(v))
                for k, v in value.get("impact_reviews", {}).items()
            },
        )


class SessionBackend(Protocol):
    def load(self, session_id: str) -> dict[str, Any]: ...
    def atomic(self, session_id: str, operation: Callable[[dict[str, Any]], T]) -> T: ...
    def reset(self, session_id: str) -> None: ...


class SessionRepository:
    """Copy-on-write decisions with optional durable atomic backend storage.

    Baseline views do not allocate sessions. Without a backend, a process restart
    clears demo state. Session UUIDs isolate demos; they are not authenticated identity.
    """

    def __init__(
        self, ttl_seconds: int, max_sessions: int, backend: SessionBackend | None = None
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_sessions = max_sessions
        self._states: dict[str, SessionState] = {}
        self._lock = RLock()
        self._backend = backend

    def _expire(self) -> None:
        expired = [
            key
            for key, state in self._states.items()
            if monotonic() - state.touched_at > self._ttl_seconds
        ]
        for key in expired:
            del self._states[key]

    def decisions(self, session_id: str | None) -> dict[str, ReviewDecision]:
        return self.snapshot(session_id).decisions

    def snapshot(self, session_id: str | None) -> SessionState:
        if self._backend:
            return SessionState.deserialize(self._backend.load(session_id) if session_id else {})
        with self._lock:
            self._expire()
            state = self._states.get(session_id) if session_id else None
            if state:
                state.touched_at = monotonic()
                return SessionState.deserialize(state.serialize())
            return SessionState(touched_at=monotonic())

    def transact(self, session_id: str, operation: Callable[[SessionState], T]) -> T:
        if self._backend:

            def apply(payload: dict[str, Any]) -> T:
                state = SessionState.deserialize(payload)
                result = operation(state)
                payload.clear()
                payload.update(state.serialize())
                return result

            return self._backend.atomic(session_id, apply)
        with self._lock:
            self._expire()
            state = self._states.get(session_id)
            if state is None:
                if len(self._states) >= self._max_sessions:
                    raise DomainError(
                        "DEMO_CAPACITY_REACHED",
                        "Demo session capacity reached. Try again later.",
                        503,
                    )
                state = SessionState(touched_at=monotonic())
            # Commit only after a successful operation; failed writes cannot leave partial state.
            working = SessionState.deserialize(state.serialize())
            result = operation(working)
            self._states[session_id] = working
            return result

    def reset(self, session_id: str) -> None:
        if self._backend:
            self._backend.reset(session_id)
            return
        with self._lock:
            self._states.pop(session_id, None)
