"""Real data-ingestion jobs: official forecast snapshots and source catalogue.

Each execution writes an ingestion_runs record with its state, duration,
counts, errors, provenance and affected data range so the data-engineer
portal can show failed, delayed or incomplete updates (UC-43). These runs
are clearly separate from user-triggered analysis requests (pipeline_runs).
"""

import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable
from uuid import uuid4

import httpx

from app.ingestion.repository import IngestionRunStore
from app.pipeline.evidence_retrieval.official_forecast import API_URL, parse_forecast
from app.pipeline.evidence_retrieval.sources import SOURCES
from app.portal.service import mask_identifier


FORECAST_SNAPSHOTS_COLLECTION = "forecast_snapshots"
SOURCE_CATALOGUE_COLLECTION = "source_catalogue"

JOBS: dict[str, dict[str, Any]] = {
    "forecast_snapshot": {
        "label": "Official weather forecast snapshot",
        "source": "data.gov.sg NEA/MSS four-day outlook",
        "staleness_hours": 24,
    },
    "source_catalogue": {
        "label": "Trusted-source catalogue refresh",
        "source": "UIABO trusted-domain allowlist",
        "staleness_hours": 24 * 7,
    },
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestionService:
    """Runs one ingestion job at a time and records every attempt."""

    def __init__(
        self,
        *,
        store: IngestionRunStore,
        clock: Callable[[], datetime] | None = None,
        http_client: Any | None = None,
        db: Any | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or _utc_now
        self._http_client = http_client
        self._db = db

    def store(self) -> IngestionRunStore:
        return self._store

    def run(self, job: str, *, trigger: str, actor_uid: str) -> dict[str, Any]:
        if job not in JOBS:
            raise ValueError(f"Unknown ingestion job: {job}")
        run_id = f"ing_{uuid4().hex[:16]}"
        started_at = self._clock()
        record: dict[str, Any] = {
            "run_id": run_id,
            "job": job,
            "source": JOBS[job]["source"],
            "status": "running",
            "trigger": trigger,
            "triggered_by_mask": mask_identifier(actor_uid, "de"),
            "started_at": started_at,
            "finished_at": None,
            "duration_ms": None,
            "items_processed": 0,
            "affected_range": {},
            "message": None,
            "error_code": None,
            "follow_ups": [],
        }
        try:
            self._store.save(dict(record))
            outcome = self._execute(job)
            record.update(outcome)
        except Exception as error:
            record.update({
                "status": "failed",
                "error_code": ("FORECAST_UNAVAILABLE" if job == "forecast_snapshot"
                               else "CATALOGUE_UPDATE_FAILED"),
                "message": str(error)[:500],
            })
        finished_at = self._clock()
        record["finished_at"] = finished_at
        record["duration_ms"] = max(0, int((finished_at - started_at).total_seconds() * 1000))
        self._store.save(dict(record))
        return record

    def _execute(self, job: str) -> dict[str, Any]:
        if job == "forecast_snapshot":
            return self._run_forecast_snapshot()
        return self._run_source_catalogue()

    def _database(self):
        if self._db is None:
            from app.firebase import get_firestore_client
            self._db = get_firestore_client()
        return self._db

    def _run_forecast_snapshot(self) -> dict[str, Any]:
        client = self._http_client or httpx.Client()
        response = client.get(API_URL, timeout=20.0)
        response.raise_for_status()
        if len(response.content) > 100_000:
            raise ValueError("Oversized official forecast response")
        now = self._clock()
        forecast = parse_forecast(response.json(), assessed_at=now)
        snapshot = forecast.model_dump(mode="json")
        snapshot["fetched_at"] = now
        self._database().collection(FORECAST_SNAPSHOTS_COLLECTION).document("latest").set(snapshot)
        dates = [str(period["date"]) for period in snapshot["periods"]]
        complete = len(dates) == 4
        return {
            "status": "succeeded" if complete else "incomplete",
            "items_processed": len(dates),
            "affected_range": {"forecast_dates": dates},
            "message": (f"Snapshot issued {snapshot['issued_at']} covers {len(dates)} of 4 days."
                        if complete else
                        f"Partial snapshot saved: {len(dates)} of 4 expected forecast days."),
        }

    def _run_source_catalogue(self) -> dict[str, Any]:
        now = self._clock()
        entries = [
            {"domain": domain, "publisher": publisher, "source_type": source_type,
             "updated_at": now}
            for domain, (publisher, source_type) in sorted(SOURCES.items())
        ]
        database = self._database()
        for entry in entries:
            database.collection(SOURCE_CATALOGUE_COLLECTION).document(entry["domain"]).set(entry)
        return {
            "status": "succeeded",
            "items_processed": len(entries),
            "affected_range": {"domains": len(entries)},
            "message": f"Refreshed {len(entries)} trusted sources in the catalogue.",
        }


@lru_cache
def get_ingestion_service() -> IngestionService:
    from app.ingestion.repository import get_ingestion_run_store
    return IngestionService(store=get_ingestion_run_store())
