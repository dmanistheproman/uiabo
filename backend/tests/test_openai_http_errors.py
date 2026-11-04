"""Provider failures retain safe HTTP details and the actual pipeline identity."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, PreparedText, RetrievalResult


VERSION = "experiment:verifier-openai:gpt-6.1-sol:reasoning-medium"
TEXT = "The community museum opens at nine."


@pytest.mark.parametrize("v3,verification,provider,code", [
    ("0", "true", "openai", "OPENAI_CONFIGURATION_INVALID"),
    ("1", "false", "openai", "OPENAI_CONFIGURATION_INVALID"),
    ("1", "true", "PRIVATE_INVALID_PROVIDER", "ASSESSMENT_CONFIGURATION_INVALID"),
])
def test_dependency_configuration_failure_is_a_safe_http_error(
        signed_analysis, monkeypatch, v3, verification, provider, code):
    store, _ = signed_analysis
    monkeypatch.setenv("EVIDENCE_PIPELINE_V3", v3)
    monkeypatch.setenv("EVIDENCE_VERIFICATION_ENABLED", verification)
    monkeypatch.setenv("EVIDENCE_VERIFICATION_PROVIDER", provider)
    monkeypatch.setenv("OPENAI_API_KEY", "PRIVATE_KEY_NEVER_PRINT")
    get_pipeline_orchestrator.cache_clear()
    try:
        response = TestClient(app).post("/analysis/text", json={"text": TEXT})
    finally:
        get_pipeline_orchestrator.cache_clear()
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert set(detail) == {"error_code", "message", "stage", "retryable"}
    assert detail["error_code"] == code
    assert detail["stage"] == "evidence_assessment"
    assert detail["retryable"] is False
    assert "PRIVATE_" not in response.text
    assert not any(collection in {"analysis_results", "usage_allowances", "analysis_locks"}
                   for collection, _ in store.documents)


def test_dependency_handler_preserves_status_and_hides_exception_context(signed_analysis):
    def unavailable():
        try:
            raise RuntimeError("PRIVATE_PROVIDER_RESPONSE")
        except RuntimeError as cause:
            raise PipelineComponentError("The assessment service is busy.",
                error_code="ASSESSMENT_BUSY", stage="evidence_assessment",
                http_status=429, retryable=True) from cause
    app.dependency_overrides[get_pipeline_orchestrator] = unavailable
    response = TestClient(app).post("/analysis/text", json={"text": TEXT})
    assert response.status_code == 429
    assert response.json() == {"detail": {
        "error_code": "ASSESSMENT_BUSY", "message": "The assessment service is busy.",
        "stage": "evidence_assessment", "retryable": True,
    }}
    assert "PRIVATE_" not in response.text


def failing_pipeline(runs):
    def assess(claim, retrieval):
        raise PipelineComponentError("OpenAI could not accept the assessment request.",
            error_code="OPENAI_REQUEST_REJECTED", stage="evidence_assessment", retryable=False)
    source = EvidenceCandidate(evidence_id="official-source", title="Museum opening hours",
        url="https://example.gov.sg/museum", publisher="Example Authority",
        passage="The community museum opens at nine each morning.", source_type="government",
        retrieval_score=.9, retrieved_at=datetime.now(timezone.utc))
    return PipelineOrchestrator(
        prepare_input=lambda text: PreparedText(original_text=text, normalised_text=text, language="en"),
        analyze_claim=lambda prepared: ClaimAnalysis(extracted_claim=prepared.normalised_text,
            claim_category="factual", checkable=True, classification_reason="A factual opening-hours claim.",
            claim_confidence=1),
        retrieve_evidence=lambda claim: RetrievalResult(retrieval_status="completed", evidence=[source]),
        assess_evidence=assess, repository=InMemoryResultRepository(),
        pipeline_version=VERSION, run_recorder=runs.append)


def test_failed_app_result_records_actual_model_without_charging_allowance(signed_analysis):
    store, _ = signed_analysis
    runs = []
    pipeline = failing_pipeline(runs)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    response = TestClient(app).post("/analysis/text", json={"text": TEXT},
                                    headers={"Idempotency-Key": "openai-failure"})
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "OPENAI_REQUEST_REJECTED"
    records = [value for (collection, _), value in store.documents.items()
               if collection == "analysis_results"]
    assert len(records) == 1
    assert records[0]["pipeline_version"] == VERSION
    assert records[0]["processing_status"] == "failed"
    assert records[0]["retryable"] is False
    allowance = store.documents["usage_allowances", "analysis-user"]
    assert allowance["successful_submissions"] == 0
    assert allowance["remaining_submissions"] == 1
    assert ("analysis_locks", "analysis-user") not in store.documents
    assert len(runs) == 1
    assert runs[0]["pipeline_version"] == VERSION
    assert runs[0]["status"] == "failed"


def test_pipeline_version_is_read_only_and_preserved_by_isolation():
    pipeline = failing_pipeline([])
    assert pipeline.pipeline_version == VERSION
    isolated = pipeline.with_repository(InMemoryResultRepository(), run_recorder=lambda _: None)
    assert isolated.pipeline_version == VERSION
    with pytest.raises(AttributeError):
        pipeline.pipeline_version = "wrong-provider"
