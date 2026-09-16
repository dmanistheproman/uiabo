"""Bounded, grounded context extraction; never rewrites a submitted claim."""

import calendar
import math
import re

from .dates import assumption_notice, infer_date_context, submission_time
from .models import ClaimContext, ClaimQuantity


NUMBER = r"[-+]?\d+(?:\.\d+)?"
TEMPERATURE = re.compile(
    rf"(?<![\w.])(?P<value>{NUMBER})\s*(?:(?:°|degrees?\s*)\s*)?"
    r"(?P<unit>Celsius|Fahrenheit|C|F)\b", re.I)
OTHER_QUANTITY = re.compile(
    rf"(?<![\w.])(?P<value>{NUMBER})\s*(?P<unit>%|percent\b|baht\b|dollars?\b|"
    r"months?\b|years?\b|km/h\b|mm\b|kilomet(?:er|re)s?\b)", re.I)
MONEY = re.compile(rf"(?<!\w)(?P<unit>SGD|USD|THB|S\$|\$)\s*(?P<value>{NUMBER})(?!\w|\.\d)", re.I)
POSSIBILITY = re.compile(r"\b(?:could|may|might|possibly|possible|potentially|chance\s+of)\b", re.I)
WEATHER = re.compile(r"\b(?:weather|forecast|temperatures?|heatwaves?|heat\s+wave|hotter|hottest|heat\s+index)\b", re.I)
SURFACE = re.compile(r"\b(?:surface|pavement|asphalt|road|ground|sand|roof)\s+temperatures?\b|\bsurface\b", re.I)
APPARENT = re.compile(r"\b(?:feels?[- ]like|apparent\s+temperatures?|heat\s+index|realfeel)\b", re.I)
POLICY = re.compile(r"\b(?:polic(?:y|ies)|passports?|immigration|ICA|fees?|tax(?:es)?|permits?|"
                    r"compulsory|mandatory|subsid(?:y|ies)|CPF|MediSave|MediShield|pensions?)\b", re.I)
PLACE_STOP = {
    'this', 'next', 'last', 'today', 'tonight', 'tomorrow', 'yesterday', 'will', 'could',
    'may', 'might', 'can', 'shall', 'would', 'should', 'is', 'are', 'was', 'were',
    'has', 'have', 'had', 'weather', 'forecast', 'temperature', 'temperatures',
    'air', 'surface', 'feels', 'due', 'because', 'during', 'from', 'at', 'on', 'in',
    'to', 'for', 'with', 'and', 'or',
    *(name.lower() for name in calendar.month_name if name),
    *(name.lower() for name in calendar.day_name),
}
NOT_PLACES = {'i', 'we', 'you', 'they', 'it', 'the', 'a', 'an', 'my', 'our', 'your',
              'their', 'its', 'there', 'here', 'sometime', 'future', 'weekend', 'week',
              'celsius', 'fahrenheit', 'degrees', 'degree', 'gpu', 'cpu', 'oven', 'water',
              'time', 'public', 'general', 'total', 'particular'}
PLACE_WORD = r"[A-Za-z][A-Za-z'’.-]*"


def _location(text, *, allow_leading=False):
    """Only retain a literal place-like span; no geocoding or assumed home city."""
    candidates = []
    patterns = [
        (rf"(?=\b(?:in|across|throughout|over)\s+(?P<place>{PLACE_WORD}(?:\s+{PLACE_WORD}){{0,5}}))", re.I),
        (rf"(?=\b(?:weather|temperatures?|forecasts?)\s+(?:for|of)\s+(?P<place>{PLACE_WORD}(?:\s+{PLACE_WORD}){{0,5}}))", re.I),
        (rf"^\s*(?P<place>{PLACE_WORD}(?:\s+{PLACE_WORD}){{0,4}}?)(?:'s|’s)?\s+"
         r"(?:(?:air|surface)\s+)?(?:weather|forecast|temperatures?|will|could|may|might|can|is|reaches?)\b", 0),
    ]
    for pattern, flags in patterns:
        if flags == 0 and not allow_leading:
            continue
        for match in re.finditer(pattern, text, flags):
            if flags == 0 and not all(word[0].isupper() for word in match['place'].split()):
                continue
            words = []
            for word in match['place'].split():
                if word.casefold() in {'and', 'or'}:
                    return None
                if word.casefold() in PLACE_STOP:
                    break
                words.append(word)
            if not words or words[0].casefold() in NOT_PLACES:
                continue
            candidate = ' '.join(words).rstrip('.').removesuffix("'s").removesuffix('’s')
            # The leading-subject heuristic only accepts place-like proper names.
            if flags == 0 and not all(word[0].isupper() for word in candidate.split()):
                continue
            if candidate and candidate in text:
                candidates.append(candidate)
    distinct = {candidate.casefold(): candidate for candidate in candidates}
    return next(iter(distinct.values())) if len(distinct) == 1 else None


def _quantities(text):
    found = []
    for pattern in (TEMPERATURE, OTHER_QUANTITY, MONEY):
        for match in pattern.finditer(text):
            value = float(match['value'])
            if not math.isfinite(value):
                continue
            unit = match['unit']
            if pattern is TEMPERATURE:
                unit = 'C' if unit.lower().startswith('c') else 'F'
            elif unit.lower() == 'percent':
                unit = '%'
            found.append((match.start(), ClaimQuantity(text=match.group(), value=value, unit=unit)))
    return [item for _, item in sorted(found, key=lambda pair: pair[0])[:12]]


def build_claim_context(text, now=None):
    """Build deterministic context from literal text and one submission instant.

    Temperature quantities retain their original value; C/F are canonical unit
    labels, not conversions. A location remains absent when missing or ambiguous.
    This helper never decides checkability, truth or a misinformation score.
    """
    assessed_at = submission_time(now)
    date_context = infer_date_context(text, assessed_at)
    quantities = _quantities(text)
    temperatures = [item for item in quantities if item.unit in {'C', 'F'}]
    location = _location(text, allow_leading=bool(temperatures or WEATHER.search(text)))
    assumptions = []
    if date_context and date_context.basis != 'explicit_date':
        assumptions.append(assumption_notice(date_context))
    weather = bool(WEATHER.search(text) or APPARENT.search(text) or SURFACE.search(text))
    if temperatures and location and re.search(r"\b(?:reach|hit|rise|climb|drop|fall)\b", text, re.I):
        weather = True
    measurement = 'unspecified'
    if APPARENT.search(text):
        measurement = 'apparent_temperature'
    elif SURFACE.search(text):
        measurement = 'surface_temperature'
    elif re.search(r"\bair\s+temperatures?\b", text, re.I):
        measurement = 'air_temperature'
    elif weather and temperatures:
        measurement = 'air_temperature'
        assumptions.append("Interpreted ordinary weather temperature as air temperature. The message did not specify feels-like or surface temperature.")
    modality_text = text.replace(date_context.claim_text, '', 1) if date_context else text
    future_language = re.search(r"\b(?:will|shall|could|may|might|forecast|expected|predicted|likely)\b", modality_text, re.I)
    forecast_period = date_context is not None and (date_context.end_date or date_context.as_of) >= assessed_at.date()
    claim_type = ('weather_forecast' if weather and (future_language or forecast_period)
                  else 'policy_change' if POLICY.search(text) and (future_language or date_context)
                  else 'general')
    return ClaimContext(claim_type=claim_type, modality='possible' if POSSIBILITY.search(modality_text) else 'asserted',
        location=location, measurement=measurement, quantities=quantities,
        as_of=assessed_at.date(), assessed_at=assessed_at, assumptions=assumptions)
