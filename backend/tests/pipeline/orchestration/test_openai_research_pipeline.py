"""Direct research keeps the app's ownership and transactional quota boundary."""
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.orchestration.research import OpenAIResearchPipeline
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import PreparedText
from app.pipeline.shared.web_research import ResearchAssessment


TEXT = 'The community museum opens at nine.'
NOW = datetime(2026, 11, 2, 17, 0, tzinfo=timezone.utc)
VERSION = 'openai-web-v1:test-model:reasoning-medium:credibility-v2'


def research_result(**changes):
    data = dict(verdict='true', summary='The published opening hours support this claim.',
        findings=[dict(claim=TEXT, status='supported', explanation='The museum publishes a nine o\'clock opening time.',
                       source_ids=['c1'], material=True, basis='direct')],
        sources=[dict(id='c1', title='Museum hours', url='https://example.gov.sg/hours')],
        limitations=['Opening hours may change.'], recommended_action='Read the museum opening hours.',
        as_of=date(2026, 11, 3), model='test-model')
    data.update(changes)
    return ResearchAssessment(**data)


def make_pipeline(repository=None, runs=None, researcher=None, prepare_input=None):
    async def complete(text, *, as_of, trace):
        assert text == TEXT
        assert as_of == date(2026, 11, 3)
        trace.search_requests = 1
        return research_result()
    return OpenAIResearchPipeline(repository=repository or InMemoryResultRepository(),
        run_recorder=(runs.append if runs is not None else None), researcher=researcher or complete,
        prepare_input=prepare_input or (lambda text: PreparedText(original_text=text, normalised_text=text, language='en')),
        clock=lambda: NOW, id_factory=lambda: 'run-1', pipeline_version=VERSION)


def test_original_claim_and_singapore_date_go_directly_to_research():
    repository, runs = InMemoryResultRepository(), []
    result = make_pipeline(repository, runs).analyze(TEXT)
    assert result.original_text == result.extracted_claim == TEXT
    assert result.research_assessment.as_of.isoformat() == '2026-11-03'
    assert result.credibility.status == 'research_only'
    assert result.credibility.score is None
    assert result.evidence == []
    assert result.verification_plan is None
    assert repository.results['run-1'] == result
    assert runs[0]['run_id'] == result.result_id
    assert set(runs[0]['stage_timings_ms']) == {'input_preparation', 'web_research'}
    assert 'original_text' not in runs[0]


def test_failed_research_is_recorded_without_a_completed_result():
    async def unavailable(*args, **kwargs):
        raise PipelineComponentError('OpenAI web search is unavailable.',
            error_code='OPENAI_RESEARCH_UNAVAILABLE', stage='evidence_assessment')
    repository, runs = InMemoryResultRepository(), []
    with pytest.raises(PipelineComponentError):
        make_pipeline(repository, runs, unavailable).analyze(TEXT)
    assert not repository.results
    assert repository.failures['run-1'].pipeline_version == VERSION
    assert runs[0]['status'] == 'failed'
    assert runs[0]['error_code'] == 'OPENAI_RESEARCH_UNAVAILABLE'


def test_provider_payload_exception_is_not_exposed():
    async def broken(*args, **kwargs):
        raise RuntimeError('PRIVATE_KEY_PROVIDER_PAYLOAD')
    with pytest.raises(PipelineComponentError) as caught:
        make_pipeline(researcher=broken).analyze(TEXT)
    assert caught.value.error_code == 'OPENAI_RESEARCH_FAILED'
    assert 'PRIVATE' not in str(caught.value)


def test_auth_route_history_and_reporting_accept_research_results(signed_analysis):
    store, _ = signed_analysis
    runs = []
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: make_pipeline(runs=runs)
    client = TestClient(app)
    response = client.post('/analysis/text', json={'text': TEXT}, headers={'Idempotency-Key': 'research-success'})
    assert response.status_code == 200, response.text
    record = response.json()
    assert record['research_assessment']['sources'][0]['id'] == 'c1'
    assert record['credibility']['score'] is None
    saved = client.get('/analysis/results/' + record['result_id'])
    assert saved.status_code == 200
    assert saved.json()['research_assessment'] == record['research_assessment']
    repeated = client.post('/analysis/text', json={'text': TEXT}, headers={'Idempotency-Key': 'research-success'})
    assert repeated.status_code == 200
    assert store.documents['usage_allowances', 'analysis-user']['successful_submissions'] == 1
    assert len(runs) == 1 and runs[0]['run_id'] == record['result_id']


def test_failed_auth_research_does_not_charge_allowance(signed_analysis):
    store, _ = signed_analysis
    async def unavailable(*args, **kwargs):
        raise PipelineComponentError('The research service is busy.', error_code='OPENAI_RATE_LIMITED', stage='evidence_assessment')
    runs = []
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: make_pipeline(runs=runs, researcher=unavailable)
    response = TestClient(app).post('/analysis/text', json={'text': TEXT})
    assert response.status_code == 503
    assert response.json()['detail']['error_code'] == 'OPENAI_RATE_LIMITED'
    assert store.documents['usage_allowances', 'analysis-user']['successful_submissions'] == 0
    records = [value for (kind, _), value in store.documents.items() if kind == 'analysis_results']
    assert records[0]['pipeline_version'] == VERSION
    assert runs[0]['status'] == 'failed'


def test_research_finishing_after_singapore_midnight_preserves_submission_date(signed_analysis):
    store, _ = signed_analysis
    submitted = datetime(2026, 11, 3, 15, 59, 50, tzinfo=timezone.utc)
    completed = datetime(2026, 11, 3, 16, 0, 5, tzinfo=timezone.utc)
    current = [submitted]
    store.clock = lambda: current[0]

    async def finish_after_midnight(text, *, as_of, trace):
        assert as_of == date(2026, 11, 3)
        current[0] = completed
        return research_result(as_of=as_of)

    pipeline = OpenAIResearchPipeline(repository=InMemoryResultRepository(),
        researcher=finish_after_midnight, clock=lambda: current[0], pipeline_version=VERSION,
        prepare_input=lambda text: PreparedText(original_text=text, normalised_text=text, language='en'))
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    client = TestClient(app)
    headers = {'Idempotency-Key': 'research-crossing-midnight'}
    response = client.post('/analysis/text', json={'text': TEXT}, headers=headers)
    assert response.status_code == 200, response.text
    record = response.json()
    assert datetime.fromisoformat(record['created_at']) == submitted
    assert record['research_assessment']['as_of'] == '2026-11-03'
    stored = store.documents['analysis_results', record['result_id']]
    assert stored['created_at'] == submitted
    assert stored['saved_at'] == completed
    saved = client.get('/analysis/results/' + record['result_id'])
    assert saved.status_code == 200
    assert saved.json()['research_assessment']['as_of'] == '2026-11-03'
    assert client.post('/analysis/text', json={'text': TEXT}, headers=headers).status_code == 200
    assert store.documents['usage_allowances', 'analysis-user']['successful_submissions'] == 1


def test_factory_web_mode_bypasses_legacy_providers(monkeypatch):
    from app.pipeline.orchestration import dependencies as dependencies
    monkeypatch.setenv('TEXT_ANALYSIS_MODE', 'openai_web')
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-key')
    monkeypatch.setenv('OPENAI_ASSESSMENT_MODEL', 'test-model')
    monkeypatch.setenv('EVIDENCE_PIPELINE_V3', '0')
    monkeypatch.setenv('EVIDENCE_VERIFICATION_ENABLED', 'false')
    monkeypatch.setenv('EVIDENCE_VERIFICATION_PROVIDER', 'invalid-legacy-setting')
    def forbidden():
        pytest.fail('Direct research must not initialize the legacy retriever or assessor')
    monkeypatch.setattr(dependencies, 'configured_retriever', forbidden)
    monkeypatch.setattr(dependencies, 'configured_assessor', forbidden)
    get_pipeline_orchestrator.cache_clear()
    try:
        instance = get_pipeline_orchestrator()
        assert isinstance(instance, OpenAIResearchPipeline)
        assert instance.pipeline_version.startswith('openai-web-v1:test-model')
    finally:
        get_pipeline_orchestrator.cache_clear()


def test_invalid_mode_fails_explicitly(monkeypatch):
    monkeypatch.setenv('TEXT_ANALYSIS_MODE', 'private-bogus')
    get_pipeline_orchestrator.cache_clear()
    try:
        with pytest.raises(PipelineComponentError) as caught:
            get_pipeline_orchestrator()
        assert caught.value.error_code == 'ASSESSMENT_CONFIGURATION_INVALID'
        assert 'private-bogus' not in str(caught.value)
    finally:
        get_pipeline_orchestrator.cache_clear()
