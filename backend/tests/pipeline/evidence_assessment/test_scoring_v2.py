"""V2 evidence formula retained in v3; synthetic regressions, not accuracy evaluation."""

from itertools import permutations
from datetime import date

import pytest

from app.pipeline.evidence_assessment.service import calculate_quality_score, summarise_assessments
from app.pipeline.evidence_assessment.semantic import aggregate, validate_judgment
from app.pipeline.shared.models import AssessedEvidence, ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult


def source(name, *, origin=None, passage=None, provenance=True, quality=.94):
    item = EvidenceCandidate(evidence_id=name, title=name, publisher=name,
        url=f"https://{name}.example/notice", source_type="government",
        passage=passage or f"The admission fee is $10. Published by {name}.",
        retrieval_score=quality, retrieved_at="2026-09-16T00:00:00Z")
    if provenance:
        item.provenance = EvidenceProvenance(source_policy="catalogue", source_reason="Test source",
            origin_group=origin or name, discovery_method="web_search", relevance="direct",
            relevance_reason="Addresses the fee", relevance_quote=item.passage,
            applicability="established", applicability_reason="Same event and date")
    return item


def assess(items, stances=None, qualities=None):
    votes = [AssessedEvidence(evidence_id=item.evidence_id,
        stance=(stances or ["supporting"] * len(items))[i],
        quality_score=(qualities or [calculate_quality_score(item, "supporting") for item in items])[i],
        assessment_reason="The passage directly addresses the complete claim.") for i, item in enumerate(items)]
    return summarise_assessments("Admission is $10.",
        RetrievalResult(retrieval_status="completed", evidence=items), votes)


def test_strong_supported_fact_is_near_zero_and_corroboration_can_reach_zero():
    results = [assess([source(name) for name in "abc"[:n]]) for n in (1, 2, 3)]
    assert [r.misinformation_risk_score for r in results] == [3, 1, 0]
    assert all(r.assessment_outcome == "supported" and r.scoring.evidence_strength == "Strong" for r in results)
    assert all(r.scoring.version == "evidence-v3" and r.scoring.status == "evidence_based" for r in results)


def test_score_changes_smoothly_with_quality_instead_of_old_buckets():
    scores = [assess([source("a", quality=q)]).misinformation_risk_score for q in (.60, .70, .80, .90, .94)]
    assert scores == [20, 15, 10, 5, 3]


@pytest.mark.parametrize("stance", ["supporting", "contradicting"])
@pytest.mark.parametrize("quality", [0, .20, .59])
def test_weak_evidence_cannot_award_a_verdict_or_zero(stance, quality):
    result = assess([source("a")], [stance], [quality])
    assert result.assessment_outcome == "insufficient_evidence"
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"
    assert result.scoring.evidence_strength == "Insufficient"
    assert result.scoring.supporting_strength == result.scoring.contradicting_strength == 0
    assert result.scoring.supporting_origins == result.scoring.contradicting_origins == 0


@pytest.mark.parametrize("duplicate_kind", ["origin", "host", "publisher", "passage"])
def test_copies_do_not_strengthen_the_result(duplicate_kind):
    first, second = source("a"), source("b")
    if duplicate_kind == "origin": second.provenance.origin_group = first.provenance.origin_group
    if duplicate_kind == "host": second.url = first.url
    if duplicate_kind == "publisher": second.publisher = first.publisher
    if duplicate_kind == "passage": second.passage = first.passage
    single, repeated = assess([first]), assess([first, second])
    assert repeated.misinformation_risk_score == single.misinformation_risk_score
    assert repeated.scoring.supporting_origins == 1


def test_missing_origin_metadata_does_not_earn_corroboration_bonus():
    result = assess([source(name, provenance=False) for name in "abc"])
    assert result.misinformation_risk_score == 3


def test_conflict_verdict_is_not_inferred_from_score_bands():
    result = assess([source("a"), source("b"), source("c"), source("d", quality=.60)],
                    ["supporting"] * 3 + ["contradicting"])
    assert result.misinformation_risk_score == 30  # formerly a Low Concern band
    assert result.assessment_outcome == "conflicting"
    assert result.concern_label == "Needs Caution"
    assert result.uncertainty == "High"


def test_same_origin_opposing_stances_are_preserved():
    result = assess([source("a", origin="one"), source("b", origin="one")], ["supporting", "contradicting"])
    assert result.assessment_outcome == "conflicting"
    assert result.misinformation_risk_score == 50


@pytest.mark.parametrize("scope", ["missing_context", "different_scope", "uncertain_time"])
def test_scope_gates_take_priority_over_strong_support(scope):
    item = source("a")
    item.provenance.applicability = scope
    result = assess([item])
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"


def test_neutral_context_never_improves_support():
    result = assess([source("a"), source("b")], ["supporting", "neutral"])
    assert result.misinformation_risk_score == 3
    assert result.scoring.supporting_origins == 1


def test_historical_evidence_does_not_lose_quality_merely_for_age():
    item = source("a")
    old = item.model_copy(update={"published_at": date(1965, 8, 9)})
    assert calculate_quality_score(old, "supporting") == calculate_quality_score(item, "supporting")


def test_order_does_not_change_score_or_verdict():
    items = [source("a", origin="same"), source("b", origin="same"), source("c")]
    for ordered in permutations(items):
        result = assess(list(ordered))
        assert result.misinformation_risk_score == 1
        assert result.assessment_outcome == "supported"


def test_tied_quality_with_mixed_origin_metadata_is_order_independent():
    items = [source("a", provenance=False), source("b"), source("c")]
    for ordered in permutations(items):
        assert assess(list(ordered)).misinformation_risk_score == 1


def test_partial_compound_support_remains_provisional_in_semantic_path():
    text = "The admission fee is $10 for all residents."
    item = source("a", passage="The admission fee is $10. Resident eligibility is not stated.")
    claim = ClaimAnalysis(extracted_claim=text, claim_category="factual", checkable=True,
        classification_reason="A fee claim", claim_confidence=1)
    judgment = validate_judgment({"stance":"supporting", "evidence_quote":item.passage,
        "reason":"The amount matches.", "comparisons":[{"aspect":"population", "claim_text":"all residents",
        "finding":"unresolved", "applies_to_claim":False, "explanation":"Eligibility is not stated.",
        "evidence_quote":""}]}, item.passage, claim=text, evidence=item)
    result = aggregate(claim, RetrievalResult(retrieval_status="completed", evidence=[item]), [judgment])
    assert result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"


def test_strong_contradiction_moves_towards_100():
    result = assess([source(name) for name in "abc"], ["contradicting"] * 3)
    assert result.misinformation_risk_score == 100
    assert result.assessment_outcome == "contradicted"
