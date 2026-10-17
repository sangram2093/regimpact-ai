import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import demo_session, respond, writable_session
from app.api.schemas import Envelope
from app.domain.workflow_review import (
    ControlImpactReview,
    ImpactReviewList,
    ImpactReviewRequest,
    ReviewRequest,
    WorkflowReviewView,
)
from app.services.workflow_review import WorkflowReviewService

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger("regimpact.api")
Session = Annotated[str, Depends(writable_session)]
ReadSession = Annotated[str | None, Depends(demo_session)]


@router.post("/workflows/runs/{run_id}/review", response_model=Envelope[WorkflowReviewView])
def review_workflow(
    run_id: str,
    body: ReviewRequest,
    request: Request,
    session: Session,
) -> Envelope[WorkflowReviewView]:
    result = WorkflowReviewService(request.app.state.scenarios).review(run_id, session, body)
    logger.info(
        json.dumps(
            {
                "event": "workflow_review",
                "request_id": request.state.request_id,
                "agent_run_id": run_id,
                "workflow_id": result.run.workflow,
                "review_action": body.decision,
                "reviewer_role": body.role,
            }
        )
    )
    return respond(request, result)


@router.get("/changes/{change_id}/impact-assessments", response_model=Envelope[ImpactReviewList])
def impact_assessments(
    change_id: str,
    request: Request,
    session: ReadSession,
) -> Envelope[ImpactReviewList]:
    return respond(
        request,
        WorkflowReviewService(request.app.state.scenarios).impact_assessments(change_id, session),
    )


@router.post(
    "/impact-assessments/{assessment_id}/review", response_model=Envelope[ControlImpactReview]
)
def review_impact(
    assessment_id: str,
    body: ImpactReviewRequest,
    request: Request,
    session: Session,
) -> Envelope[ControlImpactReview]:
    result = WorkflowReviewService(request.app.state.scenarios).review_impact(
        assessment_id, session, body
    )
    logger.info(
        json.dumps(
            {
                "event": "control_impact_review",
                "request_id": request.state.request_id,
                "assessment_id": assessment_id,
                "review_action": body.decision,
                "reviewer_role": body.role,
            }
        )
    )
    return respond(request, result)
