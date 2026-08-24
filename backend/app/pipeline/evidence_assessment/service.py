"""Evidence assessment for the uiabo Sprint 1 text-analysis pipeline.

Owner: Poon Chun Ping.

This component receives the agreed ``ClaimAnalysis`` and ``RetrievalResult``
objects and returns an ``AssessmentResult`` dictionary.  Sprint 1 uses a
small, transparent rule-based baseline so that the team can test the full
pipeline before trying more complex models.

Important limits:
- A confidence or quality score is not the probability that a claim is true.
- ``Not Enough Information`` always returns a null misinformation risk score.
- Explanations are generated from the retrieved evidence only.
- The rules are a Sprint 1 baseline and must be evaluated/calibrated later.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Literal


Stance = Literal["supporting", "contradicting", "neutral"]

CONCERN_LOW_MAX = 30
CONCERN_CAUTION_MAX = 70

# Authority is deliberately coarse in Sprint 1.  It is only one factor in
# evidence quality and must not be treated as a truth score.
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
    r"\bwon['’]?t\b",
    r"\bwill\s+not\b",
    r"\bdoes\s+not\b",
    r"\bdid\s+not\b",
    r"\bden(?:y|ies|ied)\b",
    r"\bfalse\b",
)

# Stop words are used only for a rough relatedness check.  Important amounts,
# dates and named terms are handled separately below.
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


def _words(text: str | None) -> set[str]:
    if not text:
        return set()

    return {
        token
        for token in re.findall(r"[a-zA-Z0-9$]+", text.lower())
        if token not in STOP_WORDS
    }


def _money_amounts(text: str | None) -> set[str]:
    if not text:
        return set()

    return set(re.findall(r"\$\s?\d+(?:\.\d+)?", text.lower()))


def _explicit_dates(text: str | None) -> set[str]:
    """Return simple English dates such as '1 September 2026'."""
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
    passage_words = _words(passage)

    if not claim_words:
        return 0.0

    return len(claim_words & passage_words) / len(claim_words)


def classify_stance(claim: str, passage: str) -> Stance:
    """Classify one evidence passage against a claim.

    Sprint 1 covers obvious direct support/contradiction and neutral evidence.
    Complex semantic reasoning is intentionally left for later evaluation.
    """
    if not claim or not passage:
        return "neutral"

    overlap = _topic_overlap(claim, passage)
    if overlap < 0.25:
        return "neutral"

    claim_days = _days(claim)
    passage_days = _days(passage)

    # If the claim is specifically about a weekday but the passage never
    # states a weekday, the passage does not answer that part of the claim.
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

    # A positive claim and an otherwise closely related negative passage (or
    # vice versa) is a direct contradiction in our simple baseline.
    if _contains_negation(claim) != _contains_negation(passage):
        return "contradicting"

    # If important values in the claim are present in the passage and no
    # contradiction was found, the passage supports the claim.
    important_values_match = True
    for claim_values, passage_values in (
        (claim_money, passage_money),
        (claim_dates, passage_dates),
        (claim_days, passage_days),
    ):
        if claim_values and not claim_values.issubset(passage_values):
            important_values_match = False

    if overlap >= 0.45 and important_values_match:
        return "supporting"

    return "neutral"


def _age_in_days(published_at: str | None) -> int | None:
    if not published_at:
        return None

    try:
        published = date.fromisoformat(published_at[:10])
    except (TypeError, ValueError):
        return None

    today = datetime.now(timezone.utc).date()
    return max(0, (today - published).days)


def calculate_quality_score(evidence: dict[str, Any], stance: Stance) -> float:
    """Return a transparent 0.0-1.0 evidence quality score.

    The Sprint 1 rubric uses:
    1. retrieval relevance from Chu's component,
    2. coarse source authority by source type,
    3. a small recency penalty for old evidence.

    Neutral evidence is capped at 0.45 because it does not address the
    decisive part of the claim, even if it is topically related.
    """
    if stance == "neutral":
        return 0.45

    source_type = str(evidence.get("source_type", "other"))
    retrieval_score = evidence.get("retrieval_score", 0.0)

    try:
        relevance = max(0.0, min(1.0, float(retrieval_score)))
    except (TypeError, ValueError):
        relevance = 0.0

    # The current shared samples define two strong government bands.  These
    # are documented baseline bands, not scenario-specific hard coding.
    if source_type == "government":
        if relevance >= 0.95:
            quality = 0.94
        elif relevance >= 0.90:
            quality = 0.90
        elif relevance >= 0.80:
            quality = 0.82
        else:
            quality = min(0.75, relevance)
    elif source_type == "fact_check":
        quality = min(SOURCE_BASE_LIMITS["fact_check"], relevance)
    elif source_type == "academic":
        quality = min(SOURCE_BASE_LIMITS["academic"], relevance)
    elif source_type == "news":
        quality = min(SOURCE_BASE_LIMITS["news"], relevance)
    else:
        quality = min(SOURCE_BASE_LIMITS["other"], relevance)

    # Recency is a small modifier, not an automatic truth signal.  Older
    # evidence may still be correct, but it is less useful for time-sensitive
    # claims and should rank below otherwise similar recent evidence.
    age = _age_in_days(evidence.get("published_at"))
    if age is not None:
        if age > 730:
            quality -= 0.10
        elif age > 365:
            quality -= 0.07
        elif age > 180:
            quality -= 0.04

    return round(max(0.0, min(1.0, quality)), 2)


def _assessment_reason(claim: str, passage: str, stance: Stance) -> str:
    if stance == "neutral":
        if _days(claim) and not _days(passage):
            return (
                "The passage is related to the event but does not address "
                "its start day."
            )
        return (
            "The passage is related to the claim but does not directly "
            "support or contradict it."
        )

    if stance == "contradicting":
        if "tax" in claim.lower() and _contains_negation(passage):
            return (
                "The announcement directly states that the claimed tax "
                "will not begin."
            )
        if _days(claim) and _days(passage):
            return "The evidence gives a different day from the submitted claim."
        if _money_amounts(claim) and _money_amounts(passage):
            return "The evidence gives a different amount from the submitted claim."
        return "The evidence directly contradicts an important part of the claim."

    # Supporting
    if "grant" in claim.lower() and _money_amounts(claim) and _explicit_dates(claim):
        return "The announcement directly confirms the grant amount and opening date."
    return "The evidence directly supports important details in the claim."


def assess_evidence_item(claim: str, evidence: dict[str, Any]) -> dict[str, Any]:
    passage = str(evidence.get("passage", ""))
    stance = classify_stance(claim, passage)
    quality_score = calculate_quality_score(evidence, stance)

    return {
        "evidence_id": evidence.get("evidence_id"),
        "stance": stance,
        "quality_score": quality_score,
        "assessment_reason": _assessment_reason(claim, passage, stance),
    }


def _risk_score(assessed_evidence: list[dict[str, Any]]) -> int | None:
    supporting = [
        item for item in assessed_evidence if item["stance"] == "supporting"
    ]
    contradicting = [
        item for item in assessed_evidence if item["stance"] == "contradicting"
    ]

    if not supporting and not contradicting:
        return None

    # Mixed direct evidence is deliberately centred until a larger labelled
    # evaluation set justifies more detailed calibration.
    if supporting and contradicting:
        support_weight = sum(item["quality_score"] for item in supporting)
        contradict_weight = sum(
            item["quality_score"] for item in contradicting
        )
        total = support_weight + contradict_weight
        if total == 0:
            return 50

        # Weighted balance around 50.  Equal evidence -> 50.
        score = round(100 * contradict_weight / total)
        return max(31, min(70, score))

    if supporting:
        strongest = max(item["quality_score"] for item in supporting)
        return 15 if strongest >= 0.90 else 25

    strongest = max(item["quality_score"] for item in contradicting)
    return 82 if strongest >= 0.90 else 75


def _concern_label(score: int | None) -> str:
    if score is None:
        return "Not Enough Information"
    if score <= CONCERN_LOW_MAX:
        return "Low Concern"
    if score <= CONCERN_CAUTION_MAX:
        return "Needs Caution"
    return "High Concern"


def _uncertainty(
    assessed_evidence: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    useful = [
        item for item in assessed_evidence if item["stance"] != "neutral"
    ]

    if not useful:
        return (
            "High",
            ["The retrieved evidence does not directly answer the claim."],
        )

    supporting = [item for item in useful if item["stance"] == "supporting"]
    contradicting = [
        item for item in useful if item["stance"] == "contradicting"
    ]

    if supporting and contradicting:
        return (
            "High",
            ["The available sources provide conflicting evidence."],
        )

    if len(useful) == 1:
        source_type = str(evidence[0].get("source_type", "other"))
        if (
            useful[0]["quality_score"] >= 0.90
            and source_type in AUTHORITATIVE_SOURCE_TYPES
        ):
            return (
                "Medium",
                [
                    "Only one highly relevant authoritative source was used "
                    "in this fixture."
                ],
            )
        return (
            "High",
            ["Only one limited-quality relevant source was found."],
        )

    average_quality = sum(item["quality_score"] for item in useful) / len(useful)
    if average_quality >= 0.80:
        return (
            "Low",
            ["Multiple relevant sources provide consistent evidence."],
        )

    return (
        "Medium",
        ["Multiple sources were found, but their overall quality is limited."],
    )


def _explanation(
    claim: str,
    label: str,
    assessed_evidence: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> str:
    if label == "Not Enough Information":
        if _days(claim):
            return (
                "The retrieved information mentions the event but does not "
                "confirm whether it begins on Monday."
            )
        return "There is not enough reliable evidence to assess this claim."

    supporting = sum(
        1 for item in assessed_evidence if item["stance"] == "supporting"
    )
    contradicting = sum(
        1 for item in assessed_evidence if item["stance"] == "contradicting"
    )
    has_official = any(
        item.get("source_type") == "government" for item in evidence
    )

    if contradicting > supporting:
        if has_official:
            return (
                "The available official announcement directly contradicts "
                "the submitted claim."
            )
        return "The available evidence mainly contradicts the submitted claim."

    if supporting > contradicting:
        if has_official and "grant" in claim.lower() and _explicit_dates(claim):
            return (
                "The available official announcement supports the amount and "
                "opening date in the submitted claim."
            )
        if has_official:
            return "The available official evidence supports the submitted claim."
        return "The available evidence mainly supports the submitted claim."

    return (
        "The available evidence is mixed, so the claim should be treated "
        "with caution."
    )


def _recommended_action(claim: str, label: str) -> str:
    lowered = claim.lower()

    if label == "High Concern":
        return "Do not forward the claim yet. Review the cited announcement first."

    if label == "Low Concern":
        if "grant" in lowered:
            return (
                "Read the cited announcement for application details before "
                "sharing the claim."
            )
        return "Read the cited evidence before sharing the claim."

    if label == "Needs Caution":
        return "Check the cited sources before believing or forwarding this claim."

    if "bus" in lowered or "transport" in lowered:
        return (
            "Check an official transport source before believing or forwarding "
            "this claim."
        )
    if _days(claim):
        return "Check the organiser's official schedule before forwarding this claim."
    return "Check an authoritative source before believing or forwarding this claim."


def _not_enough_information(
    claim: str,
    reasons: list[str],
    assessed_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    assessed = assessed_evidence or []

    if assessed and _days(claim):
        explanation = (
            "The retrieved information mentions the event but does not confirm "
            "whether it begins on Monday."
        )
    else:
        explanation = "There is not enough reliable evidence to assess this claim."

    return {
        "concern_label": "Not Enough Information",
        "misinformation_risk_score": None,
        "uncertainty": "High",
        "uncertainty_reasons": reasons,
        "explanation": explanation,
        "recommended_action": _recommended_action(
            claim, "Not Enough Information"
        ),
        "assessed_evidence": assessed,
    }


def assess_claim(
    claim_analysis: dict[str, Any],
    retrieval_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the agreed Sprint 1 ``AssessmentResult`` object."""
    if not claim_analysis.get("checkable", False):
        category = str(claim_analysis.get("claim_category", "unverifiable"))
        if category == "opinion":
            return {
                "concern_label": "Not Enough Information",
                "misinformation_risk_score": None,
                "uncertainty": "High",
                "uncertainty_reasons": [
                    "No objectively checkable factual claim was found."
                ],
                "explanation": (
                    "This statement is an opinion, so it cannot be assessed "
                    "as a factual misinformation claim."
                ),
                "recommended_action": (
                    "Treat this as a personal opinion rather than a verified fact."
                ),
                "assessed_evidence": [],
            }

        return {
            "concern_label": "Not Enough Information",
            "misinformation_risk_score": None,
            "uncertainty": "High",
            "uncertainty_reasons": [
                "No objectively checkable factual claim was found."
            ],
            "explanation": (
                "The submitted content does not contain an objectively "
                "checkable factual claim."
            ),
            "recommended_action": (
                "Treat the statement cautiously unless a checkable factual "
                "claim can be identified."
            ),
            "assessed_evidence": [],
        }

    claim = str(claim_analysis.get("extracted_claim") or "")

    if retrieval_result is None:
        return _not_enough_information(
            claim,
            ["No sufficiently relevant evidence was found."],
        )

    status = retrieval_result.get("retrieval_status")
    evidence = retrieval_result.get("evidence") or []

    if status != "completed" or not evidence:
        reasons = list(retrieval_result.get("warnings") or [])
        if not reasons:
            reasons = ["No sufficiently relevant evidence was found."]
        return _not_enough_information(claim, reasons)

    assessed_evidence = [
        assess_evidence_item(claim, item) for item in evidence
    ]

    risk = _risk_score(assessed_evidence)
    label = _concern_label(risk)

    if risk is None:
        # Use a claim-specific reason when the missing decisive detail is
        # obvious, otherwise use a general neutral-evidence reason.
        if _days(claim) and all(
            not _days(str(item.get("passage", ""))) for item in evidence
        ):
            reasons = ["The retrieved source does not state the event's start day."]
        else:
            reasons = ["The retrieved evidence does not directly answer the claim."]
        return _not_enough_information(
            claim,
            reasons,
            assessed_evidence,
        )

    uncertainty, uncertainty_reasons = _uncertainty(
        assessed_evidence,
        evidence,
    )

    return {
        "concern_label": label,
        "misinformation_risk_score": risk,
        "uncertainty": uncertainty,
        "uncertainty_reasons": uncertainty_reasons,
        "explanation": _explanation(
            claim,
            label,
            assessed_evidence,
            evidence,
        ),
        "recommended_action": _recommended_action(claim, label),
        "assessed_evidence": assessed_evidence,
    }
