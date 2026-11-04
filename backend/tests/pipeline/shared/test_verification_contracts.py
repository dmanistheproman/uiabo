"""Final saved results cannot accept invented claim spans or evidence quotes."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.pipeline.shared.models import TextAnalysisResult
from app.pipeline.shared.verification import (
    VerificationAssessment, VerificationAssertion, VerificationFinding,
    VerificationPlan, VerificationScopeChecks, validate_verification_provenance,
    verification_proof_quality,
    causal_fact_spans,
)


TEXT = "A new $500 community tax starts next week."
QUOTE = "No new $500 community tax will begin next week."


def plan():
    return VerificationPlan(source_text=TEXT, assertions=[VerificationAssertion(
        id="a1", text=TEXT, evidence_questions=["Has this tax been announced?"], queries=["community tax announcement"],
    )])


def finding(**changes):
    values = dict(
        assertion_id="a1", status="contradicted", basis="direct", scope="established",
        evidence_adequacy=0.9,
        scope_checks=VerificationScopeChecks(**{
            key: "established" for key in VerificationScopeChecks.model_fields
        }),
        citations=[{"evidence_id": "evidence-tax-1", "quote": QUOTE}],
        explanation="The supplied synthetic announcement explicitly denies the tax.",
    )
    values.update(changes)
    return VerificationFinding(**values)


def assessment(**changes):
    return VerificationAssessment(findings=[finding(**changes)], rationale="The announcement addresses the claimed tax.")


def payload():
    fixture = Path(__file__).parents[2] / "fixtures" / "sprint_1" / "text_analysis_result.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["verification_plan"] = plan().model_dump(mode="json")
    data["verification"] = assessment().model_dump(mode="json")
    data["assessment_outcome"] = "contradicted"
    data["misinformation_risk_score"] = 95
    data["scoring"] = {
        "version": "evidence-v4", "status": "evidence_based", "evidence_strength": "Strong",
        "supporting_strength": 0, "contradicting_strength": .9,
        "supporting_origins": 0, "contradicting_origins": 1,
        "reasons": ["One quoted direct proof is bounded by its evidence adequacy."],
    }
    return data


def test_final_result_roundtrip_retains_exact_provenance():
    result = TextAnalysisResult.model_validate(payload())
    assert result.verification.findings[0].citations[0].quote in result.evidence[0].passage
    assert TextAnalysisResult.model_validate_json(result.model_dump_json()) == result


def test_joint_outcome_cannot_disagree_with_its_verified_findings():
    data = payload()
    data["verification"]["findings"][0]["status"] = "supported"
    with pytest.raises(ValidationError, match="outcome must match"):
        TextAnalysisResult.model_validate(data)


def test_generic_proof_cannot_bypass_consistency_by_claiming_specialist_method():
    data = payload()
    data["verification"]["method"] = "specialist"
    with pytest.raises(ValidationError, match="recognised structured"):
        TextAnalysisResult.model_validate(data)


@pytest.mark.parametrize("change", ["adequacy", "source_type", "origins"])
def test_joint_score_cannot_exceed_verified_proof_limits(change):
    data = payload()
    if change == "adequacy":
        data["verification"]["findings"][0]["evidence_adequacy"] = .65
    elif change == "source_type":
        data["evidence"][0]["source_type"] = "other"
    else:
        data["scoring"]["contradicting_origins"] = 2
    with pytest.raises(ValidationError, match="proof strength"):
        TextAnalysisResult.model_validate(data)


@pytest.mark.parametrize("patch", [
    {"evidence_id": "invented-source", "quote": QUOTE},
    {"evidence_id": "evidence-tax-1", "quote": "The tax is definitely false because every official denies it."},
    {"evidence_id": "evidence-tax-1", "quote": "new $500 tax"},
])
def test_unavailable_source_or_fabricated_quote_cannot_be_saved(patch):
    data = payload()
    data["verification"]["findings"][0]["citations"] = [patch]
    with pytest.raises(ValidationError, match="quote their supplied evidence"):
        TextAnalysisResult.model_validate(data)


def test_valid_quote_from_different_source_is_not_a_valid_citation():
    with pytest.raises(ValueError, match="quote their supplied evidence"):
        validate_verification_provenance(assessment(), plan(), {
            "evidence-tax-1": {"passage": "Only current rules are listed here."},
            "other-source": {"passage": QUOTE},
        })


def test_missing_assertion_finding_or_invented_assertion_rejected():
    with pytest.raises(ValueError, match="exactly the planned"):
        validate_verification_provenance(assessment(assertion_id="a2"), plan(), {
            "evidence-tax-1": {"passage": QUOTE},
        })


@pytest.mark.parametrize("changes", [
    {"citations": []}, {"basis": "none"}, {"scope": "unknown"},
    {"scope_checks": {"entity": "established", "population": "different"}},
])
def test_decisive_claims_require_complete_scope_and_citations(changes):
    with pytest.raises(ValidationError):
        finding(**changes)


def test_partial_cited_facts_can_be_preserved_without_pretending_claim_is_proved():
    value = finding(status="unresolved", scope="unknown", scope_checks={}, gaps=["No source establishes who announced the rule."])
    assert value.citations
    assert value.status == "unresolved"


def test_whole_claim_scope_flag_needs_grounded_per_assertion_resolution():
    sources = {"evidence-tax-1": {
        "passage": QUOTE, "provenance": {"applicability": "different_scope"},
    }}
    with pytest.raises(ValueError, match="quoted resolution"):
        validate_verification_provenance(assessment(), plan(), sources)
    value = assessment(scope_resolutions=[{
        "evidence_id": "evidence-tax-1", "quote": QUOTE,
        "explanation": "This quotation concerns the exact tax and date in this assertion, although other parts of the original message concern another agency.",
    }])
    validate_verification_provenance(value, plan(), sources)
    assert sources["evidence-tax-1"]["provenance"]["applicability"] == "different_scope"


def test_scope_resolution_cannot_use_a_fabricated_quote_or_an_uncited_source():
    for resolution in [
        {"evidence_id": "evidence-tax-1", "quote": "This source covers every possible tax."},
        {"evidence_id": "other-source", "quote": QUOTE},
    ]:
        with pytest.raises(ValueError):
            validate_verification_provenance(assessment(scope_resolutions=[{
                **resolution, "explanation": "The model says this resolves the mismatch.",
            }]), plan(), {"evidence-tax-1": {"passage": QUOTE}, "other-source": {"passage": QUOTE}})


def test_material_counterfact_can_refute_event_without_proving_cause_false():
    text = "A new $500 community tax starts next week because reserve funds are empty."
    causal_plan = VerificationPlan(source_text=text, assertions=[VerificationAssertion(
        id="a1", text=text, kind="causal", evidence_questions=["Is the asserted event and its cause established?"], queries=[text],
    )])
    counterfact = {
        "evidence_id": "evidence-tax-1", "quote": QUOTE,
        "claim_span": "A new $500 community tax starts next week",
        "explanation": "The announcement refutes the tax itself; the reserve balance is not established.",
        "scope_checks": {key: "established" for key in VerificationScopeChecks.model_fields},
    }
    value = assessment(material_counterfact=counterfact)
    sources = {"evidence-tax-1": {"passage": QUOTE, "source_type": "government"}}
    validate_verification_provenance(value, causal_plan, sources)
    assert verification_proof_quality(value.findings[0], sources) == .89
    for field, bad in [("claim_span", "The annual deficit has vanished"), ("quote", "No reserves remain.")]:
        with pytest.raises(ValueError):
            validate_verification_provenance(assessment(material_counterfact={**counterfact, field: bad}), causal_plan, sources)
    with pytest.raises(ValidationError, match="only explain a contradicted"):
        finding(status="supported", material_counterfact=counterfact)


@pytest.mark.parametrize("governor", ["is not", "might be", "was allegedly", "was reported to be"])
def test_material_counterfact_cannot_drop_a_governing_qualifier(governor):
    text = f"Baymere Reservoir {governor} completely empty because illegal pipes have drained it."
    causal_plan = VerificationPlan(source_text=text, assertions=[VerificationAssertion(
        id="a1", text=text, kind="causal", evidence_questions=["Is this causal statement established?"], queries=[text],
    )])
    value = assessment(material_counterfact={
        "evidence_id": "evidence-tax-1", "quote": QUOTE,
        "claim_span": "completely empty",
        "explanation": "This cropped fragment removed its governing context.",
        "scope_checks": {key: "established" for key in VerificationScopeChecks.model_fields},
    })
    with pytest.raises(ValueError, match="exact clause"):
        validate_verification_provenance(value, causal_plan, {"evidence-tax-1": {"passage": QUOTE}})


@pytest.mark.parametrize("text", [
    "The library is open or the museum is closed because a water pipe burst.",
    "If the water pipe burst, the museum closed because the floor was flooded.",
])
def test_counterfact_shortcut_does_not_refute_disjunction_or_conditional(text):
    assert causal_fact_spans(text) == set()


def test_fallback_does_not_allow_partial_invented_decomposition():
    data = plan().model_dump()
    data["status"] = "fallback"
    data["assertions"][0]["text"] = "tax starts next week."
    with pytest.raises(ValidationError, match="preserve the whole input"):
        VerificationPlan.model_validate(data)


def test_final_plan_cannot_switch_to_an_unrelated_claim():
    data = payload()
    data["verification_plan"]["source_text"] = "The capital is changing."
    data["verification_plan"]["assertions"][0]["text"] = "The capital is changing."
    with pytest.raises(ValidationError, match="match the submitted"):
        TextAnalysisResult.model_validate(data)


def test_whitespace_normalised_original_input_is_allowed():
    data = payload()
    data["original_text"] = "  A new $500 community tax\nstarts next week.  "
    assert TextAnalysisResult.model_validate(data)


def test_input_preparation_unicode_normalisation_is_also_allowed():
    from app.pipeline.shared.verification import validate_plan_input
    original = "Cafe\u0301 library will cl\u200bose on Friday."
    normalised = "Caf\u00e9 library will close on Friday."
    value = VerificationPlan(source_text=normalised, assertions=[VerificationAssertion(
        id="a1", text=normalised, evidence_questions=["Is the closure announced?"], queries=[normalised],
    )])
    validate_plan_input(value, original, "Caf\u00e9 library will close on Friday.")


@pytest.mark.parametrize("status,attempted", [("budget_exhausted", False), ("unchanged", True), ("improved", True)])
def test_repair_audit_status_is_consistent(status, attempted):
    value = assessment().model_dump()
    value.update(repair_status=status, repair_attempted=attempted)
    assert VerificationAssessment.model_validate(value)
    value["repair_attempted"] = not attempted
    with pytest.raises(ValidationError, match="Repair status"):
        VerificationAssessment.model_validate(value)
