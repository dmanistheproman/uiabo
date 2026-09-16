"""Forecast compatibility never becomes certainty about a future event."""

import asyncio
from datetime import date, datetime, timedelta, timezone
import json

import httpx
import pytest
from pydantic import ValidationError

from app.pipeline.evidence_assessment import forecast, semantic
from app.pipeline.shared.forecast_format import render_forecast
from app.pipeline.shared.models import (ClaimAnalysis, ClaimContext, ClaimQuantity,
    DateContext, EvidenceCandidate, EvidenceProvenance, ForecastData, ForecastPeriod,
    RetrievalResult)


NOW = datetime(2026, 9, 17, 8, tzinfo=timezone.utc)
START, END = date(2026, 9, 19), date(2026, 9, 20)


def claim(text="Temperatures in Singapore could reach 52 C this weekend.", *, value=52, unit="C", quantity="52 C", **context_changes):
    return ClaimAnalysis(extracted_claim=text, claim_category="factual", checkable=True,
        classification_reason="Weather assertion", claim_confidence=1,
        date_context=DateContext(claim_text="this weekend", month=9, day=19, year=2026,
            as_of=NOW.date(), display_date="19-20 September 2026", is_future=True,
            basis="relative_submission_date", start_date=START, end_date=END),
        claim_context=ClaimContext(claim_type="weather_forecast", modality="possible",
            location="Singapore", measurement="air_temperature", as_of=NOW.date(), assessed_at=NOW,
            quantities=[ClaimQuantity(text=quantity, value=value, unit=unit)]).model_copy(update=context_changes))


def evidence(evidence_id="forecast", high=34, low=25, *, data_changes=None, **changes):
    data = ForecastData(location="Singapore", issued_at=NOW-timedelta(hours=2),
        periods=[ForecastPeriod(date=START, low=low, high=high), ForecastPeriod(date=END, low=low, high=high)])
    if data_changes:
        data = data.model_copy(update=data_changes)
    passage = render_forecast(data)
    return EvidenceCandidate(evidence_id=evidence_id, title="Official four-day forecast",
        url="https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook",
        publisher="NEA / Meteorological Service Singapore", passage=passage,
        source_type="government", retrieved_at=NOW, retrieval_score=.9, forecast=data,
        provenance=EvidenceProvenance(source_policy="catalogue", source_reason="Official API",
            origin_group="gov.sg", discovery_method="official_api", relevance="direct",
            relevance_reason="Matching forecast", relevance_quote=passage,
            applicability="established", applicability_reason="Same place, dates and measure")).model_copy(update=changes)


def assess(data=None, items=None):
    return semantic.assess_evidence(data or claim(), RetrievalResult(retrieval_status="completed", evidence=items or [evidence()]))


def test_lower_forecast_does_not_prove_possible_future_temperature_false(monkeypatch):
    monkeypatch.setattr(semantic, "api_key", lambda: pytest.fail("Structured forecast must not require an Ollama key"))
    result = assess()
    assert result.assessment_outcome == "unsupported"
    assert result.misinformation_risk_score == 50 and result.scoring.status == "provisional"
    assert result.forecast_context.status == "not_supported_by_forecast"
    assert result.forecast_context.forecast_high == 34
    assert result.forecast_context.start_date == START and result.forecast_context.end_date == END
    assert result.forecast_context.evidence_ids == ["forecast"]
    assert "does not prove" in result.explanation
    assert result.assessed_evidence[0].stance == "neutral"
    assert result.assessed_evidence[0].evidence_quote == evidence().passage


def test_compatible_prediction_is_not_a_guarantee():
    result = assess(claim("Temperatures in Singapore could reach 34 C this weekend.", value=34, quantity="34 C"))
    assert result.forecast_context.status == "supported_by_forecast"
    assert result.misinformation_risk_score == 50 and result.scoring.status == "provisional"
    assert "not confirmation" in result.explanation


def test_explicit_attribution_to_matching_forecaster_can_be_contradicted():
    result = assess(claim("MSS predicts temperatures in Singapore could reach 52 C this weekend."))
    assert result.assessment_outcome == "contradicted"
    assert result.misinformation_risk_score == 95
    assert result.scoring.status == "evidence_based"
    assert "what the official forecast says" in result.explanation


def test_pure_reported_maximum_can_be_supported():
    result = assess(claim("MSS predicts temperatures in Singapore could reach 34 C this weekend.", value=34, quantity="34 C"))
    assert result.assessment_outcome == "supported" and result.misinformation_risk_score == 5
    assert result.forecast_context.status == "supported_by_forecast"


@pytest.mark.parametrize("text", [
    "MSS predicts temperatures in Singapore could reach 34 C this weekend because of a record-breaking heatwave.",
    "Temperatures in Singapore could reach 34 C this weekend due to a heatwave.",
    "MSS predicts temperatures in Singapore could reach 34 C this weekend and everyone must stay indoors.",
    "MSS predicts temperatures in Singapore could reach 34 C this weekend, the hottest ever.",
])
def test_temperature_match_does_not_verify_causes_or_other_compound_clauses(text):
    result = assess(claim(text, value=34, quantity="34 C"))
    assert result.scoring.status == "provisional" and result.misinformation_risk_score == 50
    assert any("does not establish" in item for item in result.forecast_context.limitations)


def test_fahrenheit_conversion_matches_celsius_forecast():
    result = assess(claim("MSS predicts temperatures in Singapore could reach 93.2 F this weekend.", value=93.2, unit="F", quantity="93.2 F"))
    assert result.assessment_outcome == "supported"
    assert result.forecast_context.forecast_high == 34


@pytest.mark.parametrize("changes,expected", [
    ({"measurement": "apparent_temperature"}, "Air temperature"),
    ({"measurement": "surface_temperature"}, "Air temperature"),
    ({"measurement": "unspecified"}, "Air temperature"),
    ({"quantities": [ClaimQuantity(text="52 C", value=52, unit="K")]}, "Celsius or Fahrenheit"),
])
def test_scope_and_quantity_mismatches_do_not_produce_decisive_scores(changes, expected):
    result = assess(claim(**changes))
    assert result.forecast_context.status == "unresolved" and result.misinformation_risk_score == 50
    assert any(expected in item for item in result.forecast_context.limitations)


@pytest.mark.parametrize("issued", [NOW-timedelta(hours=25), NOW+timedelta(seconds=1)])
def test_stale_future_issued_and_unzoned_forecasts_are_unresolved(issued):
    result = assess(items=[evidence(data_changes={"issued_at": issued})])
    assert result.forecast_context.status == "unresolved"
    assert result.scoring.status == "provisional"


def test_partial_date_coverage_is_not_a_whole_weekend_comparison():
    source = evidence(data_changes={"periods": [ForecastPeriod(date=START, low=25, high=34)]})
    result = assess(items=[source])
    assert result.forecast_context.status == "unresolved"
    assert any("every day" in item for item in result.forecast_context.limitations)


def test_duplicate_dates_cannot_fake_full_coverage():
    with pytest.raises(ValidationError):
        evidence(data_changes={"periods": [ForecastPeriod(date=START, low=25, high=34)] * 2})


def test_mismatched_location_and_missing_grounding_are_not_accepted():
    result = assess(items=[evidence(data_changes={"location": "London"})])
    assert result.forecast_context.status == "unresolved"
    assert any("same location" in item for item in result.forecast_context.limitations)
    with pytest.raises(ValidationError):
        claim(location="London")
    with pytest.raises(ValidationError):
        claim(quantities=[ClaimQuantity(text="54 C", value=54, unit="C")])


def test_timezone_free_timestamps_fail_the_contract():
    with pytest.raises(ValidationError):
        claim(assessed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        evidence(data_changes={"issued_at": NOW.replace(tzinfo=None)})


@pytest.mark.parametrize("phrase,value", [("at least 20", 20), ("below 40", 40), ("above 20", 20), ("up to 40", 40), ("around 35", 35)])
def test_temperature_bounds_are_not_mistaken_for_exact_points(phrase, value):
    data = claim(f"MSS predicts temperatures in Singapore of {phrase} C this weekend.", value=value, quantity=f"{value} C")
    result = assess(data)
    assert result.forecast_context.status == "unresolved"
    assert result.scoring.status == "provisional"
    assert result.misinformation_risk_score == 50


def test_overall_maximum_does_not_establish_every_day_maximum():
    data = claim("MSS predicts temperatures in Singapore could reach 34 C every day this weekend.", value=34, quantity="34 C")
    source = evidence(data_changes={"periods": [ForecastPeriod(date=START, low=25, high=34), ForecastPeriod(date=END, low=25, high=32)]})
    result = assess(data, [source])
    assert result.forecast_context.status == "unresolved"
    assert result.scoring.status == "provisional"


def test_an_unrecognised_additional_claim_is_not_fully_supported():
    data = claim("MSS predicts temperatures in Singapore could reach 34 C this weekend, a historic emergency.", value=34, quantity="34 C")
    assert assess(data).scoring.status == "provisional"


def test_missing_or_past_date_context_cannot_be_settled_by_current_forecast():
    data = claim()
    data.date_context = None
    assert assess(data).forecast_context.status == "unresolved"
    data = claim()
    data.date_context.start_date = NOW.date()-timedelta(days=1)
    assert assess(data).forecast_context.status == "unresolved"


def test_structured_fields_must_match_cited_passage():
    result = assess(items=[evidence(passage="This page claims 52 degrees Celsius.")])
    assert result.forecast_context.status == "unresolved"
    assert "does not match" in result.assessed_evidence[0].assessment_reason


def test_unverified_structured_source_does_not_get_forecast_status():
    assert assess(items=[evidence(provenance=None)]).forecast_context.status == "unresolved"


@pytest.mark.parametrize("text", [
    "Another forecaster predicts temperatures in Singapore could reach 52 C this weekend.",
    "MSS does not predict temperatures in Singapore could reach 52 C this weekend.",
    "If MSS predicts temperatures in Singapore could reach 52 C this weekend, stay home.",
])
def test_unknown_negated_or_conditional_attribution_is_not_inverted(text):
    assert assess(claim(text)).scoring.status == "provisional"


def test_different_publisher_does_not_refute_what_mss_published():
    result = assess(claim("MSS predicts temperatures in Singapore could reach 52 C this weekend."),
                    [evidence(publisher="Another forecasting service")])
    assert result.scoring.status == "provisional"


def test_conflicting_structured_forecasts_remain_mixed():
    data = claim("Temperatures in Singapore could reach 32 C this weekend.", value=32, quantity="32 C")
    result = assess(data, [evidence("one", high=32), evidence("two", high=30)])
    assert result.forecast_context.status == "mixed"
    assert result.scoring.status == "provisional" and result.misinformation_risk_score == 50
    assert result.forecast_context.evidence_ids == ["one", "two"]
    reported = data.model_copy(update={"extracted_claim": "MSS predicts temperatures in Singapore could reach 32 C this weekend."})
    assert assess(reported, [evidence("one", high=32), evidence("two", high=30)]).assessment_outcome == "conflicting"


def test_missing_model_key_preserves_forecast_and_discloses_unassessed_sources(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    web = evidence("web", forecast=None, passage="A historical temperature record.")
    result = assess(items=[evidence(), web])
    assert len(result.assessed_evidence) == 2
    assert result.assessed_evidence[1].stance == "neutral"
    assert "could not be assessed" in result.assessed_evidence[1].assessment_reason
    assert any("could not be assessed" in value for value in result.forecast_context.limitations)


def test_async_structured_route_uses_no_provider_calls():
    def handler(request):
        pytest.fail("No model request is needed for a structured forecast")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await semantic.assess_with_client(claim(), RetrievalResult(retrieval_status="completed", evidence=[evidence()]), client)
    assert asyncio.run(run()).misinformation_risk_score == 50


def mixed_run(items, handler, data=None):
    async def run():
        async with httpx.AsyncClient(base_url="https://ollama.com", transport=httpx.MockTransport(handler)) as client:
            return await semantic.assess_with_client(data or claim(), RetrievalResult(retrieval_status="completed", evidence=items), client)
    return asyncio.run(run())


def web_response(quote, *, stance="contradicting", reason="The official clarification explicitly refutes the same claim."):
    return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({
        "stance": stance, "evidence_quote": quote, "reason": reason, "comparisons": []})}})


def test_direct_web_refutation_can_decide_while_forecast_remains_deterministic():
    passage = "The message claiming Singapore could reach 52 C this weekend because of a record-breaking heatwave is false."
    web = evidence("web", forecast=None, passage=passage)
    data = claim("Temperatures in Singapore could reach 52 C this weekend because of a record-breaking heatwave.")
    calls = []
    def handler(request):
        sent = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(sent)
        assert sent["passage"] == passage
        return web_response(passage)
    result = mixed_run([evidence(), web], handler, data)
    assert len(calls) == 1
    assert result.assessment_outcome == "contradicted" and result.scoring.status == "evidence_based"
    assert result.misinformation_risk_score == 95
    assert result.forecast_context.status == "not_supported_by_forecast"
    assert result.forecast_context.forecast_high == 34
    assert result.assessed_evidence[0].stance == "neutral"
    assert result.assessed_evidence[0].evidence_quote == evidence().passage
    assert result.assessed_evidence[1].stance == "contradicting"
    assert "explicitly refutes" in result.explanation
    assert not any("not substantively assessed" in value for value in result.forecast_context.limitations)


@pytest.mark.parametrize("stance", ["supporting", "contradicting"])
def test_forecast_only_web_comparison_cannot_decide_a_future_possibility(stance):
    passage = "The forecast for this weekend in Singapore gives 25 C to 34 C."
    web = evidence("web", forecast=None, passage=passage)
    result = mixed_run([evidence(), web], lambda request: web_response(passage, stance=stance))
    assert result.scoring.status == "provisional" and result.misinformation_risk_score == 50
    assert result.assessed_evidence[1].stance == "neutral"
    assert "does not prove or disprove" in result.assessed_evidence[1].assessment_reason


def test_one_failed_web_call_does_not_discard_valid_refutation_or_forecast():
    passage = "The message claiming Singapore could reach 52 C this weekend is false."
    web = evidence("web", forecast=None, passage=passage)
    failed = evidence("failed", forecast=None, passage="Another relevant page.")
    def handler(request):
        sent = json.loads(json.loads(request.content)["messages"][1]["content"])
        return web_response(passage) if sent["passage"] == passage else httpx.Response(503)
    result = mixed_run([evidence(), web, failed], handler)
    assert result.assessment_outcome == "contradicted"
    assert len(result.assessed_evidence) == 3
    assert result.assessed_evidence[2].stance == "neutral"
    assert result.forecast_context.forecast_high == 34
    assert any("could not be assessed reliably" in value for value in result.forecast_context.limitations)


def test_all_failed_web_calls_still_return_grounded_forecast():
    result = mixed_run([evidence(), evidence("web", forecast=None)], lambda request: httpx.Response(503))
    assert result.scoring.status == "provisional" and result.misinformation_risk_score == 50
    assert result.forecast_context.status == "not_supported_by_forecast"
    assert "verification of the whole message is incomplete" in result.explanation


def test_invalid_web_quotation_cannot_override_forecast():
    result = mixed_run([evidence(), evidence("web", forecast=None, passage="A weather report.")],
                       lambda request: web_response("The message is false."))
    assert result.scoring.status == "provisional"
    assert result.forecast_context.status == "not_supported_by_forecast"


def test_deadline_preserves_completed_web_judgment_and_forecast(monkeypatch):
    passage = "The message claiming Singapore could reach 52 C this weekend is false."
    web = evidence("web", forecast=None, passage=passage)
    pending = evidence("pending", forecast=None, passage="A slow web source.")
    async def judge(client, claim_text, source, model, **kwargs):
        if source.evidence_id == "pending":
            await asyncio.sleep(5)
        return semantic.Judgment(stance="contradicting", evidence_quote=source.passage, reason="Same-message direct refutation.")
    monkeypatch.setattr(semantic, "judge_with_client", judge)
    monkeypatch.setattr(semantic, "TOTAL_TIMEOUT_SECONDS", .01)
    result = mixed_run([evidence(), web, pending], lambda request: pytest.fail("No real requests"))
    assert result.assessment_outcome == "contradicted"
    assert result.assessed_evidence[2].stance == "neutral"
    assert any("could not be assessed" in value for value in result.forecast_context.limitations)


def test_weather_web_judgment_receives_single_submission_clock_and_preserves_future_scope():
    data = claim()
    data.claim_context.as_of = date(2026, 9, 18)
    source = evidence(forecast=None, passage="The claim circulating about the official forecast is false.")
    def handler(request):
        body = json.loads(request.content)
        sent = json.loads(body["messages"][1]["content"])
        assert sent["as_of"] == "2026-09-18"
        assert sent["claim_context"]["modality"] == "possible"
        assert "lower forecast does NOT prove" in body["messages"][0]["content"]
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({
            "stance": "contradicting", "evidence_quote": source.passage,
            "reason": "The source explicitly debunks the claim.", "comparisons": []})}})
    async def run():
        async with httpx.AsyncClient(base_url="https://ollama.com", transport=httpx.MockTransport(handler)) as client:
            return await semantic.assess_with_client(data, RetrievalResult(retrieval_status="completed", evidence=[source]), client)
    result = asyncio.run(run())
    assert result.assessment_outcome == "contradicted"
    assert result.forecast_context.status == "unresolved"
    assert "policy" not in result.assessed_evidence[0].assessment_reason
