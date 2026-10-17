"""Serializable, bounded demo-session persistence; never updates baseline tables."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from app.adapters.gcp.common import json_value, spanner_json, sql_types
from app.adapters.gcp.timeouts import TRANSACTION_RETRY_SECONDS, bounded_operation, rpc_options
from app.domain.errors import DomainError

T = TypeVar("T")
QUOTA_SESSION_ID = "00000000-0000-0000-0000-000000000000"
# Spanner JSON values are limited to 10 MB. Leave room for encoding and provider
# accounting rather than accepting a record which the database cannot commit.
MAX_SESSION_JSON_BYTES = 8 * 1024 * 1024


class SpannerSessionBackend:
    def __init__(
        self,
        database: Any,
        ttl_seconds: int,
        max_sessions: int,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl_seconds < 1 or max_sessions < 1:
            raise ValueError("Session TTL and capacity must be positive")
        self.database, self.ttl_seconds, self.max_sessions = database, ttl_seconds, max_sessions
        self._clock = clock or (lambda: datetime.now(UTC))

    def _session(self, session_id: str) -> dict[str, Any]:
        # API validates UUIDs; retain a strict bound at this persistence boundary too.
        if not session_id or len(session_id) > 36:
            raise DomainError("INVALID_SESSION", "Session ID must contain 1 to 36 characters.", 400)
        return {"params": {"session": session_id}, "param_types": {"session": sql_types().STRING}}

    @bounded_operation
    def load(self, session_id: str) -> dict[str, Any]:
        types = sql_types()
        arguments = self._session(session_id)
        arguments["params"]["cutoff"] = self._clock() - timedelta(seconds=self.ttl_seconds)
        arguments["param_types"]["cutoff"] = types.TIMESTAMP
        arguments["params"]["quota"] = QUOTA_SESSION_ID
        arguments["param_types"]["quota"] = types.STRING
        try:
            with self.database.snapshot() as snapshot:
                rows = list(
                    snapshot.execute_sql(
                        "SELECT StateJson FROM DemoSessions "
                        "WHERE SessionId = @session "
                        "AND (TouchedAt > @cutoff OR SessionId = @quota)",
                        **arguments,
                        **rpc_options(),
                    )
                )
            return json_value(rows[0][0]) if rows else {}
        except Exception as exc:
            raise DomainError(
                "SPANNER_SESSION_FAILED", "Unable to read the demo session from Spanner.", 503
            ) from exc

    @bounded_operation
    def atomic(self, session_id: str, operation: Callable[[dict[str, Any]], T]) -> T:
        """Callbacks can retry. They must be deterministic and have no external side effects."""
        arguments = self._session(session_id)

        def transact(transaction: Any) -> T:
            now = self._clock()
            cutoff = now - timedelta(seconds=self.ttl_seconds)
            transaction.execute_update(
                "DELETE FROM DemoSessions WHERE TouchedAt <= @cutoff AND SessionId != @quota",
                params={"cutoff": cutoff, "quota": QUOTA_SESSION_ID},
                param_types={"cutoff": sql_types().TIMESTAMP, "quota": sql_types().STRING},
                **rpc_options(),
            )
            rows = list(
                transaction.execute_sql(
                    "SELECT StateJson FROM DemoSessions WHERE SessionId = @session",
                    **arguments,
                    **rpc_options(),
                )
            )
            if not rows:
                count = next(
                    iter(
                        transaction.execute_sql(
                            "SELECT COUNT(*) FROM DemoSessions", **rpc_options()
                        )
                    )
                )[0]
                if count >= self.max_sessions:
                    raise DomainError(
                        "DEMO_CAPACITY_REACHED",
                        "Demo session capacity reached. Try again later.",
                        503,
                    )
            payload = json_value(rows[0][0]) if rows else {}
            result = operation(payload)
            # Match JsonObject's compact, ASCII-escaped wire serialization. A count
            # of records or Python characters alone does not bound a JSON value.
            encoded = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            if len(encoded) > MAX_SESSION_JSON_BYTES:
                raise DomainError(
                    "DEMO_SESSION_SIZE_LIMIT",
                    "This demo session has reached its storage limit. "
                    "Its previous records are preserved; reset before recording more work.",
                    409,
                )
            transaction.insert_or_update(
                "DemoSessions",
                ("SessionId", "StateJson", "TouchedAt"),
                [(session_id, spanner_json(payload), now)],
            )
            return result

        try:
            return self.database.run_in_transaction(
                transact, timeout_secs=TRANSACTION_RETRY_SECONDS
            )
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(
                "SPANNER_SESSION_FAILED", "Unable to save the demo session in Spanner.", 503
            ) from exc

    @bounded_operation
    def reset(self, session_id: str) -> None:
        arguments = self._session(session_id)
        try:
            self.database.run_in_transaction(
                lambda transaction: transaction.execute_update(
                    "DELETE FROM DemoSessions WHERE SessionId = @session",
                    **arguments,
                    **rpc_options(),
                ),
                timeout_secs=TRANSACTION_RETRY_SECONDS,
            )
        except Exception as exc:
            raise DomainError(
                "SPANNER_SESSION_FAILED", "Unable to reset the demo session in Spanner.", 503
            ) from exc
