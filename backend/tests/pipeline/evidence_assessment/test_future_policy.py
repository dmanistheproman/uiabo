"""Synthetic regression cases: policy differences versus future-change evidence."""

from datetime import date, datetime, timezone

import pytest

from app.pipeline.evidence_assessment import semantic
from app.pipeline.shared.dates import infer_date_context
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult

CLAIM = "ICA will begin rejecting passports with less than one year of validity from November"
NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)
RULE = "Travellers entering Singapore, except Singapore passport holders, need at least six months of passport validity."
DENIAL = "ICA denies the claim that it will begin rejecting passports with less than one year of validity. This claim is false."


def source(passage, **changes):
    item = EvidenceCandidate(evidence_id="official", title="Synthetic official notice",
        url="https://authority.example/notice", publisher="Synthetic authority", source_type="government",
        passage=passage, retrieval_score=.94, published_at=date(2026, 9, 15), retrieved_at=NOW,
        provenance=EvidenceProvenance(source_policy="catalogue", source_reason="Synthetic source",
            origin_group="authority", discovery_method="web_search", relevance="direct",
            relevance_reason="Addresses the claimed requirement", relevance_quote=passage,
            applicability="established", applicability_reason="Same alleged change and travellers"))
    return item.model_copy(update=changes)


def assess(item, *, denies=False, stance="contradicting", comparisons=None):
    claim = ClaimAnalysis(extracted_claim=CLAIM, checkable=True, claim_category="factual",
        classification_reason="A claimed immigration rule change", claim_confidence=1,
        date_context=infer_date_context(CLAIM, NOW))
    raw = dict(stance=stance, evidence_quote=item.passage, reason="The source addresses the claimed requirement.",
               denies_alleged_change=denies, comparisons=comparisons or [])
    judgment=semantic.validate_judgment(raw, item.passage, claim=CLAIM, evidence=item)
    return semantic.aggregate(claim, RetrievalResult(retrieval_status="completed", evidence=[item]), [judgment])


def difference(quote=RULE):
    return {"aspect":"requirement", "claim_text":"less than one year of validity", "finding":"differs",
        "applies_to_claim":False, "evidence_quote":quote,
        "explanation":"The published entry rule specifies six months for foreign travellers, rather than one year. The cited exception is Singapore passport holders."}


def test_passport_policy_difference_is_visible_but_change_remains_unverified():
    item=source(RULE)
    item.provenance.relevance="context"
    item.provenance.applicability="uncertain_time"
    result=assess(item, stance="neutral", comparisons=[difference()])
    assert result.assessment_outcome == "unsupported"
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"
    assert result.policy_context.change_status == "unverified"
    assert "six months" in result.policy_context.published_policy_summary
    assert "Singapore passport holders" in result.policy_context.published_policy_summary
    assert "November 2026" in result.policy_context.change_summary
    assert result.policy_context.evidence_ids == ["official"]
    assert result.claim_comparisons[0].scope_limitation
    assert "November" not in result.claim_comparisons[0].explanation


def test_applicable_quoted_official_denial_needs_no_literal_month_or_year():
    result=assess(source(DENIAL), denies=True)
    assert result.assessment_outcome == "contradicted"
    assert result.misinformation_risk_score == 97
    assert result.policy_context.change_status == "contradicted"


@pytest.mark.parametrize("quote", [RULE,
    "ICA has not announced a change to passport validity requirements.",
    "ICA has not commented on the claim about one-year passport validity."])
def test_existing_rules_silence_and_no_comment_cannot_use_denial_exception(quote):
    result=assess(source(quote), denies=True)
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"


@pytest.mark.parametrize("scope", ["different_scope", "missing_context", "uncertain_time"])
def test_denial_cannot_override_retrieval_scope_failure(scope):
    item=source(DENIAL)
    item.provenance.applicability=scope
    result = assess(item, denies=True)
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"


@pytest.mark.parametrize("changes", [{"source_type":"news"}, {"provenance":None}, {"published_at":date(2024, 9, 15)}])
def test_nonofficial_unscoped_or_old_denial_does_not_override_guard(changes):
    result = assess(source(DENIAL, **changes), denies=True)
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"


def test_unrelated_or_conditional_denial_with_neutral_semantic_judgment_stays_provisional():
    for passage in ["ICA denies plans to increase visa fees.",
                    "If the rumour were false, ICA would deny plans to reject these passports."]:
        result = assess(source(passage), stance="neutral")
        assert result.misinformation_risk_score == 50
        assert result.scoring.status == "provisional"


def test_denial_signal_without_quoted_denial_never_bypasses_guard():
    # Even a model flag cannot turn an ordinary rule into an explicit denial.
    result = assess(source(RULE), denies=True)
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"


def test_supporting_judgment_cannot_claim_to_be_a_denial():
    with pytest.raises(ValueError, match="explicit denial"):
        assess(source(DENIAL), denies=True, stance="supporting")


def test_sentence_repair_preserves_denial_flag_and_original_quote():
    item=source(DENIAL)
    spans=semantic.sentence_spans(item.passage)
    raw={"stance":"contradicting", "sentence_start":0,"sentence_end":len(spans)-1,
         "reason":"The official source denies this exact change.", "denies_alleged_change":True, "comparisons":[]}
    judgment=semantic.validate_sentence_judgment(raw,item.passage,spans,claim=CLAIM,evidence=item)
    assert judgment.denies_alleged_change
    assert judgment.evidence_quote == DENIAL


def test_applicable_denial_not_cancelled_by_unresolved_date_comparison():
    result=assess(source(DENIAL), denies=True, comparisons=[{
        "aspect":"start_date", "claim_text":"from November", "finding":"unresolved",
        "applies_to_claim":False, "evidence_quote":"", "explanation":"The denial does not repeat the date."}])
    assert result.assessment_outcome == "contradicted"


def test_explicit_period_rule_can_still_contradict_without_denial_flag():
    result=assess(source("From November 2026, foreign travellers need six months of passport validity for entry."))
    assert result.assessment_outcome == "contradicted"


def test_future_announcement_support_is_reported_separately_from_current_rules():
    result=assess(source("From November 2026, ICA will reject passports with less than one year of validity."), stance="supporting")
    assert result.assessment_outcome == "supported"
    assert result.policy_context.change_status == "supported"
    assert result.misinformation_risk_score == 3


def test_current_rule_is_not_accepted_as_support_for_future_change():
    result=assess(source("ICA requires one year of passport validity under the current rules."), stance="supporting")
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"


def test_denial_and_future_announcement_preserve_disagreement():
    denial=source(DENIAL)
    announcement=source("From November 2026, ICA will reject passports with less than one year of validity.", evidence_id="announcement")
    claim=ClaimAnalysis(extracted_claim=CLAIM, checkable=True, claim_category="factual",
        classification_reason="A rule change", claim_confidence=1, date_context=infer_date_context(CLAIM,NOW))
    judgments=[semantic.Judgment(stance="contradicting", evidence_quote=DENIAL,
        reason="Official denial of the same change.", denies_alleged_change=True),
        semantic.Judgment(stance="supporting", evidence_quote=announcement.passage,reason="Applicable announcement.")]
    result=semantic.aggregate(claim,RetrievalResult(retrieval_status="completed",evidence=[denial,announcement]),judgments)
    assert result.assessment_outcome == "conflicting"
    assert result.policy_context.change_status == "conflicting"
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "evidence_based"


def test_different_population_not_presented_as_the_current_rule_for_everyone():
    item=source(RULE)
    item.provenance.applicability="different_scope"
    result=assess(item, stance="neutral", comparisons=[difference()])
    assert result.policy_context.policy_scope == "related_guidance"
    assert "applicable rule has not been established" in result.policy_context.published_policy_summary
    assert result.policy_context.change_status == "unverified"
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"
