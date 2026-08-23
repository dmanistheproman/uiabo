"""Integration tests for Donovan's pipeline orchestration."""

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import (
    PipelineComponentError,
    PipelineContractError,
    PipelinePersistenceError,
    PipelineValidationError,
)
from app.pipeline.shared.models import (
    AssessmentResult,
    ClaimAnalysis,
    FailedAnalysisRecord,
    RetrievalResult,
    TextAnalysisResult,
)


FIXTURE_DIRECTORY = Path(__file__).parents[2] / "fixtures" / "sprint_1"
FIXED_TIME = datetime(2026, 8, 20, 10, 0, 5, tzinfo=timezone.utc)


def _fixture(name: str) -> dict:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _orchestrator(
    *,
    repository=None,
    prepare_input=prepare_text,
    analyze_claim=None,
    retrieve_evidence=None,
    assess_evidence=None,
) -> PipelineOrchestrator:
    claim = _fixture("claim_analysis.json")
    retrieval = _fixture("retrieval_result.json")
    assessment = _fixture("assessment_result.json")

    return PipelineOrchestrator(
        prepare_input=prepare_input,
        analyze_claim=analyze_claim or (lambda prepared: claim),
        retrieve_evidence=(
            retrieve_evidence or (lambda analyzed_claim: retrieval)
        ),
        assess_evidence=(
            assess_evidence
            or (lambda analyzed_claim, retrieved: assessment)
        ),
        repository=repository or InMemoryResultRepository(),
        id_factory=lambda: "fixture-result-tax-1",
        clock=lambda: FIXED_TIME,
    )


def test_complete_pipeline_assembles_and_saves_result() -> None:
    repository = InMemoryResultRepository()
    pipeline = _orchestrator(repository=repository)

    result = pipeline.analyze(
        "  A new $500 community tax starts next week.  "
    )

    assert result.processing_status == "completed"
    assert result.result_id == "fixture-result-tax-1"
    assert result.original_text.startswith("  ")
    assert result.extracted_claim == (
        "A new $500 community tax starts next week."
    )
    assert result.concern_label == "High Concern"
    assert result.misinformation_risk_score == 82
    assert result.evidence[0].stance == "contradicting"
    assert result.evidence[0].quality_score == 0.9
    assert repository.results[result.result_id] == result


def test_non_checkable_claim_skips_retrieval_and_assessment() -> None:
    repository = InMemoryResultRepository()
    calls = {"retrieval": 0, "assessment": 0}

    def retrieval_should_not_run(claim: ClaimAnalysis) -> None:
        del claim
        calls["retrieval"] += 1
        raise AssertionError("Retrieval should have been skipped.")

    def assessment_should_not_run(
        claim: ClaimAnalysis,
        retrieval: RetrievalResult,
    ) -> None:
        del claim, retrieval
        calls["assessment"] += 1
        raise AssertionError("Assessment should have been skipped.")

    pipeline = _orchestrator(
        repository=repository,
        analyze_claim=lambda prepared: {
            "extracted_claim": None,
            "claim_category": "opinion",
            "checkable": False,
            "classification_reason": "This is a personal preference.",
            "claim_confidence": 0.97,
        },
        retrieve_evidence=retrieval_should_not_run,
        assess_evidence=assessment_should_not_run,
    )

    result = pipeline.analyze(
        "Chicken rice is the best food in Singapore."
    )

    assert calls == {"retrieval": 0, "assessment": 0}
    assert result.concern_label == "Not Enough Information"
    assert result.misinformation_risk_score is None
    assert result.uncertainty == "High"
    assert result.evidence == []
    assert repository.results[result.result_id] == result


def test_no_evidence_skips_assessment_and_returns_no_score() -> None:
    repository = InMemoryResultRepository()

    def assessment_should_not_run(
        claim: ClaimAnalysis,
        retrieval: RetrievalResult,
    ) -> None:
        del claim, retrieval
        raise AssertionError("Assessment should have been skipped.")

    pipeline = _orchestrator(
        repository=repository,
        retrieve_evidence=lambda claim: {
            "retrieval_status": "no_evidence",
            "evidence": [],
            "warnings": [
                "No sufficiently relevant evidence was found."
            ],
        },
        assess_evidence=assessment_should_not_run,
    )

    result = pipeline.analyze(
        "A purple express bus route begins tomorrow."
    )

    assert result.concern_label == "Not Enough Information"
    assert result.misinformation_risk_score is None
    assert result.uncertainty == "High"
    assert result.evidence == []
    assert result.warnings == [
        "No sufficiently relevant evidence was found."
    ]


def test_failed_retrieval_is_not_reported_as_no_evidence() -> None:
    repository = InMemoryResultRepository()
    pipeline = _orchestrator(
        repository=repository,
        retrieve_evidence=lambda claim: {
            "retrieval_status": "failed",
            "evidence": [],
            "warnings": ["The search service timed out."],
        },
    )

    with pytest.raises(PipelineComponentError) as raised:
        pipeline.analyze("A new recycling rule begins next month.")

    assert raised.value.error_code == "RETRIEVAL_UNAVAILABLE"
    assert raised.value.http_status == 503
    assert raised.value.retryable is True
    failure = repository.failures["fixture-result-tax-1"]
    assert failure.processing_status == "failed"
    assert failure.failure_stage == "evidence_retrieval"


def test_component_not_ready_is_saved_as_a_failed_run() -> None:
    repository = InMemoryResultRepository()

    def unavailable(prepared) -> None:
        del prepared
        raise PipelineComponentError(
            "Claim analysis has not been integrated yet.",
            error_code="CLAIM_ANALYSIS_NOT_READY",
            stage="claim_analysis",
            retryable=False,
        )

    pipeline = _orchestrator(
        repository=repository,
        analyze_claim=unavailable,
    )

    with pytest.raises(PipelineComponentError) as raised:
        pipeline.analyze("A new community tax starts next week.")

    assert raised.value.error_code == "CLAIM_ANALYSIS_NOT_READY"
    assert repository.failures["fixture-result-tax-1"].retryable is False


def test_invalid_input_returns_validation_error_without_storage() -> None:
    repository = InMemoryResultRepository()
    pipeline = _orchestrator(repository=repository)

    with pytest.raises(PipelineValidationError) as raised:
        pipeline.analyze("     ")

    assert raised.value.error_code == "INVALID_TEXT"
    assert raised.value.http_status == 422
    assert repository.results == {}
    assert repository.failures == {}


def test_invalid_component_output_is_a_contract_error() -> None:
    repository = InMemoryResultRepository()
    pipeline = _orchestrator(
        repository=repository,
        analyze_claim=lambda prepared: {"unexpected": "output"},
    )

    with pytest.raises(PipelineContractError) as raised:
        pipeline.analyze("A new community tax starts next week.")

    assert raised.value.stage == "claim_analysis"
    assert raised.value.http_status == 500
    assert repository.failures["fixture-result-tax-1"].error_code == (
        "PIPELINE_CONTRACT_ERROR"
    )


def test_every_retrieved_item_requires_an_assessment() -> None:
    repository = InMemoryResultRepository()
    assessment = _fixture("assessment_result.json")
    assessment["assessed_evidence"] = []
    pipeline = _orchestrator(
        repository=repository,
        assess_evidence=lambda claim, retrieval: assessment,
    )

    with pytest.raises(PipelineContractError) as raised:
        pipeline.analyze("A new community tax starts next week.")

    assert raised.value.stage == "result_assembly"


def test_duplicate_warnings_are_returned_once() -> None:
    warning = "Synthetic fixture only."
    pipeline = _orchestrator(
        prepare_input=lambda text: {
            "original_text": text,
            "normalised_text": text,
            "language": "en",
            "warnings": [warning],
        },
        retrieve_evidence=lambda claim: {
            **_fixture("retrieval_result.json"),
            "warnings": [warning],
        },
    )

    result = pipeline.analyze("A new community tax starts next week.")

    assert result.warnings == [warning]


class AlwaysFailingRepository:
    def save_result(self, result: TextAnalysisResult) -> None:
        del result
        raise PipelinePersistenceError("Storage unavailable.")

    def save_failure(self, failure: FailedAnalysisRecord) -> None:
        del failure
        raise PipelinePersistenceError("Storage unavailable.")


def test_completed_result_must_be_saved() -> None:
    pipeline = _orchestrator(repository=AlwaysFailingRepository())

    with pytest.raises(PipelinePersistenceError) as raised:
        pipeline.analyze("A new community tax starts next week.")

    assert raised.value.error_code == "RESULT_STORAGE_FAILED"
    assert raised.value.retryable is True

