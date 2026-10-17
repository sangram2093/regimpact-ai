"""Bound costly operations globally; demo reset never resets the budget."""

from threading import Lock
from time import time
from typing import Any

from app.domain.errors import DomainError
from app.repositories.sessions import SessionBackend

QUOTA_SESSION = "00000000-0000-0000-0000-000000000000"


class OperationLimiter:
    def __init__(
        self, per_minute: int, per_day: int, backend: SessionBackend | None = None
    ) -> None:
        self.per_minute, self.per_day, self.backend = per_minute, per_day, backend
        self._lock = Lock()
        self._state: dict[str, Any] = {}

    def acquire(self) -> None:
        def reserve(state: dict[str, Any]) -> None:
            minute, day = int(time() // 60), int(time() // 86400)
            if state.get("minute") != minute:
                state.update(minute=minute, minute_calls=0)
            if state.get("day") != day:
                state.update(day=day, day_calls=0)
            if state["minute_calls"] >= self.per_minute or state["day_calls"] >= self.per_day:
                raise DomainError(
                    "AI_RATE_LIMIT",
                    (
                        "The shared AI request budget is exhausted. Try again after the "
                        "current limit resets."
                    ),
                    429,
                )
            state["minute_calls"] += 1
            state["day_calls"] += 1

        if self.backend:
            self.backend.atomic(QUOTA_SESSION, reserve)
        else:
            with self._lock:
                reserve(self._state)
