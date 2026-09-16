"""Validated NEA/MSS four-day air-temperature forecasts, not observations.

Provider contract: https://data.gov.sg/datasets/d_f131f6e343bf8168e4057a04c4326a0a/view
Only the fixed public API is requested; claim text never becomes a request URL.
"""

import asyncio
from datetime import datetime, timedelta
from hashlib import sha256
import math

from app.pipeline.shared.dates import SINGAPORE
from app.pipeline.shared.forecast_format import render_forecast
from app.pipeline.shared.models import EvidenceCandidate, EvidenceProvenance, ForecastData, ForecastPeriod


API_URL = "https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook"
TIMEOUT_SECONDS = 6.0
MAX_AGE = timedelta(hours=24)


def eligible_context(context, date_context):
    """No implicit geography, measurement substitution or invented date range."""
    return bool(context and context.claim_type == "weather_forecast"
        and context.location and context.location.strip().casefold() == "singapore"
        and context.measurement == "air_temperature"
        and date_context and date_context.start_date and date_context.end_date
        and date_context.end_date >= context.as_of)


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing official forecast timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Official forecast timestamp requires a timezone")
    return parsed


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Invalid official forecast temperature")
    # A malformed payload must not insert arbitrary scores/percentages as air
    # temperatures. These broad physical limits are validation, not a forecast.
    if not -100 <= value <= 80:
        raise ValueError("Official temperature outside physical validation range")
    return value


def parse_forecast(payload, *, assessed_at):
    """Validate the latest snapshot against the same submission clock as claims."""
    if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
        raise ValueError("Submission timestamp requires a timezone")
    if (not isinstance(payload, dict) or type(payload.get("code")) is not int
            or payload["code"] != 0 or payload.get("errorMsg", "") != ""):
        raise ValueError("Invalid official forecast response")
    data = payload.get("data")
    records = data.get("records") if isinstance(data, dict) else None
    # Latest-snapshot requests have one record; do not silently pick among an
    # unexpected historical/paginated response and risk using the wrong issue.
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise ValueError("Missing latest official forecast")
    record = records[0]
    issued = _timestamp(record.get("timestamp"))
    updated = _timestamp(record.get("updatedTimestamp"))
    if not timedelta(0) <= assessed_at - issued <= MAX_AGE or not issued <= updated <= assessed_at:
        raise ValueError("Official forecast is stale or newer than submission")
    issued_date = issued.astimezone(SINGAPORE).date()
    if record.get("date") != issued_date.isoformat():
        raise ValueError("Official forecast issue date mismatch")
    forecasts = record.get("forecasts")
    if not isinstance(forecasts, list) or not 1 <= len(forecasts) <= 4:
        raise ValueError("Invalid official forecast horizon")
    periods = []
    seen = set()
    for item in forecasts:
        if not isinstance(item, dict) or not isinstance(item.get("temperature"), dict):
            raise ValueError("Missing official temperature record")
        timestamp = _timestamp(item.get("timestamp")).astimezone(SINGAPORE)
        period_date = timestamp.date()
        if (timestamp.time().isoformat() != "00:00:00" or period_date in seen
                or not issued_date < period_date <= issued_date + timedelta(days=4)):
            raise ValueError("Invalid or duplicate official forecast date")
        temperature = item["temperature"]
        if temperature.get("unit") != "Degrees Celsius":
            raise ValueError("Unsupported official forecast unit")
        periods.append(ForecastPeriod(date=period_date, low=_number(temperature.get("low")),
                                      high=_number(temperature.get("high"))))
        seen.add(period_date)
    return ForecastData(location="Singapore", measurement="air_temperature", unit="C",
                        issued_at=issued,
                        reader_url="https://www.weather.gov.sg/weather-forecast-4dayoutlook/",
                        periods=sorted(periods, key=lambda period: period.date))


def coverage(data, date_context):
    start, end = date_context.start_date, date_context.end_date
    if not start or not end:
        return False, False
    dates = {period.date for period in data.periods}
    overlapping = any(start <= day <= end for day in dates)
    # Avoid constructing huge ranges for claims beyond the API horizon.
    full = ((end - start).days < 4 and all(start + timedelta(days=i) in dates
            for i in range((end - start).days + 1)))
    return overlapping, full


async def retrieve_forecast(client, context, date_context):
    if not eligible_context(context, date_context):
        return None
    if context.as_of != context.assessed_at.astimezone(SINGAPORE).date():
        raise ValueError("Claim and forecast submission dates disagree")
    async with asyncio.timeout(TIMEOUT_SECONDS):
        response = await client.get(API_URL, timeout=TIMEOUT_SECONDS, follow_redirects=False)
        response.raise_for_status()
        if len(response.content) > 100_000:
            raise ValueError("Oversized official forecast response")
        data = parse_forecast(response.json(), assessed_at=context.assessed_at)
    overlapping, full = coverage(data, date_context)
    if not overlapping:
        return None
    passage = render_forecast(data)
    return EvidenceCandidate(
        evidence_id="forecast-" + sha256((API_URL + data.issued_at.isoformat()).encode()).hexdigest()[:16],
        title="NEA / MSS four-day temperature forecast", url=API_URL,
        publisher="NEA / Meteorological Service Singapore", published_at=data.issued_at.astimezone(SINGAPORE).date(),
        retrieved_at=context.assessed_at, passage=passage, source_type="government", retrieval_score=.95,
        forecast=data, provenance=EvidenceProvenance(source_policy="catalogue",
            source_reason="Fixed official NEA/MSS data.gov.sg forecast API; typed fields and issue time validated.",
            origin_group="gov.sg", discovery_method="official_api", relevance="direct" if full else "context",
            relevance_reason="Official issued air-temperature forecast for the named location; not observed future weather.",
            relevance_quote=passage, applicability="established" if full else "uncertain_time",
            applicability_reason=("Forecast covers the requested dates, location and air-temperature measurement."
                                  if full else "Forecast covers only part of the requested dates; the remaining period is unresolved."),
            condition_quotes=[]))
