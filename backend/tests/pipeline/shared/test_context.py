"""Grounded claim interpretation: units, modality, scope and one submission clock."""

from datetime import date, datetime, timezone

import pytest

from app.pipeline.shared.context import build_claim_context


NOW = datetime(2026, 9, 17, 1, 30, tzinfo=timezone.utc)


def test_weather_claim_keeps_possible_modality_and_exact_quantities_without_rewriting():
    text = 'Singapore could reach 52°C this weekend due to a record-breaking heatwave.'
    result = build_claim_context(text, NOW)
    assert result.claim_type == 'weather_forecast'
    assert result.modality == 'possible'
    assert result.location == 'Singapore'
    assert result.measurement == 'air_temperature'
    assert [(q.text, q.value, q.unit) for q in result.quantities] == [('52°C', 52, 'C')]
    assert result.as_of == date(2026, 9, 17) and result.assessed_at == NOW
    assert any('19 September 2026 - 20 September 2026' in a for a in result.assumptions)
    assert any('air temperature' in a for a in result.assumptions)
    assert text == 'Singapore could reach 52°C this weekend due to a record-breaking heatwave.'


@pytest.mark.parametrize('quantity,value,unit', [
    ('52 C', 52, 'C'), ('52 degrees C', 52, 'C'), ('52 degrees Celsius', 52, 'C'),
    ('125.6°F', 125.6, 'F'), ('125.6 degrees Fahrenheit', 125.6, 'F'),
    ('-3°C', -3, 'C'), ('+31.5 Celsius', 31.5, 'C'),
])
def test_temperature_units_are_canonical_but_values_and_spans_are_original(quantity, value, unit):
    text = f'Temperatures in Singapore could reach {quantity} tomorrow.'
    result = build_claim_context(text, NOW)
    assert result.location == 'Singapore'
    assert [(q.text, q.value, q.unit) for q in result.quantities] == [(quantity, value, unit)]
    assert all(q.text in text for q in result.quantities)


@pytest.mark.parametrize('wording,measurement', [
    ('air temperature', 'air_temperature'), ('feels-like temperature', 'apparent_temperature'),
    ('heat index', 'apparent_temperature'), ('apparent temperature', 'apparent_temperature'),
    ('surface temperature', 'surface_temperature'), ('road temperature', 'surface_temperature'),
])
def test_measurements_are_distinct_and_explicit_measurements_need_no_air_assumption(wording, measurement):
    result = build_claim_context(f'The {wording} in Singapore could reach 52 C tomorrow.', NOW)
    assert result.measurement == measurement
    assert not any('Interpreted ordinary' in a for a in result.assumptions)


@pytest.mark.parametrize('wording', ['could', 'may', 'might'])
def test_possible_words_remain_possible_and_may_is_not_a_month(wording):
    result = build_claim_context(f'Singapore {wording} reach 52 C this weekend.', NOW)
    assert result.modality == 'possible'
    assert result.claim_type == 'weather_forecast'
    assert any('19 September 2026' in a for a in result.assumptions)


def test_explicit_may_date_does_not_create_possible_modality():
    result = build_claim_context('Singapore reached 32 C on 1 May 2026.', NOW)
    assert result.modality == 'asserted'
    assert result.claim_type == 'general'


@pytest.mark.parametrize('text,location', [
    ('Singapore will reach 32 C tomorrow.', 'Singapore'),
    ('New York could reach 32 C tomorrow.', 'New York'),
    ('Temperatures in singapore may reach 32 C tomorrow.', 'singapore'),
    ('Temperatures in Kuala Lumpur may reach 32 C tomorrow.', 'Kuala Lumpur'),
    ('Temperatures could reach 32 C tomorrow.', None),
    ('It could reach 32 C tomorrow.', None),
    ('The temperature could rise in the future.', None),
    ('Temperatures in Singapore and in Malaysia could reach 32 C tomorrow.', None),
    ('Weather forecasts for Singapore could exceed 32 C tomorrow.', 'Singapore'),
    ('Singapore could reach 52 C this weekend because of record-breaking heat.', 'Singapore'),
    ('Fees for passports will increase tomorrow.', None),
])
def test_locations_are_literal_and_missing_or_ambiguous_locations_are_not_invented(text, location):
    result = build_claim_context(text, NOW)
    assert result.location == location
    assert result.location is None or result.location in text


def test_general_policy_quantities_are_kept_separate_from_weather():
    text = 'From October, travellers must have passports valid for 12 months and pay $300.'
    result = build_claim_context(text, NOW)
    assert result.claim_type == 'policy_change'
    assert result.measurement == 'unspecified' and result.location is None
    assert [(q.text, q.value, q.unit) for q in result.quantities] == [('12 months', 12, 'months'), ('$300', 300, '$')]


def test_context_as_of_uses_singapore_midnight():
    result = build_claim_context('Singapore could reach 32 C tomorrow.', datetime(2026, 12, 31, 16, 1, tzinfo=timezone.utc))
    assert result.as_of == date(2027, 1, 1)
    assert any('2 January 2027' in a for a in result.assumptions)
