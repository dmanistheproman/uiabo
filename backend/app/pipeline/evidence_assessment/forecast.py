"""Compare claims with issued forecasts without claiming to know future weather.

Structured official API data is compared deterministically. Future possibility
is distinct from a factual claim about what an identified forecaster published.
"""

from datetime import timedelta
import re

from app.pipeline.shared.forecast_format import render_forecast
from app.pipeline.shared.models import AssessedEvidence, ForecastContext
from . import service as baseline


MAX_FORECAST_AGE = timedelta(hours=24)
FORECAST_LIMIT = "A forecast can change and is not a guarantee of what will happen."
UNASSESSED_WEB = "Additional web sources were retained but were not substantively assessed in this structured forecast comparison."
WEB_UNAVAILABLE = "Some additional web sources could not be assessed reliably. The official forecast comparison remains available, but verification of the whole message is incomplete."
CAUSAL = re.compile(r"\bbecause\b|\bdue\s+to\b|\bcaused\s+by\b|\brecord\b|\bheatwave\b|\bhottest\b|\bever\b|\bclimate\s+change\b|\bglobal\s+warming\b", re.I)
OTHER_CLAUSES = re.compile(r"\band\b|\bbut\b|;", re.I)
QUANTIFIED_TEMPERATURE = re.compile(
    r"[<>≤≥]|\b(?:at\s+(?:least|most)|(?:more|less)\s+than|above|below|over|under|between|up\s+to)\b"
    r"|\b(?:about|around|approximately|roughly|nearly|almost)\b"
    r"|\b\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?\s*(?:°\s*)?(?:[CF]\b|degrees)"
    r"|\b(?:every|each|all)\s+(?:day|night|weekend)\b|\ball\s+(?:of\s+)?(?:the\s+)?weekend\b", re.I)


def is_weather(claim):
    return bool(claim.claim_context and claim.claim_context.claim_type == "weather_forecast")


def _quantity(claim):
    context = claim.claim_context
    values = []
    for item in context.quantities:
        unit = item.unit.casefold().replace("°", "").strip()
        if unit not in {"c", "celsius", "f", "fahrenheit"}:
            continue
        if item.text not in (claim.extracted_claim or ""):
            return None
        value = (item.value - 32) * 5 / 9 if unit in {"f", "fahrenheit"} else item.value
        values.append((value, item.text))
    return values[0] if len(values) == 1 else None


def _reported_forecast(claim, source):
    """Only a narrow positive attribution permits a factual source contradiction.

An unspecified forecast or a claim about weather itself is not equivalent to
what this particular national service published. Negated/quoted conditionals
and historical attributions require richer analysis and remain unresolved.
"""
    text = claim.extracted_claim or ""
    if re.search(r"\b(?:not|never|no|if|previous|previously|yesterday|earlier|last)\b", text, re.I):
        return False
    authority = r"(?:MSS|Meteorological Service Singapore|NEA|National Environment Agency)"
    match = re.search(
        authority + r"(?:'s)?(?:\s+(?:weather\s+)?forecast)?\s+(?:predicts?|forecasts?|expects?|says|states|shows)\b",
        text, re.I,
    )
    # This prototype adapter exposes only NEA/MSS data. A quoted attribution to
    # another forecasting service cannot be disproved by that dataset.
    return bool(match and re.search(r"\b(?:MSS|Meteorological Service Singapore|NEA|National Environment Agency)\b", source.publisher, re.I))


def _simple_temperature_report(claim):
    """Only a narrow single-temperature report can be fully supported here.

Extra substantive words require semantic checking beyond the API temperature
fields, even if a causal keyword list did not recognise them.
"""
    text = claim.extracted_claim or ""
    for span in [claim.claim_context.location, claim.date_context.claim_text,
                 *(item.text for item in claim.claim_context.quantities)]:
        if span:
            text = re.sub(re.escape(span), " ", text, flags=re.I)
    allowed = set("mss nea meteorological service singapore national environment agency s weather forecast forecasts predict predicts expects says states shows the air temperature temperatures in could may might will can reach reaching high highs maximum a of is are to be expected".split())
    return set(re.findall(r"[a-z]+", text.casefold())) <= allowed


def _matching_periods(claim, source):
    context, dates, data = claim.claim_context, claim.date_context, source.forecast
    if not source.provenance or source.provenance.discovery_method != "official_api" or source.source_type != "government":
        return [], "The structured forecast does not have verified official API provenance."
    if source.passage != render_forecast(data):
        return [], "The displayed forecast passage does not match its structured data."
    if not context.location or context.location.casefold().strip() != data.location.casefold().strip():
        return [], "The forecast and the claim do not establish the same location."
    if context.measurement != data.measurement:
        return [], "Air temperature cannot be compared with apparent or surface temperature, or an unspecified measurement."
    if _quantity(claim) is None:
        return [], "A single grounded temperature and its Celsius or Fahrenheit unit are needed for this comparison."
    if QUANTIFIED_TEMPERATURE.search(claim.extracted_claim or ""):
        return [], "A temperature bound, range or every-day claim needs a more specific comparison than a single point against the overall forecast range."
    if not dates or not dates.start_date or not dates.end_date:
        return [], "The claim's exact date range could not be established."
    if dates.start_date < context.as_of:
        return [], "A current forecast cannot settle a past weather claim."
    if not context.assessed_at.tzinfo or not data.issued_at.tzinfo:
        return [], "A timezone-aware issue and assessment time are required."
    age = context.assessed_at - data.issued_at
    if age < timedelta(0) or age > MAX_FORECAST_AGE:
        return [], "The forecast was not issued within the 24 hours before this check."
    requested = (dates.end_date - dates.start_date).days + 1
    period_dates = [period.date for period in data.periods]
    if len(period_dates) != len(set(period_dates)):
        return [], "The forecast contains duplicate dates and cannot establish a reliable interval."
    periods = [period for period in data.periods if dates.start_date <= period.date <= dates.end_date]
    if len(periods) != requested:
        return [], "The forecast does not cover every day in the claim's date range."
    return periods, None


def assess_structured(claim, retrieval):
    """Return a grounded API comparison without depending on another model call."""
    if not is_weather(claim) or not any(item.forecast for item in retrieval.evidence):
        return None
    text = claim.extracted_claim or ""
    causal = bool(CAUSAL.search(text))
    compound = causal or bool(OTHER_CLAUSES.search(text))
    assessed, matches, limitations = [], [], []
    for source in retrieval.evidence:
        stance, quote = "neutral", None
        if source.forecast is None:
            reason = "This web source is retained for reading; it was not used to decide the structured forecast comparison."
        else:
            periods, limitation = _matching_periods(claim, source)
            if limitation:
                limitations.append(limitation)
                reason = limitation
            else:
                low, high = min(period.low for period in periods), max(period.high for period in periods)
                target, original = _quantity(claim)
                compatible = low - 0.05 <= target <= high + 0.05
                matches.append((source, low, high, compatible))
                quote = source.passage
                reason = (f"The issued forecast covers {low:g} to {high:g} degrees Celsius for the checked dates. "
                          f"The claimed {original} is {'within' if compatible else 'outside'} that range. ")
                reported = _reported_forecast(claim, source)
                if reported and not compatible:
                    stance = "contradicting"
                    reason += "This conflicts with the claim about what the identified official service forecasts."
                elif reported and compatible and not compound and _simple_temperature_report(claim) and abs(target - high) < 0.05 and re.search(r"\b(?:reach|highs?|maximum)\b", text, re.I):
                    stance = "supporting"
                    reason += "The reported maximum agrees with the issued forecast; actual future weather is not guaranteed."
                else:
                    reason += "This compares a prediction; it does not prove or disprove what will happen."
        assessed.append(AssessedEvidence(evidence_id=source.evidence_id, stance=stance,
            quality_score=baseline.calculate_quality_score(source, stance),
            assessment_reason=reason, evidence_quote=quote))

    if causal:
        limitations.append("The forecast alone does not establish the claimed cause, heatwave or record-breaking conditions.")
    elif compound:
        limitations.append("The temperature comparison alone does not establish the other clauses in the message.")
    limitations.append(FORECAST_LIMIT)
    if any(item.forecast is None for item in retrieval.evidence):
        limitations.append(UNASSESSED_WEB)
    if matches:
        flags = {item[3] for item in matches}
        status = "mixed" if len(flags) > 1 else "supported_by_forecast" if True in flags else "not_supported_by_forecast"
        low, high = min(item[1] for item in matches), max(item[2] for item in matches)
        if status == "mixed":
            explanation = "The checked official forecasts differ on whether the claimed temperature fits their forecast ranges."
        elif status == "not_supported_by_forecast":
            explanation = (f"The current official forecast gives {low:g} to {high:g} degrees Celsius for the checked dates. "
                           "It does not support the claimed temperature. This does not prove that the future temperature is impossible.")
        else:
            explanation = (f"The claimed temperature is compatible with the official forecast range of {low:g} to {high:g} degrees Celsius "
                           "for the checked dates. This is not confirmation that it will happen.")
    else:
        status, low, high = "unresolved", None, None
        explanation = "A matching, current official forecast could not be established for the claim's location, dates and temperature measurement."
    if causal:
        explanation += " The forecast alone leaves the claimed heatwave, record or cause unverified."
    elif compound:
        explanation += " The forecast alone leaves the message's other clauses unverified."
    result = baseline.summarise_assessments(text, retrieval, assessed)
    if result.scoring.status == "provisional" and matches:
        result.assessment_outcome = "unsupported"
    result.explanation = explanation
    if result.assessment_outcome == "contradicted":
        result.explanation += " The claim about what the official forecast says is contradicted by that forecast."
    result.recommended_action = "Read the latest official forecast before sharing. Check the dates and whether the number means air temperature or feels-like temperature."
    result.uncertainty_reasons = list(dict.fromkeys(limitations))[:8]
    result.forecast_context = ForecastContext(status=status, explanation=explanation,
        limitations=result.uncertainty_reasons, evidence_ids=[item[0].evidence_id for item in matches][:6],
        start_date=claim.date_context.start_date if claim.date_context else None,
        end_date=claim.date_context.end_date if claim.date_context else None,
        issued_at=max((item[0].forecast.issued_at for item in matches), default=None),
        forecast_low=low, forecast_high=high)
    return result


def guard_web_assessment(claim, source, item):
    """A forecast or historical record alone cannot settle future possibility.

The semantic and retrieval decisions still own same-claim relevance. This extra
gate requires literal refutation language before their contradiction can decide
a bare prediction, rather than treating a lower outlook as impossibility.
"""
    if not is_weather(claim) or _reported_forecast(claim, source) or item.stance == "neutral":
        return
    quote = item.evidence_quote or ""
    explicit_refutation = bool(re.search(
        r"\b(?:claim|message|rumou?r|allegation|assertion|report)\b[^.!?]{0,140}\b(?:false|untrue|fabricated|baseless|hoax|incorrect|misleading)\b"
        r"|\b(?:refutes?|refuted|debunks?|debunked)\b[^.!?]{0,100}\b(?:claim|message|rumou?r|allegation)\b",
        quote, re.I))
    if item.stance == "contradicting" and explicit_refutation:
        return
    item.stance = "neutral"
    item.quality_score = min(item.quality_score, 0.45)
    item.assessment_reason = (
        "This source does not provide a literal refutation of the same message. "
        "A forecast or historical temperature record alone does not prove or disprove future weather. "
        + item.assessment_reason
    )


def merge_web_assessments(claim, retrieval, structured, web_assessed, failed_ids=()):
    """Merge semantic web findings without allowing them to rewrite API facts."""
    updates = {item.evidence_id: item for item in web_assessed}
    failed_ids = set(failed_ids)
    combined = []
    for item in structured.assessed_evidence:
        if item.evidence_id in updates:
            combined.append(updates[item.evidence_id])
        else:
            item = item.model_copy(deep=True)
            if item.evidence_id in failed_ids:
                item.assessment_reason = "This additional web source could not be assessed reliably; no factual stance was assigned to it."
            combined.append(item)
    result = baseline.summarise_assessments(claim.extracted_claim or "", retrieval, combined)
    result.forecast_context = structured.forecast_context.model_copy(deep=True)
    limits = [value for value in result.forecast_context.limitations if value != UNASSESSED_WEB]
    if failed_ids:
        limits.append(WEB_UNAVAILABLE)
    result.forecast_context.limitations = list(dict.fromkeys(limits))[:8]
    result.uncertainty_reasons = result.forecast_context.limitations[:]
    if result.uncertainty == "Low":
        result.uncertainty = "Medium"
    by_id = {item.evidence_id: item for item in retrieval.evidence}
    web_decisive = [item for item in result.assessed_evidence if item.evidence_id in updates and item.stance != "neutral"]
    if result.scoring.status == "provisional":
        if structured.assessment_outcome == "unsupported":
            result.assessment_outcome = "unsupported"
        result.explanation = structured.explanation
        if web_assessed:
            result.explanation += " The assessed web sources do not settle the complete message."
    elif web_decisive:
        result.explanation += " " + " ".join(
            f"{by_id[item.evidence_id].publisher}: {item.assessment_reason}"
            for item in web_decisive[:3]
        )
        result.explanation += " Separately, " + structured.forecast_context.explanation
    else:
        result.explanation = structured.explanation
    if failed_ids:
        result.explanation += " " + WEB_UNAVAILABLE
    if result.scoring.status == "provisional":
        result.recommended_action = structured.recommended_action
    return result


def attach_web_context(claim, result):
    if is_weather(claim) and result.forecast_context is None:
        result.forecast_context = ForecastContext(status="unresolved",
            explanation="No structured official forecast matching the dates, location and temperature measurement was verified. Read the source-specific findings below.",
            limitations=[FORECAST_LIMIT],
            start_date=claim.date_context.start_date if claim.date_context else None,
            end_date=claim.date_context.end_date if claim.date_context else None)
    return result
