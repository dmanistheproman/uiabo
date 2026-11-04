"""Network boundaries, extraction validation and numerical use of PDF readings."""
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from types import SimpleNamespace

import httpx
import pytest
from pypdf import PdfWriter

from app.pipeline.evidence_retrieval import pdf_reader as reader
from app.pipeline.shared.pdf_reading import PdfDocument, PdfReading
from app.pipeline.evidence_assessment.pdf_comparison import compare_pdf
from app.pipeline.evidence_assessment.components import Draft, bind_findings, pairs_for
from app.pipeline.shared.components import decompose_claim
from tests.pipeline.evidence_assessment.test_component_assessment import source

TEXT = 'Fresh university graduates Unemployed June 2024 100 June 2025 130'
CLAIM = 'The number of unemployed fresh university graduates doubled from June 2024 to June 2025'


def document():
    return PdfDocument(document_title='Labour market outcomes', publication_label=None, limitations=[],
        series=[dict(page=1, metric_label='Unemployed', metric_type='unemployed_count',
            population_label='Fresh university graduates', points=[
                dict(date_label='June 2024', year=2024, month=6, value='100', unit='people', cohort_label=None),
                dict(date_label='June 2025', year=2025, month=6, value='130', unit='people', cohort_label=None)])])


def reading():
    return PdfReading(model='test', pdf_sha256='a'*64, page_count=1,
        extracted_at=datetime.now(timezone.utc), document=document())


@pytest.mark.parametrize('url', ['http://mom.gov.sg/a.pdf', 'https://127.0.0.1/a.pdf',
    'https://user:pass@mom.gov.sg/a.pdf', 'https://unknown-publisher.com/a.pdf',
    'https://mom.gov.sg:8000/a.pdf', 'https://localhost/a.pdf'])
def test_download_rejects_unsafe_or_unapproved_urls(url):
    with pytest.raises(ValueError):
        reader.checked_url(url, 'employment')


@pytest.mark.parametrize('addresses', [['127.0.0.1'], ['169.254.169.254'], ['10.0.0.1'],
    ['::1'], ['224.0.0.1'], ['8.8.8.8', '192.168.0.1']])
def test_dns_rejects_private_and_mixed_answers(monkeypatch, addresses):
    monkeypatch.setattr(reader.socket, 'getaddrinfo', lambda *a, **kw: [(2,1,6,'',(ip,443)) for ip in addresses])
    with pytest.raises(ValueError):
        asyncio.run(reader.public_address('mom.gov.sg'))


def test_download_pins_address_preserves_tls_host_and_omits_credentials(monkeypatch):
    async def resolve(host):
        assert host == 'mom.gov.sg'
        return '8.8.8.8'
    monkeypatch.setattr(reader, 'public_address', resolve)
    original = httpx.AsyncClient
    def handler(request):
        assert request.url.host == '8.8.8.8'
        assert request.headers['host'] == 'mom.gov.sg'
        assert request.extensions['sni_hostname'] == 'mom.gov.sg'
        assert 'authorization' not in request.headers and 'x-goog-api-key' not in request.headers
        return httpx.Response(200, content=b'%PDF-safe fixture')
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    assert asyncio.run(reader.download('https://mom.gov.sg/a.pdf', 'employment')).startswith(b'%PDF-')


@pytest.mark.parametrize('status,headers,body', [
    (302, {'location':'http://169.254.169.254/secret'}, b''),
    (200, {'content-length':str(reader.MAX_BYTES+1)}, b'%PDF-'),
    (200, {}, b'<html>not PDF</html>'),
    (200, {}, b'%PDF-' + b'x'*reader.MAX_BYTES),
], ids=['redirect', 'declared_size', 'html', 'streamed_size'])
def test_redirect_size_and_type_failures_do_not_reach_model(monkeypatch, status, headers, body):
    async def resolve(host): return '8.8.8.8'
    monkeypatch.setattr(reader, 'public_address', resolve)
    original = httpx.AsyncClient
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers=headers, content=body)
    monkeypatch.setattr(reader.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(ValueError):
        asyncio.run(reader.download('https://mom.gov.sg/a.pdf', 'employment'))
    assert len(calls) == 1


def test_native_pdf_limits_scans_encryption_and_page_count():
    for count, encrypted in [(1, False), (6, False), (1, True)]:
        writer = PdfWriter()
        for _ in range(count): writer.add_blank_page(100, 100)
        if encrypted: writer.encrypt('password')
        data = BytesIO(); writer.write(data)
        with pytest.raises(ValueError): reader.native_pages(data.getvalue())


@pytest.mark.parametrize('change', ['value','date','population','page','cohort','year'])
def test_uncorroborated_values_labels_and_dates_are_rejected(change):
    doc = document()
    point = doc.series[0].points[0]
    if change == 'value': point.value = '10'  # No substring matches against 100.
    elif change == 'date': point.date_label = 'May 2024'
    elif change == 'population': doc.series[0].population_label = 'All residents'
    elif change == 'page': doc.series[0].page = 2
    elif change == 'cohort': point.cohort_label = '2026 cohort'
    elif change == 'year': point.year = 2023
    with pytest.raises(ValueError): reader.corroborate(doc, [TEXT])


def test_cache_reuses_only_validated_success_and_rechecks_content(monkeypatch, tmp_path):
    monkeypatch.setenv('PDF_READER_ENABLED','true'); monkeypatch.setenv('GEMINI_API_KEY','secret-test-key')
    monkeypatch.setattr(reader, 'CACHE_DIR', tmp_path)
    content = b'%PDF-fixture'
    calls = []
    async def download(*args): return content
    async def generate(*args): calls.append(1); return document()
    monkeypatch.setattr(reader,'download',download)
    monkeypatch.setattr(reader,'native_pages',lambda data:[TEXT])
    monkeypatch.setattr(reader,'generate',generate)
    first, status = asyncio.run(reader.read_pdf('https://mom.gov.sg/a.pdf','employment'))
    second, hit = asyncio.run(reader.read_pdf('https://mom.gov.sg/a.pdf','another claim'))
    assert status == 'completed' and hit == 'cache_hit' and first == second and len(calls) == 1
    assert 'secret-test-key' not in next(tmp_path.glob('*.json')).read_text()
    content = b'%PDF-changed'
    asyncio.run(reader.read_pdf('https://mom.gov.sg/a.pdf','employment'))
    assert len(calls) == 2
    monkeypatch.setenv('PDF_READER_MODEL','different-model')
    asyncio.run(reader.read_pdf('https://mom.gov.sg/a.pdf','employment'))
    assert len(calls) == 3


def test_failed_read_is_not_retried_or_cached_and_error_is_sanitised(monkeypatch, tmp_path):
    monkeypatch.setenv('PDF_READER_ENABLED','true'); monkeypatch.setenv('GEMINI_API_KEY','secret-key')
    monkeypatch.setattr(reader,'CACHE_DIR',tmp_path)
    async def download(*args): return b'%PDF-fixture'
    calls=[]
    async def generate(*args): calls.append(1); raise ValueError('secret-key')
    monkeypatch.setattr(reader,'download',download); monkeypatch.setattr(reader,'generate',generate)
    monkeypatch.setattr(reader,'native_pages',lambda data:[TEXT])
    result,status=asyncio.run(reader.read_pdf('https://mom.gov.sg/a.pdf','employment'))
    assert result is None and status == 'unavailable_ValueError' and len(calls)==1
    assert not list(tmp_path.iterdir())


def test_pdf_comparison_uses_canonical_chart_points_and_preserves_scope():
    evidence=source(passage=TEXT,scope='established'); evidence.pdf_reading=reading()
    stance,gaps,reason=compare_pdf(CLAIM,evidence,population_matches=True)
    assert stance=='contradicting' and not gaps and '30.0% increase' in reason and 'page 1' in reason
    evidence.pdf_reading.document.series[0].points[1].value='200'
    assert compare_pdf(CLAIM,evidence,population_matches=True)[0]=='supporting'
    assert compare_pdf(CLAIM.replace('fresh university','university'),evidence,population_matches=True)[0] is None
    # Undated comparisons now use the disclosed recent-statistics default.
    assert compare_pdf(CLAIM.replace(' from June 2024 to June 2025',''),evidence,population_matches=True)[0]=='supporting'
    assert compare_pdf(CLAIM,evidence,population_matches=False)[0] is None


def test_component_uses_pdf_numbers_not_second_models_invented_comparison():
    parts=decompose_claim(CLAIM+' because employers reduced hiring.')
    evidence=source(passage=TEXT,scope='established'); evidence.pdf_reading=reading()
    drafts={k:Draft(stance='supporting',basis='direct',scope='established',decisiveness=.95,
        explanation='Model guessed double.') for k in pairs_for(parts,[evidence])}
    findings=bind_findings(parts,[evidence],drafts,.5)
    assert findings[0].stance=='contradicting' and findings[0].basis=='inference'
    assert findings[0].quality_score<=.7 and '30.0% increase' in findings[0].explanation
    assert findings[0].quotes[0].quote==TEXT
    assert findings[-1].stance=='unresolved'  # No invented causal finding.


def test_extraction_caveat_prevents_decisive_pdf_vote():
    evidence=source(passage=TEXT,scope='established'); evidence.pdf_reading=reading()
    evidence.pdf_reading.document.limitations=['Legend is unclear']
    assert compare_pdf(CLAIM,evidence,population_matches=True)[0] is None


def test_reading_survives_result_assembly_without_replacing_literal_text():
    from app.pipeline.shared.models import RetrievalResult, AssessedEvidence, EvidenceItem
    from app.pipeline.orchestration.service import _combine_evidence
    evidence=source(passage=TEXT,scope='established'); evidence.pdf_reading=reading()
    results=_combine_evidence(RetrievalResult(retrieval_status='completed',evidence=[evidence]),
        [AssessedEvidence(evidence_id=evidence.evidence_id,stance='neutral',quality_score=0,assessment_reason='Context')])
    saved=EvidenceItem.model_validate_json(results[0].model_dump_json())
    assert saved.pdf_reading==evidence.pdf_reading and saved.passage==TEXT
    assert 'full_text' not in saved.model_dump()


def test_enrichment_selects_after_reviews_and_retains_text_on_failure(monkeypatch):
    from app.pipeline.evidence_retrieval.enhanced import RetrievalRun
    from app.pipeline.shared.context import build_claim_context
    claim='The number of unemployed fresh university graduates doubled'
    run=RetrievalRun(claim,None,'g','t','o',claim_context=build_claim_context(claim,datetime.now(timezone.utc)))
    older=source(passage=TEXT,scope='established').model_copy(update={
        'title':'Youth labour force', 'url':'https://mom.gov.sg/old.pdf'})
    current=source(passage=TEXT,scope='established').model_copy(update={
        'title':'Fresh university graduate unemployment', 'url':'https://mom.gov.sg/new.pdf'})
    run.evidence=[older,current]
    monkeypatch.setattr(reader,'eligible',lambda *a:True)
    calls=[]
    async def unavailable(url, claim): calls.append(url); return None,'unavailable_ValueError'
    monkeypatch.setattr(reader,'read_pdf',unavailable)
    asyncio.run(run.enrich_pdf()); asyncio.run(run.enrich_pdf())
    assert calls==['https://mom.gov.sg/new.pdf']
    assert len(run.evidence)==2 and all(s.passage==TEXT for s in run.evidence)
    assert run.warnings and run.evidence[1].pdf_reading is None


def test_recent_statistics_do_not_spend_pdf_slot_on_methodology(monkeypatch):
    from app.pipeline.evidence_retrieval.enhanced import RetrievalRun
    from app.pipeline.shared.context import build_claim_context
    claim='The number of unemployed fresh university graduates doubled'
    run=RetrievalRun(claim,None,'g','t','o',claim_context=build_claim_context(claim,datetime.now(timezone.utc)))
    run.evidence=[source(passage=TEXT,scope='established').model_copy(update={
        'title':'Technical note: measuring graduate unemployment', 'url':'https://mom.gov.sg/note.pdf'})]
    monkeypatch.setattr(reader,'eligible',lambda *a:True)
    async def forbidden(*a): raise AssertionError('Methodology is not recent observation data')
    monkeypatch.setattr(reader,'read_pdf',forbidden)
    asyncio.run(run.enrich_pdf())
    assert run.pdf_reads==0 and len(run.evidence)==1


def test_disabled_or_ineligible_pdf_never_calls_provider(monkeypatch):
    monkeypatch.delenv('PDF_READER_ENABLED',raising=False)
    monkeypatch.setenv('GEMINI_API_KEY','test')
    assert asyncio.run(reader.read_pdf('https://mom.gov.sg/a.pdf','employment'))==(None,'disabled')
    monkeypatch.setenv('PDF_READER_ENABLED','true')
    assert not reader.eligible({'url':'https://mom.gov.sg/a.html'},SimpleNamespace(retrieval_topic='employment'))
    assert not reader.eligible({'url':'https://mom.gov.sg/a.pdf'},SimpleNamespace(retrieval_topic='policing'))


def test_bad_optional_comparison_does_not_discard_other_sources():
    from app.pipeline.evidence_assessment.components import _call_oss
    parts=decompose_claim(CLAIM+' because employers reduced hiring.')
    evidence=source(passage=TEXT,scope='established')
    pairs=pairs_for(parts,[evidence])
    payload={k:dict(stance='supporting',basis='direct',scope='established',decisiveness=.9,
                   explanation='Incomplete values',comparison={'before':{},'after':{}}) for k in pairs}
    async def run():
        async with httpx.AsyncClient(base_url='https://provider.test',transport=httpx.MockTransport(
            lambda request:httpx.Response(200,json={'done':True,'message':{'content':json.dumps(payload)}}))) as client:
            return await _call_oss(client,'test',pairs)
    drafts=asyncio.run(run())
    assert all(d.comparison is None for d in drafts.values())
    assert bind_findings(parts,[evidence],drafts,.5)[0].stance=='unresolved'
