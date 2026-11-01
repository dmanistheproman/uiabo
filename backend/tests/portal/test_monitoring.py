"""Portal monitoring endpoints: analysis runs and ingestion runs (UC-43)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.accounts.repository import InMemoryAccountRepository, get_account_repository
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.main import app
from app.ingestion.repository import InMemoryIngestionRunStore, get_ingestion_run_store
from app.ingestion.service import IngestionService, get_ingestion_service
from app.pipeline.orchestration.run_recorder import InMemoryRunStore, get_run_store

SGT = timezone(timedelta(hours=8))
NOW = datetime.now(timezone.utc)


def seed_de(accounts, uid="de-1"):
    accounts.profiles[uid] = {
        "uid": uid, "name": "Engineer", "email": f"{uid}@example.com",
        "email_verified": True, "role": "data_engineer", "account_status": "active",
        "profile": {}, "storage_used_bytes": 0, "storage_quota_bytes": 0,
        "created_at": NOW, "updated_at": NOW,
    }


def seed_free(accounts, uid="app-user"):
    accounts.profiles[uid] = {
        "uid": uid, "name": "User", "email": f"{uid}@example.com",
        "email_verified": True, "role": "free", "account_status": "active",
        "profile": {}, "storage_used_bytes": 0, "storage_quota_bytes": 0,
        "created_at": NOW, "updated_at": NOW,
    }


def seed_run(store, run_id, *, status="completed", minutes_ago=30, duration_ms=1200,
             input_type="text", failure_stage=None, error_code=None):
    created_at = NOW - timedelta(minutes=minutes_ago)
    store.runs[run_id] = {
        "run_id": run_id, "input_type": input_type, "status": status,
        "created_at": created_at, "finished_at": created_at + timedelta(seconds=2),
        "duration_ms": duration_ms,
        "stage_timings_ms": {"claim_analysis": duration_ms // 2},
        "pipeline_version": "sprint-1-v1",
        **({"failure_stage": failure_stage, "error_code": error_code, "message": "boom"}
           if status == "failed" else {}),
    }


@pytest.fixture
def env():
    runs = InMemoryRunStore()
    ingestion_runs = InMemoryIngestionRunStore()
    accounts = InMemoryAccountRepository(clock=lambda: NOW)
    identity = {"user": AuthenticatedUser(uid="de-1", email="de-1@example.com", email_verified=True)}
    app.dependency_overrides[get_current_user] = lambda: identity["user"]
    app.dependency_overrides[get_account_repository] = lambda: accounts
    app.dependency_overrides[get_run_store] = lambda: runs
    app.dependency_overrides[get_ingestion_run_store] = lambda: ingestion_runs
    app.dependency_overrides[get_ingestion_service] = lambda: IngestionService(
        store=ingestion_runs, http_client=env_http.get("client"), db=env_http.get("db"))
    with TestClient(app) as client:
        yield client, runs, ingestion_runs, accounts, identity
    app.dependency_overrides.clear()


env_http: dict = {}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b"{}" * 10

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, payload, error=None):
        self._payload = payload
        self._error = error

    def get(self, url, timeout=None):
        if self._error:
            raise self._error
        return FakeResponse(self._payload)


class FakeDocument:
    def __init__(self, written, key):
        self._written, self._key = written, key

    def set(self, value):
        self._written[self._key] = value


class FakeCollection:
    def __init__(self, written, name):
        self._written, self._name = written, name

    def document(self, doc_id):
        return FakeDocument(self._written, (self._name, doc_id))


class FakeDb:
    def __init__(self):
        self.written: dict[tuple, dict] = {}

    def collection(self, name):
        return FakeCollection(self.written, name)


def _forecast_payload(periods=4):
    issued = (NOW - timedelta(hours=1)).astimezone(SGT)
    midnight = issued.replace(hour=0, minute=0, second=0, microsecond=0)
    forecasts = []
    for offset in range(1, periods + 1):
        day = midnight + timedelta(days=offset)
        forecasts.append({
            "timestamp": day.astimezone(timezone.utc).isoformat(),
            "temperature": {"unit": "Degrees Celsius", "low": 24.0, "high": 32.0},
        })
    return {"code": 0, "errorMsg": "", "data": {"records": [{
        "timestamp": midnight.astimezone(timezone.utc).isoformat(),
        "updatedTimestamp": (NOW - timedelta(hours=1)).astimezone(timezone.utc).isoformat(),
        "date": midnight.date().isoformat(),
        "forecasts": forecasts,
    }]}}


def test_free_user_cannot_monitor_runs(env):
    client, runs, ingestion_runs, accounts, identity = env
    identity["user"] = AuthenticatedUser(uid="app-user", email="app-user@example.com", email_verified=True)
    seed_free(accounts)
    assert client.get("/portal/runs").status_code == 403
    assert client.get("/portal/runs/summary").status_code == 403
    assert client.get("/portal/ingestion-runs").status_code == 403


def test_engineer_lists_and_filters_runs(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    seed_run(runs, "run-a", status="completed", minutes_ago=10)
    seed_run(runs, "run-b", status="failed", minutes_ago=5, failure_stage="claim_analysis",
             error_code="CLAIM_ANALYSIS_FAILED")
    listed = client.get("/portal/runs").json()
    assert [run["run_id"] for run in listed["runs"]] == ["run-b", "run-a"]
    only_failed = client.get("/portal/runs", params={"status": "failed"}).json()["runs"]
    assert [run["run_id"] for run in only_failed] == ["run-b"]
    window = client.get("/portal/runs", params={"from": (NOW - timedelta(minutes=7)).isoformat()})
    assert [run["run_id"] for run in window.json()["runs"]] == ["run-b"]


def test_run_summary_aggregates(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    seed_run(runs, "run-a", status="completed", duration_ms=1000)
    seed_run(runs, "run-b", status="completed", duration_ms=3000)
    seed_run(runs, "run-c", status="failed", duration_ms=800, failure_stage="evidence_retrieval",
             error_code="RETRIEVAL_UNAVAILABLE")
    summary = client.get("/portal/runs/summary").json()
    assert summary["total"] == 3
    assert summary["completed"] == 2 and summary["failed"] == 1
    assert summary["avg_duration_ms"] == 1600
    assert summary["p95_duration_ms"] == 3000
    assert summary["failure_by_stage"] == {"evidence_retrieval": 1}
    today = NOW.astimezone(SGT).date().isoformat()
    assert summary["trend"] == [{"date": today, "count": 3}]


def test_run_detail(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    seed_run(runs, "run-a")
    found = client.get("/portal/runs/run-a").json()
    assert found["run_id"] == "run-a"
    assert found["stage_timings_ms"] == {"claim_analysis": 600}
    assert client.get("/portal/runs/run-missing").status_code == 404


def _service(ingestion_runs, http=None, db=None):
    return IngestionService(store=ingestion_runs, http_client=http, db=db)


def test_trigger_forecast_job_success(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    fake_db, fake_http = FakeDb(), FakeHttp(_forecast_payload(4))
    app.dependency_overrides[get_ingestion_service] = lambda: _service(ingestion_runs, fake_http, fake_db)
    response = client.post("/portal/ingestion-jobs/forecast_snapshot/run")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["items_processed"] == 4
    assert len(body["affected_range"]["forecast_dates"]) == 4
    assert body["trigger"] == "manual"
    assert body["duration_ms"] is not None
    assert ("forecast_snapshots", "latest") in fake_db.written


def test_trigger_forecast_job_incomplete(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    app.dependency_overrides[get_ingestion_service] = lambda: _service(
        ingestion_runs, FakeHttp(_forecast_payload(2)), FakeDb())
    body = client.post("/portal/ingestion-jobs/forecast_snapshot/run").json()
    assert body["status"] == "incomplete"
    assert body["items_processed"] == 2
    assert "2 of 4" in body["message"]


def test_trigger_forecast_job_failure(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    app.dependency_overrides[get_ingestion_service] = lambda: _service(
        ingestion_runs, FakeHttp(None, error=RuntimeError("connection refused")), FakeDb())
    body = client.post("/portal/ingestion-jobs/forecast_snapshot/run").json()
    assert body["status"] == "failed"
    assert body["error_code"] == "FORECAST_UNAVAILABLE"
    assert "connection refused" in body["message"]


def test_trigger_catalogue_job(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    fake_db = FakeDb()
    app.dependency_overrides[get_ingestion_service] = lambda: _service(
        ingestion_runs, FakeHttp(None), fake_db)
    body = client.post("/portal/ingestion-jobs/source_catalogue/run").json()
    assert body["status"] == "succeeded"
    assert body["items_processed"] == body["affected_range"]["domains"]
    catalogue = {key[1]: value for key, value in fake_db.written.items() if key[0] == "source_catalogue"}
    assert len(catalogue) == body["items_processed"]
    assert all("publisher" in entry and "source_type" in entry for entry in catalogue.values())


def test_unknown_job_is_not_routable(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    assert client.post("/portal/ingestion-jobs/nonsense/run").status_code == 422


def test_ingestion_list_and_health(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    fresh_success = {
        "run_id": "ing_fresh", "job": "forecast_snapshot", "status": "succeeded",
        "trigger": "manual", "started_at": NOW - timedelta(hours=1), "finished_at": NOW,
        "duration_ms": 900, "items_processed": 4, "affected_range": {}, "source": "x",
        "message": None, "error_code": None, "triggered_by_mask": "de_x", "follow_ups": [],
    }
    old_success = {
        "run_id": "ing_old", "job": "source_catalogue", "status": "succeeded",
        "trigger": "manual", "started_at": NOW - timedelta(days=10), "finished_at": NOW - timedelta(days=10),
        "duration_ms": 10, "items_processed": 9, "affected_range": {}, "source": "x",
        "message": None, "error_code": None, "triggered_by_mask": "de_x", "follow_ups": [],
    }
    ingestion_runs.save(fresh_success)
    ingestion_runs.save(old_success)
    body = client.get("/portal/ingestion-runs").json()
    assert body["jobs"]["forecast_snapshot"]["health"] == "healthy"
    assert body["jobs"]["source_catalogue"]["health"] == "stale"
    assert [run["run_id"] for run in body["runs"]] == ["ing_fresh", "ing_old"]

    failure = dict(fresh_success, run_id="ing_fail", status="failed",
                   started_at=NOW - timedelta(minutes=5), error_code="FORECAST_UNAVAILABLE")
    ingestion_runs.save(failure)
    body = client.get("/portal/ingestion-runs").json()
    assert body["jobs"]["forecast_snapshot"]["health"] == "failing"
    assert body["jobs"]["forecast_snapshot"]["last_error_code"] == "FORECAST_UNAVAILABLE"

    empty = client.get("/portal/ingestion-runs", params={"job": "forecast_snapshot", "status": "succeeded"})
    assert [run["run_id"] for run in empty.json()["runs"]] == ["ing_fresh"]


def test_never_run_job_health(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    body = client.get("/portal/ingestion-runs").json()
    assert body["jobs"]["forecast_snapshot"]["health"] == "never_run"
    assert body["runs"] == []


def test_follow_up_note(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    ingestion_runs.save({
        "run_id": "ing_x", "job": "forecast_snapshot", "status": "failed",
        "trigger": "manual", "started_at": NOW, "finished_at": NOW, "duration_ms": 5,
        "items_processed": 0, "affected_range": {}, "source": "x", "message": "down",
        "error_code": "FORECAST_UNAVAILABLE", "triggered_by_mask": "de_x", "follow_ups": [],
    })
    response = client.post("/portal/ingestion-runs/ing_x/follow-up",
                           json={"note": "Re-run after the provider outage window."})
    assert response.status_code == 200
    body = response.json()
    assert len(body["follow_ups"]) == 1
    assert body["follow_ups"][0]["note"].startswith("Re-run")
    assert body["follow_ups"][0]["by_mask"].startswith("de_")
    assert client.post("/portal/ingestion-runs/ing_missing/follow-up",
                       json={"note": "nothing"}).status_code == 404


def test_ingestion_run_detail(env):
    client, runs, ingestion_runs, accounts, identity = env
    seed_de(accounts)
    assert client.get("/portal/ingestion-runs/ing_none").status_code == 404
