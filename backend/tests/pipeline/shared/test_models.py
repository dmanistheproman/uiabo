"""Tests that repository fixtures obey the shared component contracts."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.pipeline.shared.models import (
    AssessmentResult,
    ClaimAnalysis,
    PreparedText,
    RetrievalResult,
    TextAnalysisResult,
)


FIXTURE_DIRECTORY = Path(__file__).parents[2] / "fixtures" / "sprint_1"


def _fixture(name: str) -> dict:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.mark.parametrize(
    ("model", "filename"),
    [
        (PreparedText, "prepared_text.json"),
        (ClaimAnalysis, "claim_analysis.json"),
        (RetrievalResult, "retrieval_result.json"),
        (AssessmentResult, "assessment_result.json"),
        (AssessmentResult, "not_enough_information.json"),
        (TextAnalysisResult, "text_analysis_result.json"),
    ],
)
def test_shared_fixture_validates(model: type, filename: str) -> None:
    assert model.model_validate(_fixture(filename))


def test_checkable_claim_requires_extracted_claim() -> None:
    payload = _fixture("claim_analysis.json")
    payload["extracted_claim"] = None

    with pytest.raises(ValidationError):
        ClaimAnalysis.model_validate(payload)


def test_completed_retrieval_requires_evidence() -> None:
    payload = _fixture("retrieval_result.json")
    payload["evidence"] = []

    with pytest.raises(ValidationError):
        RetrievalResult.model_validate(payload)


def test_not_enough_information_requires_null_score() -> None:
    payload = _fixture("not_enough_information.json")
    payload["misinformation_risk_score"] = 50

    with pytest.raises(ValidationError):
        AssessmentResult.model_validate(payload)


def test_unknown_fields_are_rejected() -> None:
    payload = _fixture("prepared_text.json")
    payload["independent_field_change"] = True

    with pytest.raises(ValidationError):
        PreparedText.model_validate(payload)

