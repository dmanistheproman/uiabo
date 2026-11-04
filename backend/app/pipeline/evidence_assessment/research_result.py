"""Adapt direct web research to app history without inventing evidence scores."""

from app.pipeline.shared.credibility import build_credibility
from app.pipeline.shared.models import ScoringSummary, TextAnalysisResult
from app.pipeline.shared.web_research import ResearchAssessment, VERDICT_PRESENTATION


def build_research_result(*, prepared, research: ResearchAssessment, result_id,
                          created_at, pipeline_version, trace=None):
    """Keep model summaries separate from legacy evidence passages and votes."""
    outcome, concern, strength, _ = VERDICT_PRESENTATION[research.verdict]
    checkable = research.verdict != "not_checkable"
    limitations = list(research.limitations) or [
        "The assessment reflects the cited web research available when this check ran."
    ]
    result = TextAnalysisResult(
        result_id=result_id,
        original_text=prepared.original_text,
        extracted_claim=prepared.original_text if checkable else None,
        claim_category="factual" if checkable else "unverifiable",
        checkable=checkable,
        concern_label=concern,
        misinformation_risk_score=None,
        assessment_outcome=outcome,
        scoring=ScoringSummary(version="evidence-v4", status="research_based",
            evidence_strength=strength,
            reasons=["The verdict is a qualitative web-research assessment. No source voting strength, origin count or numerical probability was inferred."]),
        uncertainty="High" if research.verdict in {"mixed", "insufficient_evidence", "not_checkable"} else "Medium",
        uncertainty_reasons=limitations,
        explanation=research.summary,
        recommended_action=research.recommended_action,
        evidence=[],
        research_assessment=research,
        retrieval_trace=trace,
        warnings=list(prepared.warnings),
        pipeline_version=pipeline_version,
        created_at=created_at,
    )
    return TextAnalysisResult.model_validate({
        **result.model_dump(), "credibility": build_credibility(result),
    })
