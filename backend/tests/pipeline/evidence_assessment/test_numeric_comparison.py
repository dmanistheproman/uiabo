"""Arithmetic and scope regressions use synthetic figures, never desired labels."""
import pytest

from app.pipeline.evidence_assessment.numeric_comparison import NumericComparison, compare, target_ratio
from app.pipeline.evidence_assessment.components import bind_findings, Draft, pairs_for
from app.pipeline.shared.components import decompose_claim
from tests.pipeline.evidence_assessment.test_component_assessment import source


def comparison(a='100', b='200', *, metric='unemployed_count', population='Singapore graduates'):
    measure = 'number unemployed' if metric == 'unemployed_count' else 'unemployment rate'
    quote = f'{population}: {measure}, June 2024: {a}; June 2025: {b}.'
    return NumericComparison(quote=quote,
        before=dict(value=a, period='June 2024', population=population, measure=measure,
                    metric=metric, unit='people' if metric == 'unemployed_count' else 'percent'),
        after=dict(value=b, period='June 2025', population=population, measure=measure,
                   metric=metric, unit='people' if metric == 'unemployed_count' else 'percent'),
        population_matches_claim=True)


CLAIM = 'The number of unemployed Singapore graduates doubled from June 2024 to June 2025'


@pytest.mark.parametrize('a,b,word,stance,summary', [
    ('100', '200', 'doubled', 'supporting', '100.0% increase'),
    ('4,300', '6,000', 'doubled', 'contradicting', '39.5% increase'),
    ('400', '200', 'halved', 'supporting', '50.0% decrease'),
    ('100', '300', 'tripled', 'supporting', '200.0% increase'),
])
def test_deterministic_comparison(a, b, word, stance, summary):
    data = comparison(a, b)
    result, gaps, reason = compare(CLAIM.replace('doubled', word), data.quote, data)
    assert result == stance and not gaps
    assert summary in reason


def test_rounded_rate_consistent_with_doubling_is_not_claimed_false():
    data = comparison('3.3', '6.7', metric='unemployment_rate')
    text = 'Singapore graduates unemployment rate doubled from June 2024 to June 2025'
    assert compare(text, data.quote, data)[0] == 'supporting'


def test_integer_counts_are_compared_as_reported_without_invented_rounding():
    data = comparison('100', '199')
    assert compare(CLAIM, data.quote, data)[0] == 'contradicting'


@pytest.mark.parametrize('text,code', [
    ('The number of unemployed Singapore graduates doubled', 'missing_period'),
    ('Singapore graduate unemployment doubled from June 2024 to June 2025', 'missing_measure'),
    (CLAIM.replace('2024', '2023'), 'different_period'),
    (CLAIM.replace('number of unemployed', 'unemployment rate among'), 'different_measure'),
])
def test_missing_or_incompatible_scope_is_context_not_a_vote(text, code):
    data = comparison()
    stance, gaps, reason = compare(text, data.quote, data)
    assert stance is None and code in gaps
    assert '100.0% increase' in reason


def test_fresh_graduates_do_not_stand_for_all_graduates():
    data = comparison(population='fresh Singapore graduates')
    assert 'different_population' in compare(CLAIM, data.quote, data)[1]


def test_values_must_be_complete_tokens_and_labels_literal():
    data = comparison()
    data.before.value = '10'
    with pytest.raises(ValueError):
        compare(CLAIM, data.quote, data)
    data = comparison()
    data.before.period = 'June 2023'
    with pytest.raises(ValueError):
        compare(CLAIM, data.quote, data)


def test_fabricated_quote_and_zero_baseline_cannot_vote():
    data = comparison()
    with pytest.raises(ValueError):
        compare(CLAIM, 'Different document.', data)
    data = comparison('0', '200')
    assert compare(CLAIM, data.quote, data)[:2] == (None, ['zero_baseline'])


def test_mixed_metrics_cannot_be_used_for_a_change():
    data = comparison()
    data.after.metric = 'employment_rate'
    assert compare(CLAIM, data.quote, data)[0] is None


def test_numerical_vote_uses_calculation_instead_of_model_direction():
    text = CLAIM + ' because companies hired fewer workers.'
    parts = decompose_claim(text)
    data = comparison('100', '130')
    evidence = [source(passage=data.quote, scope='established')]
    drafts = {key: Draft(stance='unresolved', basis='none', scope='unknown', decisiveness=.1,
                        explanation='The passage does not establish this part.') for key in pairs_for(parts, evidence)}
    drafts['event_s0'] = Draft(stance='supporting', basis='direct', scope='established',
        decisiveness=.95, explanation='Model arithmetic is not trusted.', comparison=data)
    findings = bind_findings(parts, evidence, drafts, .5)
    assert findings[0].stance == 'contradicting'
    assert '30.0% increase' in findings[0].explanation
    assert findings[2].stance == 'unresolved'  # Arithmetic does not establish a cause.


def test_exact_rejection_reason_preserves_established_scope():
    parts = decompose_claim('The council is closing the bridge because inspectors found damage.')
    evidence = [source()]
    drafts = {key: Draft(stance='contradicting', basis='direct', scope='established',
                        decisiveness=.1, explanation='This weighs against the claim.')
              for key in pairs_for(parts, evidence)}
    finding = bind_findings(parts, evidence, drafts, .5)[0]
    assert finding.stance == 'unresolved'
    assert finding.scope_status == 'established'
    assert finding.reason_codes == ['below_decisiveness_threshold']
    assert 'population' not in finding.explanation and 'weighs against' not in finding.explanation


@pytest.mark.parametrize('text,expected', [('grew by 20 percent', '1.2'), ('fell by 50 percent', '.5')])
def test_percentage_wording(text, expected):
    from decimal import Decimal
    assert target_ratio(text) == Decimal(expected)


def test_claim_percentage_precision_is_respected():
    data = comparison('4,300', '6,000')
    text = CLAIM.replace('doubled', 'increased by 39.5%')
    assert compare(text, data.quote, data)[0] == 'supporting'


def test_numeric_rejection_cannot_be_bypassed_through_cause():
    text = 'Singapore graduate unemployment doubled because companies hire foreigners at half the salary.'
    parts = decompose_claim(text)
    evidence = [source(passage='Graduate unemployment rate declined from 39.0% to 34.8%.')]
    drafts = {key: Draft(stance='contradicting', basis='direct', scope='established',
        decisiveness=.95, explanation='The event did not double so the whole message is false.')
        for key in pairs_for(parts, evidence)}
    findings = bind_findings(parts, evidence, drafts, .5)
    causal = next(f for f in findings if f.component_id == 'causal_link')
    assert causal.stance == 'unresolved' and 'missing_causal_evidence' in causal.reason_codes


def test_salary_minimum_cannot_refute_actual_foreign_local_pay():
    text = 'Graduate unemployment doubled because companies hire foreigners at half the salary.'
    parts = decompose_claim(text)
    evidence = [source(passage='Employment Pass applicants require a minimum qualifying salary of $5,600.')]
    drafts = {key: Draft(stance='contradicting', basis='direct', scope='established',
        decisiveness=.95, explanation='A minimum disproves lower actual pay.') for key in pairs_for(parts, evidence)}
    premise = next(f for f in bind_findings(parts, evidence, drafts, .5) if f.component_id == 'premise')
    assert premise.stance == 'unresolved'
    assert 'salary_minimum_not_actual_pay' in premise.reason_codes


def test_unambiguous_causal_denial_is_not_blocked_by_missing_statistics():
    text = 'Graduate unemployment doubled because companies hire foreigners at half the salary.'
    parts = decompose_claim(text)
    passage = 'The investigation found that hiring foreigners did not cause graduate unemployment to increase.'
    evidence = [source(passage=passage, scope='established')]
    drafts = {key: Draft(stance='unresolved', basis='none', scope='unknown',
        decisiveness=.1, explanation='No comparison.') for key in pairs_for(parts, evidence)}
    drafts['causal_link_s0'] = Draft(stance='contradicting', basis='direct', scope='established',
        decisiveness=.95, explanation='The investigation explicitly rejects this cause.', causal_quote=passage)
    causal = next(f for f in bind_findings(parts, evidence, drafts, .5) if f.component_id == 'causal_link')
    assert causal.stance == 'contradicting'


@pytest.mark.parametrize('wording', ['has not doubled', 'will double', 'may double', 'has at least doubled', 'has nearly doubled'])
def test_qualified_claims_are_not_reduced_to_exact_equality(wording):
    assert target_ratio('Unemployment ' + wording) is None


def test_may_as_a_month_does_not_disable_comparison():
    assert target_ratio('Unemployment doubled from May 2024 to May 2025') == 2


def test_reverse_periods_cannot_reverse_a_verdict():
    data = comparison()
    data.before, data.after = data.after, data.before
    assert 'different_period' in compare(CLAIM, data.quote, data)[1]


def test_population_reordering_binds_source_words_without_inventing_qualifiers():
    from app.pipeline.evidence_assessment.numeric_comparison import population_phrase
    text = 'The graduates from the 2025 cohort were surveyed.'
    assert population_phrase('2025 cohort graduates', text) == 'graduates from the 2025 cohort'
    assert population_phrase('all 2025 cohort graduates', text) is None
    assert population_phrase('Singapore 2025 cohort graduates', text) is None


def test_alternative_cause_does_not_disprove_the_alleged_cause():
    text = 'Graduate unemployment doubled because companies hire foreigners at half the salary.'
    parts = decompose_claim(text)
    passage = 'More graduates entered the labour force as a result of completing their studies.'
    evidence = [source(passage=passage, scope='established')]
    drafts = {key: Draft(stance='unresolved', basis='none', scope='unknown', decisiveness=.1,
        explanation='No comparison.') for key in pairs_for(parts, evidence)}
    drafts['causal_link_s0'] = Draft(stance='contradicting', basis='inference', scope='established',
        decisiveness=.95, explanation='A different cause was mentioned.', causal_quote=passage)
    causal = next(f for f in bind_findings(parts, evidence, drafts, .5) if f.component_id == 'causal_link')
    assert causal.stance == 'unresolved'
