"""Native citations, scoped assessment decisions, deterministic presentation and bounds."""
import asyncio
from copy import deepcopy
from datetime import date
import json

import httpx
import pytest

from app.pipeline.evidence_assessment import openai_research as research
from app.pipeline.evidence_assessment import openai_transport as transport
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import RetrievalTrace
from app.pipeline.shared.runtime_budget import request_budget


KEY = 'private-test-key-never-print'
CLAIM = 'The community museum is free to enter.'
URL = 'https://example.gov.sg/museum'
TODAY = date(2026, 11, 3)


def message(text, annotations=None):
    return {'type': 'message', 'status': 'completed', 'role': 'assistant',
        'content': [{'type': 'output_text', 'text': text, 'annotations': annotations or []}]}


def search_response(verdict='false', *, citations=True, sources=True, url=URL,
        report='Admission costs ten dollars.'):
    header = f'VERDICT: {verdict}\n\n' if verdict is not None else ''
    text = f'{header}{report} \ue200cite\ue202turn0search0\ue201'
    start = text.index('\ue200')
    annotation = {'type': 'url_citation', 'url': url, 'title': 'Official museum admission',
        'start_index': start, 'end_index': len(text)}
    action = {'type': 'search', 'queries': ['official museum admission fee']}
    if sources:
        action['sources'] = [{'type': 'url', 'url': url}]
    return {'status': 'completed', 'error': None, 'output': [
        {'type': 'reasoning', 'summary': []},
        {'type': 'web_search_call', 'status': 'completed', 'action': action},
        message(text, [annotation] if citations else []),
    ], 'usage': {'input_tokens': 30, 'output_tokens': 50, 'total_tokens': 80,
        'output_tokens_details': {'reasoning_tokens': 20}},
        'tool_usage': {'web_search': {'num_requests': 1}}}


def draft(verdict='false', *, ids=None, status='contradicted', basis='direct'):
    return {'verdict': verdict, 'summary': 'The official admission page says visitors pay ten dollars.',
        'findings': [{'claim': CLAIM, 'status': status, 'explanation': 'The official page states an admission fee.',
            'source_ids': ['c1'] if ids is None else ids, 'material': True, 'basis': basis,
            'scope': {'claim_scope': 'Current admission for visitors to this community museum.',
                'evidence_scope': 'Current admission for visitors to this community museum.',
                'applicability': 'qualified' if basis == 'bounded_inference' else 'exact',
                'reason': 'The evidence concerns the same museum, visitors and assessment date.'},
            'limitations': ['The assessment concerns the current published admission fee.']}],
        'limitations': ['The assessment concerns the current published admission fee.'],
        'recommended_action': 'Read the official admission page before sharing.'}


def assessment_response(value=None):
    return {'status': 'completed', 'error': None, 'output': [message(json.dumps(value or draft()))],
        'usage': {'input_tokens': 40, 'output_tokens': 60, 'total_tokens': 100}}


def run(monkeypatch, responses, *, trace=None, claim=CLAIM):
    requests = []
    def handler(request):
        requests.append(request)
        result = responses[len(requests) - 1]
        if isinstance(result, Exception):
            raise result
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json=result)
    original = httpx.AsyncClient
    monkeypatch.setenv('OPENAI_API_KEY', KEY)
    monkeypatch.setenv('OPENAI_ASSESSMENT_MODEL', 'gpt-6.1-sol')
    monkeypatch.setenv('OPENAI_REASONING_EFFORT', 'medium')
    monkeypatch.setattr(research.httpx, 'AsyncClient', lambda **kwargs:
        original(**kwargs, transport=httpx.MockTransport(handler)))
    async def no_wait(seconds):
        pass
    monkeypatch.setattr(transport, '_sleep', no_wait)
    return requests, lambda: asyncio.run(research.research_claim(claim, as_of=TODAY, trace=trace))


def test_research_and_assessment_preserve_claim_and_bind_native_citations(monkeypatch):
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response(), assessment_response()], trace=trace)
    result = invoke()
    assert result.verdict == 'false'
    assert result.as_of == TODAY
    assert result.model == 'gpt-6.1-sol'
    assert len(result.sources) == 1
    assert result.sources[0].id == 'c1'
    assert str(result.sources[0].url) == URL
    assert result.findings[0].source_ids == ['c1']
    assert '[c1]' in result.research_text and '\ue200' not in result.research_text
    assert len(requests) == 2
    first, second = [json.loads(request.content) for request in requests]
    assert all(request.headers['Authorization'] == f'Bearer {KEY}' for request in requests)
    assert all(KEY not in request.content.decode() for request in requests)
    assert first['store'] is second['store'] is False
    assert first['tool_choice'] == 'required'
    assert first['max_tool_calls'] == 10 and first['max_output_tokens'] == 6000
    assert first['include'] == ['web_search_call.action.sources']
    assert first['tools'][0]['type'] == 'web_search'
    assert first['tools'][0]['user_location']['timezone'] == 'Asia/Singapore'
    assert json.loads(first['input'][0]['content'])['original_claim'] == CLAIM
    assert second['max_output_tokens'] == 4000 and 'tools' not in second
    assert 'previous_response_id' not in second
    assert second['text']['format']['strict'] is True
    context = json.loads(second['input'][0]['content'])
    assert context['native_citation_sources'][0]['id'] == 'c1'
    assert 'Do not search' in second['instructions']
    assert all('temperature' not in item for item in [first, second])
    usage = [d for d in trace.decisions if d['decision'] == 'openai_web_research_usage']
    assert len(usage) == 2 and usage[0]['billable_search_requests'] == '1'
    assert sum(int(d['total_tokens']) for d in usage) == 180
    assert trace.search_requests == 1
    assert KEY not in json.dumps(trace.model_dump())


def test_search_counter_excludes_page_actions_and_preserves_existing_count(monkeypatch):
    body = search_response()
    body['output'][2:2] = [
        {'type': 'web_search_call', 'status': 'completed',
         'action': {'type': 'open_page', 'url': URL}},
        {'type': 'web_search_call', 'status': 'completed',
         'action': {'type': 'find_in_page', 'url': URL, 'pattern': 'admission'}},
        {'type': 'web_search_call', 'status': 'completed',
         'action': {'type': 'search', 'queries': ['current museum admission', 'museum admission exemptions'],
                    'sources': [{'type': 'url', 'url': URL}]}},
    ]
    body['tool_usage']['web_search']['num_requests'] = 3
    trace = RetrievalTrace(search_requests=2)
    _, invoke = run(monkeypatch, [body, assessment_response()], trace=trace)
    invoke()
    assert trace.search_requests == 4
    completed = next(item for item in trace.decisions if item['decision'] == 'web_search_completed')
    assert completed['search_count'] == '2' and completed['count'] == '4'
    usage = next(item for item in trace.decisions if item['decision'] == 'openai_web_research_usage')
    assert usage['billable_search_requests'] == '3'


def test_initial_research_receives_its_numeric_shared_web_action_budget(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response(None), assessment_response()])
    assert invoke().verdict == 'false' and len(requests) == 2
    payload = json.loads(requests[0].content)
    assert payload['max_tool_calls'] == 10
    assert payload['instructions'].startswith(research.RESEARCH_INSTRUCTIONS)
    assert 'at most 10 web tool actions left' in payload['instructions']
    assert 'including searches, page opens and find-in-page actions' in payload['instructions']
    assert 'Do not request another action after using this budget.' in payload['instructions']


def test_expanded_budget_is_a_ceiling_not_a_required_search_count(monkeypatch):
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response(), assessment_response()], trace=trace)
    assert invoke().verdict == 'false'
    assert len(requests) == 2 and trace.search_requests == 1
    tools = [item for item in trace.decisions if item['decision'] == 'openai_web_research_tool_usage']
    assert len(tools) == 1 and tools[0]['total_tool_actions'] == '1'
    assert json.loads(requests[0].content)['max_tool_calls'] == 10


def test_longer_provider_read_timeout_keeps_connect_and_total_deadlines_bounded(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response(), assessment_response()])
    invoke()
    assert requests[0].extensions['timeout']['read'] == 120
    assert requests[0].extensions['timeout']['connect'] == 15
    assert research.TOTAL_SECONDS == 180


@pytest.mark.parametrize('invalid_count', [True, -1, '3', None])
def test_invalid_provider_billing_count_is_not_invented_from_search_actions(monkeypatch, invalid_count):
    body = search_response()
    body['tool_usage']['web_search']['num_requests'] = invalid_count
    trace = RetrievalTrace()
    _, invoke = run(monkeypatch, [body, assessment_response()], trace=trace)
    invoke()
    usage = next(item for item in trace.decisions if item['decision'] == 'openai_web_research_usage')
    assert 'billable_search_requests' not in usage
    assert trace.search_requests == 1


@pytest.mark.parametrize('verdict', ['insufficient_evidence', 'not_checkable'])
def test_successful_search_without_citations_can_report_no_evidence(monkeypatch, verdict):
    value = draft(verdict, ids=[], status='unresolved', basis='unresolved')
    requests, invoke = run(monkeypatch, [search_response(verdict, citations=False), assessment_response(value)])
    result = invoke()
    assert result.verdict == verdict and result.sources == []
    assert len(requests) == 2


def test_decisive_assessment_cannot_invent_sources(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response(citations=False), assessment_response()])
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_UNCITED' and len(requests) == 2


def test_assessment_must_use_known_native_source_ids(monkeypatch):
    invalid = assessment_response(draft(ids=['c2']))
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response(), invalid, invalid], trace=trace)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 3
    failures = [item for item in trace.decisions if item['decision'] == 'openai_web_research_failure']
    assert len(failures) == 2 and all(item['phase'] == 'source_binding' for item in failures)
    assert 'research_unknown_source_ids' in failures[0]['validation_issues']


def test_archived_research_header_is_provisional_not_an_assessment_lock(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response('likely_false'), assessment_response(draft('false'))])
    result = invoke()
    assert result.verdict == 'false' and len(requests) == 2
    assert result.findings[0].status == 'contradicted' and result.findings[0].basis == 'direct'
    context = json.loads(json.loads(requests[1].content)['input'][0]['content'])
    assert context['research_evidence'].startswith('VERDICT: likely_false')
    assert 'expected_verdict' not in context


def test_native_research_does_not_need_an_overall_verdict_header(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response(None), assessment_response()])
    result = invoke()
    assert result.verdict == 'false' and len(requests) == 2
    assert not result.research_text.startswith('VERDICT:')
    assert 'Admission costs ten dollars.' in result.research_text


def test_malformed_legacy_header_does_not_decide_the_final_assessment(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response('PRIVATE_UNKNOWN_LABEL'), assessment_response()])
    result = invoke()
    assert result.verdict == 'false' and len(requests) == 2


def test_citations_not_in_supplied_search_metadata_are_rejected():
    body = search_response()
    body['output'][1]['action']['sources'][0]['url'] = 'https://example.gov.sg/unrelated'
    with pytest.raises(PipelineComponentError) as error:
        research._research_report(body)
    assert error.value.error_code == 'OPENAI_CITATION_UNVERIFIED'
    assert error.value.diagnostic_reason == 'citation_provenance_mismatch'


def test_native_annotations_work_when_provider_omits_search_source_list(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response(sources=False), assessment_response()])
    assert str(invoke().sources[0].url) == URL


def test_opened_url_can_bind_native_citation(monkeypatch):
    body = search_response()
    body['output'][1]['action']['sources'] = []
    body['output'].insert(2, {'type': 'web_search_call', 'status': 'completed',
        'action': {'type': 'open_page', 'url': URL}})
    requests, invoke = run(monkeypatch, [body, assessment_response()])
    assert str(invoke().sources[0].url) == URL


@pytest.mark.parametrize('url', [
    'http://localhost/x', 'http://127.0.0.1/x', 'http://10.0.0.1/x', 'http://169.254.169.254/x',
    'http://[::1]/x', 'http://192.168.1.1/x', 'https://example.gov.sg:8000/x',
    'file:///secrets', 'javascript:alert(1)', 'https://user:secret@example.gov.sg/x',
    'https://example.gov.sg\\@localhost/x', 'https://example.gov.sg\n/x',
    'http://2130706433/x', 'http://127.1/x', 'http://service.local/x', 'http://host.internal/x',
    'http://127.0.0.1/museum?utm_source=openai',
    'https://user:secret@example.gov.sg/museum?utm_source=openai',
    'https://example.gov.sg:8000/museum?utm_source=openai',
])
def test_unsafe_native_citation_is_never_exposed_or_requested(monkeypatch, url):
    body = search_response()
    body['output'][1]['action']['sources'][0]['url'] = url
    body['output'][2]['content'][0]['annotations'][0]['url'] = url
    requests, invoke = run(monkeypatch, [body])
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert len(requests) == 1
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID'
    assert url not in str(error.value)
    assert str(requests[0].url) == 'https://api.openai.com/v1/responses'


@pytest.mark.parametrize('mutation,code', [
    ('missing_search', 'OPENAI_SEARCH_NOT_PERFORMED'),
    ('failed_search', 'OPENAI_SEARCH_FAILED'),
    ('incomplete', 'OPENAI_RESPONSE_INCOMPLETE'),
    ('refusal', 'OPENAI_ASSESSMENT_REFUSED'),
    ('bad_offsets', 'OPENAI_RESEARCH_INVALID'),
    ('empty_report', 'OPENAI_RESEARCH_INVALID'),
    ('bad_source_metadata', 'OPENAI_RESEARCH_INVALID'),
    ('tool_budget', 'OPENAI_RESEARCH_INVALID'),
])
def test_provider_defects_do_not_become_claim_verdicts(monkeypatch, mutation, code):
    body = search_response()
    if mutation == 'missing_search':
        body['output'].pop(1)
    elif mutation == 'failed_search':
        body['output'][1]['status'] = 'failed'
    elif mutation == 'incomplete':
        body['status'] = 'incomplete'
    elif mutation == 'refusal':
        body['output'][2]['content'] = [{'type': 'refusal', 'refusal': 'PRIVATE_PROVIDER_TEXT'}]
    elif mutation == 'bad_offsets':
        body['output'][2]['content'][0]['annotations'][0]['start_index'] = -1
    elif mutation == 'bad_source_metadata':
        body['output'][1]['action']['sources'] = {'url': URL}
    elif mutation == 'tool_budget':
        body['output'][2:2] = [deepcopy(body['output'][1]) for _ in range(10)]
    else:
        body['output'][2]['content'][0]['text'] = '   '
        body['output'][2]['content'][0]['annotations'] = []
    requests, invoke = run(monkeypatch, [body])
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == code and len(requests) == 1
    assert 'PRIVATE_PROVIDER_TEXT' not in str(error.value)


@pytest.mark.parametrize('status,api_code,expected', [
    (401, None, 'OPENAI_ACCESS_DENIED'), (403, None, 'OPENAI_ACCESS_DENIED'),
    (429, None, 'OPENAI_RATE_LIMITED'), (503, None, 'OPENAI_UNAVAILABLE'),
    (400, 'invalid_json_schema', 'OPENAI_SCHEMA_INVALID'),
    (404, 'model_not_found', 'OPENAI_MODEL_UNAVAILABLE'),
    (400, None, 'OPENAI_REQUEST_REJECTED'),
    (429, 'insufficient_quota', 'OPENAI_QUOTA_EXCEEDED'),
    (408, None, 'OPENAI_UNAVAILABLE'), (409, None, 'OPENAI_UNAVAILABLE'),
])
def test_http_failures_are_safe_and_never_trigger_fallback(monkeypatch, status, api_code, expected):
    response = httpx.Response(status, json={'error': {'code': api_code,
        'message': KEY + ' PRIVATE_PROVIDER_ERROR'}})
    attempts = 3 if status == 429 and api_code is None else 2 if status in {408, 409, 503} else 1
    requests, invoke = run(monkeypatch, [response] * attempts)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == expected and len(requests) == attempts
    assert KEY not in str(error.value) and 'PRIVATE_PROVIDER_ERROR' not in str(error.value)


def test_missing_key_is_rejected_before_network(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(PipelineComponentError) as error:
        asyncio.run(research.research_claim(CLAIM, as_of=TODAY))
    assert error.value.error_code == 'OPENAI_NOT_CONFIGURED'


def test_first_connection_failure_recovers_without_reducing_search_budget(monkeypatch):
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [httpx.ConnectTimeout('PRIVATE_CONNECTION'),
        search_response(), assessment_response()], trace=trace)
    assert invoke().verdict == 'false'
    payloads = [json.loads(request.content) for request in requests]
    assert len(requests) == 3 and payloads[0] == payloads[1]
    assert payloads[1]['max_tool_calls'] == 10
    assert not any(item['decision'] == 'openai_web_research_retry_reservation' for item in trace.decisions)
    events = [item for item in trace.decisions if item['decision'] == 'openai_transport']
    assert [item['outcome'] for item in events] == ['retry', 'success', 'success']
    assert events[0]['exception_type'] == 'ConnectTimeout'
    assert 'PRIVATE_CONNECTION' not in trace.model_dump_json()


def test_assessment_service_retry_keeps_completed_research(monkeypatch):
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response(),
        httpx.Response(503, json={'error': {'code': 'server_is_overloaded'}}),
        assessment_response()], trace=trace)
    assert invoke().verdict == 'false'
    payloads = [json.loads(request.content) for request in requests]
    assert len(requests) == 3 and payloads[1] == payloads[2]
    assert sum(bool(payload.get('tools')) for payload in payloads) == 1
    assert trace.search_requests == 1
    events = [item for item in trace.decisions if item['decision'] == 'openai_transport']
    assert events[1]['phase'] == events[2]['phase'] == 'assessment_response'
    assert events[1]['http_status'] == '503' and events[2]['attempt'] == '2'


def test_ambiguous_research_failure_reserves_unobserved_tool_work(monkeypatch):
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [httpx.Response(502, text='PRIVATE_GATEWAY'),
        search_response(), assessment_response()], trace=trace)
    assert invoke().verdict == 'false'
    payloads = [json.loads(request.content) for request in requests]
    assert [payload['max_tool_calls'] for payload in payloads if 'tools' in payload] == [10, 2]
    assert 'at most 2 web tool actions' in payloads[1]['instructions']
    usage = next(item for item in trace.decisions if item['decision'] == 'openai_web_research_tool_usage')
    assert usage['reserved_tool_actions'] == '10' and usage['granted_tool_actions'] == '2'
    assert trace.search_requests == 1


def test_research_retry_cannot_exceed_its_reduced_tool_grant(monkeypatch):
    oversized = search_response()
    oversized['output'][2:2] = [deepcopy(oversized['output'][1]) for _ in range(2)]
    requests, invoke = run(monkeypatch, [httpx.Response(503), oversized])
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 2


def test_failed_research_and_citation_recovery_share_reserved_budget(monkeypatch):
    requests, invoke = run(monkeypatch, [httpx.Response(503), mismatched_response(),
        search_response(), assessment_response()])
    assert invoke().verdict == 'false'
    research_calls = [json.loads(request.content) for request in requests if 'tools' in json.loads(request.content)]
    assert [payload['max_tool_calls'] for payload in research_calls] == [10, 2, 1]
    # The failed first request reserved ten actions; the two successful requests
    # actually used one each. Overlapping grants are not extra executed actions.


def test_network_failure_retries_stay_within_original_deadline(monkeypatch):
    requests, invoke = run(monkeypatch, [httpx.ConnectError('PRIVATE_CONNECTION')])
    with request_budget(10), pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_UNAVAILABLE' and len(requests) == 1


@pytest.mark.parametrize('provider_code,expected,retryable,attempts', [
    ('rate_limit_exceeded', 'OPENAI_RATE_LIMITED', True, 3),
    ('slow_down', 'OPENAI_RATE_LIMITED', True, 3),
    ('insufficient_quota', 'OPENAI_QUOTA_EXCEEDED', False, 1),
    ('server_error', 'OPENAI_UNAVAILABLE', True, 3),
])
def test_failed_response_envelopes_preserve_operational_error(monkeypatch, provider_code, expected, retryable, attempts):
    failed = {'status': 'failed', 'error': {'code': provider_code, 'message': 'PRIVATE_PROVIDER_MESSAGE'}}
    requests, invoke = run(monkeypatch, [search_response()] + [failed] * attempts)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == expected and error.value.retryable is retryable
    assert len(requests) == 1 + attempts and 'PRIVATE_PROVIDER_MESSAGE' not in str(error.value)


def test_shared_budget_is_respected(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response(), assessment_response()])
    original_post = research._post
    async def slow(client, payload, **kwargs):
        await asyncio.sleep(.05)
        return await original_post(client, payload, **kwargs)
    monkeypatch.setattr(research, '_post', slow)
    with request_budget(.001):
        with pytest.raises(PipelineComponentError) as error:
            invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_TIMEOUT'
    assert requests == []


def test_duplicate_native_citations_bind_one_source_without_dropping_prose():
    body = search_response()
    block = body['output'][2]['content'][0]
    block['annotations'].append(deepcopy(block['annotations'][0]))
    text, sources, actions = research._research_report(body)
    assert len(sources) == 1 and text.count('[c1]') == 1
    assert 'Admission costs ten dollars.' in text


def test_metadata_citing_prose_retains_text():
    body = search_response()
    block = body['output'][2]['content'][0]
    block['annotations'][0].update(start_index=block['text'].index('Admission'),
        end_index=block['text'].index('\ue200'))
    text, sources, _ = research._research_report(body)
    assert 'Admission costs ten dollars.' in text and '[c1]' in text


@pytest.mark.parametrize('header', ['VERDICT: false', '**VERDICT: false**',
    '**VERDICT:** false', 'VERDICT: **false**'])
def test_harmless_bold_verdict_header_is_canonicalised(header):
    body = search_response()
    block = body['output'][2]['content'][0]
    block['text'] = block['text'].replace('VERDICT: false', header)
    block['annotations'][0].update(start_index=block['text'].index('\ue200'), end_index=len(block['text']))
    report, sources, _ = research._research_report(body)
    assert report.startswith('VERDICT: false\n') and len(sources) == 1


@pytest.mark.parametrize('span_kind', ['identical', 'nested', 'partial', 'marker_interior'])
def test_overlapping_native_annotations_preserve_prose_and_each_source(span_kind):
    body = search_response()
    block = body['output'][2]['content'][0]
    text = block['text']
    url2 = 'https://example.gov.sg/admission-announcement'
    body['output'][1]['action']['sources'].append({'type': 'url', 'url': url2})
    start = text.index('Admission')
    first_end = text.index('dollars') + len('dollars')
    first = dict(block['annotations'][0], start_index=start, end_index=first_end)
    if span_kind == 'identical':
        second_start, second_end = start, first_end
    elif span_kind == 'nested':
        second_start, second_end = start + 3, first_end - 3
    elif span_kind == 'partial':
        second_start, second_end = start + 10, len(text)
    else:
        second_start, second_end = first_end - 2, text.index('\ue200') + 4
    second = dict(first, url=url2, title='Official announcement',
        start_index=second_start, end_index=second_end)
    block['annotations'] = [first, second]
    report, sources, _ = research._research_report(body)
    assert [source.id for source in sources] == ['c1', 'c2']
    assert 'c1' in report and 'c2' in report and '\ue200' not in report
    # Remove only our inserted references: every original prose character remains.
    import re
    prose = re.sub(r' ?\[c\d+(?:, c\d+)*\]', '', report)
    assert 'Admission costs ten dollars.' in prose


def test_structural_assessment_review_reuses_evidence_and_sources_without_extra_search(monkeypatch, caplog):
    invalid = draft()
    invalid['PRIVATE_FIELD_KEY'] = {'nested': KEY + ' PRIVATE_PROVIDER_TEXT'}
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response(), assessment_response(invalid), assessment_response()], trace=trace)
    result = invoke()
    assert result.verdict == 'false' and len(requests) == 3
    payloads = [json.loads(request.content) for request in requests]
    before, repaired = [json.loads(payload['input'][0]['content']) for payload in payloads[1:]]
    for field in ('original_claim', 'assessment_date', 'research_evidence', 'native_citation_sources'):
        assert repaired[field] == before[field]
    assert repaired['assessment_review']['constraints'] == [{'path': '<field>', 'type': 'extra_forbidden'}]
    assert 'expected_verdict' not in repaired['assessment_review']
    assert repaired['assessment_review']['previous_assessment']['verdict'] == 'false'
    assert all('tools' not in payload for payload in payloads[1:])
    assert all(payload['store'] is False for payload in payloads)
    assert trace.search_requests == 1
    assert 'PRIVATE_' not in requests[2].content.decode()
    assert KEY not in json.dumps(trace.model_dump()) + caplog.text
    assert 'PRIVATE_' not in json.dumps(trace.model_dump()) + caplog.text
    assert 'phase=decision_validation' in caplog.text
    assert 'demote' in payloads[2]['instructions'].lower()
    assert [item['phase'] for item in trace.decisions if item['decision'] == 'openai_web_research_usage'] == [
        'research', 'assessment', 'assessment_review']


def test_unresolved_basis_repair_does_not_change_the_findings_direction(monkeypatch):
    valid = draft('insufficient_evidence', ids=[], status='unresolved', basis='unresolved')
    invalid = deepcopy(valid)
    invalid['findings'][0]['basis'] = 'direct'
    requests, invoke = run(monkeypatch, [search_response('insufficient_evidence', citations=False),
        assessment_response(invalid), assessment_response(valid)])
    result = invoke()
    assert result.verdict == 'insufficient_evidence'
    assert result.findings[0].status == result.findings[0].basis == 'unresolved'
    repair = json.loads(json.loads(requests[2].content)['input'][0]['content'])['assessment_review']
    assert repair['constraints'] == [{'path': 'findings.[]', 'type': 'research_unresolved_basis'}]


def test_duplicate_references_can_be_repaired_without_changing_a_true_verdict(monkeypatch):
    valid = draft('true', status='supported')
    invalid = deepcopy(valid)
    invalid['findings'][0]['source_ids'] = ['c1', 'c1']
    requests, invoke = run(monkeypatch, [search_response('true'),
        assessment_response(invalid), assessment_response(valid)])
    result = invoke()
    assert result.verdict == 'true' and result.findings[0].status == 'supported'
    assert result.findings[0].basis == 'direct' and result.findings[0].source_ids == ['c1']
    assert len(requests) == 3


def test_review_cannot_invent_a_misinformation_verdict_without_a_material_contradiction(monkeypatch):
    invalid = draft('insufficient_evidence', ids=[], status='unresolved', basis='direct')
    still_invalid = draft('likely_false', ids=[], status='unresolved', basis='unresolved')
    requests, invoke = run(monkeypatch, [search_response('insufficient_evidence'),
        assessment_response(invalid), assessment_response(still_invalid)])
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 3


def test_source_reference_repair_still_binds_only_original_native_sources(monkeypatch):
    requests, invoke = run(monkeypatch, [search_response(), assessment_response(draft(ids=['c2'])), assessment_response()])
    result = invoke()
    assert len(requests) == 3 and result.findings[0].source_ids == ['c1']
    repair = json.loads(json.loads(requests[2].content)['input'][0]['content'])['assessment_review']
    assert repair['constraints'] == [{'path': '<root>', 'type': 'research_unknown_source_ids'}]


def test_review_can_correct_an_overall_verdict_without_erasing_a_material_contradiction(monkeypatch):
    invalid = draft('insufficient_evidence', basis='bounded_inference')
    corrected = deepcopy(invalid)
    corrected['verdict'] = 'likely_false'
    requests, invoke = run(monkeypatch, [search_response('insufficient_evidence'),
        assessment_response(invalid), assessment_response(corrected)])
    result = invoke()
    assert result.verdict == 'likely_false' and len(requests) == 3
    assert result.findings[0].status == 'contradicted' and result.findings[0].basis == 'bounded_inference'
    review = json.loads(json.loads(requests[2].content)['input'][0]['content'])['assessment_review']
    assert 'expected_verdict' not in review
    assert review['constraints'] == [{'path': '<root>', 'type': 'research_unresolved_cannot_erase_contradiction'}]


def test_inconsistent_material_findings_still_fail_after_one_assessment_review(monkeypatch, caplog):
    invalid = draft('true', ids=['c1'], status='unresolved', basis='unresolved')
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response('true'),
        assessment_response(invalid), assessment_response(invalid)], trace=trace)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 3
    failures = [item for item in trace.decisions if item['decision'] == 'openai_web_research_failure']
    assert len(failures) == 2 and all(item['phase'] == 'decision_validation' for item in failures)
    assert all('research_support_incomplete' in item['validation_issues'] for item in failures)
    assert 'PRIVATE_' not in caplog.text


@pytest.mark.parametrize('failure,code', [
    ('http', 'OPENAI_UNAVAILABLE'), ('refusal', 'OPENAI_ASSESSMENT_REFUSED'),
    ('incomplete', 'OPENAI_RESPONSE_INCOMPLETE'),
])
def test_assessment_transport_or_refusal_failure_never_triggers_review(monkeypatch, failure, code):
    response = assessment_response()
    if failure == 'http':
        response = httpx.Response(503, json={'error': {'message': 'PRIVATE_PROVIDER_MESSAGE'}})
    elif failure == 'refusal':
        response['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'PRIVATE_PROVIDER_MESSAGE'}]
    else:
        response['status'] = 'incomplete'
    responses = [search_response()] + [response] * (3 if failure == 'http' else 1)
    requests, invoke = run(monkeypatch, responses)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == code and len(requests) == len(responses)


def test_assessment_review_shares_the_original_deadline(monkeypatch):
    invalid = draft(ids=['c2'])
    requests, invoke = run(monkeypatch, [search_response(), assessment_response(invalid), assessment_response()])
    original_post = research._post
    calls = 0
    async def slow_repair(client, payload, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            await asyncio.sleep(.1)
        return await original_post(client, payload, **kwargs)
    monkeypatch.setattr(research, '_post', slow_repair)
    with request_budget(.03):
        with pytest.raises(PipelineComponentError) as error:
            invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_TIMEOUT' and len(requests) == 2
    assert calls == 3 and research.TOTAL_SECONDS == 180


@pytest.mark.parametrize('failure,reason', [('offset', 'citation_offsets'), ('size', 'report_size')])
def test_parser_failure_diagnostics_have_safe_specific_reasons(monkeypatch, caplog, failure, reason):
    body = search_response()
    block = body['output'][2]['content'][0]
    if failure == 'offset':
        block['annotations'][0]['start_index'] = -1
    else:
        block['text'] = 'PRIVATE_RESPONSE_TEXT' * research.MAX_REPORT_CHARS
        block['annotations'] = []
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [body], trace=trace)
    with pytest.raises(PipelineComponentError):
        invoke()
    assert len(requests) == 1
    failure = next(item for item in trace.decisions if item['decision'] == 'openai_web_research_failure')
    assert failure['phase'] == 'research_parse' and failure['reason'] == reason
    assert trace.search_requests == 1
    assert 'PRIVATE_' not in caplog.text + json.dumps(trace.model_dump())


def mismatched_response(*, web_calls=1, empty_sources=False, report='Admission costs ten dollars.'):
    """Completed paid work whose citation does not match its recorded sources."""
    body = search_response(report=report)
    source_url = 'https://example.gov.sg/unrelated'
    body['output'][1]['action']['sources'] = ([] if empty_sources else
        [{'type': 'url', 'url': source_url}])
    body['output'][2:2] = [
        {'type': 'web_search_call', 'status': 'completed',
         'action': {'type': 'open_page', 'url': source_url}}
        for _ in range(web_calls - 1)
    ]
    return body


def test_tracking_only_native_citation_matches_metadata_and_preserves_display_url():
    tracked_url = URL + '?utm_source=openai'
    body = search_response(url=tracked_url)
    body['output'][1]['action']['sources'][0]['url'] = URL
    report, sources, _ = research._research_report(body)
    assert '[c1]' in report and len(sources) == 1
    assert str(sources[0].url) == tracked_url


def test_tracking_aliases_share_one_source_id_and_keep_the_first_citation_url():
    tracked_url = URL + '?utm_source=openai'
    body = search_response(url=tracked_url)
    body['output'][1]['action']['sources'][0]['url'] = URL
    block = body['output'][2]['content'][0]
    block['annotations'].append(dict(block['annotations'][0], url=URL))
    report, sources, _ = research._research_report(body)
    assert len(sources) == 1 and str(sources[0].url) == tracked_url
    assert report.count('[c1]') == 1 and 'c2' not in report
    assert 'Admission costs ten dollars.' in report


@pytest.mark.parametrize('metadata_url', [
    'https://example.gov.sg/unrelated',
    'https://example.gov.sg/museum/admission',
    'https://example.gov.sg/Museum',
    'https://other.gov.sg/museum',
    URL + '?article_id=99',
])
def test_unrelated_resources_cannot_become_equivalent_through_tracking_normalization(metadata_url):
    body = search_response(url=URL + '?utm_source=openai')
    body['output'][1]['action']['sources'][0]['url'] = metadata_url
    with pytest.raises(PipelineComponentError) as error:
        research._research_report(body)
    assert error.value.error_code == 'OPENAI_CITATION_UNVERIFIED'


@pytest.mark.parametrize('query', ['utm_source=chatgpt.com', 'utm_source=other',
    'utm_medium=referral', 'utm_source=openai&utm_medium=referral'])
def test_unrecognized_tracking_queries_do_not_authorize_unmatched_citations(query):
    body = search_response(url=URL + '?' + query)
    body['output'][1]['action']['sources'][0]['url'] = URL
    with pytest.raises(PipelineComponentError) as error:
        research._research_report(body)
    assert error.value.error_code == 'OPENAI_CITATION_UNVERIFIED'


@pytest.mark.parametrize('web_calls', [1, 3, 5, 10])
def test_citation_provenance_recovery_uses_only_remaining_web_action_budget(monkeypatch, web_calls):
    first = mismatched_response(web_calls=web_calls)
    # Provider billing units are diagnostics, not the web-tool action budget.
    first['tool_usage']['web_search']['num_requests'] = 42
    trace = RetrievalTrace(search_requests=7)
    requests, invoke = run(monkeypatch, [first, search_response(), assessment_response()], trace=trace)
    result = invoke()
    assert result.verdict == 'false' and len(requests) == 3
    initial, recovery, formatting = [json.loads(request.content) for request in requests]
    assert initial['max_tool_calls'] == 10
    assert recovery['max_tool_calls'] == 12 - web_calls
    assert recovery['max_output_tokens'] == 6000
    assert recovery['tool_choice'] == 'required'
    assert recovery['include'] == ['web_search_call.action.sources']
    assert recovery['tools'] == initial['tools']
    assert recovery['input'] == initial['input']
    assert 'previous_response_id' not in recovery and 'tools' not in formatting
    assert all(payload['store'] is False for payload in (initial, recovery, formatting))
    assert trace.search_requests == 9
    usage = [item for item in trace.decisions if item['decision'] == 'openai_web_research_usage']
    assert len(usage) == 3 and usage[0]['billable_search_requests'] == '42'
    assert sum(int(item['total_tokens']) for item in usage) == 260


def test_recovery_starts_fresh_and_can_research_a_different_verdict_and_source(monkeypatch):
    unverified_text = 'PRIVATE_UNVERIFIED_REPORT says an admission fee is compulsory.'
    first = mismatched_response(report=unverified_text)
    fresh_url = 'https://museum.gov.sg/free-admission'
    recovered = search_response('true', url=fresh_url, report='The museum now has free admission.')
    value = draft('true', status='supported')
    value['summary'] = 'The official current admission page says entry is free.'
    value['findings'][0]['explanation'] = 'The current admission page states that entry is free.'
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [first, recovered, assessment_response(value)], trace=trace)
    result = invoke()
    assert result.verdict == 'true' and result.findings[0].status == 'supported'
    assert [str(source.url) for source in result.sources] == [fresh_url]
    assert result.research_text.startswith('VERDICT: true\n')
    assert unverified_text not in result.research_text
    initial, recovery, formatting = [json.loads(request.content) for request in requests]
    assert recovery['input'] == initial['input']
    assert unverified_text not in requests[1].content.decode()
    assert URL not in requests[1].content.decode()
    context = json.loads(formatting['input'][0]['content'])
    assert context['research_evidence'] == result.research_text
    assert [source['url'] for source in context['native_citation_sources']] == [fresh_url]
    assert unverified_text not in requests[2].content.decode()


@pytest.mark.parametrize('empty_sources', [False, True])
def test_repeated_unverified_citation_fails_after_exactly_one_research_recovery(monkeypatch, empty_sources):
    trace = RetrievalTrace()
    bad = mismatched_response(empty_sources=empty_sources)
    requests, invoke = run(monkeypatch, [bad, deepcopy(bad)], trace=trace)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_CITATION_UNVERIFIED'
    assert len(requests) == 2 and trace.search_requests == 2
    assert all('tools' in json.loads(request.content) for request in requests)
    mismatches = [item for item in trace.decisions
        if item['decision'] == 'openai_citation_provenance_mismatch']
    assert len(mismatches) == 2


def test_explicit_empty_source_metadata_cannot_be_disabled_by_another_search():
    body = mismatched_response(empty_sources=True)
    body['output'].insert(2, {'type': 'web_search_call', 'status': 'completed',
        'action': {'type': 'search', 'queries': ['another admission search']}})
    with pytest.raises(PipelineComponentError) as error:
        research._research_report(body)
    assert error.value.error_code == 'OPENAI_CITATION_UNVERIFIED'


def test_recovery_cannot_resolve_provenance_failure_by_omitting_discovery_metadata(monkeypatch):
    requests, invoke = run(monkeypatch, [mismatched_response(), search_response(sources=False)])
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_CITATION_UNVERIFIED' and len(requests) == 2


def test_required_discovery_metadata_rejects_an_uncorroborated_native_annotation():
    with pytest.raises(PipelineComponentError) as error:
        research._research_report(search_response(sources=False), require_discovery=True)
    assert error.value.error_code == 'OPENAI_CITATION_UNVERIFIED'
    assert error.value.diagnostic_reason == 'citation_provenance_mismatch'


def test_recovery_citation_must_match_its_own_response_metadata(monkeypatch):
    first = mismatched_response()
    # The second response cites an initial discovered URL. That old discovery
    # must not authorize a citation missing from the second response's sources.
    second = search_response(url='https://example.gov.sg/unrelated')
    second['output'][1]['action']['sources'][0]['url'] = 'https://example.gov.sg/new-search-only'
    requests, invoke = run(monkeypatch, [first, second])
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_CITATION_UNVERIFIED' and len(requests) == 2


def test_full_initial_budget_keeps_two_recovery_actions_and_counts_paid_work(monkeypatch):
    body = mismatched_response(web_calls=10)
    recovered = search_response()
    recovered['output'].insert(2, {'type': 'web_search_call', 'status': 'completed',
        'action': {'type': 'open_page', 'url': URL}})
    trace = RetrievalTrace(search_requests=4)
    requests, invoke = run(monkeypatch, [body, recovered, assessment_response()], trace=trace)
    assert invoke().verdict == 'false' and len(requests) == 3
    assert json.loads(requests[0].content)['max_tool_calls'] == 10
    assert json.loads(requests[1].content)['max_tool_calls'] == 2
    assert trace.search_requests == 6
    usage = [item for item in trace.decisions if item['decision'] == 'openai_web_research_usage']
    assert len(usage) == 3 and usage[0]['total_tokens'] == '80'
    actions = [item for item in trace.decisions if item['decision'] == 'openai_web_research_tool_usage']
    assert [item['tool_actions'] for item in actions] == ['10', '2']
    assert actions[-1]['total_tool_actions'] == '12'


def test_initial_response_cannot_consume_the_reserved_recovery_budget(monkeypatch):
    body = search_response()
    body['output'][2:2] = [
        {'type': 'web_search_call', 'status': 'completed',
         'action': {'type': 'open_page', 'url': URL}}
        for _ in range(10)
    ]
    # Eleven actions are below the shared twelve-action limit, but exceed the
    # initial ten-action request. The response must not become an assessment.
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [body], trace=trace)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 1
    failure = next(item for item in trace.decisions if item['decision'] == 'openai_web_research_failure')
    assert failure['reason'] == 'search_budget'
    usage = next(item for item in trace.decisions if item['decision'] == 'openai_web_research_tool_usage')
    assert usage['total_tool_actions'] == '11'


@pytest.mark.parametrize('action_count', [12, 13])
def test_research_parser_enforces_the_shared_twelve_action_ceiling(action_count):
    body = search_response()
    body['output'][2:2] = [
        {'type': 'web_search_call', 'status': 'completed',
         'action': {'type': 'open_page', 'url': URL}}
        for _ in range(action_count - 1)
    ]
    if action_count == 12:
        report, sources, actions = research._research_report(body)
        assert report and len(sources) == 1 and len(actions) == 12
    else:
        with pytest.raises(PipelineComponentError) as error:
            research._research_report(body)
        assert error.value.error_code == 'OPENAI_RESEARCH_INVALID'
        assert error.value.diagnostic_reason == 'search_budget'


def test_recovery_does_not_start_without_twenty_seconds_left_in_shared_budget(monkeypatch):
    requests, invoke = run(monkeypatch, [mismatched_response()])
    with request_budget(19):
        with pytest.raises(PipelineComponentError):
            invoke()
    assert len(requests) == 1


def test_provenance_recovery_shares_the_original_deadline(monkeypatch):
    requests, invoke = run(monkeypatch, [mismatched_response(), search_response()])
    original_post = research._post
    calls = 0
    async def slow_recovery(client, payload, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            await asyncio.sleep(.1)
        return await original_post(client, payload, **kwargs)
    monkeypatch.setattr(research, '_post', slow_recovery)
    monkeypatch.setattr(research, 'MIN_RECOVERY_SECONDS', 0)
    with request_budget(.03):
        with pytest.raises(PipelineComponentError) as error:
            invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_TIMEOUT'
    assert len(requests) == 1 and calls == 2 and research.TOTAL_SECONDS == 180


def test_provenance_recovery_cannot_reset_the_research_stage_deadline(monkeypatch):
    requests, invoke = run(monkeypatch, [mismatched_response(), search_response()])
    original_post = research._post
    calls = 0
    async def slow_research(client, payload, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(.06)
        return await original_post(client, payload, **kwargs)
    monkeypatch.setattr(research, '_post', slow_research)
    monkeypatch.setattr(research, 'TOTAL_SECONDS', .1)
    monkeypatch.setattr(research, 'MIN_RECOVERY_SECONDS', 0)
    # There is deliberately no surrounding request_budget. Each call alone
    # fits the stage limit, but their combined research time must not.
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_TIMEOUT'
    assert len(requests) == 1 and calls == 2


def test_provider_cannot_exceed_remaining_web_action_budget_during_recovery(monkeypatch):
    recovered = search_response()
    recovered['output'][2:2] = [
        {'type': 'web_search_call', 'status': 'completed',
         'action': {'type': 'open_page', 'url': URL}}
        for _ in range(2)
    ]
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [mismatched_response(web_calls=10), recovered], trace=trace)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 2
    assert json.loads(requests[1].content)['max_tool_calls'] == 2
    assert trace.search_requests == 2
    failures = [item for item in trace.decisions if item['decision'] == 'openai_web_research_failure']
    assert any(item['reason'] == 'search_budget' for item in failures)


def test_unfinished_recovery_search_fails_but_completed_searches_are_counted(monkeypatch):
    recovered = search_response()
    completed_search = deepcopy(recovered['output'][1])
    unfinished_search = deepcopy(completed_search)
    unfinished_search['status'] = 'searching'
    recovered['output'][2:2] = [completed_search, unfinished_search]
    trace = RetrievalTrace(search_requests=2)
    requests, invoke = run(monkeypatch, [mismatched_response(web_calls=10), recovered], trace=trace)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_SEARCH_FAILED' and len(requests) == 2
    initial, recovery = [json.loads(request.content) for request in requests]
    assert initial['instructions'].startswith(research.RESEARCH_INSTRUCTIONS)
    assert 'at most 10 web tool actions left' in initial['instructions']
    assert recovery['max_tool_calls'] == 2
    assert 'at most 2 web tool actions' in recovery['instructions']
    assert all('tools' in payload for payload in (initial, recovery))
    # Existing two searches, one initial search, then two completed recovery
    # searches; the third unfinished recovery action is never counted.
    assert trace.search_requests == 5
    usage = [item for item in trace.decisions
        if item['decision'] == 'openai_web_research_tool_usage']
    assert usage[-1]['tool_actions'] == usage[-1]['search_actions'] == '2'
    assert usage[-1]['total_tool_actions'] == '12'


def test_malformed_message_preserves_completed_search_count_without_another_api_call(monkeypatch):
    body = search_response()
    body['output'][2]['content'] = 'PRIVATE_MALFORMED_CONTENT'
    trace = RetrievalTrace(search_requests=4)
    requests, invoke = run(monkeypatch, [body], trace=trace)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 1
    assert trace.search_requests == 5
    assert 'PRIVATE_MALFORMED_CONTENT' not in json.dumps(trace.model_dump()) + str(error.value)


def test_citation_recovery_and_assessment_review_are_bounded_to_four_model_calls(monkeypatch):
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [mismatched_response(), search_response(),
        assessment_response(draft(ids=['c2'])), assessment_response()], trace=trace)
    assert invoke().verdict == 'false' and len(requests) == 4
    payloads = [json.loads(request.content) for request in requests]
    assert [bool(payload.get('tools')) for payload in payloads] == [True, True, False, False]
    context, repair_context = [json.loads(payload['input'][0]['content']) for payload in payloads[2:]]
    assert repair_context['research_evidence'] == context['research_evidence']
    assert repair_context['native_citation_sources'] == context['native_citation_sources']
    assert 'expected_verdict' not in repair_context['assessment_review']
    assert repair_context['assessment_review']['previous_assessment']['verdict'] == 'false'
    assert trace.search_requests == 2


def test_mismatched_citation_diagnostics_exclude_urls_provider_text_and_credentials(monkeypatch, caplog):
    private_url = 'https://example.gov.sg/private-admission?token=PRIVATE_QUERY_SECRET'
    body = search_response(url=private_url, report='PRIVATE_PROVIDER_REPORT')
    body['output'][1]['action']['sources'][0]['url'] = 'https://example.gov.sg/PRIVATE_SOURCE_PATH'
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [body, deepcopy(body)], trace=trace)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert len(requests) == 2
    diagnostics = json.dumps(trace.model_dump()) + caplog.text + str(error.value)
    assert KEY not in diagnostics and 'PRIVATE_' not in diagnostics
    assert 'https://' not in diagnostics and 'example.gov.sg' not in diagnostics
    mismatches = [item for item in trace.decisions
        if item['decision'] == 'openai_citation_provenance_mismatch']
    assert len(mismatches) == 2
    assert all(any('fingerprint' in key and value for key, value in item.items()) for item in mismatches)
    failures = [item for item in trace.decisions if item['decision'] == 'openai_web_research_failure']
    assert failures and all(item['reason'] == 'citation_provenance_mismatch' for item in failures)


C11_CLAIM = ('A leaked report claims unemployment among Singapore graduates has doubled '
    'because companies are hiring foreigners at half the salary.')
C11_RESEARCH = (
    'The alleged report has not been authenticated. The unemployment comparison omits '
    'the period and graduate population. Salary thresholds weigh against a blanket '
    'half-price claim about professional hires, but the salary measures and worker '
    'populations differ and are not comparisons of people doing identical jobs. '
    'The alleged causal mechanism remains unestablished.'
)


def c11_decision(*, salary_status='contradicted', salary_applicability='qualified'):
    value = draft('insufficient_evidence', status='unresolved', basis='unresolved')
    value['summary'] = 'The claim cannot be settled from the supplied report and comparisons.'
    value['findings'] = []
    for assertion in (
        'A leaked report makes the alleged claims.',
        'Unemployment among Singapore graduates has doubled.',
        'Companies are hiring foreigners at half the salary of Singapore graduates.',
        'Hiring foreigners at half the salary caused graduate unemployment to double.',
    ):
        finding = deepcopy(draft('insufficient_evidence', status='unresolved', basis='unresolved')['findings'][0])
        finding.update(claim=assertion, explanation='The report does not establish this original assertion.')
        finding['scope'] = {
            'claim_scope': assertion + ' No comparison period or matched worker population is specified.',
            'evidence_scope': 'Public employment measures and work-pass salary thresholds for different populations.',
            'applicability': 'unknown',
            'reason': 'The relevant document, matched comparison or causal evidence is missing.',
        }
        finding['limitations'] = ['The comparison does not match equivalent workers and the causal link is unresolved.']
        value['findings'].append(finding)
    salary = value['findings'][2]
    salary.update(status=salary_status,
        basis='bounded_inference' if salary_status == 'contradicted' else 'unresolved',
        explanation='Salary thresholds weigh against a narrower blanket claim, with unmatched populations.')
    salary['scope'].update(applicability=salary_applicability,
        reason='A comparison of pass thresholds and graduate median pay does not establish a like-for-like wage difference.')
    return value


def test_c11_conflicting_salary_finding_gets_one_scope_review_and_keeps_all_assertions(monkeypatch):
    initial = c11_decision()
    corrected = c11_decision(salary_status='unresolved', salary_applicability='mismatch')
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response('insufficient_evidence', report=C11_RESEARCH),
        assessment_response(initial), assessment_response(corrected)], trace=trace, claim=C11_CLAIM)
    result = invoke()
    assert result.verdict == 'insufficient_evidence' and len(requests) == 3
    assert len(result.findings) == 4 and all(finding.material for finding in result.findings)
    assert [finding.claim for finding in result.findings] == [finding['claim'] for finding in initial['findings']]
    assert all(finding.status == finding.basis == 'unresolved' for finding in result.findings)
    before, after = [json.loads(json.loads(request.content)['input'][0]['content']) for request in requests[1:]]
    assert before['original_claim'] == after['original_claim'] == C11_CLAIM
    assert before['research_evidence'] == after['research_evidence']
    assert before['native_citation_sources'] == after['native_citation_sources']
    review = after['assessment_review']
    assert 'expected_verdict' not in review
    assert review['previous_assessment']['findings'][2]['status'] == 'contradicted'
    assert review['constraints'] == [{'path': '<root>', 'type': 'research_unresolved_cannot_erase_contradiction'}]
    assert all('tools' not in json.loads(request.content) for request in requests[1:])


def test_c11_repeated_inconsistency_remains_an_error_after_one_review(monkeypatch):
    invalid = c11_decision()
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response('insufficient_evidence', report=C11_RESEARCH),
        assessment_response(invalid), assessment_response(invalid)], trace=trace, claim=C11_CLAIM)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 3
    failures = [item for item in trace.decisions if item['decision'] == 'openai_web_research_failure']
    assert len(failures) == 2
    assert all('research_unresolved_cannot_erase_contradiction' in item['validation_issues'] for item in failures)


@pytest.mark.parametrize('change', ['drop', 'demote', 'rewrite'])
def test_consistency_review_cannot_hide_the_conflicting_original_assertion(monkeypatch, change):
    initial = c11_decision()
    invalid = c11_decision(salary_status='unresolved', salary_applicability='mismatch')
    if change == 'drop':
        invalid['findings'].pop(2)
    elif change == 'demote':
        invalid['findings'][2]['material'] = False
    else:
        invalid['findings'][2]['claim'] = 'Work-pass rules have minimum salaries.'
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response('insufficient_evidence', report=C11_RESEARCH),
        assessment_response(initial), assessment_response(invalid)], trace=trace, claim=C11_CLAIM)
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 3
    failures = [item for item in trace.decisions if item['decision'] == 'openai_web_research_failure']
    assert 'research_decision_assertions_changed' in failures[-1]['validation_issues']


@pytest.mark.parametrize('retained_material', [True, False])
def test_review_preserves_default_materiality_when_the_initial_decision_omits_it(monkeypatch, retained_material):
    initial = c11_decision()
    initial['findings'][2].pop('material')
    corrected = c11_decision(salary_status='unresolved', salary_applicability='mismatch')
    corrected['findings'][2]['material'] = retained_material
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response('insufficient_evidence', report=C11_RESEARCH),
        assessment_response(initial), assessment_response(corrected)], trace=trace, claim=C11_CLAIM)
    if retained_material:
        result = invoke()
        assert result.verdict == 'insufficient_evidence'
        assert result.findings[2].material is True
        assert result.findings[2].status == 'unresolved'
    else:
        with pytest.raises(PipelineComponentError) as error:
            invoke()
        assert error.value.error_code == 'OPENAI_RESEARCH_INVALID'
        failures = [item for item in trace.decisions if item['decision'] == 'openai_web_research_failure']
        assert 'research_decision_assertions_changed' in failures[-1]['validation_issues']
    assert len(requests) == 3
    review = json.loads(json.loads(requests[2].content)['input'][0]['content'])['assessment_review']
    assert review['previous_assessment']['findings'][2]['material'] is True


@pytest.mark.parametrize('applicability', ['mismatch', 'unknown'])
def test_inapplicable_scope_cannot_support_a_decisive_assessment(monkeypatch, applicability):
    invalid = draft('likely_false', basis='bounded_inference')
    invalid['findings'][0]['scope']['applicability'] = applicability
    requests, invoke = run(monkeypatch, [search_response(), assessment_response(invalid), assessment_response(invalid)])
    with pytest.raises(PipelineComponentError) as error:
        invoke()
    assert error.value.error_code == 'OPENAI_RESEARCH_INVALID' and len(requests) == 3


@pytest.mark.parametrize('verdict,status,basis', [
    ('true', 'supported', 'direct'),
    ('likely_true', 'supported', 'bounded_inference'),
    ('mixed', 'mixed', 'direct'),
    ('likely_false', 'contradicted', 'bounded_inference'),
    ('false', 'contradicted', 'direct'),
    ('insufficient_evidence', 'unresolved', 'unresolved'),
    ('not_checkable', 'unresolved', 'unresolved'),
])
def test_valid_assessment_decisions_are_preserved_without_another_model_call(monkeypatch, verdict, status, basis):
    value = draft(verdict, status=status, basis=basis)
    requests, invoke = run(monkeypatch, [search_response(None), assessment_response(value)])
    result = invoke()
    assert len(requests) == 2 and result.verdict == verdict
    actual = result.findings[0].model_dump()
    for field in ('claim', 'status', 'basis', 'material', 'source_ids', 'explanation'):
        assert actual[field] == value['findings'][0][field]
    assert result.summary == value['summary'] and result.recommended_action == value['recommended_action']


def test_assessment_review_does_not_relay_unknown_nested_fields_or_log_source_text(monkeypatch, caplog):
    invalid = draft()
    invalid['findings'][0]['scope']['PRIVATE_EXTRA_SCOPE'] = KEY + ' PRIVATE_SCOPE_PAYLOAD'
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response(), assessment_response(invalid), assessment_response()], trace=trace)
    assert invoke().verdict == 'false' and len(requests) == 3
    assert 'PRIVATE_' not in requests[2].content.decode()
    assert KEY not in json.dumps(trace.model_dump()) + caplog.text
    assert 'PRIVATE_' not in json.dumps(trace.model_dump()) + caplog.text


def test_invalid_assessment_json_gets_one_review_without_relaying_the_raw_payload(monkeypatch, caplog):
    invalid = assessment_response()
    invalid['output'][0]['content'][0]['text'] = '{ PRIVATE_UNPARSEABLE_PAYLOAD ' + KEY
    trace = RetrievalTrace()
    requests, invoke = run(monkeypatch, [search_response(), invalid, assessment_response()], trace=trace)
    assert invoke().verdict == 'false' and len(requests) == 3
    review = json.loads(json.loads(requests[2].content)['input'][0]['content'])['assessment_review']
    assert review['constraints'] == [{'path': '<root>', 'type': 'json_invalid'}]
    assert 'PRIVATE_' not in requests[2].content.decode()
    assert KEY not in requests[2].content.decode()
    assert 'PRIVATE_' not in caplog.text + json.dumps(trace.model_dump())
