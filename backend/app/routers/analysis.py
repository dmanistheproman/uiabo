from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.pipeline.orchestration.dependencies import (
    get_pipeline_orchestrator,
)
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineError
from app.schemas import (
    PipelineErrorResponse,
    TextAnalysisRequest,
    TextAnalysisResult,
)


router = APIRouter(
    prefix="/analysis",
    tags=["Analysis"]
)


@router.post(
    "/text",
    response_model=TextAnalysisResult,
    responses={
        500: {"model": PipelineErrorResponse},
        503: {"model": PipelineErrorResponse},
    },
)
def analyse_text(
    request: TextAnalysisRequest,
    pipeline: Annotated[
        PipelineOrchestrator,
        Depends(get_pipeline_orchestrator),
    ],
) -> TextAnalysisResult:
    try:
        return pipeline.analyze(request.text)
    except PipelineError as error:
        raise HTTPException(
            status_code=error.http_status,
            detail={
                "error_code": error.error_code,
                "message": error.message,
                "stage": error.stage,
                "retryable": error.retryable,
            },
        ) from error
