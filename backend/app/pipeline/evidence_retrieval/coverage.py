"""Bounded follow-up discovery hints, never evidence or scope overrides."""

import re
from urllib.parse import urlsplit


def requires_weather_context_search(claim):
    return bool(re.search(r"\b(?:because|due to|caus\w*|record\w*|heat\s?wave|hottest|ever|climate change|global warming)\b", claim, re.I))


def missing_coverage(items, context=None, date_context=None):
    gaps = []
    if not items:
        gaps.append("No usable source passages were found.")
    if not any(item.provenance and item.provenance.relevance == "direct"
               and item.provenance.applicability == "established" for item in items):
        gaps.append("Find evidence covering the original claim's conditions, not only its general topic.")
    if context:
        if context.location:
            gaps.append("Prioritise the named location: " + context.location)
        else:
            gaps.append("The location is not established; do not invent one.")
        if context.measurement != "unspecified":
            gaps.append("Match the measurement: " + context.measurement.replace("_", " "))
    if date_context:
        gaps.append("Find source coverage for " + date_context.display_date + ", not an unrelated date.")
    for item in items:
        if item.provenance and item.provenance.applicability != "established":
            value = item.provenance.applicability_reason[:300]
            if value not in gaps:
                gaps.append(value)
    return gaps[:6]


def weather_queries(claim, context, date_context):
    if not context or context.claim_type != "weather_forecast":
        return None
    measurement = {"air_temperature": "air temperature forecast", "apparent_temperature": "heat index feels like temperature forecast",
                   "surface_temperature": "surface temperature forecast", "unspecified": "weather forecast"}[context.measurement]
    timeframe = (f"{date_context.start_date.isoformat()} to {date_context.end_date.isoformat()}"
                 if date_context and date_context.start_date else "")
    # The second query looks for actual forecast values instead of repeating the
    # disputed number. All dimensions come from visible grounded claim context.
    neutral = " ".join(filter(None, [context.location, "official", measurement, timeframe]))
    return [claim[:400], neutral[:400]]


def weather_page_priority(context, title, url):
    if not context or context.claim_type != "weather_forecast":
        return 0
    host = (urlsplit(url).hostname or "").lower()
    labelled = bool(re.search(r"\b(?:forecast|outlook|prediction)\b", title + " " + url, re.I))
    official = host == "weather.gov.sg" or host.endswith(".weather.gov.sg") or host == "nea.gov.sg" or host.endswith(".nea.gov.sg")
    return 2 if labelled and official else 1 if labelled else 0
