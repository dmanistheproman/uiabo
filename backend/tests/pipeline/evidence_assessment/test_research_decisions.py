"""Scope-aware assessment decisions and model-free public result projection."""
from copy import deepcopy
from datetime import date

import pytest
from pydantic import ValidationError

from app.pipeline.evidence_assessment.research_decisions import (
    DecisionDraft,
    DecisionFinding,
    FindingScope,
    bind_decision,
)
from app.pipeline.shared.web_research import ResearchFinding, ResearchSource


TODAY = date(2026, 11, 4)
CLAIM = "Companies are hiring foreigners at half the salary of Singapore graduates."
SOURCE = ResearchSource(id="c1", title="Official workforce figures", url="https://example.gov.sg/workforce")


def finding(status="contradicted", basis="direct", applicability="exact", **changes):
    value = {
        "claim": "The community museum is free to enter.",
        "status": status,
        "explanation": "The current published admission rule requires every adult visitor to pay ten dollars.",
        "source_ids": ["c1"] if status != "unresolved" else [],
        "material": True,
        "basis": basis,
        "scope": {
            "claim_scope": "Current adult admission to the named community museum.",
            "evidence_scope": "The current admission rule for adults at that same museum.",
            "applicability": applicability,
            "reason": "The evidence addresses the same visitors, museum and current rule.",
        },
        "limitations": ["The inference concerns only the current published rule."] if basis == "bounded_inference" else [],
    }
    value.update(changes)
    return value


def draft(verdict="false", findings=None, **changes):
    value = {
        "verdict": verdict,
        "summary": "The current published admission rule contradicts the allegation.",
        "findings": [finding()] if findings is None else findings,
        "limitations": [],
        "recommended_action": "Read the official information before sharing the message.",
    }
    value.update(changes)
    return value


def bind(value, sources=None):
    return bind_decision(value, sources=[SOURCE] if sources is None else sources,
        as_of=TODAY, model="gpt-6.1-sol", research_text="The cited evidence notes.")


def error_codes(error):
    return {item["type"] for item in error.value.errors(include_input=False, include_context=False)}


@pytest.mark.parametrize("verdict,findings", [
    ("true", [finding("supported")]),
    ("likely_true", [finding("supported", "bounded_inference", "qualified")]),
    ("false", [finding()]),
    ("likely_false", [finding("contradicted", "bounded_inference", "qualified")]),
    ("mixed", [finding("mixed")]),
    ("insufficient_evidence", [finding("unresolved", "unresolved", "unknown")]),
    ("not_checkable", []),
])
def test_all_valid_verdicts_keep_their_assessment_decisions(verdict, findings):
    decision = DecisionDraft.model_validate(draft(verdict, findings))
    before = decision.model_dump(mode="python")
    result = bind(decision)
    assert result.verdict == verdict
    assert result.summary == decision.summary
    assert result.recommended_action == decision.recommended_action
    assert result.as_of == TODAY and result.model == "gpt-6.1-sol"
    assert result.research_text == "The cited evidence notes."
    assert len(result.findings) == len(decision.findings)
    for original, projected in zip(decision.findings, result.findings):
        assert projected.model_dump() == {
            key: original.model_dump()[key] for key in ResearchFinding.model_fields
        }
    assert decision.model_dump(mode="python") == before


def test_c11_unmatched_salary_comparison_does_not_turn_into_a_contradiction():
    salary = finding("unresolved", "unresolved", "mismatch", claim=CLAIM,
        explanation="Pass thresholds and graduate median salaries are not matched pay data for equivalent workers.",
        source_ids=["c1"], limitations=["The comparison concerns different populations and salary measures."])
    salary["scope"] = {
        "claim_scope": "Employers hiring foreign workers at half the pay of comparable Singapore graduates.",
        "evidence_scope": "Work-pass salary thresholds compared with graduate median salaries.",
        "applicability": "mismatch",
        "reason": "These populations and salary measures do not establish actual pay for equivalent jobs.",
    }
    cause = finding("unresolved", "unresolved", "unknown",
        claim="The alleged lower-pay hiring caused graduate unemployment to double.",
        explanation="The evidence does not establish that causal relationship.")
    value = DecisionDraft.model_validate(draft("insufficient_evidence", [salary, cause]))
    result = bind(value)
    assert result.verdict == "insufficient_evidence"
    assert result.findings[0].claim == CLAIM
    assert [item.status for item in result.findings] == ["unresolved", "unresolved"]
    assert salary["limitations"][0] in result.limitations


@pytest.mark.parametrize("applicability", ["mismatch", "unknown"])
@pytest.mark.parametrize("status", ["supported", "contradicted", "mixed"])
def test_nonapplicable_evidence_cannot_settle_an_assertion(applicability, status):
    with pytest.raises(ValidationError) as error:
        DecisionFinding.model_validate(finding(status, "bounded_inference", applicability))
    assert "research_scope_unresolved_required" in error_codes(error)


def test_qualified_evidence_cannot_be_called_direct_proof():
    with pytest.raises(ValidationError) as error:
        DecisionFinding.model_validate(finding("contradicted", "direct", "qualified"))
    assert "research_scope_direct_requires_exact" in error_codes(error)


def test_unknown_cause_cannot_cancel_an_applicable_material_counterfact():
    counterfact = finding("contradicted", "bounded_inference", "qualified")
    cause = finding("unresolved", "unresolved", "unknown", claim="The fee changed because reserves are depleted.")
    with pytest.raises(ValidationError) as error:
        DecisionDraft.model_validate(draft("insufficient_evidence", [counterfact, cause]))
    assert "research_unresolved_cannot_erase_contradiction" in error_codes(error)
    accepted = DecisionDraft.model_validate(draft("likely_false", [counterfact, cause]))
    result = bind(accepted)
    assert result.verdict == "likely_false"
    assert [item.status for item in result.findings] == ["contradicted", "unresolved"]


@pytest.mark.parametrize("verdict,findings,code", [
    ("true", [finding("supported"), finding("unresolved", "unresolved", "unknown", claim="The fee will remain fixed forever.")], "research_support_incomplete"),
    ("true", [finding("supported", "bounded_inference", "qualified")], "research_direct_support_required"),
    ("false", [finding("contradicted", "bounded_inference", "qualified")], "research_direct_contradiction_required"),
    ("likely_false", [finding("unresolved", "unresolved", "unknown")], "research_contradiction_required"),
    ("mixed", [finding("supported"), finding(claim="The fee is zero for adults.")], "research_mixed_conflict_required"),
    ("not_checkable", [finding()], "research_nonfactual_findings"),
])
def test_existing_verdict_safeguards_are_preserved(verdict, findings, code):
    with pytest.raises(ValidationError) as error:
        DecisionDraft.model_validate(draft(verdict, findings))
    assert code in error_codes(error)


def test_overall_warning_does_not_replace_a_bounded_findings_local_limit():
    with pytest.raises(ValidationError) as error:
        DecisionDraft.model_validate(draft("likely_false", [finding("contradicted", "bounded_inference", "qualified", limitations=[])],
            limitations=["This assessment is limited."]))
    assert "research_decision_local_limitations_required" in error_codes(error)


def test_local_limits_are_retained_once_in_stable_order_without_mutating_input():
    value = draft("likely_false", [finding("contradicted", "bounded_inference", "qualified",
        limitations=["Specific population limitation.", "Shared limitation."])],
        limitations=["Overall limitation.", "Shared limitation."])
    before = deepcopy(value)
    decision = DecisionDraft.model_validate(value)
    assert decision.limitations == ["Overall limitation.", "Shared limitation.", "Specific population limitation."]
    assert bind(decision).limitations == decision.limitations
    assert value == before


def test_too_many_combined_limits_are_rejected_not_truncated():
    with pytest.raises(ValidationError) as error:
        DecisionDraft.model_validate(draft("likely_false", [finding("contradicted", "bounded_inference", "qualified",
            limitations=["One additional local limit."])], limitations=[f"Overall limit {i}." for i in range(8)]))
    assert "research_decision_limitations_limit" in error_codes(error)


@pytest.mark.parametrize("limit", ["", "   ", "x" * 1001])
def test_invalid_local_limitation_text_is_rejected(limit):
    with pytest.raises(ValidationError) as error:
        DecisionFinding.model_validate(finding(limitations=[limit]))
    assert "research_decision_limitations_invalid" in error_codes(error)


@pytest.mark.parametrize("field", ["claim_scope", "evidence_scope", "reason"])
def test_scope_requires_meaningful_text(field):
    scope = finding()["scope"]
    scope[field] = " \n "
    with pytest.raises(ValidationError) as error:
        FindingScope.model_validate(scope)
    assert "research_decision_scope_text_invalid" in error_codes(error)


def test_duplicate_assertions_cannot_be_assessed_twice_with_different_statuses():
    a = finding("mixed", claim="The museum is free.")
    b = finding("unresolved", "unresolved", "unknown", claim="  THE   MUSEUM is free.  ")
    with pytest.raises(ValidationError) as error:
        DecisionDraft.model_validate(draft("mixed", [a, b]))
    assert "research_decision_duplicate_assertions" in error_codes(error)


def test_unknown_source_references_are_still_rejected_by_public_binding():
    decision = DecisionDraft.model_validate(draft(findings=[finding(source_ids=["c2"])]))
    with pytest.raises(ValidationError) as error:
        bind(decision)
    assert "research_unknown_source_ids" in error_codes(error)


def test_no_evidence_and_nonfactual_results_do_not_need_invented_sources():
    unresolved = DecisionDraft.model_validate(draft("insufficient_evidence", [finding("unresolved", "unresolved", "unknown")]))
    nonfactual = DecisionDraft.model_validate(draft("not_checkable", []))
    assert bind(unresolved, sources=[]).sources == []
    assert bind(nonfactual, sources=[]).sources == []


def test_binding_preserves_all_findings_and_does_not_promote_background_facts():
    background = finding("supported", material=False, claim="The museum is a public institution.")
    unresolved = finding("unresolved", "unresolved", "unknown")
    decision = DecisionDraft.model_validate(draft("insufficient_evidence", [background, unresolved]))
    result = bind(decision)
    assert result.verdict == "insufficient_evidence"
    assert result.findings[0].material is False
    assert len(result.findings) == 2


def test_binding_revalidates_scope_if_a_previously_valid_draft_is_mutated():
    decision = DecisionDraft.model_validate(draft())
    decision.findings[0].scope.applicability = "mismatch"
    with pytest.raises(ValidationError) as error:
        bind(decision)
    assert "research_scope_unresolved_required" in error_codes(error)


def test_binding_revalidates_verdict_if_a_previously_valid_draft_is_mutated():
    decision = DecisionDraft.model_validate(draft())
    decision.verdict = "insufficient_evidence"
    with pytest.raises(ValidationError) as error:
        bind(decision)
    assert "research_unresolved_cannot_erase_contradiction" in error_codes(error)


def test_public_result_is_a_copy_with_no_internal_scope_fields():
    decision = DecisionDraft.model_validate(draft())
    result = bind(decision)
    assert set(result.findings[0].model_dump()) == set(ResearchFinding.model_fields)
    decision.findings[0].source_ids.append("c2")
    decision.findings[0].explanation = "Changed after binding."
    assert result.findings[0].source_ids == ["c1"]
    assert result.findings[0].explanation != decision.findings[0].explanation
    assert result.sources[0] is not SOURCE


def test_malformed_limits_are_not_silently_dropped_by_merging():
    with pytest.raises(ValidationError):
        DecisionDraft.model_validate(draft(limitations=[17]))
    with pytest.raises(ValidationError):
        DecisionDraft.model_validate(draft(findings=[finding(limitations=[17])]))


def test_unexpected_decision_fields_are_not_accepted():
    with pytest.raises(ValidationError) as error:
        DecisionDraft.model_validate(draft(probability=0.9))
    assert "extra_forbidden" in error_codes(error)
