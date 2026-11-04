"""Regression cases for the three inconclusive checks, without fixed verdicts."""

import asyncio
from datetime import datetime, timezone
import json

import httpx
import pytest
from pydantic import ValidationError

from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.dates import infer_date_context, future_scope_limitation
from app.pipeline.shared.jurisdiction import SG_ASSUMPTION
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance
from app.pipeline.shared.public_changes import public_change_plan
from app.pipeline.evidence_retrieval import enhanced, topic_scope
from app.pipeline.evidence_retrieval.relevance import Selection

NOW = datetime(2026, 11, 3, 3, tzinfo=timezone.utc)
POLICE = 'Police will begin issuing fines to people who criticise government policies on social media if their posts receive more than 10,000 views.'
SUBSIDY = 'From 2027, households living in private property will no longer receive any government subsidies, including healthcare subsidies.'
JOBS = 'Unemployment among Singapore graduates has doubled because companies are hiring foreigners at half the salary.'


@pytest.mark.parametrize('text,country,basis', [
    (POLICE, 'Singapore', 'singapore_default'),
    (SUBSIDY, 'Singapore', 'singapore_default'),
    (JOBS, 'Singapore', 'explicit'),
    ('In Australia, ' + POLICE, 'Australia', 'explicit'),
    ('In Malaysia, ' + SUBSIDY, 'Malaysia', 'explicit'),
    ('Sri Lanka households will lose healthcare subsidies.', 'Sri Lanka', 'explicit'),
    ('Zambia will change government subsidies.', 'Zambia', 'explicit'),
    ('Singapore and Malaysia will change healthcare subsidies.', None, 'unresolved'),
    ('In Atlantis, police will introduce social media fines.', None, 'unresolved'),
    ('NHS healthcare subsidies will end.', None, 'unresolved'),
    ('Water boils at 100 C.', None, 'unresolved'),
    ('The temperature will reach 50 C tomorrow.', None, 'unresolved'),
])
def test_country_is_grounded_or_the_default_is_disclosed(text, country, basis):
    context = build_claim_context(text, NOW)
    assert (context.jurisdiction, context.jurisdiction_basis) == (country, basis)
    assert (SG_ASSUMPTION in context.assumptions) == (basis == 'singapore_default')
    claim = ClaimAnalysis(extracted_claim=text, checkable=True, claim_category='factual',
        classification_reason='Fixture', claim_confidence=1, claim_context=context,
        date_context=infer_date_context(text, NOW))
    assert claim.extracted_claim == text


def test_housing_description_is_not_a_location_and_year_is_preserved():
    context = build_claim_context(SUBSIDY, NOW)
    assert context.location is None
    assert context.retrieval_topic == 'healthcare_subsidies'
    dates = infer_date_context(SUBSIDY, NOW)
    assert dates.year == 2027 and dates.basis == 'explicit_date'
    assert dates.display_date == '2027' and dates.start_date.isoformat() == '2027-01-01'
    assert infer_date_context('Unemployment doubled from 2024 to 2026.', NOW) is None


def test_default_cannot_be_fabricated_or_hidden():
    context = build_claim_context(SUBSIDY, NOW)
    for change in [{'assumptions': []}, {'jurisdiction': 'Australia'}, {'jurisdiction_basis': 'explicit'}]:
        with pytest.raises(ValidationError):
            ClaimAnalysis(extracted_claim=SUBSIDY, checkable=True, claim_category='factual',
                classification_reason='Fixture', claim_confidence=1, claim_context=context.model_copy(update=change))


def test_year_only_scope_does_not_require_a_january_policy_announcement():
    dates = infer_date_context(SUBSIDY, NOW)
    assert future_scope_limitation(dates, 'Eligible private-property residents receive subsidies over 2025 to 2027.') is None
    assert future_scope_limitation(dates, 'The programme supports eligible residents in 2026.')
    assert future_scope_limitation(dates, 'Subsidies begin in 2028.')
    monthly = infer_date_context('From November 2027, healthcare subsidies will end.', NOW)
    assert future_scope_limitation(monthly, 'The scheme ran in January 2027.')


def test_combined_survey_is_prioritised_over_one_institution_for_all_graduates():
    context = build_claim_context(JOBS, NOW)
    title = 'GRADUATE EMPLOYMENT SURVEY - Singapore'
    joint = 'https://www.moe.gov.sg/media/Joint-Web-Publication-GES-6-AUs.pdf'
    single = 'https://www.moe.gov.sg/media/Web%20Publication%20NUS%20GES%202025.pdf'
    assert topic_scope.page_priority(context, JOBS, title, joint) > topic_scope.page_priority(context, JOBS, title, single)
    specific = 'Unemployment among Singapore NUS graduates has doubled.'
    specific_context = build_claim_context(specific, NOW)
    assert topic_scope.page_priority(specific_context, specific, title, single) == topic_scope.page_priority(specific_context, specific, title, joint)


@pytest.mark.parametrize('text,domain', [(POLICE, 'police.gov.sg'), (SUBSIDY, 'moh.gov.sg'), (JOBS, 'mom.gov.sg')])
def test_topic_routes_to_responsible_agencies_without_changing_verdict(text, domain):
    context = build_claim_context(text, NOW)
    assert domain in topic_scope.domains_for(context)
    queries = topic_scope.topic_queries(text, context)
    assert len(queries) == 2 and all('Singapore' in q for q in queries)
    foreign = build_claim_context('In Australia, ' + text.replace('Singapore ', ''), NOW)
    assert topic_scope.domains_for(foreign) == []


def test_wrong_country_rejected_but_international_reporting_on_singapore_kept():
    context = build_claim_context(SUBSIDY, NOW)
    assert topic_scope.mismatched_jurisdiction(context, 'https://www.hud.gov/budget', 'US housing subsidies')
    assert topic_scope.mismatched_jurisdiction(context, 'https://bbc.com/story', 'The Australian government offers healthcare subsidies.')
    assert not topic_scope.mismatched_jurisdiction(context, 'https://bbc.com/story', 'Singapore healthcare subsidies cover eligible households.')


def test_full_time_employment_cannot_become_direct_unemployment_evidence():
    context = build_claim_context(JOBS, NOW)
    text = 'Singapore graduates achieved a full-time employment rate of 74.4%.'
    selected = Selection(window_id=0, relevance='direct', quote=text, reason='Related figures',
        applicability='established', applicability_reason='Same population', condition_quotes=[])
    assert topic_scope.guard_selection(selected, text, context, 'https://moe.gov.sg/survey', JOBS) is None
    assert selected.relevance == 'context' and selected.applicability == 'missing_context'


def test_general_unemployment_and_foreign_pay_minimum_do_not_fill_comparison_gaps():
    context = build_claim_context(JOBS, NOW)
    text = 'Singapore unemployment rates are published quarterly. Foreign workers must satisfy the minimum salary requirements.'
    evidence = EvidenceCandidate(evidence_id='context', url='https://mom.gov.sg/statistics',
        title='Unemployment summary', publisher='MOM', source_type='government',
        retrieved_at=NOW, passage=text, retrieval_score=.5,
        provenance=EvidenceProvenance(source_policy='catalogue', source_reason='Reviewed government source',
            origin_group='gov.sg', discovery_method='preferred_search', relevance='context',
            relevance_quote=text, relevance_reason='Related figures, no graduate or pay comparison',
            applicability='missing_context', applicability_reason='Different population and missing pay comparator'))
    gaps = topic_scope.coverage_gaps(JOBS, [evidence], context)
    assert any('Graduate unemployment' in gap for gap in gaps)
    assert any('workers pay' in gap for gap in gaps)
    evidence.provenance.applicability = 'different_scope'
    assert any('No applicable passages' in gap for gap in topic_scope.coverage_gaps(JOBS, [evidence], context))


def test_link_destination_is_not_an_unemployment_measurement():
    context = build_claim_context(JOBS, NOW)
    text = 'Singapore graduates have a full-time employment rate of 74.4%. Read [the earlier survey](https://example.com/unemployed/graduates).'
    selected = Selection(window_id=0, relevance='direct', quote=text, reason='Related figures',
        applicability='established', applicability_reason='Same country', condition_quotes=[])
    topic_scope.guard_selection(selected, text, context, 'https://moe.gov.sg/survey', JOBS)
    assert selected.relevance == 'context' and selected.applicability == 'missing_context'


def test_exception_in_one_law_cannot_settle_a_new_audience_count_penalty():
    context = build_claim_context(POLICE, NOW)
    text = 'Clause 17 does not cover Singaporeans acting on their own accord.'
    selected = Selection(window_id=0, relevance='direct', quote=text, reason='A legal exception',
        applicability='established', applicability_reason='Same country', condition_quotes=[])
    topic_scope.guard_selection(selected, text, context, 'https://mha.gov.sg/speech', POLICE)
    assert selected.relevance == 'context' and selected.applicability == 'missing_context'
    matching = 'The new rule imposes fines on criticism of government policies when a social-media post exceeds 10,000 views.'
    selected = selected.model_copy(update={'quote': matching, 'relevance': 'direct', 'applicability': 'established'})
    topic_scope.guard_selection(selected, matching, context, 'https://mha.gov.sg/announcement', POLICE)
    assert selected.relevance == 'direct' and selected.applicability == 'established'


@pytest.mark.parametrize('text,eligible', [
    (POLICE, True), (SUBSIDY, True),
    ('If police fined criticism, what would happen?', False),
    (SUBSIDY.replace('2027', '2040'), False),
    ('In Australia, ' + SUBSIDY, False),
    ('Officials are discussing removing healthcare subsidies.', False),
])
def test_policy_inference_is_bounded_to_asserted_near_term_changes(text, eligible):
    context = build_claim_context(text, NOW)
    plan = public_change_plan(text, context, infer_date_context(text, NOW))
    assert bool(plan) == eligible


def test_retrieval_filters_foreign_candidate_and_passage_even_if_selector_accepts_it():
    context = build_claim_context(SUBSIDY, NOW)
    us = 'https://hud.gov/budget'
    wrong_news = 'https://bbc.com/misleading-snippet'
    right = 'https://moh.gov.sg/eligibility'
    pages = {wrong_news: 'Australian eSafety Commissioner fines individuals for online content.',
             right: 'Singapore healthcare subsidies are assessed by income and annual value for eligible households.'}
    searches, extracted = [], []
    def handler(request):
        if request.url.host == 'factchecktools.googleapis.com':
            return httpx.Response(200, json={})
        payload = json.loads(request.content)
        if request.url.path == '/search':
            searches.append(payload)
            return httpx.Response(200, json={'results': [
                {'url': us, 'title': 'United States housing assistance', 'score': .99},
                {'url': wrong_news, 'title': 'Singapore policy comparison', 'score': .98},
                {'url': right, 'title': 'Subsidy eligibility', 'score': .9}]})
        if request.url.path == '/extract':
            extracted.extend(payload['urls'])
            return httpx.Response(200, json={'results': [{'url': u, 'raw_content': pages[u]} for u in payload['urls']], 'failed_results': []})
        state = json.loads(payload['messages'][1]['content'])
        assert 'jurisdiction' in state['claim_context']
        result = {'window_id': 0, 'quote_start': 0, 'quote_end': 0, 'relevance': 'context',
                  'reason': 'Current rule', 'applicability': 'uncertain_time',
                  'applicability_reason': 'Future change not established', 'condition_ranges': []}
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps(result)}})
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await enhanced.retrieve_with_client(SUBSIDY, client, 'g', 't', 'o',
                claim_context=context, date_context=infer_date_context(SUBSIDY, NOW))
    result = asyncio.run(call())
    assert [str(e.url) for e in result.evidence] == [right]
    assert us not in extracted
    assert all('Singapore' in s['query'] for s in searches)
    assert searches[0]['include_domains'] == topic_scope.domains_for(context)
    assert any(e['decision'] == 'rejected_page_jurisdiction' for e in result.trace.decisions)
    assert result.trace.search_requests <= 4 and result.trace.relevance_calls <= 6


def test_empty_local_retrieval_has_one_bounded_repair_search():
    context = build_claim_context(JOBS, NOW)
    def handler(request):
        if request.url.host == 'factchecktools.googleapis.com':
            return httpx.Response(200, json={})
        assert request.url.path == '/search'
        return httpx.Response(200, json={'results': []})
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await enhanced.retrieve_with_client(JOBS, client, 'g', 't', 'o', claim_context=context)
    result = asyncio.run(call())
    assert result.trace.search_requests == 4
    assert result.trace.relevance_calls == 0
    assert any(e['decision'] == 'unresolved_coverage_gap' for e in result.trace.decisions)
