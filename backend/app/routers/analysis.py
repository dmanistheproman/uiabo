"""Authenticated text checks and history for the Android application."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query

from app.analyses.store import AnalysisStore, get_analysis_store
from app.auth.dependencies import get_verified_user
from app.auth.models import AuthenticatedUser
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineError
from app.pipeline.shared.models import FailedAnalysisRecord
from app.schemas import TextAnalysisRequest, TextAnalysisResult


router = APIRouter(prefix="/analysis", tags=["Analysis"])
User = Annotated[AuthenticatedUser, Depends(get_verified_user)]
Store = Annotated[AnalysisStore, Depends(get_analysis_store)]


def unavailable():
    return HTTPException(503, detail={"error_code": "RESULT_STORAGE_UNAVAILABLE",
        "message": "Saved results are temporarily unavailable. Please retry."})


@router.post("/text", response_model=TextAnalysisResult)
def analyse_text(request: TextAnalysisRequest, user: User, store: Store,
                 pipeline: Annotated[PipelineOrchestrator, Depends(get_pipeline_orchestrator)],
                 idempotency_key: Annotated[str | None, Header(max_length=64, pattern=r"^[a-zA-Z0-9-]+$")] = None):
    reservation = None
    try:
        reservation = store.reserve(user.uid, idempotency_key or str(uuid4()), request.text)
        if "existing" in reservation:
            existing = reservation["existing"]
            if existing["processing_status"] == "completed":
                return existing
            raise HTTPException(409, detail={"error_code": "PREVIOUS_CHECK_FAILED",
                "message": "The previous check failed. Start a new check to retry."})
        # Compute with request-local storage; the authoritative result and quota
        # are committed together in one Firestore transaction below.
        isolated = pipeline.with_repository(InMemoryResultRepository())
        try:
            result = isolated.analyze(request.text)
        except PipelineError as error:
            failure = FailedAnalysisRecord(result_id=reservation["result_id"],
                original_text=request.text, failure_stage=error.stage, error_code=error.error_code,
                message=error.message, retryable=error.retryable, pipeline_version="sprint-1-v1",
                created_at=datetime.now(timezone.utc))
            store.finish(user.uid, reservation, failure)
            raise HTTPException(error.http_status, detail={"error_code": error.error_code,
                "message": error.message, "stage": error.stage, "retryable": error.retryable}) from None
        return store.finish(user.uid, reservation, result)
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
    finally:
        if reservation and "token" in reservation:
            try:
                store.release(user.uid, reservation)
            except Exception:
                pass  # The bounded lease allows recovery if Firestore is down.


@router.get("/results")
def list_results(user: User, store: Store,
                 limit: Annotated[int, Query(ge=1, le=50)] = 20,
                 cursor: Annotated[str | None, Query(pattern=r"^[a-f0-9]{32}$")] = None):
    try:
        return store.history(user.uid, limit, cursor)
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None


@router.get("/results/{result_id}")
def get_result(user: User, store: Store,
               result_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]):
    try:
        return store.get_owned(user.uid, result_id)
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
