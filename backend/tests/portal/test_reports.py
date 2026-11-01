"""Report submission (app side) and portal report endpoints (DE side)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.accounts.repository import InMemoryAccountRepository, get_account_repository
from app.analyses.store import InMemoryAnalysisStore, get_analysis_store
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.main import app
from app.portal.repository import InMemoryReportRepository, get_report_repository

FIXED_TIME = datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc)
RESULT_ID = "a" * 32


def seed_user(store, uid="app-user", status="active"):
    store.documents["users", uid] = {"uid": uid, "role": "free", "account_status": status}


def seed_completed(store, result_id=RESULT_ID, uid="app-user", label="misleading"):
    store.documents["analysis_results", result_id] = {
        "result_id": result_id, "processing_status": "completed",
        "original_text": "Weather text", "extracted_claim": "It will rain tomorrow",
        "claim_category": "weather", "checkable": True,
        "concern_label": label, "misinformation_risk_score": 0.6,
        "uncertainty": "low", "uncertainty_reasons": ["Evidence agrees"],
        "explanation": "Because the evidence agrees.", "recommended_action": "Verify",
        "evidence": [], "pipeline_version": "sprint-1-v1",
        "created_at": FIXED_TIME, "user_id": uid, "input_type": "text",
        "request_fingerprint": "f" * 64, "share_enabled": False,
        "saved_at": FIXED_TIME,
    }


def seed_de(accounts, uid="de-1", role="data_engineer", status="active"):
    accounts.profiles[uid] = {
        "uid": uid, "name": "Engineer", "email": f"{uid}@example.com",
        "email_verified": True, "role": role, "account_status": status,
        "profile": {}, "storage_used_bytes": 0, "storage_quota_bytes": 0,
        "created_at": FIXED_TIME, "updated_at": FIXED_TIME,
    }


@pytest.fixture
def env():
    store = InMemoryAnalysisStore()
    reports = InMemoryReportRepository()
    accounts = InMemoryAccountRepository(clock=lambda: FIXED_TIME)
    identity = {"user": AuthenticatedUser(uid="app-user", email="user@example.com", email_verified=True)}
    app.dependency_overrides[get_current_user] = lambda: identity["user"]
    app.dependency_overrides[get_analysis_store] = lambda: store
    app.dependency_overrides[get_report_repository] = lambda: reports
    app.dependency_overrides[get_account_repository] = lambda: accounts
    with TestClient(app) as client:
        yield client, store, reports, accounts, identity
    app.dependency_overrides.clear()


def as_de(identity, uid="de-1"):
    identity["user"] = AuthenticatedUser(uid=uid, email=f"{uid}@example.com", email_verified=True)


def submit_report(client, result_id=RESULT_ID, **overrides):
    body = {"reason": "wrong_label", "detail": "The label looks wrong to me."}
    body.update(overrides)
    return client.post(f"/analysis/results/{result_id}/report", json=body)


def test_user_can_report_completed_result(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    response = submit_report(client)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    stored = list(reports.reports.values())[0]
    assert stored["result_id"] == RESULT_ID
    assert stored["snapshot"]["concern_label"] == "misleading"


def test_duplicate_active_report_is_rejected(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    assert submit_report(client).status_code == 201
    response = submit_report(client, detail="Second attempt.")
    assert response.status_code == 409
    assert response.json()["detail"]["error_code"] == "ALREADY_REPORTED"


def test_unowned_result_is_not_found(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store, uid="someone-else")
    response = submit_report(client)
    assert response.status_code == 404


def test_failed_result_is_not_reportable(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    store.documents["analysis_results", RESULT_ID] = {
        "result_id": RESULT_ID, "processing_status": "failed",
        "original_text": "Weather text", "failure_stage": "evidence_retrieval",
        "error_code": "RETRIEVAL_UNAVAILABLE", "message": "down", "retryable": True,
        "warnings": [], "pipeline_version": "sprint-1-v1", "created_at": FIXED_TIME,
        "user_id": "app-user", "input_type": "text",
    }
    response = submit_report(client)
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "RESULT_NOT_REPORTABLE"


def test_invalid_reason_is_rejected(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    response = submit_report(client, reason="not_a_reason")
    assert response.status_code == 422


def test_suspended_user_cannot_report(env):
    client, store, reports, accounts, identity = env
    seed_user(store, status="suspended")
    seed_completed(store)
    response = submit_report(client)
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "ACCOUNT_UNAVAILABLE"


def test_free_user_cannot_open_portal(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    submit_report(client)
    seed_de(accounts, uid="app-user", role="free")
    response = client.get("/portal/reports")
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "PORTAL_ACCESS_DENIED"


def test_engineer_lists_and_filters_reports(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    assert submit_report(client).status_code == 201
    as_de(identity)
    seed_de(accounts)

    listed = client.get("/portal/reports").json()["reports"]
    assert len(listed) == 1 and listed[0]["status"] == "open"
    assert client.get("/portal/reports", params={"status": "resolved"}).json()["reports"] == []
    now = datetime.now(timezone.utc)
    recent = client.get("/portal/reports", params={"from": (now - timedelta(days=1)).isoformat()})
    assert len(recent.json()["reports"]) == 1
    stale = client.get("/portal/reports", params={"from": (now + timedelta(days=1)).isoformat()})
    assert stale.json()["reports"] == []


def test_engineer_dashboard_summary(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    assert submit_report(client).status_code == 201
    stored = list(reports.reports.values())[0]
    second = dict(stored, report_id="rpt_second", status="resolved", reason="wrong_score")
    second["snapshot"] = dict(stored["snapshot"], concern_label="credible")
    reports.reports["rpt_second"] = second
    as_de(identity)
    seed_de(accounts)

    summary = client.get("/portal/reports/summary").json()
    assert summary["total"] == 2
    assert summary["by_status"] == {"open": 1, "reviewing": 0, "resolved": 1, "dismissed": 0}
    assert summary["by_concern_label"] == {"misleading": 1, "credible": 1}
    assert summary["by_input_type"] == {"text": 2}
    assert summary["by_pipeline_version"] == {"sprint-1-v1": 2}
    today = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).date().isoformat()
    assert summary["trend"] == [{"date": today, "count": 2}]


def test_engineer_sees_investigation_detail(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    submit_report(client)
    stored = list(reports.reports.values())[0]
    reports.results[RESULT_ID] = store.documents["analysis_results", RESULT_ID]
    as_de(identity)
    seed_de(accounts)

    detail = client.get(f"/portal/reports/{stored['report_id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["result_missing"] is False
    assert body["assessment"]["original_text"] == "Weather text"
    assert body["assessment"]["user_mask"].startswith("usr_")
    assert "user_id" not in body["assessment"]
    assert body["report"]["user_mask"].startswith("usr_")


def test_detail_reports_missing_result(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    submit_report(client)
    as_de(identity)
    seed_de(accounts)
    stored = list(reports.reports.values())[0]
    detail = client.get(f"/portal/reports/{stored['report_id']}")
    body = detail.json()
    assert detail.status_code == 200
    assert body["result_missing"] is True
    assert body["assessment"] is None


def test_engineer_updates_status_and_note(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    created = submit_report(client).json()
    as_de(identity)
    seed_de(accounts)

    response = client.patch(f"/portal/reports/{created['report_id']}",
                            json={"status": "reviewing", "note": "Checking the cited evidence."})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reviewing"
    assert body["review_note"] == "Checking the cited evidence."
    assert body["reviewed_by_mask"].startswith("de_")
    actions = [entry["action"] for entry in body["history"]]
    assert actions == ["created", "status_changed", "note_added"]
    changed = body["history"][1]
    assert changed["status_from"] == "open" and changed["status_to"] == "reviewing"

    same = client.patch(f"/portal/reports/{created['report_id']}", json={"status": "reviewing"})
    assert same.status_code == 422
    assert same.json()["detail"]["error_code"] == "REPORT_STATUS_UNCHANGED"


def test_update_requires_a_change(env):
    client, store, reports, accounts, identity = env
    seed_user(store)
    seed_completed(store)
    created = submit_report(client).json()
    as_de(identity)
    seed_de(accounts)
    response = client.patch(f"/portal/reports/{created['report_id']}", json={})
    assert response.status_code == 422


def test_missing_report_is_not_found(env):
    client, store, reports, accounts, identity = env
    as_de(identity)
    seed_de(accounts)
    assert client.get("/portal/reports/rpt_missing").status_code == 404
    patch = client.patch("/portal/reports/rpt_missing", json={"status": "reviewing"})
    assert patch.status_code == 404
