import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response

from app.api.dependencies import demo_session, respond, writable_session
from app.api.schemas import (
    AcknowledgeRequest,
    Envelope,
    ErrorBody,
    ErrorDetail,
    ErrorEnvelope,
    ErrorMeta,
    ResetResponse,
    ReviewRequest,
)
from app.api.workbench import router as workbench_router
from app.api.workflow_review import router as workflow_review_router
from app.bootstrap import create_adapters
from app.config.settings import Settings
from app.domain.errors import DomainError
from app.domain.models import RegulatoryInstrument
from app.domain.views import (
    AssessmentView,
    ChangeDetail,
    Dashboard,
    DeltaReview,
    EdgeExplanation,
    Health,
    ImpactResponse,
)
from app.repositories.sessions import SessionRepository
from app.services.ai_workflows import BoundedWorkflowService
from app.services.ask import AskService
from app.services.candidates import CandidateService
from app.services.demo_catalog import DemoCatalogService, DemoCatalogView
from app.services.human_review import HumanReviewService
from app.services.impact import ImpactService
from app.services.rate_limit import OperationLimiter
from app.services.scenarios import ScenarioService
from app.services.sources import SourceService

logger = logging.getLogger("regimpact.api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    adapters = create_adapters(settings)
    repository = adapters.repository
    sessions = SessionRepository(
        settings.session_ttl_seconds, settings.max_sessions, adapters.session_backend
    )
    impact = ImpactService(repository.snapshot(), adapters.graph)
    scenarios = ScenarioService(repository, sessions, impact)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if adapters.vertex_client:
            await adapters.vertex_client.aio.aclose()
            adapters.vertex_client.close()

    app = FastAPI(
        title="RegImpact AI",
        version="0.2.0",
        description=(
            "Governed demonstration API. Decisions affect only the supplied demo session. "
            "Role labels are demo controls, not production authorization."
        ),
        responses={
            status: {"model": ErrorEnvelope} for status in (400, 403, 404, 409, 422, 429, 500, 503)
        },
        dependencies=[Depends(demo_session)],
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.repository = repository
    app.state.scenarios = scenarios
    app.state.sessions = sessions
    app.state.sources = SourceService(settings.data_dir, settings.runtime_dir, adapters.storage)
    catalog = DemoCatalogService(
        mode=settings.mode,
        data_dir=settings.data_dir,
        project=settings.gcp_project_id,
        database=settings.firestore_database,
    )
    app.state.candidates = CandidateService(
        repository, adapters.embeddings, adapters.search, settings.embedding_model
    )
    app.state.workflows = BoundedWorkflowService(adapters.transport)
    app.state.ask = AskService(
        repository.snapshot(), impact, adapters.ask_transport, adapters.screen
    )
    app.state.limiter = OperationLimiter(
        settings.ai_calls_per_minute, settings.ai_calls_per_day, adapters.session_backend
    )
    app.include_router(workbench_router)
    app.include_router(workflow_review_router)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        started = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        logger.info(
            json.dumps(
                {
                    "event": "request_complete",
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                    "mode": settings.mode,
                }
            )
        )
        return response

    def error_response(
        request: Request,
        code: str,
        message: str,
        status: int,
        details: list[ErrorDetail] | None = None,
    ) -> JSONResponse:
        payload = ErrorEnvelope(
            error=ErrorBody(code=code, message=message, details=details or []),
            meta=ErrorMeta(request_id=getattr(request.state, "request_id", str(uuid4()))),
        )
        return JSONResponse(
            payload.model_dump(mode="json"),
            status_code=status,
            headers={"X-Request-ID": payload.meta.request_id, "Cache-Control": "no-store"},
        )

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError) -> JSONResponse:
        return error_response(request, error.code, error.message, error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(
            request,
            "VALIDATION_ERROR",
            "Check the request fields and try again.",
            422,
            [
                ErrorDetail(field=".".join(map(str, item["loc"])), message=item["msg"])
                for item in error.errors()
            ],
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(request, "HTTP_ERROR", str(error.detail), error.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.error(
            json.dumps(
                {
                    "event": "request_failed",
                    "request_id": getattr(request.state, "request_id", None),
                    "exception_type": type(error).__name__,
                }
            )
        )
        return error_response(request, "INTERNAL_ERROR", "Unable to complete this request.", 500)

    prefix = "/api/v1"

    @app.get(f"{prefix}/demo-catalog", response_model=Envelope[DemoCatalogView])
    def demo_catalog(request: Request) -> Envelope[DemoCatalogView]:
        return respond(request, catalog.read())

    @app.get(f"{prefix}/health", response_model=Envelope[Health])
    def health(request: Request) -> Envelope[Health]:
        return respond(
            request,
            Health(
                mode=settings.mode,
                ai_status="LIVE_AI_CONFIGURED_UNVERIFIED"
                if adapters.transport
                else "NOT_CONNECTED_SEED_MODE",
            ),
        )

    @app.get(f"{prefix}/regulations", response_model=Envelope[tuple[RegulatoryInstrument, ...]])
    def regulations(request: Request) -> Envelope[tuple[RegulatoryInstrument, ...]]:
        return respond(request, repository.snapshot().instruments)

    @app.get(
        f"{prefix}/regulations/{{instrument_id}}", response_model=Envelope[RegulatoryInstrument]
    )
    def regulation(instrument_id: str, request: Request) -> Envelope[RegulatoryInstrument]:
        instrument = next(
            (i for i in repository.snapshot().instruments if i.id == instrument_id), None
        )
        if instrument is None:
            raise DomainError(
                "REGULATION_NOT_FOUND", "The requested regulatory source was not found.", 404
            )
        return respond(request, instrument)

    @app.get(f"{prefix}/dashboard", response_model=Envelope[Dashboard])
    def dashboard(
        request: Request, session: Annotated[str | None, Depends(demo_session)]
    ) -> Envelope[Dashboard]:
        return respond(request, scenarios.dashboard(session))

    @app.get(f"{prefix}/changes/{{scenario_id}}/delta-review", response_model=Envelope[DeltaReview])
    def delta_review(
        scenario_id: str, request: Request, session: Annotated[str | None, Depends(demo_session)]
    ) -> Envelope[DeltaReview]:
        return respond(request, scenarios.delta_review(scenario_id, session))

    @app.post(
        f"{prefix}/changes/{{scenario_id}}/acknowledge-carry-forward",
        response_model=Envelope[DeltaReview],
    )
    def acknowledge(
        scenario_id: str,
        body: AcknowledgeRequest,
        request: Request,
        session: Annotated[str, Depends(writable_session)],
    ) -> Envelope[DeltaReview]:
        result = scenarios.acknowledge(scenario_id, session, body.reviewer)
        logger.info(
            json.dumps(
                {
                    "event": "scenario_acknowledgement",
                    "request_id": request.state.request_id,
                    "scenario_id": scenario_id,
                }
            )
        )
        return respond(request, result)

    @app.post(
        f"{prefix}/assessments/{{assessment_id}}/review", response_model=Envelope[AssessmentView]
    )
    def review(
        assessment_id: str,
        body: ReviewRequest,
        request: Request,
        session: Annotated[str, Depends(writable_session)],
    ) -> Envelope[AssessmentView]:
        result = scenarios.review(
            assessment_id, session, body.decision, body.reviewer, body.rationale, body.role
        )
        logger.info(
            json.dumps(
                {
                    "event": "scenario_review",
                    "request_id": request.state.request_id,
                    "assessment_id": assessment_id,
                    "decision": body.decision,
                }
            )
        )
        return respond(request, result)

    @app.get(f"{prefix}/changes/{{change_id}}/impact", response_model=Envelope[ImpactResponse])
    def change_impact(
        change_id: str,
        request: Request,
        session: Annotated[str | None, Depends(demo_session)],
        include_scenario: bool = False,
    ) -> Envelope[ImpactResponse]:
        result = (
            HumanReviewService(scenarios).prospective_impact(change_id, session)
            if include_scenario
            else impact.change_impact(change_id)
        )
        return respond(request, result)

    @app.get(f"{prefix}/changes/{{change_id}}", response_model=Envelope[ChangeDetail])
    def change_detail(
        change_id: str, request: Request, session: Annotated[str | None, Depends(demo_session)]
    ) -> Envelope[ChangeDetail]:
        return respond(request, scenarios.change_detail(change_id, session))

    @app.get(f"{prefix}/edges/{{edge_id}}/explain", response_model=Envelope[EdgeExplanation])
    def explain_edge(
        edge_id: str, request: Request, session: Annotated[str | None, Depends(demo_session)]
    ) -> Envelope[EdgeExplanation]:
        if edge_id.startswith("SCENARIO-MAPPING-"):
            return respond(request, HumanReviewService(scenarios).explain_mapping(edge_id, session))
        explanation = impact.explain_edge(edge_id)
        assessment = next(
            (a for a in scenarios.assessments(session) if a.baseline_edge_id == edge_id), None
        )
        if assessment:
            explanation = explanation.model_copy(update={"scenario_status": assessment.status})
        return respond(request, explanation)

    @app.post(f"{prefix}/demo/reset", response_model=Envelope[ResetResponse])
    def reset_demo(
        request: Request, session: Annotated[str, Depends(writable_session)]
    ) -> Envelope[ResetResponse]:
        sessions.reset(session)
        return respond(request, ResetResponse())

    return app


app = create_app()
