import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import ValidationError

from app.pipeline.evidence_assessment import public_changes as inference
from app.pipeline.evidence_assessment.service import summarise_assessments
from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.dates import infer_date_context
from app.pipeline.shared.public_changes import public_change_plan
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult, RetrievalTrace, AssessedEvidence, AssessmentResult

NOW = datetime(2026, 11, 1, 4, tzinfo=timezone.utc)
AIRPORT = 'The airport will close next Friday. Everyone needs to change their flights.'
PASSPORT = 'ICA will begin rejecting passports with less than one year of validity.'


def test_baseline_is_copied_from_sentence_ids_without_model_paraphrasing():
    claim, retrieval, result, plan, draft = fixture()
    selected = inference.InferenceSelection(**draft.model_dump(exclude={'baseline_quote'}),
        baseline_sentence_start=0, baseline_sentence_end=0)
    bound = inference.bind_baseline(selected, retrieval.evidence)
    assert bound.baseline_quote == retrieval.evidence[0].passage
    assert inference.apply_draft(claim, retrieval, result, plan, bound).assessment_outcome == 'likely_misinformation'
    with pytest.raises(ValueError):
        inference.bind_baseline(selected.model_copy(update={'baseline_sentence_end': 999}), retrieval.evidence)
    with pytest.raises(ValueError):
        inference.bind_baseline(selected.model_copy(update={'baseline_source_id': 'invented'}), retrieval.evidence)


def test_general_policy_inference_preserves_announcements_and_requires_coverage():
    text = 'From 2027, households living in private property will no longer receive healthcare subsidies.'
    claim, retrieval, _, plan, draft = fixture(text)
    passages = [
        'Singapore citizens living in private property may qualify for healthcare subsidies under the published eligibility rules.',
        'This official Singapore page describes the current healthcare subsidy eligibility rules for private-property residents.',
    ]
    for i, source in enumerate(retrieval.evidence):
        source.url = ['https://moh.gov.sg/eligibility', 'https://www.chas.sg/FAQ'][i]
        source.passage = passages[i]
        source.provenance.relevance_quote = passages[i]
    result = summarise_assessments(text, retrieval, [AssessedEvidence(evidence_id=s.evidence_id,
        stance='neutral', quality_score=.4, assessment_reason='Current baseline, not a future guarantee') for s in retrieval.evidence])
    draft = draft.model_copy(update={'baseline_quote': passages[0],
        'explanation': 'The published eligibility rules weigh against the alleged blanket removal. No supporting change was found in the official sources checked.'})
    assert plan['kind'] == 'policy_change'
    assert inference.eligible_plan(claim, retrieval, result)
    assert inference.apply_draft(claim, retrieval, result, plan, draft).assessment_outcome == 'likely_misinformation'
    assert inference.apply_draft(claim, retrieval, result, plan, draft.model_copy(update={'announcement_found': True})) is result
    retrieval.trace.decisions.clear()
    assert inference.eligible_plan(claim, retrieval, result) is None


def test_public_inference_explanation_cannot_claim_a_conclusive_future_denial():
    claim, retrieval, result, plan, draft = fixture()
    draft.explanation = 'The present operating rule directly contradicts any future closure and proves the claim false.'
    updated = inference.apply_draft(claim, retrieval, result, plan, draft)
    assert updated.assessment_outcome == 'likely_misinformation'
    assert draft.baseline_quote in updated.explanation
    assert 'limited inference' in updated.explanation
    assert 'directly contradicts' not in updated.explanation


def fixture(text=AIRPORT):
    claim = ClaimAnalysis(extracted_claim=text, claim_category='factual', checkable=True,
        claim_confidence=1, classification_reason='Fixture',
        date_context=infer_date_context(text, NOW), claim_context=build_claim_context(text, NOW))
    plan = public_change_plan(text, claim.claim_context, claim.date_context)
    sources = []
    for i, url in enumerate(['https://www.ica.gov.sg/about-ica/about-us/our-checkpoints',
                              'https://www.changiairport.com/advisory']):
        passage = 'Changi Airport passenger checkpoint operates 24 hours.' if not i else 'Passenger flights operate at Changi Airport.'
        sources.append(EvidenceCandidate(evidence_id=str(i), url=url, title='Official information',
            publisher='Official publisher', source_type='government' if not i else 'other',
            retrieved_at=NOW, passage=passage, retrieval_score=.5,
            provenance=EvidenceProvenance(source_policy='catalogue', source_reason='Official identity',
                origin_group='official', discovery_method='preferred_search', relevance='context',
                relevance_quote=passage, relevance_reason='Current operations',
                applicability='uncertain_time', applicability_reason='Current operations cannot settle a future notice')))
    retrieval = RetrievalResult(retrieval_status='completed', evidence=sources, trace=RetrievalTrace(
        decisions=[{'decision':'public_notice_search_completed', 'query': q} for q in plan['queries']]))
    result = summarise_assessments(text, retrieval, [AssessedEvidence(evidence_id=s.evidence_id,
        stance='neutral', quality_score=.4, assessment_reason='Current baseline, not conclusive denial') for s in sources])
    draft = inference.InferenceDraft(baseline_source_id='0', baseline_quote=sources[0].passage,
        same_scope=True, current_baseline=True, public_notice_expected=True, announcement_found=False,
        evidence_weighs_against=True, explanation='Normal operations weigh against the imminent closure. The successful official searches found no supporting announcement, but a new notice may change the assessment.')
    return claim, retrieval, result, plan, draft


@pytest.mark.parametrize('text', [AIRPORT, 'Changi Airport will close tomorrow.', PASSPORT])
def test_supported_discovery_plans_keep_assumptions_visible(text):
    context = build_claim_context(text, NOW)
    plan = public_change_plan(text, context, infer_date_context(text, NOW))
    assert plan
    if plan['assumption']:
        assert plan['assumption'] in context.assumptions


def test_bounded_public_change_claim_does_not_need_model_span_extraction(monkeypatch):
    from app.pipeline.claim_analysis.pool_v3 import analyse_claim_v3
    from app.pipeline.input_preparation.service import prepare_text
    monkeypatch.setattr('app.pipeline.claim_analysis.pool_v3._keys', lambda: pytest.fail('No provider needed'))
    result = analyse_claim_v3(prepare_text(PASSPORT))
    assert result.checkable and result.extracted_claim == PASSPORT


def test_checkpoint_hours_stay_with_the_correct_facility():
    from app.pipeline.shared.public_changes import baseline_section
    _, _, _, plan, _ = fixture()
    page = ('**Airport Logistics Park of Singapore**\n7.30 am to 7 pm\n\n'
            '**Changi Airport**\nPassenger Terminal Building II\n24 Hours\n\n'
            '**Parcel Post Section**\nClosed on public holidays')
    selected = baseline_section(plan, plan['baseline_urls'][0], page)
    assert selected == '**Changi Airport**\nPassenger Terminal Building II\n24 Hours'
    assert selected in page
    assert baseline_section(plan, 'https://example.com', page) == page
    assert baseline_section(plan, plan['baseline_urls'][0], 'changed format') == 'changed format'


def test_notice_pages_take_priority_over_travel_features():
    from app.pipeline.shared.public_changes import page_priority
    _, _, _, plan, _ = fixture()
    notice = page_priority(plan, 'Changi Airport newsroom', 'https://www.changiairport.com/en/corporate/our-media-hub/newsroom')
    feature = page_priority(plan, 'Growing night flights', 'https://www.changiairport.com/en/changi-journeys/night-flights')
    unrelated = page_priority(plan, 'ICA no-boarding directives', 'https://www.ica.gov.sg/no-boarding')
    assert notice > feature > unrelated


@pytest.mark.parametrize('text', [
    'Heathrow Airport will close next Friday.', 'Seletar Airport will close tomorrow.',
    'The airport in Bangkok will close next Friday.', 'The airport will not close next Friday.',
    'The airport will close in 2035.', 'The airport will close yesterday.',
    'What if the airport closes next Friday?', 'Officials are discussing a new passport rule.',
    'ICA will begin rejecting passports with less than one year of validity in 2035.',
    'Every MRT ride in Singapore will definitely become free on 1 January 2035.',
    'Singapore will definitely win the football World Cup in 2038.',
])
def test_other_scope_is_never_silently_assigned_changi_or_a_near_term_rule(text):
    assert public_change_plan(text, build_claim_context(text, NOW), infer_date_context(text, NOW)) is None


def test_quoted_baseline_and_successful_searches_allow_limited_inference(monkeypatch):
    claim, retrieval, result, plan, draft = fixture()
    async def judge(*args): return draft
    monkeypatch.setattr(inference, 'judge', judge)
    out = asyncio.run(inference.apply_inference(claim, retrieval, result))
    assert out.assessment_outcome == 'likely_misinformation'
    assert out.misinformation_risk_score is None
    assert out.scoring.status == 'inference_based'
    assert out.assessed_evidence[0].stance == 'neutral'
    for change in [{'misinformation_risk_score': 50}, {'inference_context': None}, {'assessment_outcome': 'contradicted'}]:
        with pytest.raises(ValidationError):
            AssessmentResult.model_validate({**out.model_dump(), **change})


@pytest.mark.parametrize('failure', ['warnings', 'missing_search', 'one_page', 'stale', 'no_trace'])
def test_incomplete_coverage_never_calls_inference(failure, monkeypatch):
    claim, retrieval, result, plan, draft = fixture()
    if failure == 'warnings': retrieval.warnings.append('A source could not be read.')
    if failure == 'missing_search': retrieval.trace.decisions.pop()
    if failure == 'one_page': retrieval.evidence.pop()
    if failure == 'stale': retrieval.evidence[0].retrieved_at = NOW - timedelta(days=2)
    if failure == 'no_trace': retrieval.trace = None
    monkeypatch.setattr(inference, 'judge', lambda *a: pytest.fail('Must not judge incomplete coverage'))
    assert asyncio.run(inference.apply_inference(claim, retrieval, result)) is result


@pytest.mark.parametrize('changes', [
    {'announcement_found': True}, {'same_scope': False}, {'current_baseline': False},
    {'public_notice_expected': False}, {'evidence_weighs_against': False},
    {'baseline_source_id': 'invented'}, {'baseline_quote': 'A fabricated quote that is absent.'},
])
def test_no_label_without_grounded_inference_or_when_change_is_announced(changes):
    claim, retrieval, result, plan, draft = fixture()
    assert inference.apply_draft(claim, retrieval, result, plan, draft.model_copy(update=changes)) is result


def test_inference_provider_failure_preserves_unresolved(monkeypatch):
    claim, retrieval, result, plan, draft = fixture()
    async def fail(*args): raise httpx.ConnectError('fixture')
    monkeypatch.setattr(inference, 'judge', fail)
    assert asyncio.run(inference.apply_inference(claim, retrieval, result)) is result


def test_inference_survives_api_history_and_replay(signed_analysis, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.pipeline.input_preparation.service import prepare_text
    from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
    from app.pipeline.orchestration.repository import InMemoryResultRepository
    from app.pipeline.orchestration.service import PipelineOrchestrator
    from app.pipeline.shared.models import TextAnalysisResult
    claim, retrieval, result, plan, draft = fixture()
    pipeline = PipelineOrchestrator(prepare_input=prepare_text, analyze_claim=lambda _: claim,
        retrieve_evidence=lambda _: retrieval,
        assess_evidence=lambda c, r: inference.apply_draft(c, r, result, plan, draft),
        repository=InMemoryResultRepository(), clock=lambda: NOW)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    with TestClient(app) as client:
        response = client.post('/analysis/text', json={'text': AIRPORT}, headers={'Idempotency-Key':'notice-fixture'})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['credibility']['label'] == 'Likely misinformation'
        assert data['credibility']['score'] is None
        history = client.get('/analysis/results').json()['results'][0]
        saved = client.get('/analysis/results/' + data['result_id']).json()
        replay = client.post('/analysis/text', json={'text': AIRPORT}, headers={'Idempotency-Key':'notice-fixture'}).json()
        for value in [data, saved, history, replay]:
            assert value['inference_context'] == data['inference_context']
            TextAnalysisResult.model_validate(value)
        tampered = {**data, 'inference_context': {**data['inference_context'], 'baseline_quote': 'A fabricated source quote'}}
        with pytest.raises(ValidationError): TextAnalysisResult.model_validate(tampered)


def test_official_queries_are_scoped_and_failure_is_not_recorded_as_success(monkeypatch):
    from app.pipeline.evidence_retrieval.enhanced import RetrievalRun
    claim, retrieval, result, plan, draft = fixture()
    seen = []
    async def search(client, query, key, **kwargs):
        seen.append(kwargs)
        if len(seen) == 2: raise httpx.ConnectError('unavailable')
        return []
    monkeypatch.setattr('app.pipeline.evidence_retrieval.providers.tavily_search', search)
    async def run():
        async with httpx.AsyncClient() as client:
            state = RetrievalRun(AIRPORT, client, 'fixture', 'fixture', 'fixture',
                date_context=claim.date_context, claim_context=claim.claim_context)
            for query in plan['queries']: await state.search(query, broad=True)
            return state
    state = asyncio.run(run())
    assert all(options['broad'] is False and options['preferred_domains'] == plan['domains'] for options in seen)
    assert len([e for e in state.trace.decisions if e['decision'] == 'public_notice_search_completed']) == 1
    assert state.warnings
