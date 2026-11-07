"""Transport metadata remains useful without changing verdicts, errors or quota."""
from datetime import date, datetime, timezone
import json

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.research import OpenAIResearchPipeline
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import (
    PreparedText, RetrievalTrace, provider_transport_diagnostics,
)
from app.pipeline.shared.web_research import ResearchAssessment
from app.portal.models import PipelineRun


TEXT = 'The community museum opens at nine.'
NOW = datetime(2026, 11, 7, 8, tzinfo=timezone.utc)


def event(**changes):
    values = dict(decision='openai_transport', provider='openai',
                  phase='research_response', attempt='1', outcome='failed',
                  http_status='503', error_code='server_is_overloaded',
                  error_type='service_unavailable_error', request_id='req_abcd1234',
                  elapsed_ms='900', stop_reason='attempt_limit')
    values.update(changes)
    return values


def make_pipeline(researcher, *, repository=None, runs=None):
    return OpenAIResearchPipeline(repository=repository or InMemoryResultRepository(),
        researcher=researcher, run_recorder=runs.append if runs is not None else None,
        prepare_input=lambda text: PreparedText(original_text=text, normalised_text=text, language='en'),
        clock=lambda: NOW, id_factory=lambda: 'run-transport', pipeline_version='openai-web-test')


def researched():
    return ResearchAssessment(verdict='true', summary='The published opening hours support this claim.',
        findings=[dict(claim=TEXT, status='supported', explanation='The published opening time is nine.',
                       source_ids=['c1'], material=True, basis='direct')],
        sources=[dict(id='c1', title='Museum hours', url='https://example.gov.sg/hours')],
        limitations=['Opening hours may change.'], recommended_action='Read the museum opening hours.',
        as_of=date(2026, 11, 7), model='test-model')


def test_projection_discards_unapproved_fields_and_invalid_metadata():
    trace = RetrievalTrace(decisions=[
        event(message='PRIVATE_PROVIDER_BODY', authorization='PRIVATE_KEY',
              original_text='PRIVATE_CLAIM'),
        event(request_id='sk_PRIVATE_KEY'),
        event(error_code='PRIVATE_UNKNOWN_CODE'),
        event(phase='PRIVATE_PHASE'),
        event(decision='other_decision'),
    ])
    projected = provider_transport_diagnostics(trace)
    assert len(projected) == 1
    saved = projected[0].model_dump(mode='json', exclude_none=True)
    assert saved['http_status'] == 503 and saved['attempt'] == 1
    assert 'PRIVATE' not in json.dumps(saved)
    assert 'message' not in saved and 'decision' not in saved


def test_projection_is_bounded_and_ignores_bad_diagnostic_containers():
    trace = RetrievalTrace(decisions=[event(request_id=f'req_{number}') for number in range(20)])
    assert len(provider_transport_diagnostics(trace)) == 12
    assert provider_transport_diagnostics(trace)[0].request_id == 'req_8'
    trace.decisions = None
    assert provider_transport_diagnostics(trace) == []


def test_failed_request_keeps_diagnostics_and_preserves_original_error():
    repository, runs = InMemoryResultRepository(), []
    failure = PipelineComponentError('The research service is busy.', error_code='OPENAI_UNAVAILABLE',
                                     stage='evidence_assessment', retryable=True)

    async def unavailable(text, *, as_of, trace):
        trace.decisions.extend([event(outcome='retry', stop_reason=None), event(attempt='2')])
        raise failure

    with pytest.raises(PipelineComponentError) as caught:
        make_pipeline(unavailable, repository=repository, runs=runs).analyze(TEXT)
    assert caught.value is failure
    assert not repository.results
    saved = repository.failures['run-transport']
    assert saved.error_code == 'OPENAI_UNAVAILABLE' and saved.retryable is True
    assert len(saved.provider_diagnostics) == 2
    assert runs[0]['provider_diagnostics'][1]['attempt'] == 2
    assert runs[0]['error_code'] == saved.error_code
    assert TEXT not in json.dumps(runs[0], default=str)
    assert PipelineRun.model_validate(runs[0]).provider_diagnostics == saved.provider_diagnostics


def test_completed_request_keeps_recovery_diagnostics_and_verdict():
    repository, runs = InMemoryResultRepository(), []

    async def recovered(text, *, as_of, trace):
        trace.decisions.extend([event(outcome='retry', stop_reason=None),
                                event(attempt='2', outcome='success', http_status='200',
                                      error_code=None, error_type=None, stop_reason=None)])
        # Runtime trace dictionaries use strings; omit absent fields as transport does.
        trace.decisions = [{key: value for key, value in row.items() if value is not None}
                           for row in trace.decisions]
        return researched()

    result = make_pipeline(recovered, repository=repository, runs=runs).analyze(TEXT)
    assert result.research_assessment.verdict == 'true'
    assert repository.results['run-transport'] is result
    assert len(runs[0]['provider_diagnostics']) == 2
    assert runs[0]['provider_diagnostics'][-1]['outcome'] == 'success'
    assert PipelineRun.model_validate(runs[0]).status == 'completed'


@pytest.mark.parametrize('input_source', ['text', 'ocr'])
def test_failed_authenticated_request_saves_metadata_without_charging(signed_analysis, input_source):
    store, _ = signed_analysis
    if input_source == 'ocr':
        store.documents['users', 'analysis-user']['role'] = 'premium'
    calls = []

    async def unavailable(text, *, as_of, trace):
        calls.append(text)
        trace.decisions.append(event())
        raise PipelineComponentError('The research service is busy.', error_code='OPENAI_UNAVAILABLE',
                                     stage='evidence_assessment', retryable=True)

    app.dependency_overrides[get_pipeline_orchestrator] = lambda: make_pipeline(unavailable)
    client = TestClient(app)
    payload, headers = {'text': TEXT, 'input_source': input_source}, {'Idempotency-Key': 'transport-failure'}
    response = client.post('/analysis/text', json=payload, headers=headers)
    assert response.status_code == 503
    assert set(response.json()['detail']) == {'message', 'error_code', 'stage', 'retryable'}
    assert store.documents['usage_allowances', 'analysis-user']['successful_submissions'] == 0
    saved = [value for (collection, _), value in store.documents.items() if collection == 'analysis_results']
    assert saved[0]['provider_diagnostics'][0]['http_status'] == 503
    assert saved[0]['input_source'] == input_source
    assert 'request_id' not in response.text
    assert client.post('/analysis/text', json=payload, headers=headers).status_code == 409
    assert len(calls) == 1


def test_recovered_authenticated_request_charges_one_check_and_stays_idempotent(signed_analysis):
    store, _ = signed_analysis
    calls = []

    async def recovered(text, *, as_of, trace):
        calls.append(text)
        trace.decisions.extend([event(outcome='retry'), event(attempt='2', outcome='success', http_status='200')])
        return researched()

    app.dependency_overrides[get_pipeline_orchestrator] = lambda: make_pipeline(recovered)
    client = TestClient(app)
    payload, headers = {'text': TEXT}, {'Idempotency-Key': 'transport-recovered'}
    first = client.post('/analysis/text', json=payload, headers=headers)
    repeated = client.post('/analysis/text', json=payload, headers=headers)
    assert first.status_code == repeated.status_code == 200
    assert first.json() == repeated.json()
    assert store.documents['usage_allowances', 'analysis-user']['successful_submissions'] == 1
    assert len(calls) == 1


def test_legacy_monitoring_record_without_diagnostics_remains_valid():
    run = PipelineRun(run_id='legacy', input_type='text', status='completed', created_at=NOW)
    assert run.provider_diagnostics == []
