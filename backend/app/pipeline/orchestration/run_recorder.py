"""Best-effort analysis run records that power pipeline monitoring.

Records contain no user content: only run identity, status, timings and the
failure stage/code. The data-engineer portal reads this collection; user
content stays in analysis_results behind the portal's role gate.
"""

from datetime import datetime
from functools import lru_cache
from typing import Any, Protocol

from google.cloud.firestore_v1.base_query import FieldFilter

from app.firebase import get_firestore_client


RUNS_COLLECTION = "pipeline_runs"


class RunStore(Protocol):
    """Write and read pipeline_runs monitoring records."""

    def record(self, run: dict[str, Any]) -> None:
        """Store one run record, keyed by run_id."""

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return one run record, or None when it does not exist."""

    def list_runs(
        self,
        *,
        status: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Newest-first page of runs with an optional cursor."""

    def list_window(
        self,
        *,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        """All runs inside a time window, for aggregate monitoring."""


def _matches_range(data: dict[str, Any], created_after, created_before) -> bool:
    created_at = data.get("created_at")
    if created_after is not None and created_at is not None and created_at < created_after:
        return False
    if created_before is not None and created_at is not None and created_at > created_before:
        return False
    return True


class FirestoreRunStore:
    """Store pipeline_runs in Firestore.

    At most one equality filter runs server side (prototype permissions have
    no composite-index admin); sorting and time windows apply in memory.
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = get_firestore_client()
        return self._client

    def record(self, run: dict[str, Any]) -> None:
        self.client.collection(RUNS_COLLECTION).document(run["run_id"]).set(run)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        snapshot = self.client.collection(RUNS_COLLECTION).document(run_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def _sorted_documents(self, status: str | None = None) -> list[dict[str, Any]]:
        query = self.client.collection(RUNS_COLLECTION)
        if status is not None:
            query = query.where(filter=FieldFilter("status", "==", status))
        records = [item.to_dict() for item in query.stream() if item.to_dict()]
        records.sort(key=lambda data: (data["created_at"], data["run_id"]), reverse=True)
        return records

    def list_runs(self, *, status=None, created_after=None, created_before=None, limit=20, cursor=None):
        records = self._sorted_documents(status)
        records = [data for data in records if _matches_range(data, created_after, created_before)]
        if cursor:
            index = next((i for i, data in enumerate(records) if data["run_id"] == cursor), None)
            if index is None:
                return [], None
            records = records[index + 1:]
        page = records[:limit]
        next_cursor = records[limit - 1]["run_id"] if len(records) > limit else None
        return page, next_cursor

    def list_window(self, *, created_after=None, created_before=None, limit=2000):
        records = self._sorted_documents()
        return [data for data in records if _matches_range(data, created_after, created_before)][:limit]


class InMemoryRunStore:
    """Deterministic run store used by API tests."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}

    def record(self, run: dict[str, Any]) -> None:
        self.runs[run["run_id"]] = dict(run)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        return dict(run) if run else None

    def list_runs(self, *, status=None, created_after=None, created_before=None, limit=20, cursor=None):
        records = [
            data for data in self.runs.values()
            if (status is None or data["status"] == status)
            and _matches_range(data, created_after, created_before)
        ]
        records.sort(key=lambda data: (data["created_at"], data["run_id"]), reverse=True)
        if cursor:
            index = next((i for i, data in enumerate(records) if data["run_id"] == cursor), None)
            if index is None:
                return [], None
            records = records[index + 1:]
        page = records[:limit]
        next_cursor = records[limit - 1]["run_id"] if len(records) > limit else None
        return [dict(data) for data in page], next_cursor

    def list_window(self, *, created_after=None, created_before=None, limit=2000):
        records = [
            data for data in self.runs.values()
            if _matches_range(data, created_after, created_before)
        ]
        records.sort(key=lambda data: (data["created_at"], data["run_id"]), reverse=True)
        return [dict(data) for data in records[:limit]]


@lru_cache
def get_run_store() -> RunStore:
    return FirestoreRunStore()
