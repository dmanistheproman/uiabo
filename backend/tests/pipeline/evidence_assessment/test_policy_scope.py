"""Future policy dates cannot be inferred from an earlier adopted schedule."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.pipeline.evidence_assessment.policy_scope import future_policy_scope_limitation


AS_OF = date(2026, 11, 3)


def limitation(text, quote, *, status='contradicted', claim_type='policy_change', counterfact=None):
    assertion = SimpleNamespace(text=text)
    finding = SimpleNamespace(status=status, citations=[SimpleNamespace(quote=quote)],
        material_counterfact=SimpleNamespace(claim_span=counterfact) if counterfact else None)
    return future_policy_scope_limitation(assertion, finding, as_of=AS_OF,
                                         claim_context=SimpleNamespace(claim_type=claim_type))


@pytest.mark.parametrize('status', ['supported', 'contradicted', 'conflicting'])
def test_nearer_term_schedule_cannot_establish_explicit_later_policy(status):
    reason = limitation('The council will raise the annual permit fee to 120 dollars in 2045.',
        'The adopted annual permit fee rises to 45 dollars from 1 January 2027.', status=status)
    assert reason and '2045' in reason
    assert 'cannot by itself establish or refute' in reason


@pytest.mark.parametrize('quote', [
    'The annual permit fee adopted for 2045 is 45 dollars.',
    'The annual permit fee will be 45 dollars from 1 January 2045.',
    'The adopted annual permit fee is 45 dollars throughout 2040-2050.',
])
def test_claimed_year_or_explicit_bounded_schedule_removes_only_minimum_guard(quote):
    assert limitation('The council will raise the permit fee to 120 dollars in 2045.', quote) is None


def test_current_undated_assertion_keeps_current_adopted_future_schedule():
    assert limitation('The council is raising the annual permit fee to 120 dollars.',
        'The adopted annual permit fee will be 45 dollars from 1 January 2029.') is None


def test_historical_assertion_keeps_existing_semantic_and_archive_scope_checks():
    assert limitation('The council raised the annual permit fee to 120 dollars in 2000.',
        'The adopted annual permit fee became 45 dollars from 1 January 2000.') is None


def test_another_date_in_same_future_year_does_not_cover_claimed_month():
    assert limitation('The permit fee will rise to 120 dollars in November 2045.',
        'The annual permit fee will be 45 dollars from 1 January 2045.')


def test_another_day_in_same_future_month_does_not_cover_claimed_day():
    assert limitation('The permit fee will rise to 120 dollars on 30 November 2045.',
        'The annual permit fee will be 45 dollars on 1 November 2045.')


@pytest.mark.parametrize('quote', [
    'On 30 November 2045 the annual permit fee will be 45 dollars.',
    'On November 30, 2045 the annual permit fee will be 45 dollars.',
    'The annual permit fee is 45 dollars during 2045-11-01 to 2045-12-31.',
])
def test_explicit_matching_day_or_bounded_date_range_removes_minimum_guard(quote):
    assert limitation('The permit fee will rise to 120 dollars on 30 November 2045.', quote) is None


def test_causal_counterfact_uses_its_exact_clause_date():
    event = 'The council will raise the annual permit fee to 120 dollars in 2045'
    assert limitation(event + ' because its treasury is depleted.',
        'The adopted annual permit fee will be 45 dollars from 1 January 2027.', counterfact=event)


@pytest.mark.parametrize('claim_type,status', [('general', 'contradicted'),
    ('weather_forecast', 'contradicted'), ('policy_change', 'unresolved')])
def test_other_claim_types_and_existing_unknown_findings_are_not_reinterpreted(claim_type, status):
    assert limitation('The fee will rise in 2045.', 'The scheduled fee starts in 2027.',
                      claim_type=claim_type, status=status) is None
