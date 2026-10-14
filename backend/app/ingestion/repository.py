"""Firestore and in-memory storage for data-ingestion run records."""

from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol

from google.cloud.firestore_v1.base_query import FieldFilter

from app.firebase import get_firestore_client


INGESTION_RUNS_COLLECTION = "ingestion_runs"


class IngestionRunStore(Protocol):
    """Write and read ingestion_runs monitoring records."""

    def save(self, run: dict[str, Any]) -> None:
        """Create or replace one run record."""

    def get(self, run_id: str) -> dict[str, Any] | None:
        """Return one run record, or None when it does not exist."""

    def list_runs(
        self,
        *,
        job: str | None = None,
        status: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Newest-first page of runs with an optional cursor."""

    def list_window(
        self,
        *,
        job: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Runs for one job inside a time window."""

    def list_by_job(self, job: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Newest-first runs for one job (used for health derivation)."""


def _matches(data: dict[str, Any], *, job, created_after, created_before) -> bool:
    if job is not None and data.get("job") != job:
        return False
    started_at = data.get("started_at")
    if created_after is not None and started_at is not None and started_at < created_after:
        return False
    if created_before is not None and started_at is not None and started_at > created_before:
        return False
    return True


def _sort_key(data: dict[str, Any]):
    return (data["started_at"], data["run_id"])


def _paginate(records: list[dict[str, Any]], limit: int, cursor: str | None):
    if cursor:
        index = next((i for i, data in enumerate(records) if data["run_id"] == cursor), None)
        if index is None:
            return [], None
        records = records[index + 1:]
    page = records[:limit]
    next_cursor = records[limit - 1]["run_id"] if len(records) > limit else None
    return page, next_cursor


class FirestoreIngestionRunStore:
    """Store ingestion_runs in Firestore (same in-memory sort conventions)."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = get_firestore_client()
        return self._client

    def save(self, run: dict[str, Any]) -> None:
        self.client.collection(INGESTION_RUNS_COLLECTION).document(run["run_id"]).set(run)

    def get(self, run_id: str) -> dict[str, Any] | None:
        snapshot = self.client.collection(INGESTION_RUNS_COLLECTION).document(run_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_runs(self, *, job=None, status=None, limit=20, cursor=None):
        query = self.client.collection(INGESTION_RUNS_COLLECTION)
        if status is not None:
            query = query.where(filter=FieldFilter("status", "==", status))
        records = [item.to_dict() for item in query.stream() if item.to_dict()]
        records = [data for data in records if job is None or data.get("job") == job]
        records.sort(key=_sort_key, reverse=True)
        page, next_cursor = _paginate(records, limit, cursor)
        return [dict(data) for data in page], next_cursor

    def list_window(self, *, job=None, created_after=None, created_before=None, limit=1000):
        query = self.client.collection(INGESTION_RUNS_COLLECTION)
        if job is not None:
            query = query.where(filter=FieldFilter("job", "==", job))
        records = [item.to_dict() for item in query.stream() if item.to_dict()]
        records = [data for data in records
                   if _matches(data, job=None, created_after=created_after, created_before=created_before)]
        records.sort(key=_sort_key, reverse=True)
        return [dict(data) for data in records[:limit]]

    def list_by_job(self, job: str, *, limit: int = 100):
        return self.list_window(job=job, limit=limit)


class InMemoryIngestionRunStore:
    """Deterministic ingestion-run store used by API tests."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}

    def save(self, run: dict[str, Any]) -> None:
        self.runs[run["run_id"]] = dict(run)

    def get(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        return dict(run) if run else None

    def list_runs(self, *, job=None, status=None, limit=20, cursor=None):
        records = [data for data in self.runs.values()
                   if (job is None or data.get("job") == job)
                   and (status is None or data["status"] == status)]
        records.sort(key=_sort_key, reverse=True)
        page, next_cursor = _paginate(records, limit, cursor)
        return [dict(data) for data in page], next_cursor

    def list_window(self, *, job=None, created_after=None, created_before=None, limit=1000):
        records = [data for data in self.runs.values()
                   if _matches(data, job=job, created_after=created_after, created_before=created_before)]
        records.sort(key=_sort_key, reverse=True)
        return [dict(data) for data in records[:limit]]

    def list_by_job(self, job: str, *, limit: int = 100):
        return self.list_window(job=job, limit=limit)


@lru_cache
def get_ingestion_run_store() -> IngestionRunStore:
    return FirestoreIngestionRunStore()
