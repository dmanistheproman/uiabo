"""A separate, conservative plausibility finding; no manufactured contradiction."""

import re
from datetime import timedelta

from app.pipeline.shared.climate import (
    eligible, render_record, RECORD_URL, MAX_REFERENCE_AGE,
    MIN_RECORD_GAP_C, OUTLIER_RISK, LIMITATION,
)
from app.pipeline.shared.models import AssessmentResult, PlausibilityContext, ScoringSummary
from . import forecast
from .scoring import SCORING_VERSION


def apply_plausibility(claim, retrieval, result):
    if (not claim.checkable or not eligible(claim.claim_context, claim.date_context)
            or result.assessment_outcome not in {"unsupported", "insufficient_evidence"}
            or not forecast._definite_prediction(claim)
            or forecast.CAUSAL.search(claim.extracted_claim)
            or forecast.OTHER_CLAUSES.search(claim.extracted_claim)
            or forecast.QUANTIFIED_TEMPERATURE.search(claim.extracted_claim)
            or re.search(r"\b(?:MSS|NEA|forecast|forecasts|predicts|says|states|shows)\b", claim.extracted_claim, re.I)):
        return result
    quantity = forecast._quantity(claim)
    if quantity is None:
        return result
    for source in retrieval.evidence:
        data = source.climate_record
        if (not data or str(source.url) != RECORD_URL or source.source_type != "government"
                or not any(item.evidence_id == source.evidence_id and item.stance == "neutral"
                           for item in result.assessed_evidence)
                or not source.provenance or source.provenance.source_policy != "catalogue"
                or source.passage != render_record(data)
                or not 0 <= (claim.claim_context.as_of - data.updated_at).days <= MAX_REFERENCE_AGE.days
                or not source.retrieved_at.tzinfo
                or not timedelta(0) <= claim.claim_context.assessed_at - source.retrieved_at <= timedelta(hours=24)):
            continue
        gap = round(quantity[0] - data.maximum_c, 3)
        if gap < MIN_RECORD_GAP_C:
            continue
        explanation = (f"The prediction is highly unlikely based on Singapore's climate records: "
            f"{quantity[0]:g} degrees Celsius is {gap:g} degrees above MSS's all-stations "
            f"historical maximum of {data.maximum_c:g} degrees Celsius "
            f"(table updated {data.updated_at.isoformat()}). "
            "This is a climate plausibility warning, not proof that a future event cannot happen.")
        payload = result.model_dump()
        payload.update(assessment_outcome="highly_unlikely", concern_label="High Concern",
            misinformation_risk_score=OUTLIER_RISK, uncertainty="High",
            explanation=explanation,
            recommended_action="Do not share this prediction as a fact. Read the latest MSS forecast.",
            uncertainty_reasons=[LIMITATION, "The 14-day horizon, 10-degree gap and score are prototype rules that still need evaluation."],
            scoring=ScoringSummary(version=SCORING_VERSION, status="plausibility_based",
                evidence_strength="Limited", reasons=[
                    "A simple near-term air-temperature assertion exceeds the verified national historical maximum by at least 10 degrees Celsius.",
                    "Risk 85/100 is a coarse prototype outlier indicator, not an 85% chance of being false."]),
            plausibility_context=PlausibilityContext(evidence_id=source.evidence_id,
                claimed_c=quantity[0], record=data, deviation_c=gap,
                explanation=explanation, limitations=[LIMITATION]))
        return AssessmentResult.model_validate(payload)
    return result
