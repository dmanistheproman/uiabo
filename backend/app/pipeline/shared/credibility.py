"""Public credibility contract, separate from the legacy risk field.

This is a prototype evidence index, not calibrated truth probability. Evidence
admission and whole-claim scope checks run upstream; only admitted votes count.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = "credibility-v2"
MIN_STRENGTH = 0.60
STRONG_STRENGTH = 0.90
DEFINITION = (
    "Higher means the evidence supports the claim. Lower means the evidence "
    "contradicts it. This is an evidence indicator, not a percentage probability "
    "of truth. Even 0 or 100 is not a guarantee."
)
LABELS = {
    "strong_support": "Strong evidence this is true",
    "support": "Evidence suggests this is true",
    "mixed": "Mixed evidence",
    "contradiction": "Evidence suggests this is false",
    "strong_contradiction": "Strong evidence this is false",
}


class CredibilityRating(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["credibility-v1", "credibility-v2"] = "credibility-v1"
    status: Literal["rated", "insufficient_evidence", "not_applicable", "plausibility_only", "legacy_unrated"]
    score: int | None = Field(default=None, ge=0, le=100, strict=True)
    label: str
    explanation: str


def _build_v1(result) -> CredibilityRating:
    """Derive a rating from validated evidence metadata, never a naked risk score."""
    outcome = result.assessment_outcome
    summary = result.scoring
    if getattr(result, "checkable", True) is False or outcome == "not_checkable":
        return CredibilityRating(status="not_applicable", label="Not a factual claim",
            explanation="No checkable factual claim was identified. Not rated does not mean true or false.")
    if outcome == "highly_unlikely" or (summary and summary.status == "plausibility_based"):
        return CredibilityRating(status="plausibility_only", label="Highly unlikely based on climate records",
            explanation="Climate records make this prediction implausible, but do not measure its probability or prove future weather impossible. No factual credibility score is assigned.")
    if (outcome in {"unsupported", "insufficient_evidence"}
            or result.concern_label == "Not Enough Information"
            or (summary and summary.status in {"provisional", "not_applicable"})):
        return CredibilityRating(status="insufficient_evidence", label="Not enough evidence",
            explanation="Not rated: there is not enough relevant evidence to assess this claim. Missing evidence is not proof that it is true or false.")
    if not summary or outcome not in {"supported", "contradicted", "conflicting"}:
        return _legacy_unrated()
    s, c = summary.supporting_strength, summary.contradicting_strength
    # Legacy metadata must meet today's minimum before it can be displayed on
    # this scale. Weak/neutral evidence is not a vote, including for a midpoint.
    if (not (s or c) or any(0 < value < MIN_STRENGTH for value in (s, c))
            or bool(s) != bool(summary.supporting_origins)
            or bool(c) != bool(summary.contradicting_origins)
            or outcome != ("conflicting" if s and c else "supported" if s else "contradicted")):
        return _legacy_unrated()
    key = ("mixed" if s and c else
           "strong_support" if s >= STRONG_STRENGTH else "support" if s else
           "strong_contradiction" if c >= STRONG_STRENGTH else "contradiction")
    score = round(round(50 * (1 + s - c), 8))
    reason = (
        f"{summary.supporting_origins} supporting and {summary.contradicting_origins} "
        "contradicting source groups met the relevance, scope and quality checks. "
    )
    if key == "mixed":
        reason += "Credible evidence exists on both sides. Around 50 means their strengths are balanced, not that evidence is missing. "
    else:
        reason += ("The admitted evidence supports the claim. " if s else "The admitted evidence contradicts the claim. ")
    reason += "Repeated or copied sources do not add votes. " + DEFINITION
    return CredibilityRating(status="rated", score=score, label=LABELS[key], explanation=reason)


def _legacy_unrated():
    return CredibilityRating(status="legacy_unrated", label="Earlier assessment",
        explanation="This saved result does not contain enough evidence-scoring detail for the credibility scale. Check it again for an updated assessment.")


def build_credibility(result, *, version=None) -> CredibilityRating:
    """Keep persisted v1 ratings stable; new component-aware output uses v2."""
    saved = getattr(result, "credibility", None)
    version = version or (saved.version if saved else VERSION)
    rating = _build_v1(result)
    component = getattr(result, "component_assessment", None)
    if version == "credibility-v1":
        if component is not None:
            raise ValueError("Component assessments require credibility-v2")
        return rating
    if version != VERSION:
        raise ValueError("Unknown credibility version")
    label, explanation = rating.label, rating.explanation
    if rating.status == "rated":
        if component and component.finding == "material_contradiction":
            label = "Likely misinformation"
            explanation = (component.explanation + " The score reflects evidence against a material assertion. "
                "Support for a different assertion does not cancel that finding. " + DEFINITION)
        elif label == LABELS["contradiction"]:
            label = "Likely misinformation"
    return rating.model_copy(update={"version": VERSION, "label": label, "explanation": explanation})
