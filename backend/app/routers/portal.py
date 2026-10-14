"""Data-engineer portal endpoints for incorrect-result reports (UC-41, UC-42)."""

from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.portal.dependencies import OperationalContext, require_role
from app.portal.models import (
    REPORT_STATUSES,
    FollowUpEntry,
    FollowUpRequest,
    IngestionRunListResponse,
    IngestionRunView,
    JobStatus,
    PipelineRun,
    ReportDetailResponse,
    ReportListResponse,
    ReportSummary,
    ReportUpdateRequest,
    ResultReport,
    RunListResponse,
    RunSummary,
)
from app.portal.repository import ReportRepository, get_report_repository
from app.portal.service import apply_report_update, mask_identifier
from app.pipeline.orchestration.run_recorder import RunStore, get_run_store
from app.ingestion.service import JOBS, IngestionService, get_ingestion_service
from app.ingestion.repository import IngestionRunStore, get_ingestion_run_store


SGT = timezone(timedelta(hours=8))
router = APIRouter(prefix="/portal", tags=["Portal"])

Engineer = Annotated[OperationalContext, Depends(require_role("data_engineer"))]
Reports = Annotated[ReportRepository, Depends(get_report_repository)]
Runs = Annotated[RunStore, Depends(get_run_store)]
Ingestion = Annotated[IngestionService, Depends(get_ingestion_service)]
IngestionRuns = Annotated[IngestionRunStore, Depends(get_ingestion_run_store)]

REPORT_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
RUN_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
INGESTION_JOBS = tuple(JOBS)

ASSESSMENT_FIELDS = (
    "result_id",
    "processing_status",
    "input_type",
    "original_text",
    "extracted_claim",
    "claim_category",
    "checkable",
    "concern_label",
    "misinformation_risk_score",
    "uncertainty",
    "uncertainty_reasons",
    "explanation",
    "recommended_action",
    "evidence",
    "assessment_outcome",
    "scoring",
    "warnings",
    "pipeline_version",
    "created_at",
    "saved_at",
)


def not_found():
    return HTTPException(404, detail={"error_code": "REPORT_NOT_FOUND",
        "message": "This report could not be found."})


def unavailable():
    return HTTPException(503, detail={"error_code": "PORTAL_SERVICE_UNAVAILABLE",
        "message": "The portal is temporarily unavailable. Please retry."})


def _report_view(document: dict[str, Any]) -> ResultReport:
    public = {key: value for key, value in document.items() if key != "user_id"}
    return ResultReport.model_validate(public)


def _assessment_view(record: dict[str, Any], user_mask: str) -> dict[str, Any]:
    view = {key: record[key] for key in ASSESSMENT_FIELDS if key in record}
    view["user_mask"] = user_mask
    return view


def _window(from_time: datetime | None, to_time: datetime | None):
    if from_time and to_time and from_time > to_time:
        raise HTTPException(422, detail={"error_code": "INVALID_TIME_RANGE",
            "message": "The start of the time range must come before the end."})
    return from_time, to_time


@router.get("/reports/summary", response_model=ReportSummary)
def report_summary(engineer: Engineer, reports: Reports,
                   from_time: Annotated[datetime | None, Query(alias="from")] = None,
                   to_time: Annotated[datetime | None, Query(alias="to")] = None):
    """Dashboard aggregates over reported incorrect results (UC-41)."""
    from_time, to_time = _window(from_time, to_time)
    try:
        documents = reports.list_reports_window(
            created_after=from_time, created_before=to_time)
    except Exception:
        raise unavailable() from None
    by_status: dict[str, int] = {name: 0 for name in REPORT_STATUSES}
    by_input: dict[str, int] = {}
    by_label: dict[str, int] = {}
    by_version: dict[str, int] = {}
    trend: dict[str, int] = {}
    for document in documents:
        by_status[document["status"]] = by_status.get(document["status"], 0) + 1
        by_input[document["input_type"]] = by_input.get(document["input_type"], 0) + 1
        snapshot = document.get("snapshot", {})
        by_label[snapshot["concern_label"]] = by_label.get(snapshot["concern_label"], 0) + 1
        by_version[snapshot["pipeline_version"]] = by_version.get(snapshot["pipeline_version"], 0) + 1
        day = document["created_at"].astimezone(SGT).date().isoformat()
        trend[day] = trend.get(day, 0) + 1
    return ReportSummary(
        total=len(documents),
        by_status=by_status,
        by_input_type=by_input,
        by_concern_label=by_label,
        by_pipeline_version=by_version,
        trend=[{"date": day, "count": count} for day, count in sorted(trend.items())],
    )


@router.get("/reports", response_model=ReportListResponse)
def list_reports(engineer: Engineer, reports: Reports,
                 report_status: Annotated[str | None, Query(alias="status")] = None,
                 from_time: Annotated[datetime | None, Query(alias="from")] = None,
                 to_time: Annotated[datetime | None, Query(alias="to")] = None,
                 limit: Annotated[int, Query(ge=1, le=50)] = 20,
                 cursor: Annotated[str | None, Query(pattern=REPORT_ID_PATTERN)] = None):
    """Newest-first list of reported incorrect results, filterable (UC-41/42)."""
    if report_status is not None and report_status not in REPORT_STATUSES:
        raise HTTPException(422, detail={"error_code": "INVALID_REPORT_STATUS",
            "message": "Choose one of the supported report statuses."})
    from_time, to_time = _window(from_time, to_time)
    try:
        documents, next_cursor = reports.list_reports(
            status=report_status, created_after=from_time, created_before=to_time,
            limit=limit, cursor=cursor)
    except Exception:
        raise unavailable() from None
    return ReportListResponse(
        reports=[_report_view(document) for document in documents],
        next_cursor=next_cursor,
    )


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
def report_detail(engineer: Engineer, reports: Reports,
                  report_id: Annotated[str, Path(pattern=REPORT_ID_PATTERN)]):
    """Investigation view: report, generated assessment and provenance (UC-42)."""
    try:
        document = reports.get_report(report_id)
        if document is None:
            raise not_found()
        record = reports.get_analysis_result(document["result_id"])
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
    assessment = None
    if record is not None:
        assessment = _assessment_view(record, document["user_mask"])
    return ReportDetailResponse(
        report=_report_view(document),
        assessment=assessment,
        result_missing=record is None,
    )


@router.patch("/reports/{report_id}", response_model=ResultReport)
def update_report(engineer: Engineer, reports: Reports, request: ReportUpdateRequest,
                  report_id: Annotated[str, Path(pattern=REPORT_ID_PATTERN)]):
    """Record an investigation note or permitted status change (UC-42)."""
    try:
        document = reports.get_report(report_id)
        if document is None:
            raise not_found()
        if request.status is not None and request.status == document["status"]:
            raise HTTPException(422, detail={"error_code": "REPORT_STATUS_UNCHANGED",
                "message": f"The report is already {document['status']}."})
        updated = apply_report_update(
            document,
            status_change=request.status,
            note=request.note,
            actor_uid=engineer.user.uid,
            actor_role=engineer.profile.role,
            now=datetime.now(timezone.utc),
        )
        reports.save_report(updated)
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
    return _report_view(updated)


def _run_view(document: dict[str, Any]) -> PipelineRun:
    return PipelineRun.model_validate(document)


def _percentile(durations: list[int], fraction: float) -> int | None:
    if not durations:
        return None
    ordered = sorted(durations)
    index = max(0, ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _window(from_time: datetime | None, to_time: datetime | None):
    if from_time and to_time and from_time > to_time:
        raise HTTPException(422, detail={"error_code": "INVALID_TIME_RANGE",
            "message": "The start of the time range must come before the end."})
    return from_time, to_time


@router.get("/runs/summary", response_model=RunSummary)
def run_summary(engineer: Engineer, runs: Runs,
                from_time: Annotated[datetime | None, Query(alias="from")] = None,
                to_time: Annotated[datetime | None, Query(alias="to")] = None):
    """Aggregates over analysis-request runs: health, timing and failures."""
    from_time, to_time = _window(from_time, to_time)
    try:
        documents = runs.list_window(created_after=from_time, created_before=to_time)
    except Exception:
        raise unavailable() from None
    durations = [data["duration_ms"] for data in documents if data.get("duration_ms") is not None]
    failure_by_stage: dict[str, int] = {}
    by_input: dict[str, int] = {}
    trend: dict[str, int] = {}
    for data in documents:
        by_input[data["input_type"]] = by_input.get(data["input_type"], 0) + 1
        if data["status"] == "failed":
            stage = data.get("failure_stage") or "unknown"
            failure_by_stage[stage] = failure_by_stage.get(stage, 0) + 1
        day = data["created_at"].astimezone(SGT).date().isoformat()
        trend[day] = trend.get(day, 0) + 1
    return RunSummary(
        total=len(documents),
        completed=sum(1 for data in documents if data["status"] == "completed"),
        failed=sum(1 for data in documents if data["status"] == "failed"),
        avg_duration_ms=(sum(durations) // len(durations)) if durations else None,
        p95_duration_ms=_percentile(durations, 0.95),
        failure_by_stage=failure_by_stage,
        by_input_type=by_input,
        trend=[{"date": day, "count": count} for day, count in sorted(trend.items())],
    )


@router.get("/runs", response_model=RunListResponse)
def list_runs(engineer: Engineer, runs: Runs,
              run_status: Annotated[str | None, Query(alias="status")] = None,
              from_time: Annotated[datetime | None, Query(alias="from")] = None,
              to_time: Annotated[datetime | None, Query(alias="to")] = None,
              limit: Annotated[int, Query(ge=1, le=50)] = 20,
              cursor: Annotated[str | None, Query(pattern=RUN_ID_PATTERN)] = None):
    """Newest-first analysis runs; filters by status and time window (UC-43)."""
    if run_status is not None and run_status not in {"completed", "failed"}:
        raise HTTPException(422, detail={"error_code": "INVALID_RUN_STATUS",
            "message": "Choose completed or failed."})
    from_time, to_time = _window(from_time, to_time)
    try:
        documents, next_cursor = runs.list_runs(
            status=run_status, created_after=from_time, created_before=to_time,
            limit=limit, cursor=cursor)
    except Exception:
        raise unavailable() from None
    return RunListResponse(runs=[_run_view(data) for data in documents], next_cursor=next_cursor)


@router.get("/runs/{run_id}", response_model=PipelineRun)
def run_detail(engineer: Engineer, runs: Runs,
               run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN)]):
    """One analysis run with stage timings and failure details."""
    try:
        document = runs.get_run(run_id)
    except Exception:
        raise unavailable() from None
    if document is None:
        raise HTTPException(404, detail={"error_code": "RUN_NOT_FOUND",
            "message": "This analysis run could not be found."})
    return _run_view(document)


def _job_statuses(engineer: Engineer, store: IngestionRunStore) -> dict[str, JobStatus]:
    now = datetime.now(timezone.utc)
    statuses: dict[str, JobStatus] = {}
    for job, meta in JOBS.items():
        runs = store.list_by_job(job)
        last = runs[0] if runs else None
        last_success = next((data for data in runs
                             if data["status"] in {"succeeded", "incomplete"}), None)
        if last is None:
            health = "never_run"
        elif last["status"] == "failed":
            health = "failing"
        elif last_success is None:
            health = "failing"
        else:
            staleness = timedelta(hours=meta["staleness_hours"])
            health = "stale" if now - last_success["started_at"] > staleness else "healthy"
        statuses[job] = JobStatus(
            job=job, label=meta["label"], source=meta["source"], health=health,
            last_run_at=last["started_at"] if last else None,
            last_success_at=last_success["started_at"] if last_success else None,
            last_status=last["status"] if last else None,
            last_error_code=last.get("error_code") if last else None,
        )
    return statuses


def _ingestion_view(document: dict[str, Any]) -> IngestionRunView:
    return IngestionRunView.model_validate(document)


@router.post("/ingestion-jobs/{job}/run", status_code=201, response_model=IngestionRunView)
def trigger_ingestion(engineer: Engineer, service: Ingestion,
                      job: Annotated[str, Path(pattern="^(forecast_snapshot|source_catalogue)$")]):
    """Authorised recovery action: run an ingestion job now (UC-43)."""
    try:
        record = service.run(job, trigger="manual", actor_uid=engineer.user.uid)
    except Exception:
        raise unavailable() from None
    return _ingestion_view(record)


@router.get("/ingestion-runs", response_model=IngestionRunListResponse)
def list_ingestion_runs(engineer: Engineer, store: IngestionRuns,
                        job: Annotated[str | None, Query()] = None,
                        run_status: Annotated[str | None, Query(alias="status")] = None,
                        limit: Annotated[int, Query(ge=1, le=50)] = 20,
                        cursor: Annotated[str | None, Query(pattern=RUN_ID_PATTERN)] = None):
    """Ingestion runs with per-job health: failed, delayed or incomplete (UC-43)."""
    if job is not None and job not in JOBS:
        raise HTTPException(422, detail={"error_code": "UNKNOWN_INGESTION_JOB",
            "message": "Choose a supported ingestion job."})
    if run_status is not None and run_status not in {"running", "succeeded", "incomplete", "failed"}:
        raise HTTPException(422, detail={"error_code": "INVALID_INGESTION_STATUS",
            "message": "Choose running, succeeded, incomplete or failed."})
    try:
        documents, next_cursor = store.list_runs(job=job, status=run_status, limit=limit, cursor=cursor)
        jobs = _job_statuses(engineer, store)
    except Exception:
        raise unavailable() from None
    return IngestionRunListResponse(
        runs=[_ingestion_view(data) for data in documents],
        jobs=jobs,
        next_cursor=next_cursor,
    )


@router.get("/ingestion-runs/{run_id}", response_model=IngestionRunView)
def ingestion_run_detail(engineer: Engineer, store: IngestionRuns,
                         run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN)]):
    """Run details with error information, provenance and affected range."""
    try:
        document = store.get(run_id)
    except Exception:
        raise unavailable() from None
    if document is None:
        raise HTTPException(404, detail={"error_code": "INGESTION_RUN_NOT_FOUND",
            "message": "This ingestion run could not be found."})
    return _ingestion_view(document)


@router.post("/ingestion-runs/{run_id}/follow-up", response_model=IngestionRunView)
def record_follow_up(engineer: Engineer, store: IngestionRuns, request: FollowUpRequest,
                     run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN)]):
    """Record a follow-up issue against an ingestion run (UC-43 flow 7)."""
    try:
        document = store.get(run_id)
        if document is None:
            raise HTTPException(404, detail={"error_code": "INGESTION_RUN_NOT_FOUND",
                "message": "This ingestion run could not be found."})
        entry = FollowUpEntry(
            at=datetime.now(timezone.utc),
            by_mask=mask_identifier(engineer.user.uid, "de"),
            note=request.note,
        ).model_dump(mode="json")
        document["follow_ups"] = [*document.get("follow_ups", []), entry]
        store.save(document)
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
    return _ingestion_view(document)
