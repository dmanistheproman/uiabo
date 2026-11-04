"""Public dataset boundaries, real rows/headers, pagination and fallback."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.pipeline.evidence_retrieval import datasets, enhanced, pdf_reader

IDENTIFIER = 'd_' + 'a' * 32
URL = 'https://data.gov.sg/datasets/' + IDENTIFIER + '/view'


@pytest.mark.parametrize('url', [
    'http://data.gov.sg/datasets/'+IDENTIFIER+'/view',
    'https://data.gov.sg.evil.com/datasets/'+IDENTIFIER+'/view',
    'https://user:pass@data.gov.sg/datasets/'+IDENTIFIER+'/view',
    'https://data.gov.sg:8000/datasets/'+IDENTIFIER+'/view',
    'https://data.gov.sg/datasets/../../secrets/view',
    'https://127.0.0.1/datasets/'+IDENTIFIER+'/view',
])
def test_dataset_rejects_unapproved_urls(url):
    assert datasets.dataset_id(url) is None


def test_fixed_public_endpoint_uses_pinned_address_without_secrets(monkeypatch):
    async def address(host):
        assert host == 'data.gov.sg'
        return '8.8.8.8'
    monkeypatch.setattr(datasets, 'public_address', address)
    original = httpx.AsyncClient
    def handler(request):
        assert request.url.host == '8.8.8.8'
        assert request.url.path == '/api/action/datastore_search'
        assert request.url.params['resource_id'] == IDENTIFIER
        assert request.url.params['limit'] == str(datasets.PAGE_SIZE)
        assert request.headers['host']=='data.gov.sg'
        assert request.extensions['sni_hostname']=='data.gov.sg'
        assert 'authorization' not in request.headers and 'x-goog-api-key' not in request.headers
        return httpx.Response(200, json={'success':True,'result':{'records':[]}})
    def factory(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(datasets.httpx, 'AsyncClient', factory)
    assert asyncio.run(datasets.request_page(IDENTIFIER,0)) == {'records':[]}


@pytest.mark.parametrize('status,headers,body', [
    (302, {'location':'http://169.254.169.254/secret'}, b''),
    (200, {'content-length':str(datasets.MAX_BYTES+1)}, b'{}'),
    (200, {}, b'X'*(datasets.MAX_BYTES+1)),
    (200, {}, b'{"success": false, "result": {}}'),
], ids=['redirect','declared-size','streamed-size','unsuccessful-response'])
def test_redirect_size_and_invalid_result_rejected(monkeypatch,status,headers,body):
    async def address(host): return '8.8.8.8'
    monkeypatch.setattr(datasets,'public_address',address)
    original=httpx.AsyncClient
    monkeypatch.setattr(datasets.httpx,'AsyncClient', lambda **kw: original(
        transport=httpx.MockTransport(lambda request:httpx.Response(status,headers=headers,content=body)),**kw))
    with pytest.raises(ValueError): asyncio.run(datasets.request_page(IDENTIFIER,0))


def test_pagination_is_bounded_and_keeps_relevant_rows_and_headers(monkeypatch):
    calls=[]
    async def page(identifier,offset):
        calls.append(offset)
        records=[{'Sex':'Other', '2024':str(i), '2025':str(i+1)} for i in range(100)]
        if offset==100:
            records[80]={'Sex':'Male', '2024':'120', '2025':'130'}
        return {'fields':[{'id':v} for v in ['Sex','2024','2025']], 'records':records, 'total':50000}
    monkeypatch.setattr(datasets,'request_page',page)
    text=asyncio.run(datasets.read_dataset(URL,'male admissions comparison 2024 2025'))
    assert calls==[0,100]
    assert '| Sex | 2024 | 2025 |' in text
    assert '| Male | 120 | 130 |' in text
    assert 'may omit rows or columns' in text and '200 rows of 50000' in text
    assert len(text)<=datasets.MAX_TEXT


def test_missing_values_are_not_replaced_by_zero_and_no_derived_figures():
    text=datasets.table_text(IDENTIFIER,['Category','2024','2025'],
        [{'Category':'male','2024':100,'2025':None}], 'male count 2024 2025')
    assert '| male | 100 | [missing] |' in text
    assert 'increase' not in text and '0%' not in text


def test_indented_rows_keep_their_parent_labels_and_original_order():
    rows = [
        {'DataSeries':'Male','2025':'100'},
        {'DataSeries':'  Accountancy','2025':'30'},
        {'DataSeries':'  Engineering','2025':'70'},
        {'DataSeries':'Female','2025':'110'},
        {'DataSeries':'  Accountancy','2025':'60'},
        {'DataSeries':'  Engineering','2025':'50'},
    ]
    # Relevant repeated labels must not float above their male/female groups.
    text = datasets.table_text(IDENTIFIER,['DataSeries','2025'],rows,'Accountancy female')
    expected=['| Male | 100 |','|   Accountancy | 30 |','|   Engineering | 70 |',
              '| Female | 110 |','|   Accountancy | 60 |','|   Engineering | 50 |']
    assert [text.index(line) for line in expected] == sorted(text.index(line) for line in expected)


def test_bounded_row_selection_includes_ancestor_even_when_not_a_query_match():
    rows=[]
    for i in range(30):
        rows.extend([{'Series':f'Group {i}','2025':str(i)},
                     {'Series':'  Accountancy','2025':str(i+100)}])
    text=datasets.table_text(IDENTIFIER,['Series','2025'],rows,'Accountancy')
    lines=text.splitlines()
    for i,line in enumerate(lines):
        if line.startswith('|   Accountancy |'):
            assert lines[i-1].startswith('| Group ')


def test_schema_changes_or_metadata_only_response_fail_closed(monkeypatch):
    for raw in [{'fields':[],'records':[]}, {'fields':[{'id':'Year'}],'records':[{'wrong':'x'}]},
                {'fields':[{'id':'Year'}],'records':[{'Year':{'nested':'x'}}]}]:
        with pytest.raises(ValueError): datasets.validated_page(raw)


def test_native_rows_precede_html_preview_and_keep_source_url(monkeypatch):
    from .test_requirement_repair import selection
    text='| Sex | Intake |\n| --- | --- |\n| Male | 120 |\n| Female | 130 |'
    async def read(url,focus): assert url==URL; return text
    async def select(client,claim,page,key,**kw): return selection(page)
    async def no_html(*a,**kw): raise AssertionError('Native rows succeeded; no HTML preview needed')
    monkeypatch.setattr(datasets,'read_dataset',read)
    monkeypatch.setattr(enhanced,'select_with_client',select)
    monkeypatch.setattr(enhanced.providers,'tavily_extract',no_html)
    run=enhanced.RetrievalRun('Singapore university intake by sex',None,'g','t','o')
    run.add({'url':URL,'title':'University intake','score':.9},'preferred_search')
    asyncio.run(run.extract_pages(run.next_pages(1)))
    assert len(run.evidence)==1 and str(run.evidence[0].url)==URL
    assert run.evidence[0].passage==text
    assert run.evidence[0].provenance.discovery_method=='official_api'


def test_native_outage_falls_back_to_html_with_trace(monkeypatch):
    from .test_requirement_repair import selection
    async def fail(*a,**kw): raise httpx.ConnectError('secret')
    async def extract(*a,**kw): return {'results':[{'url':URL,'raw_content':'Official university intake information.'}], 'failed_results':[]}
    async def select(client,claim,page,key,**kw): return selection(page)
    monkeypatch.setattr(datasets,'read_dataset',fail)
    monkeypatch.setattr(enhanced.providers,'tavily_extract',extract)
    monkeypatch.setattr(enhanced,'select_with_client',select)
    run=enhanced.RetrievalRun('University intake',None,'g','t','o')
    run.add({'url':URL,'title':'Intake','score':.9},'preferred_search')
    asyncio.run(run.extract_pages(run.next_pages(1)))
    assert run.evidence and any(d['decision']=='native_dataset_unavailable' for d in run.trace.decisions)


def test_generic_fields_keep_verified_catalogue_footnotes_with_api_rows(monkeypatch):
    from .test_requirement_repair import selection
    text='| DataSeries | 2024 | 2025 |\n| --- | --- | --- |\n| Male | 120 | 130 |'
    calls=[]
    async def read(*a): return text
    async def extract(client,urls,key,**kw):
        calls.append(urls)
        return {'results':[{'url':URL,'raw_content':
            'Navigation\n# Full-time first-degree university intake by sex\n\nFootnotes: First-degree intake only; excludes part-time students.\n\n## Data explorer\n\n| bad HTML preview |'}]}
    async def select(client,claim,page,key,**kw): return selection(page)
    monkeypatch.setattr(datasets,'read_dataset',read)
    monkeypatch.setattr(enhanced.providers,'tavily_extract',extract)
    monkeypatch.setattr(enhanced,'select_with_client',select)
    run=enhanced.RetrievalRun('University intake by sex',None,'g','t','o')
    run.add({'url':URL,'title':'Unverified search title','score':.9},'preferred_search')
    asyncio.run(run.extract_pages(run.next_pages(1)))
    assert calls==[[URL]]
    passage=run.evidence[0].passage
    assert 'First-degree intake only; excludes part-time students.' in passage
    assert '| Male | 120 | 130 |' in passage
    assert 'Unverified search title' not in passage and 'bad HTML preview' not in passage


def test_failed_catalogue_metadata_does_not_discard_real_rows(monkeypatch):
    from .test_requirement_repair import selection
    text='| DataSeries | 2024 | 2025 |\n| --- | --- | --- |\n| Male | 120 | 130 |'
    async def read(*a): return text
    async def fail(*a,**kw): raise httpx.ConnectError('secret')
    async def select(client,claim,page,key,**kw): return selection(page)
    monkeypatch.setattr(datasets,'read_dataset',read)
    monkeypatch.setattr(enhanced.providers,'tavily_extract',fail)
    monkeypatch.setattr(enhanced,'select_with_client',select)
    run=enhanced.RetrievalRun('University intake',None,'g','t','o')
    run.add({'url':URL,'title':'Intake','score':.9},'preferred_search')
    asyncio.run(run.extract_pages(run.next_pages(1)))
    assert run.evidence[0].passage==text
    assert any(d['decision']=='native_dataset_catalogue_context_unavailable' for d in run.trace.decisions)


def test_numeric_pdf_requirement_is_not_employment_only(monkeypatch):
    monkeypatch.setenv('PDF_READER_ENABLED','true');monkeypatch.setenv('GEMINI_API_KEY','test')
    plan=SimpleNamespace(status='planned',assertions=[SimpleNamespace(material=True,kind='comparison')])
    context=SimpleNamespace(retrieval_topic='general')
    assert pdf_reader.eligible({'url':'https://gov.uk/transport.pdf'},context,plan)
    assert not pdf_reader.eligible({'url':'https://gov.uk/transport.html'},context,plan)
    assert not pdf_reader.eligible({'url':'https://gov.uk/law.pdf'},context,None)
