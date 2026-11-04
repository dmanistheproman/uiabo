"""Bounded recovery across unseen subjects, outages and source-pool pressure."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.pipeline.evidence_retrieval import enhanced, repair, service
from app.pipeline.evidence_retrieval.relevance import Selection, assessment_excerpt
from app.pipeline.evidence_retrieval.requirements import clean_queries, plan_queries
from app.pipeline.shared.jurisdiction import topic_for
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult, RetrievalTrace


CLAIM = 'The UK has stopped issuing driving licences because road collisions doubled.'


def claim():
    return ClaimAnalysis(extracted_claim=CLAIM, claim_category='factual', checkable=True,
                         classification_reason='A factual assertion.', claim_confidence=.95)


def source(index, *, direct=False):
    return EvidenceCandidate(evidence_id=f'source-{index}', title=f'Licensing source {index}',
        url=f'https://gov.uk/licences/{index}', publisher='gov.uk', source_type='government',
        retrieved_at=datetime.now(timezone.utc), passage=f'Licensing administration background {index}.',
        retrieval_score=.9 if direct else .5,
        provenance=EvidenceProvenance(source_policy='government_namespace', source_reason='Reviewed government domain.',
            origin_group='gov.uk', discovery_method='preferred_search', relevance='direct' if direct else 'context',
            relevance_reason='Administrative information.', relevance_quote=f'Licensing administration background {index}.',
            applicability='established' if direct else 'missing_context', applicability_reason='Scope checked.'))


def selection(text):
    return Selection(window_id=0, relevance='direct', quote=text[:1800], reason='The document addresses the rule.',
        applicability='established', applicability_reason='The named jurisdiction and action match.', condition_quotes=[]), text


def install_providers(monkeypatch, *, fail_first=False, count=6):
    calls = {'search': [], 'extract': []}
    async def search(client, query, key, **kwargs):
        calls['search'].append(query)
        if fail_first and 'collisions' in query:
            raise httpx.ConnectError('private-provider-diagnostic-must-not-leak')
        return [dict(url=f'https://gov.uk/licences/new-{i}', title=f'Driving licence current application rules {i}',
                     score=.95-i*.01, content=f'Driving licence applications remain open for eligible applicants {i}.')
                for i in range(count)]
    async def extract(client, urls, key, **kwargs):
        calls['extract'].extend(urls)
        return {'results': [{'url':url, 'raw_content':f'Driving licence applications remain open: {url.rsplit("/",1)[-1]}.'}
                            for url in urls], 'failed_results': []}
    async def select(client, text_claim, text, key, **kwargs):
        return selection(text)
    monkeypatch.setattr(enhanced.providers, 'tavily_search', search)
    monkeypatch.setattr(enhanced.providers, 'tavily_extract', extract)
    monkeypatch.setattr(enhanced, 'select_with_client', select)
    return calls


def test_repair_survives_one_search_outage_and_keeps_old_evidence(monkeypatch):
    calls = install_providers(monkeypatch, fail_first=True)
    previous = RetrievalResult(retrieval_status='completed', evidence=[source(0)],
        trace=RetrievalTrace(search_requests=3, decisions=[{'decision':'initial_trace'}]))
    result = asyncio.run(repair.retrieve_with_client(claim(), previous,
        ['UK road collisions comparable counts', 'UK current driving licence application rules'], None, 't', 'o'))
    assert len(calls['search']) == 2 and len(calls['extract']) == 3
    assert result.retrieval_status == 'completed'
    assert 'source-0' in {s.evidence_id for s in result.evidence}
    assert len(result.evidence) == 4
    assert result.trace.search_requests == 5 and previous.trace.search_requests == 3
    assert any(d['decision']=='provider_failure' for d in result.trace.decisions)
    assert any(d.get('outcome')=='partial_failure' for d in result.trace.decisions)
    assert 'private-provider' not in result.model_dump_json()


def test_no_old_evidence_and_failed_repair_is_failure_not_empty_search(monkeypatch):
    async def fail(*a, **kw): raise httpx.ConnectError('secret')
    monkeypatch.setattr(enhanced.providers, 'tavily_search', fail)
    previous = RetrievalResult(retrieval_status='no_evidence')
    result = asyncio.run(repair.retrieve_with_client(claim(), previous, ['UK driving licence policy'], None, 't', 'o'))
    assert result.retrieval_status == 'failed' and result.warnings


def test_repair_timeout_retains_validated_previous_and_new_sources(monkeypatch):
    install_providers(monkeypatch)
    monkeypatch.setattr(repair, 'TIMEOUT_SECONDS', .025)
    async def partial(self, pages):
        self.evidence.append(source('partial', direct=True))
        await asyncio.sleep(.2)
    monkeypatch.setattr(enhanced.RetrievalRun, 'extract_pages', partial)
    old = RetrievalResult(retrieval_status='completed', evidence=[source(0)])
    result = asyncio.run(repair.retrieve_with_client(claim(), old, ['UK licensing rules'], None, 't', 'o'))
    assert len(result.evidence)==2
    assert any(d['decision']=='assessment_driven_repair_timed_out' for d in result.trace.decisions)
    assert len(old.evidence)==1


def test_gap_evidence_displaces_context_when_pool_is_full():
    old = [source(i) for i in range(6)]
    new = source('new', direct=True)
    retained = repair.retained_pool(old, [new], ['UK current driving licence applications'])
    assert len(retained)==6 and new in retained
    assert len({s.evidence_id for s in retained})==6


def test_existing_document_can_expose_a_missing_section_without_another_fetch():
    old = source(0)
    additional = 'Current applications require a recognised driving test pass and identity documents. Applicants must provide proof of residence.'
    old.full_text = old.passage + '\n\n' + additional
    queries = ['current applications identity documents proof residence']
    refreshed = repair.reselect_existing(CLAIM, [old], queries)
    assert len(refreshed)==1 and old.passage in refreshed[0].passage
    assert additional in refreshed[0].passage and additional not in old.passage
    retained = repair.retained_pool([old], refreshed, queries)
    assert len(retained)==1 and additional in retained[0].passage
    assert retained[0].evidence_id==old.evidence_id and retained[0].provenance==old.provenance
    assert repair.reselect_existing(CLAIM, retained, queries)==[]


def test_verification_queries_replace_topic_shortcuts_on_initial_retrieval(monkeypatch):
    calls = install_providers(monkeypatch, count=2)
    async def google(*a,**kw): return []
    monkeypatch.setattr(enhanced.providers,'google_search',google)
    plan = SimpleNamespace(status='planned',assertions=[
        SimpleNamespace(material=True, kind='change', queries=['DVLA current licence application rules'],
                        evidence_questions=['What are the current licensing application criteria?']),
        SimpleNamespace(material=True, kind='comparison', queries=['UK road collision comparable annual counts'],
                        evidence_questions=['What are comparable annual collision counts?'])])
    result = asyncio.run(enhanced.retrieve_with_client(CLAIM,None,'','t','o',verification_plan=plan))
    assert calls['search']==['DVLA current licence application rules','UK road collision comparable annual counts']
    assert result.evidence and any(d['decision']=='verification_plan_discovery' for d in result.trace.decisions)


def test_repair_query_budget_and_invalid_urls():
    assert clean_queries([' rules ', 'RULES', 'https://localhost/x', 'site:gov.uk test', 'other rules', 'third']) == ['rules', 'other rules']
    plan = SimpleNamespace(status='planned', assertions=[
        SimpleNamespace(material=True, queries=['event rule', 'event alternate']),
        SimpleNamespace(material=True, queries=['causal evidence', 'causal alternate'])])
    assert plan_queries(plan)==['event rule', 'causal evidence', 'event alternate', 'causal alternate']


@pytest.mark.parametrize('text', [
    'Singapore universities reduce admissions for men because National Service makes them graduate later.',
    'Students graduate later because an Australian university changed its course requirements.',
    'Singapore graduates need different admissions qualifications for further study.',
])
def test_education_is_not_employment_without_employment_predicate(text):
    assert topic_for(text) != 'employment'


@pytest.mark.parametrize('text', ['Singapore graduate unemployment doubled',
    'Graduates earn lower salaries this year', 'Foreign workers work pass salary requirements changed'])
def test_actual_employment_claims_keep_domain_route(text):
    assert topic_for(text)=='employment'


def test_selected_and_separate_evidence_survive_navigation_prefix():
    rule = 'Current driving licence applications remain open to qualified residents.'
    table = '| Period | Collisions |\n| --- | --- |\n| 2024 | 100 |\n| 2025 | 110 |'
    text = 'Navigation unrelated menu. ' * 700 + '\n\n' + rule + '\n\n' + table
    excerpt = assessment_excerpt(CLAIM, text, rule,
        repair_queries=['UK current driving licence applications', 'road collisions 2024 2025'])
    assert excerpt.startswith(rule) and table in excerpt and len(excerpt)<=8000


def test_optional_fact_check_failure_does_not_disable_local_recovery(monkeypatch):
    install_providers(monkeypatch, count=1)
    async def fail(*a, **kw): raise httpx.ConnectError('private')
    monkeypatch.setattr(enhanced.providers, 'google_search', fail)
    monkeypatch.setattr(enhanced.topic_scope, 'recovery_query', lambda *a: 'UK current licensing official rules')
    monkeypatch.setattr(enhanced.topic_scope, 'coverage_gaps', lambda *a: ['Missing policy evidence'])
    async def plan(*a, **kw): return ['UK driving licence applications']
    monkeypatch.setattr(enhanced, 'plan_queries', plan)
    result = asyncio.run(enhanced.retrieve_with_client(CLAIM, None, 'g', 't', 'o'))
    assert any(d['decision']=='targeted_coverage_recovery' for d in result.trace.decisions)
    issues=[i for i in result.trace.coverage_issues if 'fact-check' in i.warning]
    assert issues and not issues[0].blocks_inference


def test_population_scope_is_not_misread_as_foreign_jurisdiction():
    from app.pipeline.evidence_retrieval.topic_scope import guard_selection
    choice, text=selection('Singapore resident unemployment was reported for the whole resident population.')
    choice.applicability='different_scope'
    choice.applicability_reason='The figures describe overall residents, not specifically to Singapore graduates.'
    context=SimpleNamespace(jurisdiction='Singapore',retrieval_topic='employment')
    assert guard_selection(choice,text,context,'https://mom.gov.sg/report','Singapore graduate unemployment doubled') is None
    assert choice.applicability=='different_scope'


def test_numeric_observation_search_ranks_report_over_methodology_across_topics():
    from app.pipeline.evidence_retrieval.requirements import document_priority, methodology_document
    plan=SimpleNamespace(status='planned',assertions=[SimpleNamespace(material=True,kind='comparison',
        evidence_questions=['What are the transport collision counts?'])])
    technical={'title':'Measuring road collisions','url':'https://gov.uk/Reports/Transport_Technical_Note.pdf'}
    observed={'title':'Annual road collision statistics','url':'https://gov.uk/transport/2025'}
    assert methodology_document(technical['title'],technical['url'])
    assert document_priority(CLAIM,technical,plan)<document_priority(CLAIM,observed,plan)


@pytest.mark.parametrize('notice_outage',[False,True])
def test_planned_airport_claim_preserves_successful_official_notice_coverage(monkeypatch,notice_outage):
    from app.pipeline.shared.context import build_claim_context
    from app.pipeline.shared.dates import infer_date_context
    from app.pipeline.shared.public_changes import public_change_plan
    from app.pipeline.shared.verification import VerificationPlan, VerificationAssertion
    from app.pipeline.evidence_assessment.public_changes import eligible_plan
    text='The airport will close next Friday.'
    now=datetime(2026,11,1,4,tzinfo=timezone.utc)
    context, dates=build_claim_context(text,now),infer_date_context(text,now)
    public_plan=public_change_plan(text,context,dates)
    plan=VerificationPlan(source_text=text,as_of=context.as_of,assumptions=context.assumptions,assertions=[
        VerificationAssertion(id='a1',text=text,kind='prediction',
            evidence_questions=['What current official advisory establishes whether Changi Airport will close?'],
            queries=['Changi Airport official operating hours and next Friday closure'])])
    analysis=ClaimAnalysis(extracted_claim=text,claim_category='factual',checkable=True,
        claim_confidence=.95,classification_reason='Factual assertion',claim_context=context,date_context=dates,
        verification_plan=plan)
    queries=[]
    async def google(*a,**kw): return []
    async def search(client,query,key,**kw):
        queries.append(query)
        if notice_outage and query==public_plan['queries'][0]:
            raise httpx.ConnectError('private diagnostic')
        return [dict(url=url,title='Official Changi Airport operating information',score=.9,
                     content='Changi Airport passenger checkpoint operates 24 hours.')
                for url in public_plan['baseline_urls']]
    async def extract(client,urls,key,**kw):
        return {'results':[{'url':url,'raw_content':
            'Changi Airport passenger checkpoint operates 24 hours.' if 'ica.gov.sg' in url else
            'Passenger flights operate at Changi Airport each day.'} for url in urls], 'failed_results':[]}
    async def select(client,claim,page,key,**kw):
        selected,body=selection(page)
        selected.relevance='context';selected.applicability='uncertain_time'
        selected.applicability_reason='Current operations are a baseline, not a guarantee about a future date.'
        return selected,body
    monkeypatch.setattr(enhanced.providers,'google_search',google)
    monkeypatch.setattr(enhanced.providers,'tavily_search',search)
    monkeypatch.setattr(enhanced.providers,'tavily_extract',extract)
    monkeypatch.setattr(enhanced,'select_with_client',select)
    retrieval=asyncio.run(enhanced.retrieve_with_client(text,None,'g','t','o',claim_context=context,
                                                      date_context=dates,verification_plan=plan))
    assert set(public_plan['queries'])<=set(queries) and len(queries)==3
    result=SimpleNamespace(assessment_outcome='insufficient_evidence',component_assessment=None)
    eligible=eligible_plan(analysis,retrieval,result)
    assert (eligible is not None) is (not notice_outage)
