"""Regression tests for the corrected Poon reference implementation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


from app.pipeline.evidence_assessment.service import (
    AssessmentInputError,
    assess_claim,
    assess_evidence,
    assess_evidence_item,
    calculate_quality_score,
)
from app.pipeline.shared.models import (
    AssessmentResult,
    ClaimAnalysis,
    EvidenceCandidate,
    RetrievalResult,
)


SAMPLES_PATH = Path(__file__).parents[4] / "sprint_1_samples" / (
    "04_poon_assessment_samples.json"
)


def _samples() -> list[dict]:
    return json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))["samples"]


def _claim(text: str, *, checkable: bool = True) -> ClaimAnalysis:
    return ClaimAnalysis(
        extracted_claim=text if checkable else None,
        claim_category="factual" if checkable else "opinion",
        checkable=checkable,
        classification_reason="Test claim.",
        claim_confidence=0.90,
    )


def _evidence(
    evidence_id: str,
    passage: str,
    *,
    source_type: str = "government",
    retrieval_score: float = 0.90,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "title": f"Source {evidence_id}",
        "url": f"https://example.test/{evidence_id}",
        "publisher": f"Publisher {evidence_id}",
        "published_at": "2026-08-20",
        "passage": passage,
        "source_type": source_type,
        "retrieval_score": retrieval_score,
        "retrieved_at": "2026-08-21T00:00:00Z",
    }


@pytest.mark.parametrize(
    "sample",
    _samples(),
    ids=lambda sample: sample["scenario_id"],
)
def test_shared_samples_keep_core_contract_and_outcome(sample: dict) -> None:
    result = assess_claim(
        sample["input"]["claim_analysis"],
        sample["input"]["retrieval_result"],
    )
    validated = AssessmentResult.model_validate(result)
    expected = sample["expected_output"]

    assert validated.concern_label == expected["concern_label"]
    assert (
        validated.misinformation_risk_score
        == expected["misinformation_risk_score"]
    )
    assert [item.stance for item in validated.assessed_evidence] == [
        item["stance"] for item in expected["assessed_evidence"]
    ]


def test_pipeline_boundary_accepts_and_returns_shared_models() -> None:
    sample = _samples()[0]["input"]
    claim = ClaimAnalysis.model_validate(sample["claim_analysis"])
    retrieval = RetrievalResult.model_validate(sample["retrieval_result"])

    result = assess_evidence(claim, retrieval)

    assert isinstance(result, AssessmentResult)
    assert result.concern_label == "High Concern"


def test_tuesday_claim_never_mentions_monday() -> None:
    claim = _claim("The community event begins on Tuesday.")
    retrieval = RetrievalResult.model_validate(
        {
            "retrieval_status": "completed",
            "warnings": [],
            "evidence": [
                _evidence(
                    "neutral",
                    "The community event includes food stalls.",
                )
            ],
        }
    )

    result = assess_evidence(claim, retrieval)

    assert "Tuesday" in result.explanation
    assert "Monday" not in result.explanation


def test_explanation_attributes_contradiction_to_actual_source() -> None:
    claim = _claim("The community event begins on Monday.")
    retrieval = RetrievalResult.model_validate(
        {
            "retrieval_status": "completed",
            "warnings": [],
            "evidence": [
                _evidence(
                    "government-neutral",
                    "The community event includes food stalls.",
                    source_type="government",
                ),
                _evidence(
                    "news-contradiction",
                    "The community event begins on Friday.",
                    source_type="news",
                ),
            ],
        }
    )

    result = assess_evidence(claim, retrieval)

    assert result.concern_label == "High Concern"
    assert result.explanation == (
        "The cited evidence contradicts the submitted claim."
    )
    assert "government" not in result.explanation.lower()


def test_uncertainty_uses_useful_evidence_not_first_evidence() -> None:
    claim = _claim("The community event begins on Monday.")
    retrieval = RetrievalResult.model_validate(
        {
            "retrieval_status": "completed",
            "warnings": [],
            "evidence": [
                _evidence(
                    "government-neutral",
                    "The community event includes food stalls.",
                    source_type="government",
                    retrieval_score=0.99,
                ),
                _evidence(
                    "news-contradiction",
                    "The community event begins on Friday.",
                    source_type="news",
                    retrieval_score=0.90,
                ),
            ],
        }
    )

    result = assess_evidence(claim, retrieval)

    assert result.uncertainty == "High"
    assert result.uncertainty_reasons == [
        "Only one limited-quality relevant source was found."
    ]


def test_tax_amount_reason_does_not_invent_a_start_event() -> None:
    item = EvidenceCandidate.model_validate(
        _evidence("tax", "The tax rate is not $500.")
    )

    result = assess_evidence_item("The tax rate is $500.", item)

    assert result.stance == "contradicting"
    assert "will not begin" not in result.assessment_reason
    assert result.assessment_reason == (
        "The passage reverses the claim's positive or negative meaning."
    )


def test_neutral_quality_is_a_cap_not_an_automatic_score() -> None:
    zero_relevance = EvidenceCandidate.model_validate(
        _evidence(
            "zero",
            "A related passage.",
            source_type="other",
            retrieval_score=0.0,
        )
    )
    strong_relevance = EvidenceCandidate.model_validate(
        _evidence(
            "strong",
            "A related passage.",
            source_type="government",
            retrieval_score=0.99,
        )
    )

    assert calculate_quality_score(zero_relevance, "neutral") == 0.0
    assert calculate_quality_score(strong_relevance, "neutral") == 0.45


def test_failed_retrieval_is_not_reported_as_no_evidence() -> None:
    claim = _claim("A new policy begins tomorrow.")
    retrieval = RetrievalResult(
        retrieval_status="failed",
        evidence=[],
        warnings=["Evidence service unavailable."],
    )

    with pytest.raises(AssessmentInputError):
        assess_evidence(claim, retrieval)
