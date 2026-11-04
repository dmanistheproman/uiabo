"""Integration of planned evidence gaps, bounded repair and owned persistence."""
from datetime import datetime, timezone

import pytest

from app.pipeline.evidence_assessment.scoring import group_evidence, score_evidence, LABELS
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import (
    AssessmentResult, AssessedEvidence, ClaimAnalysis, EvidenceCandidate,
    PreparedText, RetrievalResult, RetrievalTrace, TextAnalysisResult,
)
from app.pipeline.shared.verification import VerificationPlan, VerificationAssessment

NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)
TEXT = "The library closes at six."
QUOTE = "The library closes at eight every evening."


def plan(claim, *, original_text):
    return VerificationPlan(source_text=original_text, assertions=[dict(
        id="a1", text=original_text, evidence_questions=["What are the library opening hours?"],
        queries=["library official opening hours"],
    )], as_of=claim.claim_context.as_of, assumptions=claim.claim_context.assumptions)


def source(key="old", passage="The library has reading rooms."):
    return EvidenceCandidate(evidence_id=key, title="Library hours", url=f"https://example.org/{key}",
        publisher="Library", passage=passage, source_type="government",
        retrieval_score=.5, retrieved_at=NOW)


def retrieval(items):
    return RetrievalResult(retrieval_status="completed" if items else "no_evidence", evidence=items,
        trace=RetrievalTrace(search_requests=1, decisions=[{"decision": "initial_search"}]))


def assessment(claim, retrieved):
    decisive = next((s for s in retrieved.evidence if s.passage == QUOTE), None)
    assessed = [AssessedEvidence(evidence_id=s.evidence_id,
        stance="contradicting" if s == decisive else "neutral", quality_score=.7 if s == decisive else .4,
        evidence_quote=QUOTE if s == decisive else None,
        assessment_reason="Published hours." if s == decisive else "Context only.") for s in retrieved.evidence]
    sources = {s.evidence_id: s for s in retrieved.evidence}
    outcome, score, summary = score_evidence(group_evidence(assessed, sources), sources)
    # Neutral contextual evidence is not a scoring vote.
    explanation = "The published hours contradict six." if decisive else "The opening hours are missing."
    finding = dict(assertion_id="a1", status="contradicted" if decisive else "unresolved",
        explanation=explanation, repair_queries=[] if decisive else ["library official opening hours"],
        gaps=[] if decisive else ["Closing time"], citations=[])
    if decisive:
        finding.update(citations=[dict(evidence_id=decisive.evidence_id, quote=QUOTE)],
            basis="direct", scope="established", evidence_adequacy=.7, scope_checks=dict(
                entity="established", jurisdiction="not_applicable", time="established",
                population="not_applicable", metric="not_applicable", modality="established", attribution="not_applicable"))
    return AssessmentResult(concern_label=LABELS[outcome], misinformation_risk_score=score,
        assessment_outcome=outcome, scoring=summary, uncertainty="Medium" if decisive else "High",
        uncertainty_reasons=[explanation], explanation=explanation,
        recommended_action="Read the opening hours before visiting.", assessed_evidence=assessed,
        verification=VerificationAssessment(findings=[finding], rationale=explanation,
            repair_queries=finding["repair_queries"]))


def pipeline(*, initial=None, repair=None, assessor=assessment, planner=plan, recorder=None):
    return PipelineOrchestrator(
        prepare_input=lambda text: PreparedText(original_text=text, normalised_text=text, language="en"),
        analyze_claim=lambda prepared: ClaimAnalysis(extracted_claim=prepared.normalised_text,
            claim_category="factual", checkable=True, classification_reason="A factual assertion.", claim_confidence=.99),
        retrieve_evidence=lambda claim: initial or retrieval([source()]),
        assess_evidence=assessor, plan_verification=planner, repair_evidence=repair,
        repository=InMemoryResultRepository(), clock=lambda: NOW, id_factory=lambda: "planned-check",
        run_recorder=recorder,
    )


def test_one_gap_driven_repair_reassesses_and_persists_grounded_findings():
    calls, runs = [], []
    def repair(claim, previous, queries):
        calls.append(queries)
        result = retrieval([*previous.evidence, source("hours", QUOTE)])
        result.trace.search_requests = 2
        return result
    p = pipeline(repair=repair, recorder=runs.append)
    result = p.analyze(TEXT)
    assert calls == [["library official opening hours"]]
    assert result.assessment_outcome == "contradicted"
    assert result.verification.repair_status == "improved"
    assert result.verification.repair_attempted
    assert result.retrieval_trace.search_requests == 2
    assert result.verification.findings[0].citations[0].quote == QUOTE
    assert TextAnalysisResult.model_validate_json(result.model_dump_json()) == result
    assert p._repository.results[result.result_id] == result
    assert "verification_reassessment" in runs[0]["stage_timings_ms"]


def test_no_new_source_does_not_repeat_assessment_or_repair():
    calls = []
    def counted(claim, retrieved):
        calls.append(True)
        return assessment(claim, retrieved)
    result = pipeline(repair=lambda c, r, q: r, assessor=counted).analyze(TEXT)
    assert len(calls) == 1
    assert result.verification.repair_status == "no_new_evidence"
    assert result.assessment_outcome == "insufficient_evidence"


def test_successful_empty_search_can_be_repaired():
    result = pipeline(initial=retrieval([]), repair=lambda c, r, q: retrieval([source("hours", QUOTE)])).analyze(TEXT)
    assert result.assessment_outcome == "contradicted"
    assert result.verification.repair_attempted


def test_optional_repair_failure_preserves_partial_evidence_with_limitation():
    def fail(*args):
        raise ValueError("Provider failure must not be exposed")
    result = pipeline(repair=fail).analyze(TEXT)
    assert result.assessment_outcome == "insufficient_evidence"
    assert result.verification.repair_status == "unavailable"
    assert result.evidence[0].evidence_id == "old"
    assert any("could not finish" in warning for warning in result.warnings)
    assert "Provider failure" not in result.model_dump_json()


def test_empty_search_followed_by_outage_is_retryable_failure():
    with pytest.raises(PipelineComponentError) as error:
        pipeline(initial=retrieval([]), repair=lambda *args: RetrievalResult(retrieval_status="failed")).analyze(TEXT)
    assert error.value.error_code == "RETRIEVAL_REPAIR_UNAVAILABLE"


def test_repair_is_skipped_when_deadline_budget_is_spent(monkeypatch):
    from app.pipeline.orchestration import service
    monkeypatch.setattr(service, "REPAIR_START_LIMIT_SECONDS", -1)
    def unexpected(*args):
        pytest.fail("Repair must not start after the budget is spent")
    result = pipeline(repair=unexpected).analyze(TEXT)
    assert result.verification.repair_status == "budget_exhausted"
    assert not result.verification.repair_attempted


def test_decisive_result_does_not_start_an_unnecessary_repair():
    def unexpected(*args):
        pytest.fail("A settled assertion needs no gap repair")
    result = pipeline(initial=retrieval([source("hours", QUOTE)]), repair=unexpected).analyze(TEXT)
    assert result.assessment_outcome == "contradicted"
    assert not result.verification.repair_attempted


def test_account_isolation_keeps_planning_and_repair_callbacks():
    isolated = pipeline(repair=lambda c, r, q: r).with_repository(InMemoryResultRepository())
    result = isolated.analyze(TEXT)
    assert result.verification_plan is not None
    assert result.verification.repair_status == "no_new_evidence"


def test_reassessment_outage_preserves_initial_result_not_unassessed_new_evidence():
    def assessor(claim, retrieved):
        if len(retrieved.evidence) > 1:
            raise ValueError("Broken provider response")
        return assessment(claim, retrieved)
    result = pipeline(assessor=assessor,
        repair=lambda c, r, q: retrieval([*r.evidence, source("hours", QUOTE)])).analyze(TEXT)
    assert [s.evidence_id for s in result.evidence] == ["old"]
    assert result.verification.repair_status == "unavailable"


def test_partial_search_outage_is_not_recorded_as_successful_absence():
    def repair(claim, previous, queries):
        previous.trace.decisions.append({"decision": "assessment_driven_repair_finished", "outcome": "partial_failure"})
        previous.warnings.append("The follow-up search provider was unavailable.")
        return previous
    result = pipeline(repair=repair).analyze(TEXT)
    assert result.verification.repair_status == "unavailable"
    assert "unavailable" in result.warnings[-1]
    assert result.assessment_outcome == "insufficient_evidence"
