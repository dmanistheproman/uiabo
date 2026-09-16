"""Versioned score contracts for new assessments and unchanged saved results."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.pipeline.evidence_assessment.scoring import provisional_summary, unscored_summary
from app.pipeline.shared.models import AssessmentResult, ScoringSummary, TextAnalysisResult


FIXTURES = Path(__file__).parents[2] / "fixtures" / "sprint_1"
MODELS = [AssessmentResult, TextAnalysisResult]


def payload(model, *, outcome="insufficient_evidence", status="provisional"):
    name = "not_enough_information.json" if model is AssessmentResult else "text_analysis_result.json"
    value = json.loads((FIXTURES / name).read_text())
    value.update(concern_label="Not Enough Information", assessment_outcome=outcome,
                 misinformation_risk_score=50,
                 scoring=provisional_summary("No applicable evidence.").model_dump())
    if model is TextAnalysisResult:
        value["evidence"] = []
    if status == "not_applicable":
        value.update(assessment_outcome="not_checkable", misinformation_risk_score=None,
                     scoring=unscored_summary("No factual claim.").model_dump())
        if model is TextAnalysisResult:
            value.update(checkable=False, claim_category="opinion", extracted_claim=None)
    return value


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("outcome", ["insufficient_evidence", "unsupported"])
def test_completed_unresolved_claim_has_explicit_provisional_midpoint(model, outcome):
    result = model.model_validate(payload(model, outcome=outcome))
    assert result.misinformation_risk_score == 50
    assert result.assessment_outcome == outcome
    assert result.scoring.status == "provisional"
    assert result.scoring.supporting_strength == result.scoring.contradicting_strength == 0
    assert result.scoring.supporting_origins == result.scoring.contradicting_origins == 0


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("changes", [
    {"misinformation_risk_score": None}, {"misinformation_risk_score": 0},
    {"misinformation_risk_score": 49}, {"misinformation_risk_score": 51},
    {"assessment_outcome": "supported"}, {"assessment_outcome": "not_checkable"},
    {"assessment_outcome": None}, {"concern_label": "Needs Caution"},
])
def test_provisional_score_cannot_be_presented_as_an_evidence_verdict(model, changes):
    with pytest.raises(ValidationError):
        model.model_validate({**payload(model), **changes})


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("changes", [
    {"status": None}, {"status": "evidence_based"}, {"status": "not_applicable"},
    {"supporting_strength": .8}, {"contradicting_strength": .8},
    {"supporting_origins": 1}, {"contradicting_origins": 1},
    {"evidence_strength": "Strong"},
])
def test_provisional_summary_cannot_claim_decisive_evidence(model, changes):
    value = payload(model)
    value["scoring"].update(changes)
    with pytest.raises(ValidationError):
        model.model_validate(value)


@pytest.mark.parametrize("model", MODELS)
def test_nonfactual_input_is_explicitly_not_applicable(model):
    result = model.model_validate(payload(model, status="not_applicable"))
    assert result.scoring.version == "evidence-v3"
    assert result.scoring.status == "not_applicable"
    assert result.misinformation_risk_score is None


@pytest.mark.parametrize("checkable,status", [(False, "provisional"), (True, "not_applicable")])
def test_completed_result_checkability_must_match_score_status(checkable, status):
    value = payload(TextAnalysisResult, status=status)
    value.update(checkable=checkable, extracted_claim="A factual statement.")
    with pytest.raises(ValidationError):
        TextAnalysisResult.model_validate(value)


@pytest.mark.parametrize("model", MODELS)
def test_conflicting_evidence_at_fifty_remains_distinct_from_provisional_fifty(model):
    value = payload(model)
    value.update(concern_label="Needs Caution", assessment_outcome="conflicting")
    value["scoring"].update(status="evidence_based", evidence_strength="Strong",
        supporting_strength=.94, contradicting_strength=.94,
        supporting_origins=1, contradicting_origins=1)
    result = model.model_validate(value)
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "evidence_based"
    assert result.assessment_outcome == "conflicting"
    value["misinformation_risk_score"] = 80
    with pytest.raises(ValidationError):
        model.model_validate(value)


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("with_summary", [False, True])
def test_legacy_null_results_remain_null_without_a_provisional_status(model, with_summary):
    value = payload(model)
    value.update(misinformation_risk_score=None)
    value.pop("assessment_outcome")
    value.pop("scoring")
    if with_summary:
        value["scoring"] = {"version": "evidence-v2", "evidence_strength": "Insufficient",
                            "reasons": ["Legacy result with no score."]}
    before = deepcopy(value)
    result = model.model_validate(value)
    assert value == before
    assert result.misinformation_risk_score is None
    assert result.scoring is None or result.scoring.status is None
    assert result.model_dump(mode="json", exclude_unset=True) == before


def test_legacy_summary_default_does_not_silently_upgrade_version():
    summary = ScoringSummary(evidence_strength="Insufficient", reasons=["Legacy result."])
    assert summary.version == "evidence-v2"
    assert summary.status is None
