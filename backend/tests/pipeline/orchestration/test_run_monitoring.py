"""Monitoring records emitted by the text pipeline (no user content)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.pipeline.evidence_assessment.service import assess_evidence
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.run_recorder import InMemoryRunStore
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineComponentError


FIXTURE_DIRECTORY = Path(__file__).parents[2] / "fixtures" / "sprint_1"
FIXED_TIME = datetime(2026, 10, 7, 2, 0, 0, tzinfo=timezone.utc)


def _fixture(name: str) -> dict:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _orchestrator(store, *, analyze_claim=None, prepare_input=prepare_text) -> PipelineOrchestrator:
    claim = _fixture("claim_analysis.json")
    retrieval = _fixture("retrieval_result.json")
    assessment = _fixture("assessment_result.json")
    return PipelineOrchestrator(
        prepare_input=prepare_input,
        analyze_claim=analyze_claim or (lambda prepared: claim),
        retrieve_evidence=lambda analyzed_claim: retrieval,
        assess_evidence=lambda analyzed_claim, retrieved: assessment,
        repository=InMemoryResultRepository(),
        id_factory=lambda: "run-fixture-1",
        clock=lambda: FIXED_TIME,
        run_recorder=store.record,
    )


def test_completed_run_is_recorded_with_stage_timings():
    store = InMemoryRunStore()
    pipeline = _orchestrator(store)
    pipeline.analyze("A new $500 community tax starts next week.")
    assert len(store.runs) == 1
    record = store.runs["run-fixture-1"]
    assert record["status"] == "completed"
    assert record["input_type"] == "text"
    assert record["created_at"] == FIXED_TIME
    assert record["finished_at"] == FIXED_TIME
    assert record["duration_ms"] == 0
    assert set(record["stage_timings_ms"]) == {
        "input_preparation", "claim_analysis", "evidence_retrieval", "evidence_assessment",
    }
    assert all(value >= 0 for value in record["stage_timings_ms"].values())
    assert "original_text" not in record
    assert "extracted_claim" not in record


def test_failed_run_records_stage_and_error():
    store = InMemoryRunStore()

    def broken_claim(prepared):
        raise PipelineComponentError(
            "Claim analysis failed.", error_code="CLAIM_ANALYSIS_FAILED",
            stage="claim_analysis")

    pipeline = _orchestrator(store, analyze_claim=broken_claim)
    with pytest.raises(PipelineComponentError):
        pipeline.analyze("Some claim that never gets analysed.")
    record = store.runs["run-fixture-1"]
    assert record["status"] == "failed"
    assert record["failure_stage"] == "claim_analysis"
    assert record["error_code"] == "CLAIM_ANALYSIS_FAILED"
    assert record["stage_timings_ms"]["input_preparation"] >= 0


def test_recorder_failure_never_breaks_analysis():
    def broken_recorder(record):
        raise RuntimeError("firestore down")

    claim = _fixture("claim_analysis.json")
    pipeline = PipelineOrchestrator(
        prepare_input=prepare_text,
        analyze_claim=lambda prepared: claim,
        retrieve_evidence=lambda analyzed_claim: _fixture("retrieval_result.json"),
        assess_evidence=lambda analyzed_claim, retrieved: _fixture("assessment_result.json"),
        repository=InMemoryResultRepository(),
        id_factory=lambda: "run-fixture-1",
        clock=lambda: FIXED_TIME,
        run_recorder=broken_recorder,
    )
    result = pipeline.analyze("A new $500 community tax starts next week.")
    assert result.result_id == "run-fixture-1"


def test_with_repository_keeps_recorder():
    store = InMemoryRunStore()
    pipeline = _orchestrator(store).with_repository(InMemoryResultRepository())
    pipeline.analyze("A new $500 community tax starts next week.")
    assert len(store.runs) == 1


@pytest.mark.parametrize("storage_fails", [False, True])
def test_api_monitoring_uses_saved_id_and_waits_for_commit(signed_analysis, monkeypatch, storage_fails):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
    store, _ = signed_analysis
    runs = InMemoryRunStore()
    pipeline = _orchestrator(runs)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    finish = store.finish
    def guarded_finish(*args, **kwargs):
        assert not runs.runs, "Completion must not be published before persistence"
        if storage_fails:
            raise RuntimeError("Firestore unavailable")
        return finish(*args, **kwargs)
    monkeypatch.setattr(store, "finish", guarded_finish)
    response = TestClient(app).post('/analysis/text', json={'text':'A new $500 community tax starts next week.'},
                                    headers={'Idempotency-Key':'monitoring-test'})
    assert response.status_code == (503 if storage_fails else 200)
    assert len(runs.runs) == 1
    run = next(iter(runs.runs.values()))
    if storage_fails:
        assert run['status'] == 'failed' and run['failure_stage'] == 'persistence'
        assert not any(collection == 'analysis_results' for collection, _ in store.documents)
    else:
        assert run['run_id'] == response.json()['result_id']
        assert ('analysis_results',run['run_id']) in store.documents
