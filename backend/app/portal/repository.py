"""Firestore and in-memory repositories for incorrect-result reports."""

from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol

from google.cloud.firestore_v1.base_query import FieldFilter

from app.firebase import get_firestore_client


RESULT_REPORTS_COLLECTION = "result_reports"
ANALYSIS_RESULTS_COLLECTION = "analysis_results"


class ReportRepository(Protocol):
    """Storage contract for the portal's report screens."""

    def create_report(self, report: dict[str, Any]) -> dict[str, Any]:
        """Store a new report and return it."""

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        """Return one report, or None when it does not exist."""

    def find_active_report(self, result_id: str, user_id: str) -> dict[str, Any] | None:
        """Return the open or in-review report a user filed for a result."""

    def save_report(self, report: dict[str, Any]) -> None:
        """Replace an existing report document."""

    def list_reports(
        self,
        *,
        status: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Newest-first page of reports with an optional cursor."""

    def list_reports_window(
        self,
        *,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """All reports inside a time window, for dashboard aggregation."""

    def get_analysis_result(self, result_id: str) -> dict[str, Any] | None:
        """Return the raw stored analysis result behind a report."""


def _matches_range(data: dict[str, Any], created_after, created_before) -> bool:
    created_at = data.get("created_at")
    if created_after is not None and created_at is not None and created_at < created_after:
        return False
    if created_before is not None and created_at is not None and created_at > created_before:
        return False
    return True


class FirestoreReportRepository:
    """Reads and writes result_reports in Firestore.

    Like the owned-history query, at most one equality filter runs server side
    because composite indexes need index-admin access; sorting and the time
    window are applied in memory, which suits the prototype data volume.
    """

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = get_firestore_client()
        return self._client

    def create_report(self, report: dict[str, Any]) -> dict[str, Any]:
        self.client.collection(RESULT_REPORTS_COLLECTION).document(
            report["report_id"]
        ).set(report)
        return report

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        snapshot = self.client.collection(RESULT_REPORTS_COLLECTION).document(report_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def find_active_report(self, result_id: str, user_id: str) -> dict[str, Any] | None:
        query = self.client.collection(RESULT_REPORTS_COLLECTION).where(
            filter=FieldFilter("result_id", "==", result_id)
        )
        for snapshot in query.stream():
            data = snapshot.to_dict() or {}
            if data.get("user_id") == user_id and data.get("status") in {"open", "reviewing"}:
                return data
        return None

    def save_report(self, report: dict[str, Any]) -> None:
        self.client.collection(RESULT_REPORTS_COLLECTION).document(
            report["report_id"]
        ).set(report)

    def _sorted_documents(self, status: str | None = None) -> list[dict[str, Any]]:
        query = self.client.collection(RESULT_REPORTS_COLLECTION)
        if status is not None:
            query = query.where(filter=FieldFilter("status", "==", status))
        records = [item.to_dict() for item in query.stream() if item.to_dict()]
        records.sort(key=lambda data: (data["created_at"], data["report_id"]), reverse=True)
        return records

    def list_reports(self, *, status=None, created_after=None, created_before=None, limit=20, cursor=None):
        records = self._sorted_documents(status)
        records = [data for data in records if _matches_range(data, created_after, created_before)]
        if cursor:
            index = next(
                (i for i, data in enumerate(records) if data["report_id"] == cursor), None
            )
            if index is None:
                return [], None
            records = records[index + 1:]
        page = records[:limit]
        next_cursor = records[limit - 1]["report_id"] if len(records) > limit else None
        return page, next_cursor

    def list_reports_window(self, *, created_after=None, created_before=None, limit=1000):
        records = self._sorted_documents()
        return [
            data for data in records
            if _matches_range(data, created_after, created_before)
        ][:limit]

    def get_analysis_result(self, result_id: str) -> dict[str, Any] | None:
        snapshot = self.client.collection(ANALYSIS_RESULTS_COLLECTION).document(result_id).get()
        return snapshot.to_dict() if snapshot.exists else None


class InMemoryReportRepository:
    """Deterministic repository used by API tests."""

    def __init__(self) -> None:
        self.reports: dict[str, dict[str, Any]] = {}
        self.results: dict[str, dict[str, Any]] = {}

    def create_report(self, report: dict[str, Any]) -> dict[str, Any]:
        self.reports[report["report_id"]] = dict(report)
        return dict(report)

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        report = self.reports.get(report_id)
        return dict(report) if report else None

    def find_active_report(self, result_id: str, user_id: str) -> dict[str, Any] | None:
        for report in self.reports.values():
            if (
                report["result_id"] == result_id
                and report["user_id"] == user_id
                and report["status"] in {"open", "reviewing"}
            ):
                return dict(report)
        return None

    def save_report(self, report: dict[str, Any]) -> None:
        self.reports[report["report_id"]] = dict(report)

    def list_reports(self, *, status=None, created_after=None, created_before=None, limit=20, cursor=None):
        records = [
            data for data in self.reports.values()
            if (status is None or data["status"] == status)
            and _matches_range(data, created_after, created_before)
        ]
        records.sort(key=lambda data: (data["created_at"], data["report_id"]), reverse=True)
        if cursor:
            index = next(
                (i for i, data in enumerate(records) if data["report_id"] == cursor), None
            )
            if index is None:
                return [], None
            records = records[index + 1:]
        page = records[:limit]
        next_cursor = records[limit - 1]["report_id"] if len(records) > limit else None
        return [dict(data) for data in page], next_cursor

    def list_reports_window(self, *, created_after=None, created_before=None, limit=1000):
        records = [
            data for data in self.reports.values()
            if _matches_range(data, created_after, created_before)
        ]
        records.sort(key=lambda data: (data["created_at"], data["report_id"]), reverse=True)
        return [dict(data) for data in records[:limit]]

    def get_analysis_result(self, result_id: str) -> dict[str, Any] | None:
        record = self.results.get(result_id)
        return dict(record) if record else None


@lru_cache
def get_report_repository() -> ReportRepository:
    return FirestoreReportRepository()
