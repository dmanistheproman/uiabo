"""A dated legislative snapshot cannot independently establish today's rule."""

import asyncio
from datetime import date, datetime, timezone
import json

import httpx
import pytest

from app.pipeline.evidence_retrieval.relevance import select_with_client
from app.pipeline.evidence_retrieval.source_versions import (
    exclude_archived_current_policy_source, source_version_context,
)
from app.pipeline.shared.dates import infer_date_context


AS_OF = date(2026, 11, 3)
ARCHIVE = 'https://sso.agc.gov.sg/Act-Rev/RRA1993/Published/20120930?DocDate=20000701'
TEXT = 'The minimum eligibility age is 21 years.'


def select(*, claim='The minimum eligibility age is now 25.', url=ARCHIVE,
           text=TEXT, published_at=None, applicability='established', relevance='direct', date_context=None):
    payloads = []

    def handler(request):
        payload = json.loads(request.content)
        payloads.append(json.loads(payload['messages'][1]['content']))
        result = {'window_id': 0, 'relevance': relevance, 'quote_start': 0, 'quote_end': 0,
                  'reason': 'The current rule specifies the age for the same policy.',
                  'applicability': applicability, 'applicability_reason': 'Same scope.',
                  'condition_ranges': []}
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps(result)}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await select_with_client(client, claim, text, 'test', as_of=AS_OF,
                                            published_at=published_at, date_context=date_context, source_url=url)

    selected, passage = asyncio.run(run())
    return selected, passage, payloads[0]


def test_selected_edition_uses_docdate_instead_of_archive_route_date():
    assert source_version_context(ARCHIVE) == {
        'kind': 'dated_version', 'version_date': '2000-07-01', 'basis': 'selected_edition_docdate'}


@pytest.mark.parametrize('url,expected', [
    ('https://sso.agc.gov.sg/Act-Rev/EX1990/Published/20120930', '2012-09-30'),
    ('https://sso.agc.gov.sg/Act/EX1990?DocDate=20000701', '2000-07-01'),
    ('https://example.gov/legislation/versions/2000-07-01/rule', '2000-07-01'),
])
def test_explicit_dated_versions_are_recognised(url, expected):
    assert source_version_context(url)['version_date'] == expected


@pytest.mark.parametrize('url', [
    'https://sso.agc.gov.sg/Act/RRA1993',
    'https://example.gov/news/2000/07/01/current-rule',
    'https://example.gov/archive/2000/07/01/news',
    'https://sso.agc.gov.sg/Act/EX1990?DocDate=20000230',
])
def test_enactment_and_publication_dates_are_not_historical_version_markers(url):
    assert source_version_context(url, 'Revised edition published on 1 July 2000.') is None


def test_page_level_historical_label_survives_missing_url_metadata():
    version = source_version_context(None, '## Historical version as at 2000-07-01\n' + TEXT)
    assert version['version_date'] == '2000-07-01'


def test_current_claim_keeps_archive_as_context_and_sends_version_to_selector():
    selected, passage, payload = select()
    assert passage == TEXT
    assert selected.quote == TEXT
    assert selected.relevance == 'context'
    assert selected.applicability == 'uncertain_time'
    assert '2000-07-01' in selected.applicability_reason
    assert 'independent corroboration' in selected.applicability_reason
    assert 'current rule specifies' not in selected.reason
    assert payload['source_url'] == ARCHIVE
    assert payload['source_version']['version_date'] == '2000-07-01'


@pytest.mark.parametrize('with_context', [True, False])
def test_historical_claim_preserves_semantic_period_assessment(with_context):
    claim = 'In July 2000 the minimum eligibility age was 21.'
    context = infer_date_context(claim, datetime(2026, 11, 3, tzinfo=timezone.utc)) if with_context else None
    selected, _, _ = select(claim=claim, date_context=context)
    assert selected.relevance == 'direct'
    assert selected.applicability == 'established'


def test_old_publication_on_unversioned_official_page_can_still_be_current():
    selected, _, payload = select(url='https://sso.agc.gov.sg/Act/EX1990', published_at=date(2000, 7, 1))
    assert payload['source_version'] is None
    assert selected.relevance == 'direct'
    assert selected.applicability == 'established'


@pytest.mark.parametrize('applicability', ['missing_context', 'different_scope', 'uncertain_time'])
def test_version_guard_does_not_erase_other_scope_limitations(applicability):
    selected, _, _ = select(applicability=applicability)
    assert selected.applicability == applicability
    assert selected.relevance == 'context'
    assert '2000-07-01' in selected.applicability_reason


def test_current_dated_snapshot_is_not_automatically_downgraded():
    selected, _, _ = select(url='https://sso.agc.gov.sg/Act/EX1990?DocDate=20261103')
    assert selected.relevance == 'direct'
    assert selected.applicability == 'established'


def test_unrelated_snapshot_is_not_promoted_to_context():
    selected, _, _ = select(relevance='irrelevant', applicability='different_scope')
    assert selected.relevance == 'irrelevant'


@pytest.mark.parametrize('url,text', [
    (ARCHIVE, TEXT),
    ('https://sso.agc.gov.sg/Act-Rev/EX1990?DocDate=20000701', TEXT),
    ('https://example.gov/legislation/historical/2000-07-01/rule', TEXT),
    ('https://example.gov/legislation/archived/20000701/rule', TEXT),
    ('https://example.gov/rule', '## Archived version as at 2000-07-01\n' + TEXT),
    ('https://example.gov/rule', 'Superseded version: 2000-07-01\n' + TEXT),
])
def test_explicit_old_archives_cannot_independently_establish_current_policy(url, text):
    assert exclude_archived_current_policy_source(url, text, as_of=AS_OF)


@pytest.mark.parametrize('url,text', [
    ('https://sso.agc.gov.sg/Act/EX1990', 'Revised edition published on 1 July 2000. ' + TEXT),
    ('https://sso.agc.gov.sg/Act/EX1990?DocDate=20000701', TEXT),
    ('https://sso.agc.gov.sg/Act/EX1990?DocDate=20261103', TEXT),
    ('https://example.gov/legislation/versions/2000-07-01/rule', TEXT),
    ('https://example.gov/legislation/point-in-time/2000-07-01/rule', TEXT),
    ('https://example.gov/archive/2000/07/01/news', TEXT),
    ('https://example.gov/rule', 'Point-in-time version as at 2000-07-01\n' + TEXT),
    ('https://example.gov/rule', TEXT * 100 + '\nHistorical version as at 2000-07-01\n'),
    ('https://example.gov/legislation/historical/2000-02-30/rule', TEXT),
    ('https://sso.agc.gov.sg/Act-Rev/EX1990?DocDate=20261103', TEXT),
])
def test_age_or_bare_version_date_does_not_trigger_archive_exclusion(url, text):
    assert not exclude_archived_current_policy_source(url, text, as_of=AS_OF)


def test_explicit_archive_remains_available_for_a_historical_assertion():
    context = infer_date_context('In July 2000 the minimum eligibility age was 21.',
                                 datetime(2026, 11, 3, tzinfo=timezone.utc))
    assert not exclude_archived_current_policy_source(ARCHIVE, TEXT, as_of=AS_OF, date_context=context)


def test_archive_exclusion_does_not_invent_an_assessment_date():
    assert not exclude_archived_current_policy_source(ARCHIVE, TEXT, as_of=None)
