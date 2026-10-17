"""Per-database RPC limits and a shared budget for synchronous Spanner operations."""

from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from time import monotonic
from typing import Any

RPC_TIMEOUT_SECONDS = 10.0
OPERATION_TIMEOUT_SECONDS = 35.0
TRANSACTION_RETRY_SECONDS = 20.0
_deadline: ContextVar[float | None] = ContextVar("spanner_operation_deadline", default=None)


def rpc_options() -> dict[str, Any]:
    deadline = _deadline.get()
    remaining = RPC_TIMEOUT_SECONDS if deadline is None else deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Spanner operation deadline exceeded")
    # Disable GAPIC transport retries. The Spanner transaction runner still retries
    # ABORTED transactions; streaming resume attempts share this operation budget.
    return {"timeout": min(RPC_TIMEOUT_SECONDS, remaining), "retry": None}


def bounded_operation[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        deadline = monotonic() + OPERATION_TIMEOUT_SECONDS
        previous = _deadline.get()
        token = _deadline.set(min(deadline, previous) if previous is not None else deadline)
        try:
            return function(*args, **kwargs)
        finally:
            _deadline.reset(token)

    return wrapped


def configure_rpc_deadlines(api: Any) -> None:
    """Wrap public methods on this database's GAPIC client, never global SDK classes.

    The high-level Transaction.commit API has no timeout argument in the pinned
    SDK. Its underlying public commit RPC otherwise defaults to 3600 seconds.
    Session creation and rollback need limits for the same reason.
    """

    def limited(method):
        @wraps(method)
        def call(*args, **kwargs):
            options = rpc_options()
            requested = kwargs.get("timeout")
            if isinstance(requested, (int, float)):
                options["timeout"] = min(options["timeout"], requested)
            kwargs.update(options)
            return method(*args, **kwargs)

        call._regimpact_bounded = True
        return call

    for name in (
        "create_session",
        "batch_create_sessions",
        "get_session",
        "delete_session",
        "begin_transaction",
        "execute_sql",
        "execute_streaming_sql",
        "execute_batch_dml",
        "read",
        "streaming_read",
        "commit",
        "rollback",
    ):
        method = getattr(api, name)
        if not getattr(method, "_regimpact_bounded", False):
            setattr(api, name, limited(method))
