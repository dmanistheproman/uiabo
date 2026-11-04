"""Cited research stays distinct from the existing quote/scoring contracts."""

from datetime import datetime, timezone

from pydantic import ValidationError
import pytest

from app.pipeline.evidence_assessment.research_result import build_research_result
from app.pipeline.shared.credibility import build_credibility
from app.pipeline.shared.models import PreparedText, TextAnalysisResult
from app.pipeline.shared.web_research import (
    ResearchAssessment, ResearchDraft, ResearchFinding, ResearchSource, VERDICT_PRESENTATION,
)


CREATED = datetime(2026, 11, 3, 10, 30, tzinfo=timezone.utc)
TEXT = "The community museum admits visitors free of charge."
SOURCE = {"id": "c1", "title": "Museum fees", "url": "https://example.gov.sg/museum", "publisher": "Example Authority"}


def finding(status="contradicted", basis="direct", **changes):
    value = dict(claim=TEXT, status=status, basis=basis, source_ids=["c1"],
        explanation="The published admission policy requires visitors to pay an entrance fee.")
    value.update(changes)
    return value


def research(verdict="false", findings=None, **changes):
    value = dict(verdict=verdict, summary="The published admission policy weighs against this claim.",
        recommended_action="Read the museum's admission policy before sharing this claim.",
        findings=findings if findings is not None else [finding()], sources=[SOURCE],
        limitations=["Admission policies can change; this research concerns the current published policy."],
        as_of="2026-11-03", model="gpt-6.1-sol", research_text="The published policy lists an admission fee.")
    value.update(changes)
    return ResearchAssessment.model_validate(value)


def result(value=None, *, created=CREATED):
    return build_research_result(
        prepared=PreparedText(original_text=TEXT, normalised_text=TEXT, language="en"),
        research=value or research(), result_id="research-result", created_at=created,
        pipeline_version="openai-web-v1:gpt-6.1-sol")


@pytest.mark.parametrize("verdict,findings", [
    ("true", [finding("supported")]),
    ("likely_true", [finding("supported", "bounded_inference")]),
    ("mixed", [finding("mixed")]),
    ("likely_false", [finding("contradicted", "bounded_inference")]),
    ("false", [finding()]),
    ("insufficient_evidence", [finding("unresolved", "unresolved")]),
    ("not_checkable", []),
])
def test_research_verdict_maps_to_qualitative_result_only(verdict, findings):
    record = result(research(verdict, findings))
    outcome, concern, strength, label = VERDICT_PRESENTATION[verdict]
    assert record.assessment_outcome == outcome
    assert record.concern_label == concern
    assert record.scoring.evidence_strength == strength
    assert record.scoring.status == "research_based"
    assert record.credibility.status == "research_only"
    assert record.credibility.label == label
    assert record.credibility.score is None and record.misinformation_risk_score is None
    assert not record.evidence and not record.verification and not record.verification_plan
    assert record.scoring.supporting_strength == record.scoring.contradicting_strength == 0
    assert record.scoring.supporting_origins == record.scoring.contradicting_origins == 0
    assert record.original_text == TEXT
    assert record.extracted_claim == (None if verdict == "not_checkable" else TEXT)
    assert TextAnalysisResult.model_validate_json(record.model_dump_json()) == record


def test_bounded_inference_can_support_likely_false_with_explicit_limits():
    record = result(research("likely_false", [finding("contradicted", "bounded_inference"),
        finding("unresolved", "unresolved", claim="A separate allegation is not established.")]))
    assert record.credibility.label == "Likely misinformation"
    assert record.research_assessment.findings[1].status == "unresolved"
    assert record.inference_context is None  # No invented legacy quote proof.


def test_supported_and_contradicted_components_cannot_cancel_into_mixed():
    findings = [finding("supported", claim="The museum is open."),
                finding("contradicted", claim="Admission to the museum is free.")]
    with pytest.raises(ValidationError, match="same material assertion"):
        research("mixed", findings)
    assert research("false", findings).verdict == "false"


def test_mixed_requires_a_material_conflict_about_one_assertion():
    findings = [finding("supported"),
                finding("mixed", material=False, claim="An ancillary claim has conflicting evidence.")]
    with pytest.raises(ValidationError, match="same material assertion"):
        research("mixed", findings)
    findings[1]["material"] = True
    assert research("mixed", findings).verdict == "mixed"


@pytest.mark.parametrize("basis,verdict", [("direct", "false"), ("bounded_inference", "likely_false")])
def test_unknown_cause_cannot_erase_a_material_counterfact(basis, verdict):
    findings = [finding("contradicted", basis, claim="Officials are raising a fee to ninety dollars."),
                finding("unresolved", "unresolved", claim="The alleged reason is that reserves are depleted.")]
    with pytest.raises(ValidationError, match="cannot erase"):
        research("insufficient_evidence", findings)
    assert research(verdict, findings).verdict == verdict


def test_nonmaterial_counterfact_does_not_force_overall_misinformation():
    findings = [finding("contradicted", material=False),
                finding("unresolved", "unresolved", claim="The material allegation cannot be assessed.")]
    assert research("insufficient_evidence", findings).verdict == "insufficient_evidence"


@pytest.mark.parametrize("verdict,findings", [
    ("true", [finding("unresolved", "unresolved")]),
    ("true", [finding("supported", "bounded_inference")]),
    ("likely_true", [finding(), finding("supported")]),
    ("false", [finding("contradicted", "bounded_inference")]),
    ("likely_false", [finding("unresolved", "unresolved")]),
    ("mixed", [finding("unresolved", "unresolved")]),
    ("insufficient_evidence", [finding("supported")]),
    ("not_checkable", [finding("supported")]),
])
def test_verdict_cannot_disguise_missing_or_incompatible_findings(verdict, findings):
    with pytest.raises(ValidationError):
        research(verdict, findings)


def test_draft_does_not_accept_server_metadata_or_model_invented_sources():
    value = research().model_dump()
    with pytest.raises(ValidationError):
        ResearchDraft.model_validate(value)
    valid = {key: value[key] for key in ResearchDraft.model_fields}
    assert ResearchDraft.model_validate(valid).verdict == "false"


def test_finding_cannot_cite_unknown_sources():
    with pytest.raises(ValidationError, match="server-bound sources"):
        research(findings=[finding(source_ids=["c99"])])


def test_duplicate_sources_are_not_independent_evidence():
    with pytest.raises(ValidationError, match="URLs must be unique"):
        research(sources=[SOURCE, {**SOURCE, "id": "c2"}])
    with pytest.raises(ValidationError, match="IDs must be unique"):
        research(sources=[SOURCE, {**SOURCE, "url": "https://example.gov.sg/other"}])


@pytest.mark.parametrize("updates", [
    {"source_ids": []}, {"source_ids": ["c1", "c1"]},
    {"basis": "unresolved"}, {"status": "unresolved"},
])
def test_decisive_findings_require_citations_and_consistent_basis(updates):
    with pytest.raises(ValidationError):
        ResearchFinding.model_validate(finding(**updates))


def test_inference_requires_explicit_limitations():
    with pytest.raises(ValidationError, match="state its limitations"):
        research("likely_false", [finding("contradicted", "bounded_inference")], limitations=[])


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "file:///private.txt", "http://localhost/page",
    "http://127.0.0.1/page", "http://192.168.1.1/page", "http://[::1]/page",
    "https://username:password@example.org/page", "http://internal/page", "http://computer.local/page",
])
def test_research_sources_require_public_http_citations(url):
    with pytest.raises(ValidationError):
        ResearchSource.model_validate({**SOURCE, "url": url})


@pytest.mark.parametrize("change", [
    {"misinformation_risk_score": 95},
    {"assessment_outcome": "supported"},
    {"concern_label": "Low Concern"},
    {"checkable": False},
    {"explanation": "An unrelated summary."},
    {"recommended_action": "Trust an unrelated instruction."},
    {"extracted_claim": "Only part of the claim."},
    {"research_assessment": None},
])
def test_research_result_cannot_be_relabelled_or_scored(change):
    payload = result().model_dump()
    payload.update(change)
    with pytest.raises(ValidationError):
        TextAnalysisResult.model_validate(payload)


def test_research_result_rejects_invented_voting_strength():
    payload = result().model_dump()
    payload["scoring"]["contradicting_strength"] = .95
    payload["scoring"]["contradicting_origins"] = 1
    with pytest.raises(ValidationError, match="fabricated evidence votes"):
        TextAnalysisResult.model_validate(payload)


def test_research_is_not_a_legacy_scored_record():
    payload = result().model_dump()
    payload["scoring"]["status"] = "evidence_based"
    with pytest.raises(ValidationError):
        TextAnalysisResult.model_validate(payload)
    with pytest.raises(ValueError, match="credibility-v2"):
        build_credibility(result(), version="credibility-v1")


def test_research_uses_singapore_submission_day():
    # UTC afternoon is already the following date in Singapore.
    created = datetime(2026, 11, 2, 18, tzinfo=timezone.utc)
    assert result(created=created).research_assessment.as_of.isoformat() == "2026-11-03"
    with pytest.raises(ValidationError, match="Singapore submission date"):
        result(research(as_of="2026-11-02"), created=created)
    with pytest.raises(ValidationError, match="Singapore submission date"):
        result(created=CREATED.replace(tzinfo=None))


def test_saved_research_does_not_accept_a_relabelled_credibility_badge():
    payload = result().model_dump()
    payload["credibility"]["label"] = "Definitely true"
    with pytest.raises(ValidationError, match="Credibility rating must match"):
        TextAnalysisResult.model_validate(payload)


def test_provider_research_summary_cannot_be_stored_as_a_source_quote():
    payload = result().model_dump()
    payload["evidence"] = [{
        "evidence_id": "c1", "title": "Museum fees", "url": SOURCE["url"],
        "publisher": "Example Authority", "passage": "The model said the claim is false.",
        "source_type": "government", "stance": "contradicting", "quality_score": .9,
        "evidence_quote": "The model said the claim is false.",
    }]
    with pytest.raises(ValidationError, match="quote-validated evidence"):
        TextAnalysisResult.model_validate(payload)
