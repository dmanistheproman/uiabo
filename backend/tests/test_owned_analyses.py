from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.analyses.store import InMemoryAnalysisStore, MemorySession, get_analysis_store
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.main import app
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import FailedAnalysisRecord, TextAnalysisResult


FIXTURE = json.loads((Path(__file__).parent / "fixtures/sprint_1/text_analysis_result.json").read_text())
TEXT = "A new community tax starts next week."


class SuccessfulPipeline:
    def __init__(self):
        self.calls = 0
    def with_repository(self, repository):
        return self
    def analyze(self, text):
        self.calls += 1
        return TextAnalysisResult.model_validate({**FIXTURE, "original_text": text})


@pytest.fixture
def context(signed_analysis):
    pipeline = SuccessfulPipeline()
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    with TestClient(app) as client:
        yield client, *signed_analysis, pipeline


def submit(client, key="first", text=TEXT):
    return client.post("/analysis/text", json={"text": text, "user_id": "attacker-choice"}, headers={"Idempotency-Key": key})


def test_result_saved_with_owner_and_allowance_charged_once(context):
    client, store, _, pipeline = context
    first = submit(client)
    second = submit(client)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert pipeline.calls == 1
    result_id = first.json()["result_id"]
    assert store.documents["analysis_results", result_id]["user_id"] == "analysis-user"
    assert store.documents["usage_allowances", "analysis-user"]["successful_submissions"] == 1
    assert submit(client, "second").status_code == 429
    assert pipeline.calls == 1


def test_idempotency_key_cannot_be_reused_for_different_text(context):
    client, _, _, _ = context
    assert submit(client).status_code == 200
    assert submit(client, text="Different claim.").status_code == 409


def test_other_user_cannot_list_or_open_result(context):
    client, store, identity, _ = context
    result = submit(client).json()
    assert client.get("/analysis/results").json()["results"][0]["result_id"] == result["result_id"]
    identity["user"] = AuthenticatedUser(uid="other-user", email="other@example.com", email_verified=True)
    store.documents["users", "other-user"] = {"uid": "other-user", "role": "free", "account_status": "active"}
    assert client.get("/analysis/results").json()["results"] == []
    assert client.get(f"/analysis/results/{result['result_id']}").status_code == 404
    assert client.get(f"/analysis/results?cursor={result['result_id']}").status_code == 404


def test_unverified_and_suspended_users_are_blocked(context):
    client, store, identity, pipeline = context
    identity["user"] = identity["user"].model_copy(update={"email_verified": False})
    assert submit(client).status_code == 403
    identity["user"] = identity["user"].model_copy(update={"email_verified": True})
    store.documents["users", "analysis-user"]["account_status"] = "suspended"
    assert submit(client).status_code == 403
    assert client.get("/analysis/results").status_code == 403
    assert pipeline.calls == 0


def test_unauthenticated_requests_cannot_check_or_read():
    with TestClient(app) as client:
        assert submit(client).status_code == 401
        assert client.get("/analysis/results").status_code == 401


def test_provider_failure_is_saved_without_charging(context):
    client, store, _, pipeline = context
    def failure(text):
        raise PipelineComponentError("Search unavailable.", error_code="SEARCH_FAILED", stage="evidence_retrieval")
    pipeline.analyze = failure
    assert submit(client).status_code == 503
    assert store.documents["usage_allowances", "analysis-user"]["remaining_submissions"] == 1
    assert client.get("/analysis/results").json()["results"][0]["processing_status"] == "failed"
    assert submit(client).status_code == 409
    assert submit(client, "retry").status_code == 503
    assert ("analysis_locks", "analysis-user") not in store.documents


def test_midnight_singapore_resets_free_allowance(context):
    client, store, _, _ = context
    now = datetime(2026, 9, 7, 15, 59, tzinfo=timezone.utc)
    store.clock = lambda: now
    assert submit(client).status_code == 200
    assert submit(client, "again").status_code == 429
    now += timedelta(minutes=2)
    assert submit(client, "tomorrow").status_code == 200
    assert store.documents["usage_allowances", "analysis-user"]["successful_submissions"] == 1


def test_concurrent_reservations_only_allow_one_active_check(signed_analysis):
    store, _ = signed_analysis
    def reserve(index):
        try:
            store.reserve("analysis-user", str(index), TEXT)
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=4) as executor:
        statuses = list(executor.map(reserve, range(4)))
    assert sorted(statuses) == [200, 409, 409, 409]


def test_expired_worker_cannot_commit_or_release_new_worker(signed_analysis):
    store, _ = signed_analysis
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    store.clock = lambda: now
    old = store.reserve("analysis-user", "old", TEXT)
    now += timedelta(minutes=6)
    current = store.reserve("analysis-user", "current", TEXT)
    with pytest.raises(HTTPException):
        store.finish("analysis-user", old, TextAnalysisResult.model_validate(FIXTURE))
    store.release("analysis-user", old)
    assert store.documents["analysis_locks", "analysis-user"]["token"] == current["token"]


def test_result_and_allowance_writes_roll_back_together(signed_analysis, monkeypatch):
    store, _ = signed_analysis
    reservation = store.reserve("analysis-user", "first", TEXT)
    original = MemorySession.set
    def broken(self, collection, document, value):
        if collection == "analysis_results":
            raise RuntimeError("Simulated write failure")
        return original(self, collection, document, value)
    monkeypatch.setattr(MemorySession, "set", broken)
    with pytest.raises(RuntimeError):
        store.finish("analysis-user", reservation, TextAnalysisResult.model_validate(FIXTURE))
    assert store.documents["usage_allowances", "analysis-user"]["remaining_submissions"] == 1
    assert ("analysis_results", reservation["result_id"]) not in store.documents


def test_history_pagination_is_stable_for_equal_timestamps(signed_analysis):
    store, _ = signed_analysis
    for index in range(3):
        data = {**FIXTURE, "result_id": f"{index:032x}", "user_id": "analysis-user", "created_at": datetime(2026, 9, 7, tzinfo=timezone.utc)}
        store.documents["analysis_results", data["result_id"]] = data
    first = store.history("analysis-user", limit=2)
    second = store.history("analysis-user", limit=2, cursor=first["next_cursor"])
    assert len(first["results"]) == 2 and len(second["results"]) == 1
    assert second["next_cursor"] is None
    assert len({item["result_id"] for item in first["results"] + second["results"]}) == 3


def test_not_enough_information_is_completed_and_charged(context):
    client, store, _, pipeline = context
    pipeline.analyze = lambda text: TextAnalysisResult.model_validate({**FIXTURE,
        "concern_label": "Not Enough Information", "misinformation_risk_score": None})
    assert submit(client).status_code == 200
    assert store.documents["usage_allowances", "analysis-user"]["remaining_submissions"] == 0


def test_premium_role_grants_monthly_60_and_resets_at_month_boundary(context):
    client, store, _, _ = context
    now = datetime(2026, 9, 30, 15, 59, tzinfo=timezone.utc)
    store.clock = lambda: now
    store.documents["users", "analysis-user"]["role"] = "premium"
    assert submit(client).status_code == 200
    allowance = store.documents["usage_allowances", "analysis-user"]
    assert allowance["remaining_submissions"] == 59 and allowance["submission_limit"] == 60
    assert allowance["period_type"] == "monthly"
    now += timedelta(minutes=2)
    assert submit(client, "next-month").status_code == 200
    assert store.documents["usage_allowances", "analysis-user"]["successful_submissions"] == 1


def test_client_cannot_choose_premium_role_or_quota(context):
    client, store, _, _ = context
    assert client.post('/analysis/text', json={'text': TEXT, 'role': 'premium', 'submission_limit': 60}).status_code == 200
    assert store.documents["users", "analysis-user"]["role"] == "free"
    assert store.documents["usage_allowances", "analysis-user"]["remaining_submissions"] == 0
