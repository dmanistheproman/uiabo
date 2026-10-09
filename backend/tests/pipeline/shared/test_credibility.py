"""Credibility meaning, sufficiency gate, labels and persisted contract."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.pipeline.shared.credibility import build_credibility
from app.pipeline.shared.models import ScoringSummary, TextAnalysisResult


def record(s=0, c=0, **changes):
    outcome = "conflicting" if s and c else "supported" if s else "contradicted" if c else "insufficient_evidence"
    summary = ScoringSummary(version="evidence-v4", status="evidence_based" if s or c else "provisional",
        evidence_strength="Strong" if max(s, c) >= .9 else "Moderate" if s or c else "Insufficient",
        supporting_strength=s, contradicting_strength=c,
        supporting_origins=int(bool(s)), contradicting_origins=int(bool(c)), reasons=["Fixture evidence."])
    return SimpleNamespace(**dict(dict(assessment_outcome=outcome, scoring=summary, checkable=True,
        concern_label="Needs Caution" if s and c else "Low Concern" if s else "High Concern" if c else "Not Enough Information"), **changes))


@pytest.mark.parametrize("s,c,score,label", [
    (.94, 0, 97, "Strong evidence this is true"),
    (.70, 0, 85, "Evidence suggests this is true"),
    (.94, .94, 50, "Mixed evidence"),
    (0, .70, 15, "Likely misinformation"),
    (0, .94, 3, "Strong evidence this is false"),
    (1, .60, 70, "Mixed evidence"),
    (.60, 1, 30, "Mixed evidence"),
    (1, 0, 100, "Strong evidence this is true"),
    (0, 1, 0, "Strong evidence this is false"),
    (.93, 0, 96, "Strong evidence this is true"),
    (0, .93, 4, "Strong evidence this is false"),
])
def test_rated_labels_follow_evidence_not_equal_score_buckets(s, c, score, label):
    rating = build_credibility(record(s, c))
    assert rating.score == score
    assert rating.label == label
    assert rating.status == "rated"
    assert "not a percentage probability" in rating.explanation


def test_missing_evidence_is_not_balanced_evidence():
    unknown = build_credibility(record())
    balanced = build_credibility(record(.8, .8))
    assert unknown.score is None and unknown.label == "Not enough evidence"
    assert balanced.score == 50 and balanced.label == "Mixed evidence"


def test_one_sided_strength_is_continuous_and_moves_in_correct_direction():
    support = [build_credibility(record(q)).score for q in (.60, .70, .80, .90, 1)]
    contradiction = [build_credibility(record(0, q)).score for q in (.60, .70, .80, .90, 1)]
    assert support == [80, 85, 90, 95, 100]
    assert contradiction == [20, 15, 10, 5, 0]


@pytest.mark.parametrize("changes,status", [
    ({"scoring": None, "assessment_outcome": "supported", "concern_label": "Low Concern"}, "legacy_unrated"),
    ({"checkable": False, "assessment_outcome": "not_checkable"}, "not_applicable"),
    ({"assessment_outcome": "unsupported"}, "insufficient_evidence"),
    ({"assessment_outcome": "highly_unlikely"}, "plausibility_only"),
])
def test_non_numeric_findings_do_not_gain_scores(changes, status):
    rating = build_credibility(record(**changes))
    assert rating.status == status and rating.score is None


def test_insufficient_legacy_metadata_is_not_reverse_scored():
    assert build_credibility(record(.2)).score is None
    item = record(.9)
    item.scoring.supporting_origins = 0
    assert build_credibility(item).score is None


def final_payload():
    value = json.loads((Path(__file__).parents[2] / "fixtures/sprint_1/text_analysis_result.json").read_text())
    item = record(0, .94)
    value.update(assessment_outcome=item.assessment_outcome, concern_label=item.concern_label,
        misinformation_risk_score=97, scoring=item.scoring.model_dump())
    value["credibility"] = build_credibility(TextAnalysisResult.model_validate(value)).model_dump()
    return value


def test_credibility_survives_json_roundtrip_without_changing_legacy_risk():
    result = TextAnalysisResult.model_validate(final_payload())
    restored = TextAnalysisResult.model_validate_json(result.model_dump_json())
    assert restored.credibility == result.credibility
    assert restored.credibility.score == 3
    assert restored.misinformation_risk_score == 97


def test_saved_v1_labels_and_explanations_are_not_rewritten():
    item = record(0, .7)
    previous = build_credibility(item, version="credibility-v1")
    item.credibility = previous
    assert previous.label == "Evidence suggests this is false"
    assert build_credibility(item) == previous
    assert build_credibility(item, version="credibility-v2").label == "Likely misinformation"


@pytest.mark.parametrize("changes", [
    {"score": 97}, {"score": None}, {"score": 3.0}, {"score": "3"},
    {"label": "Strong evidence this is true"}, {"status": "insufficient_evidence"},
    {"version": "unknown"}, {"explanation": "Definitely false, guaranteed."},
])
def test_result_rejects_inconsistent_public_rating(changes):
    value = final_payload()
    value["credibility"].update(changes)
    with pytest.raises(ValidationError):
        TextAnalysisResult.model_validate(value)
