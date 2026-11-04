"""Real verifier contracts with an offline OpenAI Responses transport."""
import asyncio
import json
import time

import httpx
import pytest

from app.pipeline.evidence_assessment import pool, verification as v
from app.pipeline.orchestration import dependencies
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import (
    ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult, RetrievalTrace,
)
from app.pipeline.shared.runtime_budget import request_budget
from app.pipeline.shared.verification import VerificationAssertion, VerificationPlan


KEY = 'fake-openai-key-for-offline-tests'
CLAIM = 'Entry requires an age of 75 years.'
PASSAGE = 'Entry requires an age of 64 years. The office opens at 09:00 each day.'


@pytest.fixture(autouse=True)
def openai_environment(monkeypatch):
    monkeypatch.setenv('EVIDENCE_VERIFICATION_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', KEY)
    monkeypatch.setenv('OPENAI_ASSESSMENT_MODEL', 'gpt-6.1-sol')
    monkeypatch.setenv('OPENAI_REASONING_EFFORT', 'medium')
    def forbidden_keys():
        pytest.fail('An OpenAI check must not load Ollama or Jev credentials.')
    async def forbidden_fallback(*args, **kwargs):
        pytest.fail('An OpenAI check must not silently fall back to Ollama.')
    monkeypatch.setattr(pool, '_provider_keys', forbidden_keys)
    monkeypatch.setattr(v, '_call_oss', forbidden_fallback)


def inputs(parts=None):
    parts = parts or [CLAIM]
    text = ' '.join(parts)
    assertions = [VerificationAssertion(id=f'a{index}', text=part,
        evidence_questions=['What do the applicable rules state?'], queries=[part])
        for index, part in enumerate(parts, start=1)]
    claim = ClaimAnalysis(extracted_claim=text, claim_category='factual', checkable=True,
        classification_reason='Public factual test claim.', claim_confidence=1,
        verification_plan=VerificationPlan(source_text=text, assertions=assertions, as_of='2026-11-03'))
    source = EvidenceCandidate(evidence_id='official-rule', title='Published eligibility rules',
        url='https://example.gov.sg/entry-rules', publisher='Example Authority', passage=PASSAGE,
        source_type='government', retrieval_score=.9, retrieved_at='2026-11-03T00:00:00Z',
        provenance=EvidenceProvenance(source_policy='government_namespace',
            source_reason='Official source.', origin_group='example-authority',
            discovery_method='preferred_search', relevance='direct',
            relevance_reason='These are the applicable entry rules.', relevance_quote=PASSAGE,
            applicability='established', applicability_reason='Same current eligibility rule.'))
    retrieval = RetrievalResult(retrieval_status='completed', evidence=[source], trace=RetrievalTrace())
    return claim, retrieval


def finding(id='a1', sentence=0, **changes):
    result = dict(assertion_id=id, status='contradicted',
        citations=[dict(evidence_id='official-rule', start_sentence=sentence, end_sentence=sentence)],
        explanation='The published rule states age 64, which contradicts the claimed age of 75.',
        scope_checks={key: 'established' for key in v.VerificationScopeChecks.model_fields},
        decisiveness=.95, reasoning_type='incompatible_rule', comparisons=[], scope_resolutions=[],
        gaps=[], repair_queries=[])
    result.update(changes)
    return result


def response(findings=None, **changes):
    value = {'status': 'completed', 'error': None, 'output': [
        {'type': 'reasoning', 'summary': []},
        {'type': 'message', 'role': 'assistant', 'status': 'completed', 'content': [
            {'type': 'output_text', 'text': json.dumps({'findings': findings or [finding()]})}]},
    ], 'usage': {'input_tokens': 100, 'output_tokens': 40, 'total_tokens': 140,
                 'output_tokens_details': {'reasoning_tokens': 20}}}
    value.update(changes)
    return value


def responses(monkeypatch, values):
    requests = []
    def handler(request):
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['Authorization'] == f'Bearer {KEY}'
        requests.append(json.loads(request.content))
        assert len(requests) <= len(values), 'Unexpected additional provider request'
        value = values[len(requests) - 1]
        return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)
    client_type = httpx.AsyncClient
    monkeypatch.setattr(v.httpx, 'AsyncClient', lambda **kwargs:
        client_type(**kwargs, transport=httpx.MockTransport(handler)))
    return requests


def test_openai_selected_citation_becomes_original_source_span(monkeypatch):
    claim, retrieval = inputs()
    requests = responses(monkeypatch, [response()])
    draft = asyncio.run(v.judge(claim, retrieval))
    assert len(requests) == 1
    assert draft.findings[0].status == 'contradicted'
    assert draft.findings[0].citations[0].quote == 'Entry requires an age of 64 years.'
    bound = v.bind_findings(claim, retrieval, draft)
    assessed = v.assemble(claim, retrieval, bound)
    assert assessed.assessment_outcome == 'contradicted'
    assert bound.findings[0].citations[0].quote in PASSAGE
    assert requests[0]['store'] is False
    supplied = json.loads(requests[0]['input'][0]['content'])
    assert supplied['plan']['source_text'] == CLAIM
    assert supplied['sources'][0]['sentences'][0]['text'].strip() == 'Entry requires an age of 64 years.'
    assert 'passage' not in supplied['sources'][0]
    selected = [d for d in retrieval.trace.decisions if d['decision'] == 'verification_provider_selected']
    usage = [d for d in retrieval.trace.decisions if d['decision'] == 'verification_provider_usage']
    assert selected == [{'decision': 'verification_provider_selected', 'provider': 'openai', 'model': 'gpt-6.1-sol'}]
    assert usage[0]['input_tokens'] == '100'
    assert usage[0]['reasoning_tokens'] == '20'
    assert KEY not in json.dumps(retrieval.trace.model_dump())


def test_unresolved_is_preserved_without_manufacturing_a_verdict(monkeypatch):
    claim, retrieval = inputs()
    gap = 'The evidence does not establish whether the stated exception applies.'
    unresolved = finding(status='unresolved', citations=[], decisiveness=0., reasoning_type='none',
        scope_checks={key: 'unknown' for key in v.VerificationScopeChecks.model_fields},
        explanation=gap, gaps=[gap], repair_queries=['Find the published exception to the entry rule'])
    requests = responses(monkeypatch, [response([unresolved])])
    draft = asyncio.run(v.judge(claim, retrieval))
    assessment = v.assemble(claim, retrieval, v.bind_findings(claim, retrieval, draft))
    assert len(requests) == 1
    assert assessment.assessment_outcome == 'insufficient_evidence'
    assert assessment.verification.findings[0].status == 'unresolved'
    assert gap in assessment.verification.findings[0].gaps
    assert not assessment.verification.findings[0].citations


def test_bad_citation_gets_one_repair_with_same_original_evidence(monkeypatch):
    claim, retrieval = inputs()
    invalid = finding(citations=[dict(evidence_id='invented-rule', start_sentence=0, end_sentence=0)])
    requests = responses(monkeypatch, [response([invalid]), response()])
    draft = asyncio.run(v.judge(claim, retrieval))
    assert len(requests) == 2
    assert draft.findings[0].citations[0].evidence_id == 'official-rule'
    assert 'Validation feedback:' in requests[1]['instructions']
    first = json.loads(requests[0]['input'][0]['content'])
    second = json.loads(requests[1]['input'][0]['content'])
    assert first['sources'] == second['sources']
    assert len([d for d in retrieval.trace.decisions if d['decision'] == 'verification_contract_failure']) == 1


def test_repair_retains_valid_findings_and_only_requests_failed_assertion(monkeypatch):
    claim, retrieval = inputs([CLAIM, 'The office opens at 09:00 each day.'])
    valid = finding()
    invalid = finding('a2', sentence=99, status='supported', reasoning_type='explicit_statement',
        explanation='The published office opening time supports the asserted opening time.')
    repaired = finding('a2', sentence=1, status='supported', reasoning_type='explicit_statement',
        explanation='The published office opening time supports the asserted opening time.')
    requests = responses(monkeypatch, [response([valid, invalid]), response([repaired])])
    draft = asyncio.run(v.judge(claim, retrieval))
    assert [f.assertion_id for f in draft.findings] == ['a1', 'a2']
    assert [f.status for f in draft.findings] == ['contradicted', 'supported']
    assert draft.findings[0].explanation == valid['explanation']
    repair_state = json.loads(requests[1]['input'][0]['content'])
    assert [a['id'] for a in repair_state['plan']['assertions']] == ['a2']
    assert repair_state['previously_validated_findings'][0]['assertion']['id'] == 'a1'
    assert draft.findings[1].citations[0].quote == 'The office opens at 09:00 each day.'


def test_two_invalid_responses_fail_explicitly_without_ollama_fallback(monkeypatch):
    claim, retrieval = inputs()
    invalid = finding(citations=[dict(evidence_id='official-rule', start_sentence=80, end_sentence=81)])
    requests = responses(monkeypatch, [response([invalid]), response([invalid])])
    with pytest.raises(PipelineComponentError) as error:
        asyncio.run(v.judge(claim, retrieval))
    assert error.value.error_code == 'OPENAI_ASSESSMENT_INVALID'
    assert error.value.retryable is True
    assert len(requests) == 2
    failures = [d for d in retrieval.trace.decisions if d['decision'] == 'verification_contract_failure']
    assert [d['attempt'] for d in failures] == ['1', '2']


@pytest.mark.parametrize('body,code,retryable', [
    (httpx.Response(401, json={'error': {'message': f'private account data {KEY}'}}), 'OPENAI_ACCESS_DENIED', False),
    (httpx.Response(429, json={'error': {'message': 'private quota details'}}), 'OPENAI_RATE_LIMITED', True),
    ({'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'}}, 'OPENAI_RESPONSE_INCOMPLETE', True),
    (response(output=[{'type': 'message', 'role': 'assistant', 'status': 'completed',
        'content': [{'type': 'refusal', 'refusal': 'private refusal text'}]}]), 'OPENAI_ASSESSMENT_REFUSED', False),
])
def test_provider_failure_is_an_error_and_not_an_unresolved_finding(monkeypatch, body, code, retryable):
    claim, retrieval = inputs()
    requests = responses(monkeypatch, [body])
    with pytest.raises(PipelineComponentError) as error:
        asyncio.run(v.judge(claim, retrieval))
    assert error.value.error_code == code
    assert error.value.retryable is retryable
    assert error.value.stage == 'evidence_assessment'
    assert len(requests) == 1
    diagnostic = json.dumps(retrieval.trace.model_dump()) + str(error.value)
    assert KEY not in diagnostic
    assert 'private' not in diagnostic
    failure = [d for d in retrieval.trace.decisions if d['decision'] == 'verification_provider_failure'][0]
    assert failure['provider'] == 'openai'
    assert failure['error_code'] == code


def test_missing_openai_key_fails_before_network_or_ollama_access(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY')
    requests = responses(monkeypatch, [])
    with pytest.raises(PipelineComponentError) as error:
        asyncio.run(v.judge(*inputs()))
    assert error.value.error_code == 'OPENAI_NOT_CONFIGURED'
    assert error.value.retryable is False
    assert requests == []


def test_default_provider_is_ollama_and_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.delenv('EVIDENCE_VERIFICATION_PROVIDER')
    assert v.selected_provider() == 'ollama'
    assert v.provider_version() == ':verifier-ollama:gpt-oss-120b'
    monkeypatch.setenv('EVIDENCE_VERIFICATION_PROVIDER', 'unsupported-provider-secret')
    with pytest.raises(PipelineComponentError) as error:
        v.selected_provider()
    assert error.value.error_code == 'ASSESSMENT_CONFIGURATION_INVALID'
    assert error.value.retryable is False
    assert 'unsupported-provider-secret' not in str(error.value)


def test_openai_version_identifies_model_and_effort_without_credentials(monkeypatch):
    monkeypatch.setenv('OPENAI_ASSESSMENT_MODEL', 'gpt-6.1-sol')
    monkeypatch.setenv('OPENAI_REASONING_EFFORT', 'high')
    assert v.provider_version() == ':verifier-openai:gpt-6.1-sol:reasoning-high'
    monkeypatch.setenv('OPENAI_ASSESSMENT_MODEL', 'https://secret.example/key')
    monkeypatch.setenv('OPENAI_REASONING_EFFORT', 'secret')
    assert v.provider_version() == ':verifier-openai:invalid:reasoning-invalid'


@pytest.mark.parametrize('v3,verification', [('0', 'true'), ('1', 'false')])
def test_openai_cannot_be_selected_with_a_disabled_verification_pipeline(monkeypatch, v3, verification):
    monkeypatch.setenv('EVIDENCE_PIPELINE_V3', v3)
    monkeypatch.setenv('EVIDENCE_VERIFICATION_ENABLED', verification)
    dependencies.get_pipeline_orchestrator.cache_clear()
    try:
        with pytest.raises(PipelineComponentError) as error:
            dependencies.get_pipeline_orchestrator()
        assert error.value.error_code == 'OPENAI_CONFIGURATION_INVALID'
    finally:
        dependencies.get_pipeline_orchestrator.cache_clear()


def test_shared_request_budget_stops_waiting_without_fallback(monkeypatch):
    calls = []
    async def handler(request):
        calls.append(request)
        await asyncio.sleep(.1)
        return httpx.Response(200, json=response())
    client_type = httpx.AsyncClient
    monkeypatch.setattr(v.httpx, 'AsyncClient', lambda **kwargs:
        client_type(**kwargs, transport=httpx.MockTransport(handler)))
    started = time.perf_counter()
    with request_budget(.01), pytest.raises(PipelineComponentError) as error:
        asyncio.run(v.judge(*inputs()))
    assert error.value.error_code == 'OPENAI_ASSESSMENT_TIMEOUT'
    assert time.perf_counter() - started < 1
    assert len(calls) <= 1
