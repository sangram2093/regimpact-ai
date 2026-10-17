from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request

from app.api.schemas import Envelope, Meta
from app.domain.errors import DomainError
from app.services.rate_limit import QUOTA_SESSION


def demo_session(value: Annotated[str | None, Header(alias="X-Demo-Session")] = None) -> str | None:
    if value is None:
        return None
    try:
        result = str(UUID(value))
        if result == QUOTA_SESSION:
            raise ValueError("Reserved session")
        return result
    except (ValueError, AttributeError) as exc:
        raise DomainError(
            "INVALID_SESSION", "X-Demo-Session must be a non-reserved UUID.", 422
        ) from exc


def writable_session(value: Annotated[str | None, Depends(demo_session)]) -> str:
    if value is None:
        raise DomainError(
            "SESSION_REQUIRED", "A demo session is required to record this operation."
        )
    return value


def respond[T](request: Request, data: T) -> Envelope[T]:
    settings = request.app.state.settings
    return Envelope(
        data=data,
        meta=Meta(
            request_id=request.state.request_id,
            mode=settings.mode,
            data_origin="PUBLIC_SOURCES / SYNTHETIC_HACKATHON"
            if settings.mode == "gcp"
            else "SEED / GOLDEN_LABELS",
        ),
    )
