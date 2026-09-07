import json
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.orchestration.dependencies import (
    get_pipeline_orchestrator,
)
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import TextAnalysisResult


client = TestClient(app)
RESULT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "sprint_1"
    / "text_analysis_result.json"
)


@pytest.fixture(autouse=True)
def authenticated_analysis(signed_analysis):
    return signed_analysis


class SuccessfulPipeline:
    def with_repository(self, repository):
        return self
    def analyze(self, text: str) -> TextAnalysisResult:
        del text
        with RESULT_FIXTURE.open(encoding="utf-8") as handle:
            return TextAnalysisResult.model_validate(json.load(handle))


class UnavailablePipeline:
    def with_repository(self, repository):
        return self
    def analyze(self, text: str) -> TextAnalysisResult:
        del text
        raise PipelineComponentError(
            "Claim analysis has not been integrated yet.",
            error_code="CLAIM_ANALYSIS_NOT_READY",
            stage="claim_analysis",
            retryable=False,
        )


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok"
    }


def test_text_analysis():
    test_text = (
        "Singapore is introducing "
        "a new $500 tax next week."
    )

    app.dependency_overrides[get_pipeline_orchestrator] = (
        lambda: SuccessfulPipeline()
    )
    try:
        response = client.post(
            "/analysis/text",
            json={
                "text": test_text
            }
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    data = response.json()

    assert data["processing_status"] == "completed"
    assert data["extracted_claim"]
    assert data["concern_label"] == "High Concern"
    assert data["misinformation_risk_score"] == 82
    assert data["uncertainty"] == "Medium"
    assert data["result_id"]
    assert data["evidence"][0]["stance"] == "contradicting"


def test_pipeline_error_is_returned_as_structured_api_error():
    app.dependency_overrides[get_pipeline_orchestrator] = (
        lambda: UnavailablePipeline()
    )
    try:
        response = client.post(
            "/analysis/text",
            json={"text": "A test claim."},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "error_code": "CLAIM_ANALYSIS_NOT_READY",
            "message": "Claim analysis has not been integrated yet.",
            "stage": "claim_analysis",
            "retryable": False,
        }
    }
