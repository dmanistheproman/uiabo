"""Material component aggregation and grounding, using synthetic evidence only.

Mocked judgments test admission and aggregation; they do not establish whether a
live model interprets real financial sources accurately.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.pipeline.evidence_assessment.components import (
    Draft, aggregate_components, bind_findings, format_state, pairs_for,
)
from app.pipeline.shared.component_assessment import (
    ComponentAssessment, ComponentFinding, ComponentQuote, validate_component_result,
)
from app.pipeline.shared.components import decompose_claim
from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.models import (
    ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, PreparedText, RetrievalResult, TextAnalysisResult,
)
from app.pipeline.orchestration.service import _assemble_result


CPF_CLAIM = (
    "Government officials are discussing raising the retirement age to 75 "
    "because CPF reserves are running out faster than expected."
)
BRIDGE_CLAIM = (
    "The council is closing the bridge because inspectors found severe structural damage."
)


def claim(text=CPF_CLAIM):
    return ClaimAnalysis(extracted_claim=text, claim_category="factual", checkable=True,
        classification_reason="Synthetic regression claim", claim_confidence=1,
        claim_context=build_claim_context(text, datetime(2026, 10, 8, tzinfo=timezone.utc)))


def source(evidence_id="source", passage="The claim that CPF reserves are running out faster than expected is false.",
           *, origin="primary", quality=.95, scope="uncertain_time"):
    return EvidenceCandidate(evidence_id=evidence_id, title="Synthetic test source",
        url=f"https://{origin}.example/{evidence_id}", publisher=f"Synthetic {origin}",
        source_type="government", retrieval_score=quality, passage=passage,
        retrieved_at="2026-10-08T00:00:00Z", published_at="2026-10-08",
        provenance=EvidenceProvenance(source_policy="government_namespace",
            source_reason="Synthetic test authority", origin_group=origin,
            discovery_method="preferred_search", relevance="context",
            relevance_reason="Context for the complete allegation", relevance_quote=passage,
            applicability=scope, applicability_reason="Does not settle the entire allegation"))


def draft(stance="unresolved", **changes):
    value = dict(stance=stance, basis="none" if stance == "unresolved" else "direct",
        scope="unknown" if stance == "unresolved" else "established",
        decisiveness=0 if stance == "unresolved" else .9,
        explanation="Synthetic scoped component judgment.")
    value.update(changes)
    return Draft(**value)


def assess(sources, judgments, *, text=CPF_CLAIM):
    value = claim(text)
    parts = decompose_claim(text)
    drafts = {key: draft() for key in pairs_for(parts, sources)}
    drafts.update(judgments)
    findings = bind_findings(parts, sources, drafts, .5)
    result = aggregate_components(value, RetrievalResult(retrieval_status="completed", evidence=sources),
                                  parts, findings)
    return result


def final_result():
    evidence = source()
    assessment = assess([evidence], {"premise_s0": draft("contradicting")})
    return _assemble_result(result_id="component-regression", created_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        pipeline_version="test-components-v1", prepared=PreparedText(original_text=CPF_CLAIM,
            normalised_text=CPF_CLAIM, language="en"), claim=claim(),
        retrieval=RetrievalResult(retrieval_status="completed", evidence=[evidence]),
        assessment=assessment, warnings=[])


def test_contextual_source_can_refute_material_premise_without_disproving_discussion():
    evidence = source()
    original = evidence.model_dump()
    result = assess([evidence], {"premise_s0": draft("contradicting")})
    assert result.assessment_outcome == "contradicted"
    assert result.component_assessment.finding == "material_contradiction"
    assert "Likely misinformation" in result.explanation
    findings = {f.component_id: f for f in result.component_assessment.findings}
    assert findings["event"].stance == "unresolved"
    assert findings["premise"].stance == "contradicting"
    assert findings["causal_link"].stance == "unresolved"
    assert result.scoring.supporting_origins == 0
    assert result.scoring.contradicting_origins == 1
    assert evidence.model_dump() == original
    assert evidence.provenance.relevance == "context"
    validate_component_result(result, CPF_CLAIM, {evidence.evidence_id: evidence})


def test_supporting_discussion_does_not_cancel_contradicted_material_premise():
    sources = [source("discussion", "Officials are currently discussing retirement at age 75."), source("denial", origin="other")]
    result = assess(sources, {"event_s0": draft("supporting"), "premise_s1": draft("contradicting")})
    assert result.assessment_outcome == "contradicted"
    assert result.scoring.supporting_strength == 0
    assert result.component_assessment.finding == "material_contradiction"


def test_current_discussion_needs_no_implementation_date():
    sources = [source(passage="Officials are currently discussing retirement at age 75.")]
    result = assess(sources, {"event_s0": draft("supporting")})
    event = next(f for f in result.component_assessment.findings if f.component_id == "event")
    assert event.stance == "supporting"
    assert result.component_assessment.components[0].time_scope == "current"
    assert result.assessment_outcome == "insufficient_evidence"
    assert result.misinformation_risk_score is None


@pytest.mark.parametrize("supported", [["event"], ["premise"], ["event", "premise"]])
def test_partial_support_does_not_establish_complete_causal_message(supported):
    result = assess([source(passage="Bridge closure and engineering report.")],
        {f"{key}_s0": draft("supporting") for key in supported}, text=BRIDGE_CLAIM)
    assert result.assessment_outcome == "insufficient_evidence"
    assert result.component_assessment.finding == "unresolved"
    assert result.misinformation_risk_score is None


def test_support_for_all_material_parts_can_establish_message():
    result = assess([source(passage="Council closed the bridge because inspectors documented severe structural damage.")],
        {f"{key}_s0": draft("supporting") for key in ["event", "premise", "causal_link"]}, text=BRIDGE_CLAIM)
    assert result.assessment_outcome == "supported"
    assert result.scoring.supporting_origins == 1
    assert result.scoring.supporting_strength == .94


def test_complete_support_is_limited_by_weakest_component_after_origin_dedup_and_corroboration():
    sources = [
        source("event-one", "The bridge is closed.", origin="event-one", quality=.85),
        source("event-two", "The council closed the bridge.", origin="event-two", quality=.85),
        source("premise", "Inspectors found severe structural damage.", origin="premise", quality=.86),
        source("cause", "The closure was caused by the documented structural damage.", origin="cause", quality=.94),
    ]
    result = assess(sources, {"event_s0": draft("supporting"), "event_s1": draft("supporting"),
        "premise_s2": draft("supporting"), "causal_link_s3": draft("supporting")}, text=BRIDGE_CLAIM)
    # Event strength .884 exceeds premise .86 after independent corroboration.
    # Selecting the weakest raw vote (.85) first would incorrectly return .884.
    assert result.scoring.supporting_strength == .86
    assert result.scoring.supporting_origins == 1


def test_opposing_evidence_about_same_premise_is_conflicting():
    sources = [source("denial"), source("trend", "CPF reserves are declining faster than the expected baseline.", origin="other")]
    result = assess(sources, {"premise_s0": draft("contradicting"), "premise_s1": draft("supporting")})
    assert result.assessment_outcome == "conflicting"
    assert result.component_assessment.finding == "conflicting"
    assert result.misinformation_risk_score == 50


@pytest.mark.parametrize("passage", [
    "CPF savings are guaranteed by the government.",
    "CPF accounts are fully funded through individual savings.",
    "The government has strong net assets and guarantees repayment.",
])
def test_general_financial_guarantee_is_not_trend_contradiction_even_if_judge_calls_it_one(passage):
    result = assess([source(passage=passage)], {"premise_s0": draft("contradicting")})
    assert result.assessment_outcome == "insufficient_evidence"
    assert result.misinformation_risk_score is None
    premise = next(f for f in result.component_assessment.findings if f.component_id == "premise")
    assert premise.stance == "unresolved"
    assert "financial trend" in premise.explanation


def test_published_policy_with_no_discussion_evidence_does_not_become_false():
    result = assess([source(passage="The published retirement age is 64, with a target of 65 by 2030.")], {})
    assert result.component_assessment.finding == "unresolved"
    assert result.misinformation_risk_score is None


@pytest.mark.parametrize("changes", [
    {"scope": "unknown"}, {"scope": "different"}, {"basis": "none"}, {"decisiveness": .49},
])
def test_inapplicable_or_insufficient_component_judgment_cannot_vote(changes):
    result = assess([source()], {"premise_s0": draft("contradicting", **changes)})
    assert result.assessment_outcome == "insufficient_evidence"
    assert result.scoring.contradicting_origins == 0


def test_low_quality_source_cannot_supply_material_contradiction():
    result = assess([source(quality=.4)], {"premise_s0": draft("contradicting")})
    assert result.assessment_outcome == "insufficient_evidence"


def test_inferential_component_strength_is_bounded():
    result = assess([source()], {"premise_s0": draft("contradicting", basis="inference")})
    assert result.assessment_outcome == "contradicted"
    assert result.scoring.contradicting_strength == .7
    assert result.misinformation_risk_score == 85


def test_same_source_on_multiple_components_does_not_add_origins_or_duplicate_evidence():
    result = assess([source(passage="Synthetic evidence denying the alleged closure and structural damage.")],
        {"event_s0": draft("contradicting"), "premise_s0": draft("contradicting")}, text=BRIDGE_CLAIM)
    assert result.scoring.contradicting_origins == 1
    assert result.scoring.contradicting_strength == .94
    assert len(result.assessed_evidence) == 1


def test_repeated_origin_across_pages_does_not_add_corroboration():
    sources = [source("one"), source("two")]
    result = assess(sources, {"premise_s0": draft("contradicting"), "premise_s1": draft("contradicting")})
    assert result.scoring.contradicting_origins == 1
    assert result.scoring.contradicting_strength == .94


def test_state_uses_actual_assessment_date_and_returned_passage_only():
    value = claim()
    evidence = source()
    evidence.full_text = "Secret full-page content unavailable in returned evidence."
    state = format_state(value, decompose_claim(CPF_CLAIM), [evidence])
    assert "2026-10-08" in state
    assert evidence.passage in state
    assert evidence.full_text not in state


def test_component_assessment_json_roundtrip_preserves_findings():
    result = assess([source()], {"premise_s0": draft("contradicting")})
    restored = ComponentAssessment.model_validate_json(result.component_assessment.model_dump_json())
    assert restored == result.component_assessment


def test_final_assembly_and_json_roundtrip_keep_component_evidence_and_credibility():
    result = final_result()
    restored = TextAnalysisResult.model_validate_json(result.model_dump_json())
    assert restored.component_assessment == result.component_assessment
    assert restored.credibility.version == "credibility-v2"
    assert restored.credibility.label == "Likely misinformation"
    assert restored.credibility.score < 50
    assert restored.evidence[0].provenance.relevance == "context"
    assert len(restored.evidence) == 1


@pytest.mark.parametrize("mutation", ["invented_quote", "missing_source", "v1_rating"])
def test_final_schema_rejects_ungrounded_or_legacy_component_payload(mutation):
    payload = final_result().model_dump()
    if mutation == "invented_quote":
        payload["component_assessment"]["findings"][0]["quotes"][0]["quote"] = "Invented quote."
    elif mutation == "missing_source":
        payload["evidence"] = []
    else:
        payload["credibility"]["version"] = "credibility-v1"
    with pytest.raises(ValidationError):
        TextAnalysisResult.model_validate(payload)


@pytest.mark.parametrize("mutation", ["strength", "origins"])
def test_final_schema_rejects_scoring_that_does_not_match_recorded_component_votes(mutation):
    payload = final_result().model_dump()
    payload["credibility"] = None  # Isolate the persisted evidence-scoring contract.
    if mutation == "strength":
        payload["scoring"]["contradicting_strength"] = .6
        payload["misinformation_risk_score"] = 80
    else:
        payload["scoring"]["contradicting_origins"] = 2
    with pytest.raises(ValidationError):
        TextAnalysisResult.model_validate(payload)


@pytest.mark.parametrize("mutation", ["unknown_source", "invented_quote", "invented_component", "wrong_outcome"])
def test_final_component_grounding_rejects_tampering(mutation):
    evidence = source()
    result = assess([evidence], {"premise_s0": draft("contradicting")})
    changed = result.model_copy(deep=True)
    if mutation == "unknown_source":
        changed.component_assessment.findings[0].quotes[0].evidence_id = "invented"
    elif mutation == "invented_quote":
        changed.component_assessment.findings[0].quotes[0].quote = "This quotation was not in the source."
    elif mutation == "invented_component":
        changed.component_assessment.components[0].text = "An invented event claim."
    else:
        changed.assessment_outcome = "supported"
    with pytest.raises(ValueError):
        validate_component_result(changed, CPF_CLAIM, {evidence.evidence_id: evidence})


@pytest.mark.parametrize("changes", [
    {"evidence_ids": ["one", "one"]},
    {"scope_matched": False},
    {"quotes": []},
    {"quality_score": .59},
    {"basis": "inference", "quality_score": .94},
])
def test_component_vote_contract_rejects_ungrounded_votes(changes):
    fields = dict(component_id="premise", stance="contradicting", basis="direct",
        evidence_ids=["one"], quotes=[ComponentQuote(evidence_id="one", quote="Synthetic evidence.")],
        explanation="Synthetic explanation.", scope_matched=True, quality_score=.94)
    fields.update(changes)
    with pytest.raises(ValidationError):
        ComponentFinding(**fields)
