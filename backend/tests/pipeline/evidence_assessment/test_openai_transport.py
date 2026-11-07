"""Offline recovery tests for cold connections and transient provider failures."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json

import httpx
import pytest

from app.pipeline.evidence_assessment import openai_transport as transport
from app.pipeline.shared.models import RetrievalTrace


KEY = 'PRIVATE_API_KEY_NEVER_LOG'
CLAIM = 'PRIVATE_CLAIM_NEVER_LOG'
PAYLOAD = {'model': 'test-model', 'store': False, 'input': CLAIM}
COMPLETED = {'status': 'completed', 'error': None, 'output': []}


@pytest.fixture
def sleeps(monkeypatch):
    waits = []

    async def record_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(transport, '_sleep', record_sleep)
    monkeypatch.setattr(transport.random, 'uniform', lambda *_: 0.0)
    return waits


def setup_call(responses, *, payload=None, budget=180, reserve_retry=None):
    requests, trace = [], RetrievalTrace()

    def handler(request):
        requests.append(request)
        assert len(requests) <= len(responses), 'Unexpected additional provider request'
        item = responses[len(requests) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    async def invoke():
        async with httpx.AsyncClient(base_url='https://api.openai.com',
                headers={'Authorization': f'Bearer {KEY}'},
                transport=httpx.MockTransport(handler)) as client:
            return await transport.post_with_retries(client,
                deepcopy(PAYLOAD if payload is None else payload),
                deadline=asyncio.get_running_loop().time() + budget,
                phase='research_response', trace=trace, reserve_retry=reserve_retry)

    return requests, trace, lambda: asyncio.run(invoke())


def events(trace):
    return [row for row in trace.decisions if row.get('decision') == 'openai_transport']


def test_transient_service_failure_recovers_within_same_request(sleeps):
    requests, trace, invoke = setup_call([
        httpx.Response(503, json={'error': {'code': 'server_is_overloaded',
                                         'type': 'service_unavailable_error'}}),
        httpx.Response(200, json=COMPLETED),
    ])
    assert invoke().status_code == 200
    assert len(requests) == 2 and len(sleeps) == 1
    assert [row['outcome'] for row in events(trace)] == ['retry', 'success']
    assert int(events(trace)[0]['http_status']) == 503
    assert all(request.url.path == '/v1/responses' for request in requests)


@pytest.mark.parametrize('error_class', [httpx.ConnectError, httpx.ConnectTimeout])
def test_first_connection_failure_is_retried_without_reserving_search_work(sleeps, error_class):
    reservations = []

    def reserve(payload):
        reservations.append(payload)
        return payload

    requests, trace, invoke = setup_call([
        error_class('PRIVATE_NETWORK_DETAIL'), httpx.Response(200, json=COMPLETED),
    ], reserve_retry=reserve)
    assert invoke().status_code == 200
    assert len(requests) == 2 and reservations == []
    assert events(trace)[0]['exception_type'] == error_class.__name__
    assert requests[0].extensions['timeout']['connect'] == transport.CONNECT_SECONDS
    assert 5 < transport.CONNECT_SECONDS <= 20


@pytest.mark.parametrize('status,code,error_type', [
    (400, 'invalid_json_schema', 'invalid_request_error'),
    (400, 'context_length_exceeded', 'invalid_request_error'),
    (401, 'invalid_api_key', 'authentication_error'),
    (403, None, 'permission_error'),
    (429, 'insufficient_quota', 'insufficient_quota'),
    (429, 'billing_hard_limit_reached', 'insufficient_quota'),
    (429, 'project_spend_limit_exceeded', 'insufficient_quota'),
    (429, 'organization_spend_limit_exceeded', 'insufficient_quota'),
    (429, 'organization_usage_limit_exceeded', 'insufficient_quota'),
    (429, 'unrecognised_billing_code', 'insufficient_quota'),
])
def test_permanent_request_and_billing_errors_are_not_retried(sleeps, status, code, error_type):
    response = httpx.Response(status, json={'error': {
        'code': code, 'type': error_type, 'message': 'PRIVATE_PROVIDER_MESSAGE'}})
    requests, trace, invoke = setup_call([response])
    assert invoke().status_code == status
    assert len(requests) == 1 and sleeps == []
    assert events(trace)[0]['outcome'] == 'failed'
    assert events(trace)[0]['stop_reason'] == 'non_retryable'


@pytest.mark.parametrize('status', [408, 409, 429, 500, 502, 503, 504])
def test_transient_http_statuses_allow_a_bounded_retry(sleeps, status):
    requests, _, invoke = setup_call([
        httpx.Response(status, json={'error': {'code': 'rate_limit_exceeded' if status == 429 else None}}),
        httpx.Response(200, json=COMPLETED),
    ])
    assert invoke().status_code == 200
    assert len(requests) == 2


@pytest.mark.parametrize('headers,minimum', [
    ({'Retry-After': '3'}, 3),
    ({'retry-after-ms': '3500'}, 3.5),
])
def test_rate_limit_respects_server_retry_delay(sleeps, headers, minimum):
    requests, _, invoke = setup_call([
        httpx.Response(429, headers=headers, json={'error': {'code': 'rate_limit_exceeded'}}),
        httpx.Response(200, json=COMPLETED),
    ])
    assert invoke().status_code == 200
    assert len(requests) == 2 and len(sleeps) == 1
    assert sleeps[0] >= minimum


def test_retry_after_http_date_is_respected(sleeps):
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=8)
    requests, _, invoke = setup_call([
        httpx.Response(429, headers={'Retry-After': format_datetime(retry_at, usegmt=True)},
                       json={'error': {'code': 'rate_limit_exceeded'}}),
        httpx.Response(200, json=COMPLETED),
    ])
    assert invoke().status_code == 200 and len(requests) == 2
    assert 6 <= sleeps[0] <= 9


@pytest.mark.parametrize('budget,retry_after', [(10, '1'), (40, '35')])
def test_retry_does_not_extend_total_deadline(sleeps, budget, retry_after):
    requests, trace, invoke = setup_call([
        httpx.Response(503, headers={'Retry-After': retry_after}, json={'error': {}}),
    ], budget=budget)
    assert invoke().status_code == 503
    assert len(requests) == 1 and sleeps == []
    assert events(trace)[-1]['stop_reason'] == 'deadline'


def test_attempt_cap_prevents_unbounded_retries(sleeps):
    requests, trace, invoke = setup_call([
        httpx.Response(503, json={'error': {}}) for _ in range(3)
    ])
    assert invoke().status_code == 503
    assert len(requests) == transport.MAX_ATTEMPTS == 3
    assert len(sleeps) == 2
    assert events(trace)[-1]['stop_reason'] == 'attempt_limit'


def test_server_failure_inside_http_success_can_recover(sleeps):
    requests, trace, invoke = setup_call([
        httpx.Response(200, json={'status': 'failed', 'error': {'code': 'server_error'}}),
        httpx.Response(200, json=COMPLETED),
    ])
    assert invoke().json()['status'] == 'completed'
    assert len(requests) == 2
    assert events(trace)[0]['outcome'] == 'retry'


def test_cancelled_analysis_does_not_retry_or_swallow_cancellation(sleeps):
    requests = []

    async def handler(request):
        requests.append(request)
        raise asyncio.CancelledError()

    async def invoke():
        async with httpx.AsyncClient(base_url='https://api.openai.com',
                transport=httpx.MockTransport(handler)) as client:
            await transport.post_with_retries(client, PAYLOAD,
                deadline=asyncio.get_running_loop().time() + 180,
                phase='assessment_response')

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(invoke())
    assert len(requests) == 1 and sleeps == []


def test_html_service_error_is_not_misclassified_as_json_validation(sleeps):
    requests, trace, invoke = setup_call([
        httpx.Response(502, text='<html>PRIVATE_PROXY_DETAIL</html>'),
        httpx.Response(200, json=COMPLETED),
    ])
    assert invoke().status_code == 200
    assert len(requests) == 2
    assert int(events(trace)[0]['http_status']) == 502


def test_ambiguous_research_failure_reserves_previous_search_grant(sleeps):
    reserved = []
    payload = {**PAYLOAD, 'tools': [{'type': 'web_search'}], 'max_tool_calls': 10}

    def reserve(previous):
        reserved.append(previous['max_tool_calls'])
        return {**previous, 'max_tool_calls': 2}

    requests, _, invoke = setup_call([
        httpx.Response(503, json={'error': {}}),
        httpx.Response(200, json=COMPLETED),
    ], payload=payload, reserve_retry=reserve)
    assert invoke().status_code == 200
    assert reserved == [10]
    assert [json.loads(req.content)['max_tool_calls'] for req in requests] == [10, 2]
    assert payload['max_tool_calls'] == 10


def test_exhausted_search_reservation_stops_retry(sleeps):
    requests, trace, invoke = setup_call([
        httpx.Response(503, json={'error': {}}),
    ], reserve_retry=lambda _: None)
    assert invoke().status_code == 503
    assert len(requests) == 1 and sleeps == []
    assert events(trace)[-1]['stop_reason'] == 'search_budget'


def test_rate_limit_rejection_does_not_consume_search_reservation(sleeps):
    reservations = []

    def reserve(payload):
        reservations.append(payload)
        return None

    requests, _, invoke = setup_call([
        httpx.Response(429, json={'error': {'code': 'rate_limit_exceeded'}}),
        httpx.Response(200, json=COMPLETED),
    ], reserve_retry=reserve)
    assert invoke().status_code == 200
    assert len(requests) == 2 and reservations == []


def test_read_timeout_preserves_failure_when_search_budget_prevents_replay(sleeps):
    reservations = []

    def reserve(payload):
        reservations.append(payload)
        return None

    requests, trace, invoke = setup_call([
        httpx.ReadTimeout('PRIVATE_TIMEOUT_DETAIL'),
    ], reserve_retry=reserve)
    with pytest.raises(httpx.ReadTimeout):
        invoke()
    assert len(requests) == len(reservations) == 1
    assert events(trace)[-1]['stop_reason'] == 'search_budget'


def test_diagnostics_keep_safe_metadata_without_credentials_content_or_raw_errors(sleeps, caplog):
    requests, trace, invoke = setup_call([
        httpx.Response(400, headers={'x-request-id': 'req_known-safe-id'}, json={'error': {
            'code': 'PRIVATE_ERROR_CODE', 'type': 'PRIVATE_ERROR_TYPE',
            'message': 'PRIVATE_PROVIDER_MESSAGE ' + KEY + CLAIM,
            'param': 'PRIVATE_ERROR_PARAMETER'}, 'debug': 'PRIVATE_PROVIDER_PAYLOAD'}),
    ])
    assert invoke().status_code == 400 and len(requests) == 1
    row = events(trace)[0]
    assert int(row['http_status']) == 400
    assert row['request_id'] == 'req_known-safe-id'
    assert row.get('error_code') in (None, 'other')
    assert row.get('error_type') in (None, 'other')
    exposed = json.dumps(trace.model_dump(), default=str) + caplog.text
    assert 'PRIVATE_' not in exposed


def test_invalid_success_body_is_returned_for_existing_contract_validation(sleeps):
    response = httpx.Response(200, text='not-json')
    requests, _, invoke = setup_call([response])
    assert invoke().text == 'not-json'
    assert len(requests) == 1 and sleeps == []
