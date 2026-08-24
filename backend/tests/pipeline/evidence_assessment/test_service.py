"""Tests for Poon's Sprint 1 evidence-assessment component.

The shared Poon fixture is used directly so field names and expected sample
behaviour stay aligned with the team interface.  Additional tests cover mixed
and failed retrieval cases that are not in the shared sample file.
"""

import json
from pathlib import Path

import pytest

from app.pipeline.evidence_assessment.service import (
    assess_claim,
    calculate_quality_score,
    classify_stance,
)


SAMPLES_PATH = (
    Path(__file__).parents[4]
    / "sprint_1_samples"
    / "04_poon_assessment_samples.json"
)


def _load_samples() -> list[dict]:
    with SAMPLES_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)["samples"]


SAMPLES = _load_samples()


@pytest.mark.parametrize(
    "sample",
    SAMPLES,
    ids=[sample["scenario_id"] for sample in SAMPLES],
)
def test_shared_sprint_1_samples(sample: dict) -> None:
    """The five agreed Poon samples must pass unchanged."""
    actual = assess_claim(
        sample["input"]["claim_analysis"],
        sample["input"]["retrieval_result"],
    )

    assert actual == sample["expected_output"]


class TestStanceRules:
    def test_supporting(self) -> None:
        assert classify_stance(
            "The event begins on Monday.",
            "The official schedule says the event begins on Monday.",
        ) == "supporting"

    def test_contradicting_day(self) -> None:
        assert classify_stance(
            "The event begins on Monday.",
            "The official schedule says the event begins on Friday.",
        ) == "contradicting"

    def test_contradicting_amount(self) -> None:
        assert classify_stance(
            "The support payment is $300.",
            "The support payment is $500.",
        ) == "contradicting"

    def test_neutral_related_passage(self) -> None:
        assert classify_stance(
            "The community event begins on Monday.",
            "The community event will include food stalls and performances.",
        ) == "neutral"


class TestQualityRules:
    def test_high_relevance_government_source(self) -> None:
        evidence = {
            "source_type": "government",
            "retrieval_score": 0.96,
            "published_at": "2026-08-12",
        }
        assert calculate_quality_score(evidence, "supporting") == 0.94

    def test_neutral_is_capped(self) -> None:
        evidence = {
            "source_type": "government",
            "retrieval_score": 0.99,
            "published_at": "2026-08-12",
        }
        assert calculate_quality_score(evidence, "neutral") == 0.45


class TestSafeExitAndMixedEvidence:
    def test_failed_retrieval_returns_no_score(self) -> None:
        claim = {
            "extracted_claim": "A new policy starts tomorrow.",
            "claim_category": "factual",
            "checkable": True,
            "classification_reason": "This is checkable.",
            "claim_confidence": 0.80,
        }
        retrieval = {
            "retrieval_status": "failed",
            "evidence": [],
            "warnings": ["Evidence retrieval failed."],
        }

        result = assess_claim(claim, retrieval)

        assert result["concern_label"] == "Not Enough Information"
        assert result["misinformation_risk_score"] is None
        assert result["uncertainty"] == "High"
        assert result["uncertainty_reasons"] == ["Evidence retrieval failed."]

    def test_mixed_evidence_needs_caution_and_high_uncertainty(self) -> None:
        claim = {
            "extracted_claim": "The community event begins on Monday.",
            "claim_category": "factual",
            "checkable": True,
            "classification_reason": "The event date is checkable.",
            "claim_confidence": 0.90,
        }
        retrieval = {
            "retrieval_status": "completed",
            "evidence": [
                {
                    "evidence_id": "support-1",
                    "title": "Schedule A",
                    "url": "https://example.test/a",
                    "publisher": "Agency A",
                    "published_at": "2026-08-15",
                    "passage": "The community event begins on Monday.",
                    "source_type": "government",
                    "retrieval_score": 0.95,
                    "retrieved_at": "2026-08-20T10:00:00Z",
                },
                {
                    "evidence_id": "contradict-1",
                    "title": "Schedule B",
                    "url": "https://example.test/b",
                    "publisher": "News B",
                    "published_at": "2026-08-16",
                    "passage": "The community event begins on Friday.",
                    "source_type": "news",
                    "retrieval_score": 0.90,
                    "retrieved_at": "2026-08-20T10:01:00Z",
                },
            ],
            "warnings": [],
        }

        result = assess_claim(claim, retrieval)

        assert result["concern_label"] == "Needs Caution"
        assert 31 <= result["misinformation_risk_score"] <= 70
        assert result["uncertainty"] == "High"
        assert {item["stance"] for item in result["assessed_evidence"]} == {
            "supporting",
            "contradicting",
        }
