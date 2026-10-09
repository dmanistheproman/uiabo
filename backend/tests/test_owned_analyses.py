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
from app.pipeline.shared.models import EvidenceProvenance, FailedAnalysisRecord, TextAnalysisResult


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


def test_source_provenance_survives_submit_history_and_idempotent_replay(context):
    client, store, _, pipeline = context
    original_analyze = pipeline.analyze
    def analyze(text):
        result = original_analyze(text)
        result.evidence[0].provenance = EvidenceProvenance(source_policy="government_namespace",
            source_reason="Restricted government namespace.", origin_group="gov", discovery_method="web_search",
            relevance="direct", relevance_reason="The passage addresses the claim.",
            relevance_quote=result.evidence[0].passage, applicability="established",
            applicability_reason="Same scope and applicable period.")
        return result
    pipeline.analyze = analyze
    first = submit(client)
    assert first.status_code == 200
    body = first.json()
    result_id = body["result_id"]
    provenance = body["evidence"][0]["provenance"]
    assert provenance["source_policy"] == "government_namespace"
    assert store.documents["analysis_results", result_id]["evidence"][0]["provenance"] == provenance
    assert client.get(f"/analysis/results/{result_id}").json()["evidence"][0]["provenance"] == provenance
    assert submit(client).json() == body
    assert pipeline.calls == 1


def test_idempotency_key_cannot_be_reused_for_different_text(context):
    client, _, _, _ = context
    assert submit(client).status_code == 200
    assert submit(client, text="Different claim.").status_code == 409


@pytest.mark.parametrize("version,status", [("evidence-v2", None), ("evidence-v3", "evidence_based")])
def test_scoring_summary_survives_storage_history_and_replay(context, version, status):
    from app.pipeline.shared.models import ScoringSummary
    client, store, _, pipeline = context
    original_analyze = pipeline.analyze
    def analyze(text):
        result = original_analyze(text)
        result.misinformation_risk_score = 97
        result.assessment_outcome = "contradicted"
        result.scoring = ScoringSummary(version=version, status=status,
            evidence_strength="Strong", contradicting_strength=.94,
            contradicting_origins=1, reasons=["A directly applicable source contradicts the claim."])
        return result
    pipeline.analyze = analyze
    first = submit(client)
    assert first.status_code == 200
    result = first.json()
    saved = client.get(f"/analysis/results/{result['result_id']}").json()
    history = client.get('/analysis/results').json()['results'][0]
    assert saved['scoring'] == history['scoring'] == result['scoring']
    assert saved['misinformation_risk_score'] == 97
    assert submit(client).json() == result
    assert pipeline.calls == 1


@pytest.mark.parametrize("outcome", ["supported", "contradicted", "conflicting", "insufficient_evidence"])
def test_credibility_contract_survives_api_history_storage_and_replay(context, outcome):
    from app.pipeline.shared.credibility import build_credibility
    from app.pipeline.shared.models import ScoringSummary
    client, store, _, pipeline = context
    original_analyze = pipeline.analyze

    def analyze(text):
        value = original_analyze(text).model_dump()
        s = .94 if outcome in {"supported", "conflicting"} else 0
        c = .94 if outcome in {"contradicted", "conflicting"} else 0
        value.update(assessment_outcome=outcome,
            concern_label={"supported": "Low Concern", "contradicted": "High Concern",
                "conflicting": "Needs Caution", "insufficient_evidence": "Not Enough Information"}[outcome],
            misinformation_risk_score=round(50 * (1 - s + c)) if s or c else None,
            scoring=ScoringSummary(version="evidence-v4", status="evidence_based" if s or c else "provisional",
                evidence_strength="Strong" if s or c else "Insufficient", supporting_strength=s,
                contradicting_strength=c, supporting_origins=int(bool(s)), contradicting_origins=int(bool(c)),
                reasons=["Applicable fixture evidence."]))
        result = TextAnalysisResult.model_validate(value)
        return TextAnalysisResult.model_validate({**result.model_dump(), "credibility": build_credibility(result)})

    pipeline.analyze = analyze
    response = submit(client)
    assert response.status_code == 200, response.text
    result = response.json()
    result_id = result["result_id"]
    expected = {"supported": 97, "contradicted": 3, "conflicting": 50, "insufficient_evidence": None}[outcome]
    assert result["credibility"]["score"] == expected
    for item in [client.get(f"/analysis/results/{result_id}").json(),
                 client.get("/analysis/results").json()["results"][0],
                 store.documents["analysis_results", result_id], submit(client).json()]:
        assert item["credibility"] == result["credibility"]
    assert pipeline.calls == 1
    assert store.documents["usage_allowances", "analysis-user"]["successful_submissions"] == 1


@pytest.mark.parametrize("outcome", ["insufficient_evidence", "unsupported"])
@pytest.mark.parametrize("version,score", [("evidence-v3", 50), ("evidence-v4", None)])
def test_provisional_factual_score_survives_storage_history_and_replay(context, outcome, version, score):
    from app.pipeline.evidence_assessment.scoring import provisional_summary
    client, store, _, pipeline = context
    original_analyze = pipeline.analyze

    def analyze(text):
        value = original_analyze(text).model_dump()
        value.update(concern_label="Not Enough Information", misinformation_risk_score=score,
            assessment_outcome=outcome, evidence=[],
            scoring={**provisional_summary("No applicable evidence establishes the claim.").model_dump(), "version": version})
        return TextAnalysisResult.model_validate(value)

    pipeline.analyze = analyze
    response = submit(client)
    assert response.status_code == 200, response.text
    result = response.json()
    result_id = result["result_id"]
    saved = client.get(f"/analysis/results/{result_id}").json()
    history = client.get("/analysis/results").json()["results"][0]
    stored = store.documents["analysis_results", result_id]
    for item in [result, saved, history, stored]:
        assert item["misinformation_risk_score"] == score
        assert item["assessment_outcome"] == outcome
        assert item["scoring"]["version"] == version
        assert item["scoring"]["status"] == "provisional"
        assert item["scoring"]["supporting_strength"] == item["scoring"]["contradicting_strength"] == 0
    assert submit(client).json() == result
    assert pipeline.calls == 1
    assert store.documents["usage_allowances", "analysis-user"]["successful_submissions"] == 1


@pytest.mark.parametrize("with_summary", [False, True])
def test_legacy_unresolved_saved_results_and_replays_are_not_rescored(context, with_summary):
    from copy import deepcopy
    client, store, _, pipeline = context
    first = submit(client).json()
    result_id = first["result_id"]
    record = store.documents["analysis_results", result_id]
    record.update(concern_label="Not Enough Information", misinformation_risk_score=None,
                  assessment_outcome="insufficient_evidence")
    record.pop("scoring", None)
    if with_summary:
        record["scoring"] = {"version": "evidence-v2", "evidence_strength": "Insufficient",
                             "reasons": ["Legacy unresolved check."]}
    original_record = deepcopy(record)
    results = [client.get(f"/analysis/results/{result_id}").json(),
               client.get("/analysis/results").json()["results"][0], submit(client).json()]
    for result in results:
        assert result["misinformation_risk_score"] is None
        if with_summary:
            assert all(result["scoring"][key] == value for key, value in record["scoring"].items())
        else:
            assert result.get("scoring") is None
        assert not (result.get("scoring") or {}).get("status")
    assert store.documents["analysis_results", result_id] == original_record
    assert pipeline.calls == 1
    assert store.documents["usage_allowances", "analysis-user"]["successful_submissions"] == 1


def test_policy_context_survives_storage_history_and_replay(context):
    from app.pipeline.shared.models import PolicyContext
    client, _, _, pipeline = context
    original_analyze = pipeline.analyze
    def analyze(text):
        result = original_analyze(text)
        result.policy_context = PolicyContext(
            published_policy_summary="The cited official rule differs from the alleged change.",
            change_status="contradicted", change_summary="The applicable source contradicts this change.",
            evidence_ids=[result.evidence[0].evidence_id])
        return result
    pipeline.analyze = analyze
    response = submit(client)
    assert response.status_code == 200
    result = response.json()
    saved = client.get(f"/analysis/results/{result['result_id']}").json()
    history = client.get('/analysis/results').json()['results'][0]
    assert saved['policy_context'] == history['policy_context'] == result['policy_context']
    assert submit(client).json() == result
    assert pipeline.calls == 1


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


@pytest.mark.parametrize("has_evidence", [True, False])
def test_component_result_survives_submission_history_and_replay(context, monkeypatch, has_evidence):
    from app.pipeline.evidence_assessment import components as component_stage
    from app.pipeline.evidence_assessment.pool import assess_pool_evidence
    from app.pipeline.input_preparation.service import prepare_text
    from app.pipeline.orchestration.service import PipelineOrchestrator
    from app.pipeline.orchestration.repository import InMemoryResultRepository
    from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, RetrievalResult
    client, store, _, pipeline = context
    text = "The council is closing the bridge because inspectors found severe structural damage."
    source = EvidenceCandidate(evidence_id="inspection", title="Synthetic inspection report",
        url="https://synthetic.example/inspection", publisher="Synthetic council",
        source_type="government", retrieval_score=.94, retrieved_at="2026-10-08T00:00:00Z",
        passage="Inspectors examined this bridge today and found no structural damage.")
    async def judge(claim, parts, evidence):
        return {key: component_stage.Draft(stance="contradicting" if part.component_id == "premise" else "unresolved",
            basis="direct" if part.component_id == "premise" else "none",
            scope="established" if part.component_id == "premise" else "unknown",
            decisiveness=.9, explanation="Synthetic inspection addresses the alleged structural damage.")
            for key,(part,_) in component_stage.pairs_for(parts,evidence).items()}, "oss"
    monkeypatch.setattr(component_stage, "judge_components", judge)
    runner = PipelineOrchestrator(prepare_input=prepare_text,
        analyze_claim=lambda _: ClaimAnalysis(extracted_claim=text, claim_category="factual", checkable=True,
            classification_reason="Synthetic check", claim_confidence=1),
        retrieve_evidence=lambda _: RetrievalResult(retrieval_status="completed" if has_evidence else "no_evidence",
            evidence=[source] if has_evidence else []),
        assess_evidence=assess_pool_evidence, repository=InMemoryResultRepository(),
        clock=lambda: datetime(2026,10,8,tzinfo=timezone.utc))
    def analyze(value):
        pipeline.calls += 1
        return runner.analyze(value)
    pipeline.analyze=analyze
    response=submit(client,text=text)
    assert response.status_code == 200, response.text
    body=response.json()
    assert body['credibility']['version'] == 'credibility-v2'
    assert body['credibility']['label'] == ('Likely misinformation' if has_evidence else 'Not enough evidence')
    assert body['component_assessment']['finding'] == ('material_contradiction' if has_evidence else 'unresolved')
    assert len(body['component_assessment']['components']) == 3
    result_id=body['result_id']
    for saved in [client.get(f"/analysis/results/{result_id}").json(),
                  client.get('/analysis/results').json()['results'][0],
                  store.documents['analysis_results',result_id], submit(client,text=text).json()]:
        assert saved['component_assessment'] == body['component_assessment']
        assert saved['credibility'] == body['credibility']
    assert pipeline.calls == 1
    assert store.documents['usage_allowances','analysis-user']['successful_submissions'] == 1
