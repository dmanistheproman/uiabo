import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from pydantic import ValidationError

from app.pipeline.evidence_assessment import control, pool
from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.credibility import build_credibility
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult, TextAnalysisResult

NOW = datetime(2026, 11, 1, 5, tzinfo=timezone.utc)
TEXT = 'Singapore airline is controlled by Singapore Government'
QUOTE = 'SIA makes independent operational decisions without government direction.'


def fixture():
    claim = ClaimAnalysis(extracted_claim=TEXT, checkable=True, claim_category='factual',
        classification_reason='Fixture', claim_confidence=1, claim_context=build_claim_context(TEXT, NOW))
    source = EvidenceCandidate(evidence_id='official', title='Governance',
        url='https://www.temasek.com.sg/governance', publisher='Temasek', source_type='other',
        passage=QUOTE, retrieved_at=NOW, retrieval_score=.5,
        provenance=EvidenceProvenance(source_policy='scoped_first_party', source_reason='Reviewed identity',
            origin_group='temasek-portfolio', discovery_method='preferred_search', relevance='context',
            relevance_reason='Operational governance', relevance_quote=QUOTE,
            applicability='missing_context', applicability_reason='Ownership must be assessed separately'))
    retrieval = RetrievalResult(retrieval_status='completed', evidence=[source])
    draft = control.Draft(operations=control.DraftFinding(outcome='contradicting',
        explanation='The statement weighs against direct day-to-day government management.',
        citations=[{'evidence_id':'official', 'quote':QUOTE}], scope_matched=True, current_enough=True),
        ownership=control.DraftFinding(outcome='unresolved', explanation='This source does not establish the ownership chain.',
            citations=[], scope_matched=False, current_enough=True))
    return claim, retrieval, draft


def test_separate_meanings_do_not_create_blanket_false_or_fifty(monkeypatch):
    claim, retrieval, draft = fixture()
    async def judge(*a): return draft
    monkeypatch.setattr(control, 'judge', judge)
    monkeypatch.setattr(pool, '_pool_verdicts', lambda *a: pytest.fail('No blanket vote'))
    result = pool.assess_pool_evidence(claim, retrieval)
    assert result.assessment_outcome == 'insufficient_evidence'
    assert result.misinformation_risk_score is None
    assert result.control_interpretations.operations.outcome == 'contradicting'
    assert result.control_interpretations.ownership.outcome == 'unresolved'
    assert 'if referring to day-to-day management' in build_credibility(result).label
    assert result.assessed_evidence[0].stance == 'neutral'


@pytest.mark.parametrize('change', ['quote', 'source', 'scope', 'date'])
def test_unsupported_conditional_verdict_is_downgraded(change):
    claim, retrieval, draft = fixture()
    if change == 'quote': draft.operations.citations[0].quote = 'Fabricated statement about control.'
    if change == 'source': draft.operations.citations[0].evidence_id = 'missing'
    if change == 'scope': draft.operations.scope_matched = False
    if change == 'date': draft.operations.current_enough = False
    result = control.assemble(claim, retrieval, draft)
    assert result.control_interpretations.operations.outcome == 'unresolved'
    assert build_credibility(result).label == 'The meaning of control matters'


def test_failure_is_not_a_false_finding(monkeypatch):
    claim, retrieval, _ = fixture()
    async def fail(*a): raise httpx.ConnectError('offline')
    monkeypatch.setattr(control, 'judge', fail)
    result = asyncio.run(control.assess(claim, retrieval))
    assert result.control_interpretations.operations.outcome == 'unresolved'


@pytest.mark.parametrize('text,expected', [
    (TEXT, True), ('SIA is controlled by the Government', True),
    ('SIA is controlled by the Government through voting rights', False),
    ('SIA is controlled by the Government in its day-to-day management', False),
    ('SIA is not controlled by the Government', False),
    ('What if SIA is controlled by the Government?', False),
    ('The fire is controlled by the rain', False),
])
def test_meanings_are_not_applied_to_explicit_or_noncorporate_claims(text, expected):
    from app.pipeline.shared.interpretation import ambiguous_control
    assert ambiguous_control(text) is expected


def test_optional_judge_validates_fenced_json_object(monkeypatch):
    claim, retrieval, draft = fixture()
    monkeypatch.setattr(pool, '_provider_keys', lambda: (None, 'test-key'))
    original_client = httpx.AsyncClient
    def handler(request):
        payload = json.loads(request.content)
        assert 'operations' in payload['format']['properties']
        assert 'ownership' in payload['format']['properties']
        return httpx.Response(200, json={'done': True, 'message': {
            'content': '```json\n' + draft.model_dump_json() + '\n```'}})
    monkeypatch.setattr(control.httpx, 'AsyncClient', lambda **kwargs:
        original_client(transport=httpx.MockTransport(handler), **kwargs))
    assert asyncio.run(control.judge(claim, retrieval)) == draft


def test_conditional_findings_cannot_acquire_a_whole_claim_score():
    claim, retrieval, draft = fixture()
    result = control.assemble(claim, retrieval, draft)
    for change in [{'misinformation_risk_score': 50}, {'assessment_outcome':'contradicted'}]:
        with pytest.raises(ValidationError):
            type(result).model_validate({**result.model_dump(), **change})


def test_api_history_replay_keep_scoped_findings_and_reject_forged_quote(signed_analysis):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.pipeline.input_preparation.service import prepare_text
    from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
    from app.pipeline.orchestration.repository import InMemoryResultRepository
    from app.pipeline.orchestration.service import PipelineOrchestrator
    claim, retrieval, draft = fixture()
    pipeline = PipelineOrchestrator(prepare_input=prepare_text, analyze_claim=lambda _: claim,
        retrieve_evidence=lambda _: retrieval, assess_evidence=lambda c,r: control.assemble(c,r,draft),
        repository=InMemoryResultRepository(), clock=lambda: NOW)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    with TestClient(app) as client:
        response = client.post('/analysis/text', json={'text':TEXT}, headers={'Idempotency-Key':'control-test'})
        assert response.status_code == 200, response.text
        data = response.json()
        history = client.get('/analysis/results').json()['results'][0]
        saved = client.get('/analysis/results/' + data['result_id']).json()
        replay = client.post('/analysis/text', json={'text':TEXT}, headers={'Idempotency-Key':'control-test'}).json()
        for value in [data, history, saved, replay]:
            assert value['control_interpretations'] == data['control_interpretations']
            TextAnalysisResult.model_validate(value)
        data['control_interpretations']['operations']['citations'][0]['quote'] = 'Fabricated evidence quotation'
        with pytest.raises(ValidationError): TextAnalysisResult.model_validate(data)
