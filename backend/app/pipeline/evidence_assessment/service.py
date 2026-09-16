"""Sprint 1 lexical evidence-assessment baseline and shared aggregation.

The baseline is retained for reproducible comparisons with semantic assessment.

The public pipeline boundary is::

    assess_evidence(ClaimAnalysis, RetrievalResult) -> AssessmentResult

The older ``assess_claim`` function is retained only as a JSON/dictionary
adapter so the existing shared samples remain easy to run.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal

from app.pipeline.shared.models import (
    AssessmentResult,
    AssessedEvidence,
    ClaimAnalysis,
    EvidenceCandidate,
    RetrievalResult,
)


from .scoring import LABELS, MIN_DECISIVE_QUALITY, group_evidence, score_evidence, unscored_summary, provisional_summary


Stance = Literal["supporting", "contradicting", "neutral"]

AUTHORITATIVE_SOURCE_TYPES = {"government", "fact_check", "academic"}

SOURCE_BASE_LIMITS = {
    "government": 0.94,
    "fact_check": 0.92,
    "academic": 0.89,
    "news": 0.84,
    "other": 0.70,
}

DAY_WORDS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}

MONTH_WORDS = (
    "january|february|march|april|may|june|july|august|"
    "september|october|november|december"
)

NEGATION_PATTERNS = (
    r"\bno\b",
    r"\bnot\b",
    r"\bnever\b",
    r"\b(?:is|are|was|were|do|does|did|has|have|had|will|would|can|"
    r"could|should|must)n['’]?t\b",
    r"\bden(?:y|ies|ied)\b",
    r"\bfalse\b",
)

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "will",
}


class AssessmentInputError(ValueError):
    """The retrieval output cannot be assessed as a completed result."""


def _words(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9$]+", text.lower())
        if token not in STOP_WORDS
    }


def _money_amounts(text: str | None) -> set[str]:
    """Return normalised dollar/SGD amounts mentioned in text."""
    if not text:
        return set()
    matches = re.findall(
        r"(?:S\$|SGD|\$)\s?(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    return set(matches)


def _explicit_dates(text: str | None) -> set[str]:
    if not text:
        return set()
    pattern = rf"\b\d{{1,2}}\s+(?:{MONTH_WORDS})\s+\d{{4}}\b"
    return {match.lower() for match in re.findall(pattern, text, re.I)}


def _days(text: str | None) -> set[str]:
    return _words(text) & DAY_WORDS


def _contains_negation(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in NEGATION_PATTERNS)


def _topic_overlap(claim: str, passage: str) -> float:
    claim_words = _words(claim)
    if not claim_words:
        return 0.0
    return len(claim_words & _words(passage)) / len(claim_words)


def classify_stance(claim: str, passage: str) -> Stance:
    """Classify direct Sprint 1 cases as supporting/contradicting/neutral.

    This remains a deliberately simple lexical baseline. Complex paraphrase,
    implied contradiction, sarcasm and multi-step reasoning require a later
    evaluated model rather than more untested hard-coded phrases.
    """
    if not claim or not passage:
        return "neutral"

    overlap = _topic_overlap(claim, passage)
    if overlap < 0.25:
        return "neutral"

    claim_days = _days(claim)
    passage_days = _days(passage)
    if claim_days and not passage_days:
        return "neutral"
    if claim_days and passage_days and claim_days.isdisjoint(passage_days):
        return "contradicting"

    claim_dates = _explicit_dates(claim)
    passage_dates = _explicit_dates(passage)
    if claim_dates and passage_dates and claim_dates.isdisjoint(passage_dates):
        return "contradicting"

    claim_money = _money_amounts(claim)
    passage_money = _money_amounts(passage)
    if claim_money and passage_money and claim_money.isdisjoint(passage_money):
        return "contradicting"

    if _contains_negation(claim) != _contains_negation(passage):
        return "contradicting"

    important_values_match = all(
        not claim_values or claim_values.issubset(passage_values)
        for claim_values, passage_values in (
            (claim_money, passage_money),
            (claim_dates, passage_dates),
            (claim_days, passage_days),
        )
    )
    if overlap >= 0.45 and important_values_match:
        return "supporting"

    return "neutral"


def _as_evidence(
    evidence: EvidenceCandidate | Mapping[str, Any],
) -> EvidenceCandidate:
    if isinstance(evidence, EvidenceCandidate):
        return evidence
    return EvidenceCandidate.model_validate(evidence)


def calculate_quality_score(
    evidence: EvidenceCandidate | Mapping[str, Any],
    stance: Stance,
) -> float:
    """Calculate evidence quality; neutral evidence is capped, not fixed."""
    item = _as_evidence(evidence)
    relevance = max(0.0, min(1.0, float(item.retrieval_score)))

    # Relevance varies continuously. Age alone cannot invalidate historical facts;
    # date/scope applicability is checked before evidence may vote.
    quality = min(SOURCE_BASE_LIMITS[item.source_type], relevance)

    if stance == "neutral":
        quality = min(quality, 0.45)

    return round(max(0.0, min(1.0, quality)), 2)


def _display(values: set[str]) -> str:
    return ", ".join(sorted(value.title() for value in values))


def _assessment_reason(claim: str, passage: str, stance: Stance) -> str:
    claim_days = _days(claim)
    passage_days = _days(passage)
    claim_dates = _explicit_dates(claim)
    passage_dates = _explicit_dates(passage)
    claim_money = _money_amounts(claim)
    passage_money = _money_amounts(passage)

    if stance == "neutral":
        if claim_days and not passage_days:
            return (
                "The passage discusses the topic but does not state the "
                f"claimed day ({_display(claim_days)})."
            )
        return (
            "The passage is related to the claim but does not directly "
            "support or contradict its decisive detail."
        )

    if stance == "contradicting":
        if claim_days and passage_days and claim_days.isdisjoint(passage_days):
            return (
                f"The claim states {_display(claim_days)}, while the evidence "
                f"states {_display(passage_days)}."
            )
        if claim_dates and passage_dates and claim_dates.isdisjoint(passage_dates):
            return "The evidence gives a different date from the claim."
        if claim_money and passage_money and claim_money.isdisjoint(passage_money):
            return "The evidence gives a different amount from the claim."
        if _contains_negation(claim) != _contains_negation(passage):
            return (
                "The passage reverses the claim's positive or negative "
                "meaning."
            )
        return "The evidence contradicts an important detail in the claim."

    matched_details: list[str] = []
    if claim_money:
        matched_details.append("amount")
    if claim_dates:
        matched_details.append("date")
    if claim_days:
        matched_details.append("day")
    if matched_details:
        return "The evidence matches the claim's " + " and ".join(
            matched_details
        ) + "."
    return "The evidence directly supports important details in the claim."


def assess_evidence_item(
    claim: str,
    evidence: EvidenceCandidate | Mapping[str, Any],
) -> AssessedEvidence:
    item = _as_evidence(evidence)
    stance = classify_stance(claim, item.passage)
    return AssessedEvidence(
        evidence_id=item.evidence_id,
        stance=stance,
        quality_score=calculate_quality_score(item, stance),
        assessment_reason=_assessment_reason(claim, item.passage, stance),
    )


def _evidence_by_id(
    evidence: list[EvidenceCandidate],
) -> dict[str, EvidenceCandidate]:
    return {item.evidence_id: item for item in evidence}


def _uncertainty(
    assessed: list[AssessedEvidence],
    evidence: list[EvidenceCandidate],
) -> tuple[str, list[str]]:
    useful = [item for item in assessed if item.stance != "neutral"]
    if not useful:
        return (
            "High",
            ["The retrieved evidence does not directly answer the claim."],
        )

    supporting = [item for item in useful if item.stance == "supporting"]
    contradicting = [
        item for item in useful if item.stance == "contradicting"
    ]
    if supporting and contradicting:
        return "High", ["The available sources provide conflicting evidence."]

    sources = _evidence_by_id(evidence)
    if len(useful) == 1:
        useful_item = useful[0]
        source = sources[useful_item.evidence_id]
        if (
            useful_item.quality_score >= 0.90
            and source.source_type in AUTHORITATIVE_SOURCE_TYPES
        ):
            return (
                "Medium",
                ["Only one highly relevant authoritative source was found."],
            )
        return "High", ["Only one limited-quality relevant source was found."]

    average_quality = sum(item.quality_score for item in useful) / len(useful)
    if average_quality >= 0.80:
        return "Low", ["Multiple relevant sources provide consistent evidence."]
    return (
        "Medium",
        ["Multiple sources were found, but their overall quality is limited."],
    )


def _direct_sources(
    stance: Literal["supporting", "contradicting"],
    assessed: list[AssessedEvidence],
    evidence: list[EvidenceCandidate],
) -> list[EvidenceCandidate]:
    ids = {item.evidence_id for item in assessed if item.stance == stance}
    return [item for item in evidence if item.evidence_id in ids]


def _source_description(sources: list[EvidenceCandidate]) -> str:
    if not sources:
        return "The available evidence"
    if all(source.source_type == "government" for source in sources):
        return "The cited government evidence"
    if all(source.source_type == "fact_check" for source in sources):
        return "The cited fact-check evidence"
    return "The cited evidence"


def _explanation(
    label: str,
    assessed: list[AssessedEvidence],
    evidence: list[EvidenceCandidate],
) -> str:
    if label == "Not Enough Information":
        return "There is not enough reliable evidence to assess this claim."

    supporting = [item for item in assessed if item.stance == "supporting"]
    contradicting = [
        item for item in assessed if item.stance == "contradicting"
    ]
    if supporting and contradicting:
        return (
            "The cited sources conflict, so the claim should be treated "
            "with caution."
        )
    if contradicting:
        sources = _direct_sources("contradicting", assessed, evidence)
        return f"{_source_description(sources)} contradicts the submitted claim."
    sources = _direct_sources("supporting", assessed, evidence)
    return f"{_source_description(sources)} supports the submitted claim."


def _recommended_action(label: str) -> str:
    if label == "High Concern":
        return (
            "Do not forward the claim yet. Review the contradicting cited "
            "evidence first."
        )
    if label == "Low Concern":
        return "Review the supporting cited evidence before sharing the claim."
    if label == "Needs Caution":
        return "Compare the conflicting cited sources before sharing the claim."
    return "Check an authoritative source before believing or forwarding the claim."


def _claimed_day_explanation(claim: str) -> str:
    days = _days(claim)
    if not days:
        return "There is not enough reliable evidence to assess this claim."
    return (
        "The retrieved evidence does not confirm the claimed start day "
        f"({_display(days)})."
    )


def _not_enough_information(
    claim: str,
    reasons: list[str],
    assessed: list[AssessedEvidence] | None = None,
) -> AssessmentResult:
    assessed_items = assessed or []
    explanation = (
        _claimed_day_explanation(claim)
        if assessed_items and _days(claim)
        else "There is not enough reliable evidence to assess this claim."
    )
    return AssessmentResult(
        concern_label="Not Enough Information",
        misinformation_risk_score=50,
        uncertainty="High",
        uncertainty_reasons=reasons,
        explanation=explanation,
        recommended_action=_recommended_action("Not Enough Information"),
        assessed_evidence=assessed_items,
        assessment_outcome="insufficient_evidence",
        scoring=provisional_summary(reasons[0]),
    )


def _non_checkable_result(claim: ClaimAnalysis) -> AssessmentResult:
    if claim.claim_category == "opinion":
        explanation = (
            "This statement is an opinion, so it cannot be assessed as a "
            "factual misinformation claim."
        )
        action = "Treat this as a personal opinion rather than a verified fact."
    else:
        explanation = (
            "The submitted content does not contain an objectively checkable "
            "factual claim."
        )
        action = (
            "Treat the statement cautiously unless a checkable factual claim "
            "can be identified."
        )
    return AssessmentResult(
        concern_label="Not Enough Information",
        misinformation_risk_score=None,
        uncertainty="High",
        uncertainty_reasons=[
            "No objectively checkable factual claim was found."
        ],
        explanation=explanation,
        recommended_action=action,
        assessed_evidence=[],
        assessment_outcome="not_checkable",
        scoring=unscored_summary("No checkable factual claim was identified; no risk score is assigned."),
    )


def _assess(
    claim: ClaimAnalysis,
    retrieval: RetrievalResult | None,
) -> AssessmentResult:
    if not claim.checkable:
        return _non_checkable_result(claim)

    claim_text = claim.extracted_claim or ""
    if retrieval is None:
        return _not_enough_information(
            claim_text,
            ["No sufficiently relevant evidence was found."],
        )

    if retrieval.retrieval_status == "failed":
        raise AssessmentInputError(
            "A technical retrieval failure must be handled as a retryable "
            "pipeline error, not as Not Enough Information."
        )

    if retrieval.retrieval_status == "no_evidence":
        reasons = retrieval.warnings or [
            "No sufficiently relevant evidence was found."
        ]
        return _not_enough_information(claim_text, reasons)

    assessed = [
        assess_evidence_item(claim_text, item) for item in retrieval.evidence
    ]
    return summarise_assessments(claim_text, retrieval, assessed)


def summarise_assessments(
    claim_text: str,
    retrieval: RetrievalResult,
    assessed: list[AssessedEvidence],
) -> AssessmentResult:
    """Determine a verdict from admissible evidence, then calculate its indicator."""
    by_id = _evidence_by_id(retrieval.evidence)
    # New retrieval scope decisions constrain both semantic and lexical assessors.
    # Old saved results are not rescored; these rules apply only to new checks.
    assessed = [item.model_copy(deep=True) for item in assessed]
    for item in assessed:
        provenance = by_id[item.evidence_id].provenance
        if provenance and (provenance.relevance != "direct" or provenance.applicability != "established"):
            item.stance = "neutral"
            item.quality_score = min(item.quality_score, 0.45)
            item.assessment_reason = provenance.applicability_reason if provenance.applicability != "established" else provenance.relevance_reason
    for item in assessed:
        if item.stance != "neutral" and item.quality_score < MIN_DECISIVE_QUALITY:
            item.stance = "neutral"
            item.assessment_reason = "The passage has insufficient relevance or source quality for a decisive finding."
    voting = group_evidence(assessed, by_id)
    outcome, risk, scoring = score_evidence(voting, by_id)
    label = LABELS[outcome]

    if scoring.status == "provisional":
        claim_days = _days(claim_text)
        passages_have_days = any(
            _days(item.passage) for item in retrieval.evidence
        )
        reasons = (
            ["The retrieved evidence does not state the claimed start day."]
            if claim_days and not passages_have_days
            else ["The retrieved evidence does not directly answer the claim."]
        )
        result = _not_enough_information(claim_text, reasons, assessed)
        result.scoring = scoring
        return result

    uncertainty, uncertainty_reasons = _uncertainty(
        voting,
        retrieval.evidence,
    )
    return AssessmentResult(
        concern_label=label,
        assessment_outcome=outcome,
        scoring=scoring,
        misinformation_risk_score=risk,
        uncertainty=uncertainty,
        uncertainty_reasons=uncertainty_reasons,
        explanation=_explanation(label, assessed, retrieval.evidence),
        recommended_action=_recommended_action(label),
        assessed_evidence=assessed,
    )


def assess_evidence(
    claim: ClaimAnalysis,
    retrieval: RetrievalResult,
) -> AssessmentResult:
    """Integration-ready Poon -> Donovan pipeline boundary."""
    if not isinstance(claim, ClaimAnalysis):
        raise TypeError("claim must be a ClaimAnalysis object.")
    if not isinstance(retrieval, RetrievalResult):
        raise TypeError("retrieval must be a RetrievalResult object.")
    return _assess(claim, retrieval)


def assess_claim(
    claim_analysis: ClaimAnalysis | Mapping[str, Any],
    retrieval_result: RetrievalResult | Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compatibility adapter for the existing dictionary/JSON samples."""
    claim = (
        claim_analysis
        if isinstance(claim_analysis, ClaimAnalysis)
        else ClaimAnalysis.model_validate(claim_analysis)
    )
    if retrieval_result is None:
        retrieval = None
    elif isinstance(retrieval_result, RetrievalResult):
        retrieval = retrieval_result
    else:
        retrieval = RetrievalResult.model_validate(retrieval_result)
    return _assess(claim, retrieval).model_dump(mode="json")
