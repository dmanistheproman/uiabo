"""The latest-period default must not pick dates to obtain a preferred verdict."""
from datetime import date, datetime, timezone

import pytest

from app.pipeline.shared.statistical_dates import uses_latest_statistics, LATEST_STATISTICS_NOTICE
from app.pipeline.shared.context import build_claim_context
from app.pipeline.evidence_assessment.numeric_comparison import compare, claim_limitations
from app.pipeline.evidence_assessment.pdf_comparison import compare_pdf
from tests.pipeline.evidence_assessment.test_numeric_comparison import comparison, CLAIM
from tests.pipeline.evidence_retrieval.test_pdf_reader import reading, TEXT, CLAIM as PDF_CLAIM
from tests.pipeline.evidence_assessment.test_component_assessment import source

NOW = date(2026, 11, 3)
UNDATED = 'The number of unemployed Singapore graduates doubled'


@pytest.mark.parametrize('text', [UNDATED, UNDATED + ' recently', UNDATED + ' according to the latest report',
    'The unemployment rate increased by 30%', 'Median salaries fell by 10 percent'])
def test_undated_change_uses_recent_default(text):
    assert uses_latest_statistics(text)


@pytest.mark.parametrize('suffix', [' from June 2024 to June 2025', ' since 2020', ' last year',
    ' this year', ' over the past five years', ' during the pandemic', ' in Q1',
    " in Jun'25", ' historically', ' from 2020 to 2025', ' year-on-year'])
def test_stated_or_historical_period_is_never_overwritten(suffix):
    assert not uses_latest_statistics(UNDATED + suffix)


@pytest.mark.parametrize('end,stance', [('200','supporting'),('130','contradicting')])
def test_date_omission_alone_does_not_block_either_direction(end, stance):
    data = comparison('100',end)
    data.scope_gaps=['missing_period','different_period']  # Recompute date suitability under the server default.
    vote,gaps,reason=compare(UNDATED,data.quote,data,as_of=NOW)
    assert vote==stance and not gaps
    assert 'No dates were given' in reason and 'June 2024 to June 2025' in reason
    assert not claim_limitations(UNDATED)


def test_other_scope_objections_are_not_removed_by_date_default():
    data=comparison('100','130',population='fresh Singapore graduates')
    vote,gaps,reason=compare('Singapore graduate unemployment doubled',data.quote,data,as_of=NOW)
    assert vote is None and 'different_population' in gaps and 'missing_measure' in gaps
    assert 'missing_period' not in gaps and 'No dates were given' in reason


def test_explicit_dates_are_checked_even_when_another_pair_is_newer():
    data=comparison('100','200')
    assert compare(CLAIM,data.quote,data,as_of=NOW,latest_known=(2026,6))[0]=='supporting'
    assert 'No dates' not in compare(CLAIM,data.quote,data,as_of=NOW)[2]


def test_old_pair_cannot_outvote_newer_comparable_observations():
    data=comparison('100','200')
    assert 'newer_statistics_available' in compare(UNDATED,data.quote,data,as_of=NOW,latest_known=(2026,6))[1]


@pytest.mark.parametrize('first,last,gap', [
    ('June 2010','June 2011','outdated_statistics'),
    ('June 2026','June 2027','future_statistics'),
    ('June 2022','June 2025','incomparable_periods'),
    ('2024','June 2025','incomparable_periods'),
])
def test_default_rejects_old_future_or_irregular_pairs(first,last,gap):
    data=comparison()
    data.quote=data.quote.replace('June 2024',first).replace('June 2025',last)
    data.before.period, data.after.period=first,last
    assert gap in compare(UNDATED,data.quote,data,as_of=NOW)[1]


def test_latest_pdf_pair_is_selected_by_date_not_by_doubling():
    evidence=source(passage=TEXT,scope='established'); evidence.pdf_reading=reading()
    series=evidence.pdf_reading.document.series[0]
    early=series.points[0].model_copy(update={'date_label':'June 2023','year':2023,'value':'50'})
    # 50 -> 100 supports doubling, but the newer 100 -> 130 does not.
    series.points=[series.points[1],early,series.points[0]]
    vote,gaps,reason=compare_pdf(PDF_CLAIM.split(' from')[0],evidence,population_matches=True,as_of=NOW)
    assert vote=='contradicting' and not gaps
    assert 'June 2024 to June 2025' in reason and '30.0%' in reason


def test_other_chart_and_publication_dates_do_not_replace_observation_dates():
    evidence=source(passage=TEXT+' Published September 2026. Employment rate August 2026: 90%.',scope='established')
    evidence.pdf_reading=reading()
    vote,gaps,_=compare_pdf(PDF_CLAIM.split(' from')[0],evidence,population_matches=True,as_of=NOW)
    assert vote=='contradicting' and not gaps


def test_recent_monthly_data_uses_previous_month_not_old_annual_baseline():
    evidence=source(passage=TEXT,scope='established'); evidence.pdf_reading=reading()
    series=evidence.pdf_reading.document.series[0]
    series.points[0]=series.points[0].model_copy(update={'date_label':'September 2026','year':2026,'month':9,'value':'100'})
    series.points[1]=series.points[1].model_copy(update={'date_label':'October 2026','year':2026,'month':10,'value':'200'})
    vote,gaps,reason=compare_pdf(PDF_CLAIM.split(' from')[0],evidence,population_matches=True,as_of=NOW)
    assert vote=='supporting' and not gaps and 'September 2026 to October 2026' in reason


def test_normalised_duplicate_dates_are_ambiguous():
    evidence=source(passage=TEXT,scope='established'); evidence.pdf_reading=reading()
    s=evidence.pdf_reading.document.series[0]
    s.points.append(s.points[-1].model_copy(update={'date_label':"Jun'25",'value':'200'}))
    assert compare_pdf(PDF_CLAIM.split(' from')[0],evidence,population_matches=True,as_of=NOW)[0] is None


def test_context_records_assumption_without_rewriting_claim_or_explicit_date():
    now=datetime(2026,11,3,tzinfo=timezone.utc)
    assert LATEST_STATISTICS_NOTICE in build_claim_context(UNDATED,now).assumptions
    assert LATEST_STATISTICS_NOTICE not in build_claim_context(CLAIM,now).assumptions


def test_default_does_not_turn_one_observation_into_a_comparison():
    evidence=source(passage=TEXT,scope='established'); evidence.pdf_reading=reading()
    evidence.pdf_reading.document.series[0].points=evidence.pdf_reading.document.series[0].points[:1]
    assert compare_pdf(PDF_CLAIM.split(' from')[0],evidence,population_matches=True,as_of=NOW)[0] is None
