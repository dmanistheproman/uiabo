import asyncio
from datetime import datetime, timezone

from app.pipeline.evidence_retrieval import enhanced
from app.pipeline.evidence_retrieval.extraction_scope import html_alternative, inference_blockers, UNAVAILABLE_WARNING
from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.models import CoverageIssue
from tests.pipeline.evidence_assessment.test_public_changes import fixture
from tests.pipeline.evidence_retrieval.test_component_coverage import item


def test_unknown_or_material_warning_still_blocks_inference():
    _, retrieval, _, _, _ = fixture()
    retrieval.warnings = ['Unknown retrieval failure']
    assert inference_blockers(retrieval)
    retrieval.trace.coverage_issues.append(CoverageIssue(warning=retrieval.warnings[0], stage='search',
        reason='Announcement search failed.'))
    assert inference_blockers(retrieval) == ['Announcement search failed.']


def test_nonessential_or_resolved_warning_does_not_override_valid_coverage():
    from app.pipeline.evidence_assessment.public_changes import eligible_plan
    claim, retrieval, result, plan, _ = fixture()
    retrieval.warnings = [UNAVAILABLE_WARNING]
    issue = CoverageIssue(warning=UNAVAILABLE_WARNING, stage='extraction', reason='Unrelated offence.',
                          blocks_inference=False)
    retrieval.trace.coverage_issues.append(issue)
    assert eligible_plan(claim, retrieval, result) == plan
    issue.blocks_inference = True
    assert eligible_plan(claim, retrieval, result) is None
    issue.resolved_by = 'https://sso.agc.gov.sg/Act/test'
    assert eligible_plan(claim, retrieval, result) == plan
    retrieval.trace.decisions.clear()  # A resolved page never substitutes for a search.
    assert eligible_plan(claim, retrieval, result) is None


def test_html_alternative_preserves_document_and_date():
    url = 'https://sso.agc.gov.sg/Bills-Supp/49-2024/Published/20241112?DocDate=20241112&ViewType=Pdf&_=123'
    assert html_alternative(url) == 'https://sso.agc.gov.sg/Bills-Supp/49-2024/Published/20241112?DocDate=20241112'
    assert html_alternative('https://stats.mom.gov.sg/report.pdf') is None
    assert html_alternative('https://other.example/law?ViewType=Pdf') is None


def test_advanced_extraction_is_bounded_and_failed_sso_has_same_document_recovery(monkeypatch):
    text = 'Police will issue fines for government criticism on social media.'
    run = enhanced.RetrievalRun(text, None, 'g', 't', 'o',
        claim_context=build_claim_context(text, datetime(2026, 11, 3, tzinfo=timezone.utc)))
    url = 'https://sso.agc.gov.sg/Act/Test?DocDate=20261103&ViewType=Pdf'
    run.add(item(url, 'Official current rules', text), 'preferred_search')
    calls = []
    async def extract(client, urls, key, **kwargs):
        calls.append(kwargs)
        return {'results': [], 'failed_results': [{'url': u} for u in urls]}
    monkeypatch.setattr(enhanced.providers, 'tavily_extract', extract)
    asyncio.run(run.extract_pages(run.next_pages(1)))
    assert calls[0]['depth'] == 'advanced'
    assert run.next_pages(1)[0]['url'] == html_alternative(url)
    assert run.trace.coverage_issues[0].blocks_inference
    for i in range(3):
        run.add(item(f'https://sso.agc.gov.sg/law{i}.pdf', 'Statute', text), 'preferred_search')
    asyncio.run(run.extract_pages(run.next_pages(4)))
    assert run.advanced_pages == 2
    assert len([c for c in calls if c.get('depth') == 'advanced']) == 2
