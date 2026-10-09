"""Pydantic contracts for incorrect-result reports and the portal dashboard."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ReportStatus = Literal["open", "reviewing", "resolved", "dismissed"]
ReportReason = Literal["wrong_label", "wrong_score", "wrong_evidence", "other"]

REPORT_STATUSES: tuple[str, ...] = ("open", "reviewing", "resolved", "dismissed")
ACTIVE_REPORT_STATUSES = frozenset({"open", "reviewing"})
REPORT_REASONS: tuple[str, ...] = (
    "wrong_label",
    "wrong_score",
    "wrong_evidence",
    "other",
)


def _clean_text(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Text cannot be empty.")
    return cleaned


class ResultReportRequest(BaseModel):
    """A user's incorrect-result submission from the app."""

    model_config = ConfigDict(extra="forbid")

    reason: ReportReason
    detail: str = Field(min_length=1, max_length=2000)

    @field_validator("detail")
    @classmethod
    def normalise_detail(cls, value: str) -> str:
        return _clean_text(value)


class ReportUpdateRequest(BaseModel):
    """A data engineer's review note or status change."""

    model_config = ConfigDict(extra="forbid")

    status: ReportStatus | None = None
    note: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def normalise_note(cls, value: str | None) -> str | None:
        return _clean_text(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "ReportUpdateRequest":
        if self.status is None and self.note is None:
            raise ValueError("Provide a status update or an investigation note.")
        return self


class ReportAuditEntry(BaseModel):
    at: datetime
    actor_mask: str
    actor_role: str
    action: Literal["created", "status_changed", "note_added"]
    status_from: str | None = None
    status_to: str | None = None
    note: str | None = None


class ReportSnapshot(BaseModel):
    """Denormalised result facts that power dashboard aggregates."""

    claim_category: str
    checkable: bool
    concern_label: str
    misinformation_risk_score: float | None = None
    uncertainty: str
    pipeline_version: str
    result_created_at: datetime


class ResultReport(BaseModel):
    """A report as shown in the portal; user identity is masked."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    result_id: str
    user_mask: str
    input_type: str
    reason: ReportReason
    detail: str
    status: ReportStatus
    created_at: datetime
    updated_at: datetime
    snapshot: ReportSnapshot
    review_note: str | None = None
    reviewed_by_mask: str | None = None
    reviewed_at: datetime | None = None
    history: list[ReportAuditEntry] = Field(default_factory=list)


class ReportCreated(BaseModel):
    report_id: str
    status: ReportStatus
    created_at: datetime


class ReportListResponse(BaseModel):
    reports: list[ResultReport]
    next_cursor: str | None = None


class ReportDetailResponse(BaseModel):
    report: ResultReport
    assessment: dict[str, Any] | None = None
    result_missing: bool = False


class ReportSummary(BaseModel):
    """Aggregate dashboard metrics for a time window (UC-41)."""

    model_config = ConfigDict(extra="forbid")

    total: int
    by_status: dict[str, int]
    by_input_type: dict[str, int]
    by_concern_label: dict[str, int]
    by_pipeline_version: dict[str, int]
    trend: list[dict[str, Any]]


RunStatus = Literal["completed", "failed"]
IngestionStatus = Literal["running", "succeeded", "incomplete", "failed"]
JobHealth = Literal["healthy", "stale", "failing", "never_run"]


class PipelineRun(BaseModel):
    """One analysis request's monitoring record (no user content)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    input_type: str
    status: RunStatus
    created_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    stage_timings_ms: dict[str, int] = Field(default_factory=dict)
    pipeline_version: str | None = None
    failure_stage: str | None = None
    error_code: str | None = None
    message: str | None = None


class RunListResponse(BaseModel):
    runs: list[PipelineRun]
    next_cursor: str | None = None


class RunSummary(BaseModel):
    """Analysis-request monitoring aggregates for a time window (UC-43)."""

    model_config = ConfigDict(extra="forbid")

    total: int
    completed: int
    failed: int
    avg_duration_ms: int | None = None
    p95_duration_ms: int | None = None
    failure_by_stage: dict[str, int]
    by_input_type: dict[str, int]
    trend: list[dict[str, Any]]


class FollowUpEntry(BaseModel):
    at: datetime
    by_mask: str
    note: str


class IngestionRunView(BaseModel):
    """One data-ingestion execution (clearly separate from analysis runs)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    job: str
    status: IngestionStatus
    trigger: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    items_processed: int | None = None
    affected_range: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    message: str | None = None
    error_code: str | None = None
    triggered_by_mask: str | None = None
    follow_ups: list[FollowUpEntry] = Field(default_factory=list)


class JobStatus(BaseModel):
    """Derived health for one ingestion job (UC-43 delayed/failing marking)."""

    model_config = ConfigDict(extra="forbid")

    job: str
    label: str
    source: str
    health: JobHealth
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_status: str | None = None
    last_error_code: str | None = None


class IngestionRunListResponse(BaseModel):
    runs: list[IngestionRunView]
    jobs: dict[str, JobStatus]
    next_cursor: str | None = None


class FollowUpRequest(BaseModel):
    """A data engineer's follow-up issue recorded against an ingestion run."""

    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=1000)

    @field_validator("note")
    @classmethod
    def normalise_note(cls, value: str) -> str:
        return _clean_text(value)
