"""Public API contract, conservative scope, fallback and request budgets."""

import asyncio
from copy import deepcopy
from datetime import date, datetime

import httpx
import pytest

from app.pipeline.evidence_retrieval import enhanced, official_forecast as forecast, service
from app.pipeline.evidence_retrieval.coverage import missing_coverage, weather_queries
from app.pipeline.shared.forecast_format import render_forecast
from app.pipeline.shared.models import ClaimAnalysis, ClaimContext, DateContext


NOW = datetime.fromisoformat("2026-09-17T01:00:00+08:00")
CLAIM = "Singapore could reach 52C over the next few days."


def contexts(**changes):
    context = ClaimContext(claim_type="weather_forecast", modality="possible", location="Singapore",
        measurement="air_temperature", quantities=[{"text": "52C", "value": 52, "unit": "C"}],
        as_of=NOW.date(), assessed_at=NOW)
    for key, value in changes.items():
        setattr(context, key, value)
    dates = DateContext(claim_text="next few days", month=9, day=17, year=2026,
        basis="relative_submission_date", as_of=NOW.date(), display_date="17 to 19 September 2026", is_future=True,
        start_date=date(2026, 9, 17), end_date=date(2026, 9, 19))
    return context, dates


def payload():
    return {"code": 0, "errorMsg": "", "data": {"records": [{"date": "2026-09-16",
        "timestamp": "2026-09-16T17:07:00+08:00", "updatedTimestamp": "2026-09-16T17:11:26+08:00",
        "forecasts": [{"timestamp": f"2026-09-{day}T00:00:00+08:00",
                       "temperature": {"low": 25, "high": 34 if day != 19 else 33, "unit": "Degrees Celsius"}}
                      for day in range(17, 21)]}]}}


def test_official_fields_are_preserved_and_rendered_without_claim_numbers():
    data = forecast.parse_forecast(payload(), assessed_at=NOW)
    assert data.location == "Singapore" and data.unit == "C" and data.measurement == "air_temperature"
    assert data.issued_at.isoformat() == "2026-09-16T17:07:00+08:00"
    assert [period.high for period in data.periods] == [34, 34, 33, 34]
    assert data.periods[0].date == date(2026, 9, 17)
    assert "52" not in render_forecast(data)


@pytest.mark.parametrize("change", [
    "error", "boolean_code", "no_records", "multiple_records", "stale", "future_issue", "future_update",
    "naive_issue", "wrong_issue_date", "wrong_unit", "boolean_temperature", "numeric_string", "nan",
    "inverted", "duplicate_date", "far_future", "same_day", "not_midnight", "too_many", "no_periods",
])
def test_invalid_snapshots_are_rejected(change):
    raw = payload()
    record = raw["data"]["records"][0]
    item = record["forecasts"][0]
    if change == "error": raw["code"] = 1
    elif change == "boolean_code": raw["code"] = False
    elif change == "no_records": raw["data"]["records"] = []
    elif change == "multiple_records": raw["data"]["records"].append(deepcopy(record))
    elif change == "stale": record["timestamp"] = "2026-09-15T17:07:00+08:00"
    elif change == "future_issue": record["timestamp"] = "2026-09-17T02:07:00+08:00"
    elif change == "future_update": record["updatedTimestamp"] = "2026-09-17T02:07:00+08:00"
    elif change == "naive_issue": record["timestamp"] = "2026-09-16T17:07:00"
    elif change == "wrong_issue_date": record["date"] = "2026-09-17"
    elif change == "wrong_unit": item["temperature"]["unit"] = "Degrees Fahrenheit"
    elif change == "boolean_temperature": item["temperature"]["low"] = True
    elif change == "numeric_string": item["temperature"]["low"] = "25"
    elif change == "nan": item["temperature"]["high"] = float("nan")
    elif change == "inverted": item["temperature"]["low"] = 40
    elif change == "duplicate_date": record["forecasts"][1]["timestamp"] = item["timestamp"]
    elif change == "far_future": item["timestamp"] = "2026-09-25T00:00:00+08:00"
    elif change == "same_day": item["timestamp"] = "2026-09-16T00:00:00+08:00"
    elif change == "not_midnight": item["timestamp"] = "2026-09-17T01:00:00+08:00"
    elif change == "too_many": record["forecasts"].append(deepcopy(item))
    elif change == "no_periods": record["forecasts"] = []
    with pytest.raises(ValueError):
        forecast.parse_forecast(raw, assessed_at=NOW)


@pytest.mark.parametrize("changes", [
    {"location": None}, {"location": "Malaysia"}, {"location": "Singapore and Malaysia"},
    {"measurement": "apparent_temperature"}, {"measurement": "surface_temperature"},
    {"measurement": "unspecified"}, {"claim_type": "general"},
])
def test_no_api_request_for_unknown_or_different_scope(changes):
    context, dates = contexts(**changes)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail("Scope mismatch requested API"))) as client:
            return await forecast.retrieve_forecast(client, context, dates)
    assert asyncio.run(run()) is None


def test_complete_forecast_fast_path_needs_no_api_keys_or_paid_provider_calls(monkeypatch):
    context, dates = contexts()
    seen = []
    def handler(request):
        seen.append(str(request.url))
        assert str(request.url) == forecast.API_URL
        assert not any(header in request.headers for header in ("authorization", "x-api-key", "x-goog-api-key"))
        return httpx.Response(200, json=payload())
    for name in ("GOOGLE_FACT_CHECK_API_KEY", "TAVILY_API_KEY", "OLLAMA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    original = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    claim = ClaimAnalysis(extracted_claim=CLAIM, claim_category="factual", checkable=True,
        classification_reason="Checkable forecast", claim_confidence=1, date_context=dates, claim_context=context)
    result = service.retrieve_evidence(claim, mode="web")
    assert result.retrieval_status == "completed" and len(result.evidence) == 1
    assert len(seen) == 1 and result.trace.search_requests == result.trace.relevance_calls == 0
    source = result.evidence[0]
    assert source.forecast and source.provenance.discovery_method == "official_api"
    assert source.passage == source.provenance.relevance_quote == render_forecast(source.forecast)
    assert source.provenance.applicability == "established"


@pytest.mark.parametrize("scenario", ["missing", "out_of_horizon", "partial", "stale", "additional_claim"])
def test_uncovered_claims_keep_bounded_web_fallback(scenario):
    context, dates = contexts()
    claim = CLAIM
    raw = payload()
    if scenario == "out_of_horizon":
        dates.start_date, dates.end_date = date(2026, 9, 21), date(2026, 9, 23)
    if scenario == "partial":
        dates.end_date = date(2026, 9, 23)
    if scenario == "stale":
        raw["data"]["records"][0]["timestamp"] = "2026-09-15T17:07:00+08:00"
    if scenario == "additional_claim":
        claim += " This will be a record-breaking heatwave."
    calls = []
    def handler(request):
        calls.append(request.url.host + request.url.path)
        if request.url.host == "api-open.data.gov.sg":
            return httpx.Response(503) if scenario == "missing" else httpx.Response(200, json=raw)
        if request.url.host == "factchecktools.googleapis.com":
            return httpx.Response(200, json={})
        assert request.url.host == "api.tavily.com" and request.url.path == "/search"
        return httpx.Response(200, json={"results": []})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await enhanced.retrieve_with_client(claim, client, "g", "t", "o",
                date_context=dates, claim_context=context)
    result = asyncio.run(run())
    assert result.retrieval_status == ("completed" if scenario in {"partial", "additional_claim"} else "no_evidence")
    assert result.trace.search_requests == 3
    assert result.trace.extraction_urls <= 4 and result.trace.relevance_calls <= 4
    assert len(calls) == 5  # One official call, one Google request, three Tavily searches.
    if scenario == "partial":
        assert result.evidence[0].provenance.applicability == "uncertain_time"


def test_second_pass_targets_date_and_measurement_without_disputed_temperature():
    context, dates = contexts(measurement="apparent_temperature")
    queries = weather_queries(CLAIM, context, dates)
    assert "52" in queries[0] and "52" not in queries[1]
    assert "heat index" in queries[1] and "2026-09-17" in queries[1]
    assert "Singapore" in queries[1]
    assert any("apparent temperature" in gap for gap in missing_coverage([], context, dates))


def test_official_forecast_is_preferred_over_general_news_for_weather_context():
    context, dates = contexts()
    run = enhanced.RetrievalRun(CLAIM, None, "g", "t", "o", claim_context=context, date_context=dates)
    run.add({"url": "https://channelnewsasia.com/climate-news", "title": "Regional heat news", "score": .99}, "preferred_search")
    run.add({"url": "https://weather.gov.sg/weather-forecast-4dayoutlook/", "title": "MSS four-day forecast", "score": .60}, "preferred_search")
    assert run.next_pages(1)[0]["url"].startswith("https://weather.gov.sg/")


def test_public_forecast_timeout_keeps_working_web_fallback(monkeypatch):
    context, dates = contexts()
    monkeypatch.setattr(forecast, "TIMEOUT_SECONDS", .001)
    async def handler(request):
        if request.url.host == "api-open.data.gov.sg":
            await asyncio.sleep(.1)
            return httpx.Response(200, json=payload())
        return httpx.Response(200, json={} if request.url.host == "factchecktools.googleapis.com" else {"results": []})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await enhanced.retrieve_with_client(CLAIM, client, "g", "t", "o", claim_context=context, date_context=dates)
    result = asyncio.run(run())
    assert result.retrieval_status == "no_evidence"
    assert result.trace.search_requests == 3 and result.warnings
