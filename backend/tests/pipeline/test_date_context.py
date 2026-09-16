"""Year inference, evidence scope and persisted assumptions across the app API."""

import asyncio
from datetime import date, datetime, timezone
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.pipeline.shared.dates import infer_date_context, dated_search_claim, future_scope_limitation, assumption_notice
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, RetrievalResult, TextAnalysisResult
from app.pipeline.evidence_assessment import semantic
from app.pipeline.evidence_retrieval import enhanced
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository

NOW = datetime(2026, 9, 10, 3, tzinfo=timezone.utc)
TEXT = 'From October, residents must pay a $300 monthly permit fee.'


def claim(text=TEXT):
    return ClaimAnalysis(extracted_claim=text, checkable=True, claim_category='factual',
                         classification_reason='Policy claim', claim_confidence=1,
                         date_context=infer_date_context(text, NOW))


def source(passage):
    return EvidenceCandidate(evidence_id='policy', title='Permit rules', publisher='Test authority',
        url='https://gov.sg/permit', source_type='government', passage=passage,
        retrieval_score=.9, retrieved_at=NOW)


@pytest.mark.parametrize('phrase,day', [
    ('From October', None), ('Starting in October', None), ('In October', None),
    ('Effective October 1', 1), ('From 1 October', 1), ('On October 1st', 1),
])
def test_current_year_is_explicit_metadata_without_rewriting_the_claim(phrase, day):
    text = f'{phrase}, residents pay the fee.'
    context = infer_date_context(text, NOW)
    assert context.claim_text == phrase and context.year == 2026
    assert context.day == day and context.month == 10 and context.is_future
    assert context.basis == 'assumed_current_year'
    assert f'{phrase} 2026' in dated_search_claim(text, context)
    assert text == f'{phrase}, residents pay the fee.'


@pytest.mark.parametrize('text', [
    'In 2027, residents pay a fee from October.',
    'From October next year, residents pay a fee.',
    'Residents pay every October.',
    'Residents pay every year from October.',
    'From February 29, residents pay a fee.',  # Invalid in the assumed year.
    'From October, a fee begins; from December, a rebate starts.',
])
def test_recurring_invalid_or_ambiguous_dates_are_not_invented(text):
    assert infer_date_context(text, NOW) is None


def test_year_comes_from_singapore_at_submission_including_new_year_boundary():
    context = infer_date_context(TEXT, datetime(2026, 12, 31, 16, 1, tzinfo=timezone.utc))
    assert context.year == 2027 and context.as_of.isoformat() == '2027-01-01'
    past = infer_date_context('From January, residents pay a fee.', NOW)
    assert past.year == 2026 and not past.is_future  # Never silently roll forward.


@pytest.mark.parametrize('amount', ['$2000', 'SGD 2000', '2000 baht'])
def test_a_four_digit_monetary_amount_is_not_a_stated_year(amount):
    context = infer_date_context(f'From October, the permit fee is {amount}.', NOW)
    assert context.year == 2026


@pytest.mark.parametrize('phrase,start,end', [
    ('today', '2026-09-10', '2026-09-10'),
    ('tonight', '2026-09-10', '2026-09-10'),
    ('tomorrow', '2026-09-11', '2026-09-11'),
    ('yesterday', '2026-09-09', '2026-09-09'),
    ('this weekend', '2026-09-12', '2026-09-13'),
    ('next weekend', '2026-09-19', '2026-09-20'),
    ('this week', '2026-09-07', '2026-09-13'),
    ('next week', '2026-09-14', '2026-09-20'),
    ('last week', '2026-08-31', '2026-09-06'),
])
def test_relative_dates_use_one_visible_singapore_submission_interval(phrase, start, end):
    text = f'Singapore may reach 52 C {phrase}.'
    context = infer_date_context(text, NOW)
    assert context.claim_text == phrase
    assert context.basis == 'relative_submission_date'
    assert context.start_date == date.fromisoformat(start) and context.end_date == date.fromisoformat(end)
    assert context.timezone == 'Asia/Singapore' and context.as_of == date(2026, 9, 10)
    assert 'submission date 2026-09-10' in assumption_notice(context)
    assert phrase not in dated_search_claim(text, context)
    assert text == f'Singapore may reach 52 C {phrase}.'


@pytest.mark.parametrize('day', [12, 13])
def test_this_weekend_keeps_the_current_weekend_on_saturday_and_sunday(day):
    context = infer_date_context('Temperatures rise this weekend.', datetime(2026, 9, day, 3, tzinfo=timezone.utc))
    assert (context.start_date, context.end_date) == (date(2026, 9, 12), date(2026, 9, 13))
    assert not context.is_future


def test_relative_date_rollover_uses_singapore_not_utc_and_can_cross_years():
    instant = datetime(2026, 12, 31, 16, 1, tzinfo=timezone.utc)
    context = infer_date_context('Tomorrow will be warmer.', instant)
    assert context.as_of == date(2027, 1, 1)
    assert context.start_date == context.end_date == date(2027, 1, 2)
    week = infer_date_context('The temperature rises this week.', instant)
    assert (week.start_date, week.end_date) == (date(2026, 12, 28), date(2027, 1, 3))


@pytest.mark.parametrize('phrase,start,end', [
    ('From October 2025', '2025-10-01', '2025-10-31'),
    ('Effective October 1, 2027', '2027-10-01', '2027-10-01'),
    ('From 1 October 2027', '2027-10-01', '2027-10-01'),
    ('on 19 September 2026', '2026-09-19', '2026-09-19'),
    ('19-20 September 2026', '2026-09-19', '2026-09-20'),
    ('September 19-20, 2026', '2026-09-19', '2026-09-20'),
    ('19 September to 20 September 2026', '2026-09-19', '2026-09-20'),
    ('30 September 2026 to 1 October 2026', '2026-09-30', '2026-10-01'),
    ('2026-09-19', '2026-09-19', '2026-09-19'),
    ('2026-09-19 to 2026-09-20', '2026-09-19', '2026-09-20'),
])
def test_explicit_dates_are_interpreted_without_an_assumed_year(phrase, start, end):
    context = infer_date_context(phrase, NOW)
    assert context.basis == 'explicit_date'
    assert context.start_date == date.fromisoformat(start) and context.end_date == date.fromisoformat(end)
    assert dated_search_claim(phrase, context) == phrase
    assert assumption_notice(context).startswith('Stated date:')


@pytest.mark.parametrize('text', [
    'tomorrow or this weekend', 'today and 19 September 2026',
    'every weekend', 'this weekend and next week', '2026-02-30',
    'on 0 September 2026', '31-32 September 2026', '20-19 September 2026',
    '2026-09-20 to 2026-09-19', '2026-09-19 and 2026-09-20',
])
def test_ambiguous_or_impossible_intervals_do_not_silently_pick_a_date(text):
    assert infer_date_context(text, NOW) is None


def assess(passage, text=TEXT):
    item = source(passage)
    raw = {'stance':'contradicting', 'evidence_quote':passage, 'reason':'The fee differs.',
           'comparisons':[{'aspect':'amount','claim_text':'$300 monthly','finding':'differs',
               'applies_to_claim':True,'evidence_quote':passage,'explanation':'The quoted fee differs.'}]}
    judgment = semantic.validate_judgment(raw, passage, claim=text, evidence=item)
    return semantic.aggregate(claim(text), RetrievalResult(retrieval_status='completed', evidence=[item]), [judgment])


def test_assumed_past_date_can_be_resolved_by_applicable_evidence():
    result = assess('Effective 1 January 2026, the permit fee is $120 annually.',
                    text=TEXT.replace('October', 'January'))
    assert result.assessment_outcome == 'contradicted'
    assert result.claim_comparisons[0].applies_to_claim
    assert all('has no year' not in reason for reason in result.uncertainty_reasons)


def test_assumed_future_change_is_not_disproved_by_an_existing_rule():
    result = assess('The permit fee is $120 annually under the January 2026 schedule.')
    assert result.assessment_outcome == 'unsupported'
    assert result.concern_label == 'Not Enough Information'
    assert not result.claim_comparisons[0].applies_to_claim
    assert 'October 2026' in result.claim_comparisons[0].scope_limitation


def test_an_explicit_rule_for_the_assumed_future_period_can_resolve_the_claim():
    result = assess('Effective 1 October 2026, the permit fee is $120 annually.')
    assert result.assessment_outcome == 'contradicted'
    assert result.claim_comparisons[0].applies_to_claim


def test_future_scope_guard_does_not_depend_on_model_returning_comparisons():
    item = source('The permit fee is $120 annually under the January 2026 schedule.')
    judgment = semantic.Judgment(stance='contradicting', evidence_quote=item.passage, reason='Conflicting fee.')
    result = semantic.aggregate(claim(), RetrievalResult(retrieval_status='completed', evidence=[item]), [judgment])
    assert result.concern_label == 'Not Enough Information'
    assert future_scope_limitation(claim().date_context, item.passage)


def test_assessment_and_retrieval_receive_original_claim_and_separate_assumption():
    item = source('Effective 1 October 2026, the permit fee is $120 annually.')
    data = claim()
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        body = json.loads(payload['messages'][1]['content'])
        requests.append(body)
        assert body['claim'] == TEXT and body['date_context']['year'] == 2026
        assert body['as_of'] == '2026-09-10'
        result = {'stance':'neutral','evidence_quote':'','reason':'Future rule needs checking.','comparisons':[]}
        return httpx.Response(200, json={'done':True,'message':{'content':json.dumps(result)}})
    async def run():
        async with httpx.AsyncClient(base_url='https://ollama.com', transport=httpx.MockTransport(handler)) as client:
            await semantic.judge_with_client(client, TEXT, item, date_context=data.date_context)
    asyncio.run(run())
    assert len(requests) == 1
    retrieval = enhanced.RetrievalRun(TEXT, None, 'g', 't', 'o', date_context=data.date_context)
    assert retrieval.claim == TEXT
    assert retrieval.search_claim == TEXT.replace('October', 'October 2026')


def test_web_search_uses_assumed_year_while_relevance_keeps_original_wording():
    data = claim()
    passage = 'Effective 1 October 2026, residents pay an annual permit fee of $120.'
    seen = []
    def handler(request):
        if request.url.host == 'factchecktools.googleapis.com':
            assert 'October 2026' in request.url.params['query']
            return httpx.Response(200, json={})
        payload = json.loads(request.content)
        if request.url.host == 'api.tavily.com':
            if request.url.path == '/search':
                seen.append(payload['query'])
                return httpx.Response(200, json={'results':[
                    {'url':'https://gov.sg/permit','title':'Permit rules','content':passage,'score':.9}]})
            return httpx.Response(200, json={'results':[
                {'url':'https://gov.sg/permit','raw_content':passage}], 'failed_results':[]})
        body = json.loads(payload['messages'][1]['content'])
        if payload['model'] == 'gemma4:31b':
            assert 'October 2026' in body['claim']
            raw = {'queries':['October 2026 permit fee $300 monthly', 'Permit fee official schedule']}
        else:
            assert body['claim'] == TEXT
            assert body['date_context']['year'] == 2026 and body['as_of'] == '2026-09-10'
            raw = {'window_id':0,'quote_start':0,'quote_end':0,'relevance':'direct',
                'reason':'Same permit scheme and period.','applicability':'established',
                'applicability_reason':'Explicit October 2026 rule.','condition_ranges':[]}
        return httpx.Response(200, json={'done':True,'message':{'content':json.dumps(raw)}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await enhanced.retrieve_with_client(TEXT, client, 'g', 't', 'o', date_context=data.date_context)
    result = asyncio.run(run())
    assert result.retrieval_status == 'completed' and len(result.evidence) == 1
    assert 'October 2026' in seen[0]
    assert result.evidence[0].passage == passage


def test_api_history_keeps_assumption_and_a_corrected_year_creates_a_separate_result(signed_analysis):
    from app.main import app
    from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
    seen = []
    def retrieve(data):
        seen.append(data)
        return RetrievalResult(retrieval_status='no_evidence')
    pipeline = PipelineOrchestrator(prepare_input=prepare_text,
        analyze_claim=lambda prepared: claim(prepared.normalised_text), retrieve_evidence=retrieve,
        assess_evidence=lambda *_: pytest.fail('No evidence must skip assessment'),
        repository=InMemoryResultRepository(), clock=lambda: NOW)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    store, _ = signed_analysis
    store.documents['users','analysis-user']['role'] = 'premium'
    with TestClient(app) as client:
        response = client.post('/analysis/text', json={'text':TEXT}, headers={'Idempotency-Key':'year-assumed'})
        assert response.status_code == 200, response.text
        first = response.json()
        assert first['date_context']['year'] == 2026
        assert first['original_text'] == first['extracted_claim'] == TEXT
        assert any('Assumed date: October 2026' in r for r in first['uncertainty_reasons'])
        assert seen[0].date_context.year == 2026
        corrected = TEXT.replace('October', 'October 2025')
        response = client.post('/analysis/text', json={'text':corrected}, headers={'Idempotency-Key':'year-corrected'})
        assert response.status_code == 200, response.text
        second = response.json()
        assert second['date_context']['basis'] == 'explicit_date'
        assert second['date_context']['year'] == 2025 and second['extracted_claim'] == corrected
        assert not any('Assumed date:' in reason for reason in second['uncertainty_reasons'])
        assert second['result_id'] != first['result_id']
        assert client.get('/analysis/results/'+first['result_id']).json()['date_context'] == first['date_context']
        assert client.post('/analysis/text', json={'text':TEXT}, headers={'Idempotency-Key':'year-assumed'}).json() == first
        assert store.documents['usage_allowances','analysis-user']['successful_submissions'] == 2
        old = dict(first); old.pop('date_context')
        assert TextAnalysisResult.model_validate(old).date_context is None
