"""Authenticated text checks and history for the Android application."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from fastapi.responses import Response
from google.api_core.exceptions import NotFound
from app.analyses.images import get_image_storage, storage_unavailable

from app.analyses.store import AnalysisStore, get_analysis_store
from app.auth.dependencies import get_verified_user
from app.auth.models import AuthenticatedUser
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineError
from app.pipeline.shared.models import FailedAnalysisRecord
from app.portal.models import ReportCreated, ResultReportRequest
from app.portal.repository import ReportRepository, get_report_repository
from app.portal.service import build_report_document, REPORTABLE_TYPES
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
    pending_runs = []
    persisted = False
    try:
        if request.input_source == "ocr":
            store.require_premium(user.uid)
        reservation = store.reserve(user.uid, idempotency_key or str(uuid4()), request.text,
                                    input_type="ocr_text" if request.input_source == "ocr" else "text")
        if "existing" in reservation:
            existing = reservation["existing"]
            if existing["processing_status"] == "completed":
                return existing
            raise HTTPException(409, detail={"error_code": "PREVIOUS_CHECK_FAILED",
                "message": "The previous check failed. Start a new check to retry."})
        # Compute with request-local storage; the authoritative result and quota
        # are committed together in one Firestore transaction below.
        isolated = pipeline.with_repository(InMemoryResultRepository(),
            id_factory=lambda: reservation["result_id"], run_recorder=pending_runs.append)
        try:
            result = isolated.analyze(request.text)
        except PipelineError as error:
            failure = FailedAnalysisRecord(result_id=reservation["result_id"],
                original_text=request.text, input_source=request.input_source, failure_stage=error.stage, error_code=error.error_code,
                message=error.message, retryable=error.retryable,
                pipeline_version=getattr(pipeline, "pipeline_version", "unknown"),
                created_at=datetime.now(timezone.utc))
            store.finish(user.uid, reservation, failure)
            raise HTTPException(error.http_status, detail={"error_code": error.error_code,
                "message": error.message, "stage": error.stage, "retryable": error.retryable}) from None
        result = result.model_copy(update={"input_source": request.input_source})
        saved = store.finish(user.uid, reservation, result)
        persisted = True
        return saved
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
    finally:
        for run in pending_runs:
            run["input_type"] = reservation.get("input_type", "text")
            if run["status"] == "completed" and not persisted:
                run.update(status="failed", failure_stage="persistence", error_code="RESULT_STORAGE_UNAVAILABLE")
            pipeline._record_run_best_effort(run)
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


@router.post("/results/{result_id}/report", status_code=201, response_model=ReportCreated)
def report_result(request: ResultReportRequest, user: User, store: Store,
                  reports: Annotated[ReportRepository, Depends(get_report_repository)],
                  result_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]):
    """Report a completed check as an incorrect result (feeds the DE portal)."""
    try:
        record = store.get_owned(user.uid, result_id)
        if record.get("processing_status") != "completed" or record.get("input_type", "text") not in REPORTABLE_TYPES:
            raise HTTPException(422, detail={"error_code": "RESULT_NOT_REPORTABLE",
                "message": "Only completed text, image or link checks can be reported as incorrect."})
        if reports.find_active_report(result_id, user.uid):
            raise HTTPException(409, detail={"error_code": "ALREADY_REPORTED",
                "message": "An investigation is already in progress for this result."})
        document = build_report_document(
            user_id=user.uid, result_id=result_id, reason=request.reason,
            detail=request.detail, record=record,
            now=datetime.now(timezone.utc))
        created = reports.create_report(document)
        return ReportCreated(report_id=created["report_id"],
                             status=created["status"], created_at=created["created_at"])
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None


@router.get("/results/{result_id}/image")
def get_saved_image(user: User, store: Store,
                    result_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]):
    record = store.get_owned(user.uid, result_id)
    attachment = record.get("saved_image")
    if not attachment:
        raise HTTPException(404, detail="No saved image is available for this result.")
    try:
        data = get_image_storage().read(user.uid, result_id, attachment)
    except NotFound:
        raise HTTPException(404, detail="The saved image is no longer available.") from None
    except Exception:
        raise storage_unavailable() from None
    return Response(data, media_type=attachment["content_type"], headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/results/{result_id}/image", status_code=204)
def delete_saved_image(user: User, store: Store,
                       result_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]):
    record = store.get_owned(user.uid, result_id)
    attachment = record.get("saved_image")
    if attachment:
        try:
            get_image_storage().delete(user.uid, result_id, attachment)
            store.clear_saved_image(user.uid, result_id)
        except Exception:
            raise HTTPException(503, detail="The image could not be removed. Please retry.") from None
    return Response(status_code=204)
