"""Offline regression tests for claim-wide, quote-bound verification."""
import asyncio
import json

import httpx
import pytest

from app.pipeline.evidence_assessment import pool, verification as v
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult
from app.pipeline.shared.verification import VerificationPlan, VerificationAssertion


def claim(text, assertions=None):
    assertions = assertions or [dict(id='a1', text=text)]
    parts = [VerificationAssertion(**a, evidence_questions=['Which applicable facts establish this assertion?'],
                                  queries=[a['text'][:300]]) for a in assertions]
    return ClaimAnalysis(extracted_claim=text, claim_category='factual', checkable=True,
        classification_reason='Test factual claim', claim_confidence=1,
        verification_plan=VerificationPlan(source_text=text, assertions=parts, as_of='2026-11-03'))


def source(id, passage, scope='missing_context', score=.5, type='government'):
    return EvidenceCandidate(evidence_id=id, title='Official source',
        url=f'https://example.gov.sg/{id}', publisher='Official publisher', passage=passage,
        source_type=type, retrieval_score=score, retrieved_at='2026-11-03T00:00:00Z',
        provenance=EvidenceProvenance(source_policy='government_namespace', source_reason='Official domain',
            origin_group='one-official-origin', discovery_method='preferred_search',
            relevance='context', relevance_reason='This source establishes one required fact.',
            relevance_quote=passage[:1800], applicability=scope,
            applicability_reason='The complete claim needs the other evidence.'))


def draft(assertion_id, sources, status='supported', **changes):
    data = dict(assertion_id=assertion_id, status=status,
        citations=[dict(evidence_id=s.evidence_id, quote=s.passage) for s in sources],
        explanation='The cited facts together establish this assertion.', basis='direct',
        scope='established', scope_checks={k: 'established' for k in v.VerificationScopeChecks.model_fields},
        decisiveness=.95, reasoning_type='linked_facts')
    data.update(changes)
    return v.DraftFinding(**data)


def assess(c, sources, findings):
    retrieval = RetrievalResult(retrieval_status='completed', evidence=sources)
    coverage = v.bind_findings(c, retrieval, v.Draft(findings=findings))
    return v.assemble(c, retrieval, coverage)


def mock_responses(monkeypatch, responses):
    """Exercise the real request parser without external model calls."""
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        content = responses[len(requests) - 1]
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps(content)}})
    client_type = httpx.AsyncClient
    monkeypatch.setattr(v.httpx, 'AsyncClient', lambda **kwargs:
        client_type(**kwargs, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(pool, '_provider_keys', lambda: (None, 'fake'))
    return requests


def unresolved_draft(id):
    return draft(id, [], status='unresolved', basis='none', scope='unknown',
        reasoning_type='none', decisiveness=0.,
        explanation='The supplied sources do not establish this assertion.', gaps=['missing_evidence']).model_dump()


def wire_finding(id='a1', evidence_id='policy', **updates):
    value = dict(assertion_id=id, status='contradicted',
        citations=[dict(evidence_id=evidence_id, start_sentence=0, end_sentence=0)],
        explanation='The same policy has an incompatible value in the applicable official source.',
        scope_checks={key: 'established' for key in v.VerificationScopeChecks.model_fields},
        decisiveness=.95, reasoning_type='incompatible_rule', comparisons=[], scope_resolutions=[],
        gaps=[], repair_queries=[])
    value.update(updates)
    return value


def test_joint_ownership_chain_resolves_earlier_missing_context_and_counts_once():
    c = claim('The government owns a controlling stake in Airline A.')
    sources = [source('owner', 'Investment Company B is wholly owned by the government.'),
               source('stake', 'Investment Company B owns 60% of Airline A voting shares.')]
    result = assess(c, sources, [draft('a1', sources)])
    assert result.assessment_outcome == 'supported'
    assert result.scoring.supporting_origins == 1
    assert result.scoring.supporting_strength == .9
    assert len(result.verification.findings[0].citations) == 2
    assert all(s.provenance.applicability == 'missing_context' and s.retrieval_score == .5 for s in sources)


def test_ownership_chain_does_not_establish_management():
    c = claim('Airline A is managed by the government.')
    sources = [source('owner', 'Investment Company B is wholly owned by the government.'),
               source('stake', 'Investment Company B owns 60% of Airline A voting shares.')]
    result = assess(c, sources, [draft('a1', sources)])
    assert result.assessment_outcome == 'insufficient_evidence'
    assert 'missing_management_evidence' in result.verification.findings[0].gaps


def test_decisive_validated_scope_can_resolve_low_retrieval_rank():
    c = claim('The event is free.')
    sources = [source('fee', 'Admission to this event costs ten dollars per person.')]
    result = assess(c, sources, [draft('a1', sources, status='contradicted', reasoning_type='incompatible_rule')])
    assert result.assessment_outcome == 'contradicted'
    assert result.assessed_evidence[0].stance == 'contradicting'
    assert result.assessed_evidence[0].quality_score > .5


def test_confirmed_scope_mismatch_remains_rejected():
    c = claim('The event is free.')
    sources = [source('fee', 'Admission to another event costs ten dollars.', scope='different_scope')]
    result = assess(c, sources, [draft('a1', sources, status='contradicted')])
    assert result.assessment_outcome == 'insufficient_evidence'
    assert 'different_scope' in result.verification.findings[0].gaps


def test_whole_claim_scope_hint_can_be_resolved_for_quoted_intermediate_link():
    c = claim('The government owns a controlling stake in Airline A.')
    owner = source('owner', 'Investment Company B is wholly owned by the government.', scope='different_scope')
    stake = source('stake', 'Investment Company B owns 60% of Airline A voting shares.')
    resolution = dict(evidence_id='owner', quote=owner.passage, claim_span='government',
        role='intermediate_fact', bridge='Investment Company B',
        explanation='This supplies the government-to-investment-company link; the second passage supplies the airline link.')
    result = assess(c, [owner, stake], [draft('a1', [owner, stake], scope_resolutions=[resolution])])
    assert result.assessment_outcome == 'supported'
    assert result.verification.findings[0].scope_resolutions[0].quote == owner.passage
    assert owner.provenance.applicability == 'different_scope'


def test_two_sources_without_a_quoted_bridge_cannot_override_scope():
    c = claim('The government owns a controlling stake in Airline A.')
    owner = source('owner', 'Investment Company B is wholly owned by the government.', scope='different_scope')
    unrelated = source('other', 'Investment Company C owns 60% of Airline A voting shares.')
    resolution = dict(evidence_id='owner', quote=owner.passage, claim_span='government',
        role='intermediate_fact', bridge='Investment Company B',
        explanation='The sources supposedly establish a chain, but their intermediaries are different.')
    result = assess(c, [owner, unrelated], [draft('a1', [owner, unrelated], scope_resolutions=[resolution])])
    assert result.assessment_outcome == 'insufficient_evidence'


def test_existing_configured_threshold_is_retained(monkeypatch):
    monkeypatch.setattr(pool, 'settles_threshold', lambda provider: .85)
    c = claim('The event is free.')
    sources = [source('fee', 'Admission costs ten dollars per person.')]
    result = assess(c, sources, [draft('a1', sources, status='contradicted', decisiveness=.8)])
    assert result.assessment_outcome == 'insufficient_evidence'
    assert 'below_evidence_adequacy_threshold' in result.verification.findings[0].gaps


def test_proof_quality_cannot_exceed_evidence_adequacy(monkeypatch):
    monkeypatch.setattr(pool, 'settles_threshold', lambda provider: .5)
    c = claim('The event is free.')
    sources = [source('fee', 'Admission costs ten dollars per person.')]
    result = assess(c, sources, [draft('a1', sources, status='contradicted', decisiveness=.65)])
    assert result.scoring.contradicting_strength == .65


def test_current_rule_does_not_disprove_private_discussions():
    c = claim('Officials are discussing raising the retirement age to 75.')
    sources = [source('policy', 'The current retirement age is 64, with an announced target of 65.')]
    result = assess(c, sources, [draft('a1', sources, status='contradicted', reasoning_type='incompatible_rule')])
    assert result.assessment_outcome == 'insufficient_evidence'
    assert 'missing_discussion_evidence' in result.verification.findings[0].gaps


def test_adopted_schedule_can_refute_asserted_change_while_cause_is_unresolved():
    event = 'Officials are raising the annual permit fee to 90 dollars'
    text = event + ' because the permit fund is depleted.'
    c = claim(text, [dict(id='a1', text=event, kind='change'),
                     dict(id='a2', text=text, kind='causal')])
    policy = source('schedule',
        'The adopted annual permit fee schedule is 40 dollars from 1 July 2026 '
        'and 50 dollars from 1 January 2027.', scope='established', score=.2)
    explanation = ('The official adopted schedule sets the same annual permit fee at '
        '40 dollars now and 50 dollars from January 2027. Those are incompatible '
        'with the claimed adopted increase to 90 dollars as of 3 November 2026.')
    findings = [draft('a1', [policy], status='contradicted', reasoning_type='incompatible_rule',
                      explanation=explanation),
                draft('a2', [], status='unresolved', basis='none', scope='unknown',
                      reasoning_type='none', decisiveness=0., gaps=['missing_causal_evidence'],
                      explanation='No supplied evidence establishes the alleged fund depletion or causal relationship.')]

    result = assess(c, [policy], findings)

    assert result.assessment_outcome == 'contradicted'
    assert result.verification.findings[0].citations[0].quote == policy.passage
    assert result.verification.findings[1].status == 'unresolved'
    assert result.scoring.contradicting_strength == .89
    assert result.assessed_evidence[0].stance == 'contradicting'
    assert policy.provenance.relevance == 'context' and policy.retrieval_score == .2


def test_adopted_schedule_can_refute_complete_material_clause_in_causal_assertion():
    event = 'Officials are raising the annual permit fee to 90 dollars'
    text = event + ' because the permit fund is depleted.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    policy = source('schedule',
        'The adopted annual permit fee schedule is 40 dollars from 1 July 2026 '
        'and 50 dollars from 1 January 2027.', scope='established')
    counterfact = dict(evidence_id=policy.evidence_id, quote=policy.passage,
        claim_span=event,
        explanation='The adopted schedule for the same fee specifies an increase to 50 dollars, not 90 dollars.',
        scope_checks={k: 'established' for k in v.VerificationScopeChecks.model_fields})

    result = assess(c, [policy], [draft('a1', [policy], status='contradicted',
        reasoning_type='incompatible_rule', material_counterfact=counterfact)])

    assert result.assessment_outcome == 'contradicted'
    assert result.verification.findings[0].material_counterfact.claim_span == event
    assert 'causal connection remains unresolved' in result.explanation
    assert result.scoring.contradicting_strength == .89


@pytest.mark.parametrize('scope_status', ['unknown', 'different'])
def test_different_policy_values_cannot_bypass_effective_date_scope(scope_status):
    policy = source('schedule', 'The annual permit fee is 40 dollars from 1 July 2026.')
    checks = {k: 'established' for k in v.VerificationScopeChecks.model_fields}
    checks['time'] = scope_status

    with pytest.raises(ValueError, match='scope requirement unresolved'):
        draft('a1', [policy], status='contradicted', reasoning_type='incompatible_rule',
              scope_checks=checks,
              explanation='This current fee does not establish the fee in the later claimed period.')


def test_policy_comparison_receives_assessment_date_and_source_version_url():
    c = claim('Officials are raising the annual permit fee to 90 dollars.',
        [dict(id='a1', text='Officials are raising the annual permit fee to 90 dollars.', kind='change')])
    policy = source('archive', 'Revised edition published on 1 July 2000. The annual permit fee is 40 dollars.')
    policy.url = 'https://example.gov.sg/versions/2000-07-01/permits'
    retrieval = RetrievalResult(retrieval_status='completed', evidence=[policy])

    state = json.loads(v.format_state(c, retrieval))

    assert state['plan']['as_of'] == '2026-11-03'
    assert state['sources'][0]['url'] == str(policy.url)
    assert state['sources'][0]['source_version'] == {
        'kind': 'dated_version', 'version_date': '2000-07-01', 'basis': 'dated_version_route'}
    assert state['sources'][0]['passage'] == policy.passage


def test_material_false_premise_is_not_cancelled_by_unknown_cause():
    text = 'Admission is free because a donor paid the fees.'
    c = claim(text, [dict(id='a1', text='Admission is free'),
                     dict(id='a2', text='because a donor paid the fees', kind='causal')])
    sources = [source('fee', 'Admission to the event costs ten dollars per person.')]
    findings = [draft('a1', sources, status='contradicted', reasoning_type='incompatible_rule'),
                draft('a2', [], status='unresolved', basis='none', scope='unknown',
                      reasoning_type='none', decisiveness=.1,
                      explanation='There is no evidence addressing the alleged donor.', gaps=['missing_causal_evidence'])]
    result = assess(c, sources, findings)
    assert result.assessment_outcome == 'contradicted'
    assert 'Other parts remain unresolved' in result.explanation
    assert result.scoring.contradicting_strength == .89
    assert result.verification.findings[1].status == 'unresolved'


def test_partial_support_does_not_verify_a_causal_compound_message():
    text = 'Admission is free because a donor paid the fees.'
    c = claim(text, [dict(id='a1', text='Admission is free'),
                     dict(id='a2', text='because a donor paid the fees', kind='causal')])
    sources = [source('fee', 'Admission to the event is free for all visitors.')]
    findings = [draft('a1', sources), draft('a2', [], status='unresolved', basis='none',
        scope='unknown', reasoning_type='none', decisiveness=.1, gaps=['missing_causal_evidence'])]
    result = assess(c, sources, findings)
    assert result.assessment_outcome == 'insufficient_evidence'
    assert result.verification.findings[0].status == 'supported'
    assert result.misinformation_risk_score is None


def test_fallback_causal_claim_can_be_refuted_by_a_grounded_material_fact():
    text = 'Baymere Reservoir is completely empty because illegal pipes have drained it.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('level', 'Baymere Reservoir is at 85% of usable storage capacity. The reservoir is not empty. This report does not establish whether illegal pipes exist.')
    counterfact = dict(evidence_id='level', quote=s.passage,
        claim_span='Baymere Reservoir is completely empty',
        explanation='An applicable measurement of 85% contradicts the claim that the reservoir is empty.',
        scope_checks={k: 'established' for k in v.VerificationScopeChecks.model_fields})
    result = assess(c, [s], [draft('a1', [s], status='contradicted',
        reasoning_type='explicit_statement', material_counterfact=counterfact)])
    assert result.assessment_outcome == 'contradicted'
    assert result.scoring.contradicting_strength == .89
    assert result.verification.findings[0].material_counterfact.claim_span == counterfact['claim_span']
    assert 'causal connection remains unresolved' in result.explanation


def test_counterfact_cannot_crop_away_private_discussion_modality():
    text = 'Officials are discussing raising the retirement age to 75 because reserves are declining.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('policy', 'The retirement age is 64. This statement concerns the current published rule.')
    counterfact = dict(evidence_id='policy', quote=s.passage, claim_span='raising the retirement age to 75',
        explanation='The current rule is a different number.',
        scope_checks={k: 'established' for k in v.VerificationScopeChecks.model_fields})
    with pytest.raises(ValueError, match='complete event or premise clause'):
        assess(c, [s], [draft('a1', [s], status='contradicted', material_counterfact=counterfact)])


def test_counterfact_cannot_crop_away_negation():
    text = 'Baymere Reservoir is not completely empty because heavy rain refilled it.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('level', 'Baymere Reservoir is not empty. Its storage capacity is 85%.')
    counterfact = dict(evidence_id='level', quote=s.passage, claim_span='completely empty',
        explanation='This cropped phrase would reverse the meaning of the original claim.',
        scope_checks={k: 'established' for k in v.VerificationScopeChecks.model_fields})
    with pytest.raises(ValueError, match='complete event or premise clause'):
        assess(c, [s], [draft('a1', [s], status='contradicted', material_counterfact=counterfact)])


def test_true_numerical_premise_cannot_promote_whole_causal_claim_to_supported():
    text = 'The unemployment rate doubled from 2024 to 2025 because firms closed.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('data', 'The resident unemployment rate was 2% in 2024 and 4% in 2025.')
    counterfact = dict(evidence_id='data', quote=s.passage,
        claim_span='The unemployment rate doubled from 2024 to 2025',
        explanation='The proposed counterfact must be checked against the actual arithmetic.',
        scope_checks={k: 'established' for k in v.VerificationScopeChecks.model_fields})
    point = dict(population='resident', measure='unemployment rate', metric='unemployment_rate', unit='percent')
    comparison = dict(evidence_id='data', before=dict(**point, value='2', period='2024'),
                      after=dict(**point, value='4', period='2025'))
    result = assess(c, [s], [draft('a1', [s], status='contradicted', material_counterfact=counterfact,
                                 comparisons=[comparison])])
    assert result.assessment_outcome == 'insufficient_evidence'
    assert result.verification.findings[0].material_counterfact is None
    assert 'material_counterfact_not_contradicted' in result.verification.findings[0].gaps


def test_causal_support_still_requires_relationship_evidence():
    text = 'Baymere Reservoir is completely empty because illegal pipes have drained it.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('level', 'Baymere Reservoir has no water left. The report does not investigate pipes.')
    result = assess(c, [s], [draft('a1', [s], status='supported')])
    assert result.assessment_outcome == 'insufficient_evidence'
    assert 'missing_causal_evidence' in result.verification.findings[0].gaps


@pytest.mark.parametrize('alteration', ['unknown_id', 'invented_quote', 'missing_assertion'])
def test_provider_contract_rejects_ungrounded_or_incomplete_output(alteration):
    c = claim('The event is free.')
    sources = [source('fee', 'Admission costs ten dollars per person.')]
    finding = draft('a1', sources, status='contradicted')
    if alteration == 'unknown_id':
        finding.citations[0].evidence_id = 'invented'
    elif alteration == 'invented_quote':
        finding.citations[0].quote = 'The event definitely charges a thousand dollars.'
    else:
        finding.assertion_id = 'a2'
    with pytest.raises(ValueError):
        v.bind_findings(c, RetrievalResult(retrieval_status='completed', evidence=sources), v.Draft(findings=[finding]))


def test_quote_layout_and_typography_are_restored_to_original_contiguous_span():
    c = claim('The council owns the company.')
    s = source('owner', 'The council\u2019s\n\nonly investment company is wholly owned by the council.')
    value = draft('a1', [s])
    value.citations[0].quote = "The council's only investment company is wholly owned by the council."
    result = assess(c, [s], [value])
    assert result.verification.findings[0].citations[0].quote == s.passage


def test_ellipsis_cannot_join_noncontiguous_passage_fragments():
    c = claim('The council owns the company.')
    s = source('owner', 'The council appointed a reviewer. The company is privately owned.')
    value = draft('a1', [s])
    value.citations[0].quote = 'The council ... company is privately owned.'
    with pytest.raises(ValueError, match='contiguous span'):
        assess(c, [s], [value])


def test_blank_quote_cannot_expand_to_entire_passage():
    from app.pipeline.evidence_assessment.semantic import source_quote
    with pytest.raises(ValueError, match='must contain'):
        source_quote(' \n \t ', 'The full passage cannot be manufactured from an empty quotation.')


def test_numeric_claim_requires_grounded_same_measure_comparison():
    c = claim('The number of unemployed residents doubled from 2024 to 2025.')
    s = source('data', 'The resident unemployment rate was 2% in 2024 and 3% in 2025.')
    comparison = dict(evidence_id='data',
        before=dict(value='2', period='2024', population='resident', measure='unemployment rate',
                    metric='unemployment_rate', unit='percent'),
        after=dict(value='3', period='2025', population='resident', measure='unemployment rate',
                   metric='unemployment_rate', unit='percent'))
    result = assess(c, [s], [draft('a1', [s], status='contradicted',
                                 reasoning_type='measured_comparison', comparisons=[comparison])])
    assert result.assessment_outcome == 'insufficient_evidence'
    assert result.verification.findings[0].gaps


def test_general_percentage_rate_uses_arithmetic_without_confusing_count():
    c = claim('The household recycling participation rate doubled between 2024 and 2025.')
    s = source('data', 'In 2024 there were 1,000 participating households out of 2,000 eligible households: a participation rate of 50%. '
        'In 2025 there were 2,000 participating households out of 4,000 eligible households: a participation rate of 50%.')
    point = dict(value='50%', population='households', measure='participation rate', metric='other', unit='percent')
    comparison = dict(evidence_id='data', before=dict(**point, period='2024'), after=dict(**point, period='2025'))
    result = assess(c, [s], [draft('a1', [s], status='contradicted',
        reasoning_type='measured_comparison', comparisons=[comparison])])
    assert result.assessment_outcome == 'contradicted'
    assert result.verification.findings[0].status == 'contradicted'


def test_decisive_numerical_response_missing_comparison_is_a_contract_gap():
    c = claim('The household recycling participation rate doubled between 2024 and 2025.')
    s = source('data', 'The household participation rate was 50% in 2024 and 50% in 2025.')
    with pytest.raises(ValueError, match='requires comparisons'):
        v.bind_findings(c, RetrievalResult(retrieval_status='completed', evidence=[s]),
                       v.Draft(findings=[draft('a1', [s], status='contradicted')]))


def test_causal_span_containing_doubled_keeps_causal_gap_explanation():
    text = 'Unemployment doubled because employers hired foreigners.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('data', 'The unemployment rate was 2% in 2024 and 4% in 2025.')
    reason = 'The statistic does not establish why unemployment changed.'
    result = assess(c, [s], [draft('a1', [s], status='unresolved', basis='none', scope='unknown',
        reasoning_type='none', decisiveness=.1, explanation=reason, gaps=['missing_causal_evidence'])])
    assert result.verification.findings[0].explanation == reason
    assert 'missing_comparison' not in result.verification.findings[0].gaps


def test_no_evidence_generates_specific_repair_without_provider(monkeypatch):
    c = claim('The event is free.')
    result = asyncio.run(v.assess_verification(c, RetrievalResult(retrieval_status='no_evidence')))
    assert result.assessment_outcome == 'insufficient_evidence'
    assert result.verification.repair_queries == ['The event is free.']


def test_provider_failure_is_not_an_insufficient_evidence_result(monkeypatch):
    monkeypatch.setattr(pool, '_provider_keys', lambda: (None, None))
    with pytest.raises(PipelineComponentError) as err:
        asyncio.run(v.assess_verification(claim('The event is free.'),
            RetrievalResult(retrieval_status='completed', evidence=[source('a', 'The event is free for everyone.')])) )
    assert err.value.retryable
    assert err.value.error_code == 'ASSESSMENT_UNAVAILABLE'


def test_structured_contract_failure_gets_one_correction_retry(monkeypatch):
    c = claim('The event is free.')
    sources = [source('a', 'The event is free for all visitors.')]
    calls = []
    async def fake(client, state, correction=False):
        calls.append(bool(correction))
        f = draft('a1', sources)
        if not correction:
            f.citations[0].evidence_id = 'unknown'
        return v.Draft(findings=[f])
    monkeypatch.setattr(v, '_call_oss', fake)
    monkeypatch.setattr(pool, '_provider_keys', lambda: (None, 'fake'))
    output = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=sources)))
    assert calls == [False, True]
    assert output.findings[0].citations[0].evidence_id == 'a'


def test_quote_correction_names_citation_and_accepts_separate_exact_spans(monkeypatch):
    c = claim('The annual permit fee is 90 dollars.')
    first = 'The annual permit fee is 40 dollars from July 2026.'
    second = 'The annual permit fee will rise to 50 dollars from January 2027.'
    s = source('fee-schedule', first + '\n\nApplications may be submitted online.\n\n' + second)
    corrections = []
    async def fake(client, state, correction=None):
        corrections.append(correction)
        raw = draft('a1', [s], status='contradicted', reasoning_type='incompatible_rule').model_dump()
        quotes = [first, second] if correction else [first + '\n' + second]
        raw['citations'] = [dict(evidence_id=s.evidence_id, quote=quote) for quote in quotes]
        return v.Draft.model_validate({'findings': [raw]})
    monkeypatch.setattr(v, '_call_oss', fake)
    monkeypatch.setattr(pool, '_provider_keys', lambda: (None, 'fake'))

    output = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert len(corrections) == 2 and corrections[0] is None
    assert 'Assertion a1, citation 1 (fee-schedule)' in corrections[1]
    assert 'contiguous span' in corrections[1] and 'separate citations' in corrections[1]
    assert [item.quote for item in output.findings[0].citations] == [first, second]


@pytest.mark.parametrize('counterfact,expected', [
    (True, 'material_counterfact requires every scope_checks value to be established or not_applicable'),
    (False, 'A decisive status cannot have unknown/different scope_checks'),
])
def test_scope_correction_explains_local_validator_without_echoing_input(monkeypatch, counterfact, expected):
    event = 'The annual permit fee is 90 dollars'
    text = event + ' because the permit fund is depleted.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('fee-schedule', 'The annual permit fee is 40 dollars from July 2026.')
    corrections = []
    async def fake(client, state, correction=None):
        corrections.append(correction)
        if correction:
            return v.Draft(findings=[draft('a1', [], status='unresolved', basis='none',
                scope='unknown', reasoning_type='none', decisiveness=0.,
                explanation='The available source does not establish the relevant period.')])
        raw = draft('a1', [s], status='contradicted', explanation='provider-input-sentinel').model_dump()
        if counterfact:
            checks = {key: 'established' for key in v.VerificationScopeChecks.model_fields}
            checks['time'] = 'unknown'
            raw['material_counterfact'] = dict(evidence_id=s.evidence_id, quote=s.passage,
                claim_span=event, explanation='provider-input-sentinel', scope_checks=checks)
        else:
            raw['scope_checks']['time'] = 'unknown'
        return v.Draft.model_validate({'findings': [raw]})
    monkeypatch.setattr(v, '_call_oss', fake)
    monkeypatch.setattr(pool, '_provider_keys', lambda: (None, 'fake'))

    output = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert len(corrections) == 2 and corrections[0] is None
    assert expected in corrections[1]
    assert 'provider-input-sentinel' not in corrections[1]
    assert 'findings.0' in corrections[1]
    assert output.findings[0].status == 'unresolved'


def test_untrusted_exception_payload_is_not_sent_in_correction_and_retry_stays_bounded(monkeypatch):
    corrections = []
    async def fake(client, state, correction=None):
        corrections.append(correction)
        raise ValueError('provider-error-payload-sentinel')
    monkeypatch.setattr(v, '_call_oss', fake)
    monkeypatch.setattr(pool, '_provider_keys', lambda: (None, 'fake'))

    with pytest.raises(PipelineComponentError):
        asyncio.run(v.judge(claim('The event is free.'), RetrievalResult(retrieval_status='completed',
            evidence=[source('fee', 'The event is free for all visitors.')])) )

    assert len(corrections) == 2 and corrections[0] is None
    assert 'Invalid verification response' in corrections[1]
    assert 'provider-error-payload-sentinel' not in corrections[1]


def test_repair_request_requires_complete_findings_including_unresolved_assertions():
    c = claim('The event is free. The venue is open.',
        [dict(id='a1', text='The event is free.'), dict(id='a2', text='The venue is open.')])
    s = source('event', 'The event is free for all visitors.')
    raw = {'findings': [draft('a1', [s]).model_dump(),
        draft('a2', [], status='unresolved', basis='none', scope='unknown',
              reasoning_type='none', decisiveness=0.).model_dump()]}
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps(raw)}})
    async def run():
        async with httpx.AsyncClient(base_url='https://ollama.com', transport=httpx.MockTransport(handler)) as client:
            return await v._call_oss(client,
                v.format_state(c, RetrievalResult(retrieval_status='completed', evidence=[s])),
                correction='Assertion a1 citation needs an exact source quotation.')

    result = asyncio.run(run())

    prompt = requests[0]['messages'][0]['content']
    assert 'exactly these assertion IDs: a1, a2' in prompt
    assert 'COMPLETE replacement JSON, not a patch or only corrected findings' in prompt
    assert 'including unresolved findings' in prompt
    assert [finding.assertion_id for finding in result.findings] == ['a1', 'a2']
    assert result.findings[1].status == 'unresolved'


def test_pending_only_repair_preserves_fully_validated_first_finding(monkeypatch):
    c = claim('The event is free. The venue is open.',
        [dict(id='a1', text='The event is free.'), dict(id='a2', text='The venue is open.')])
    s = source('event', 'Admission costs ten dollars. The venue is open on Saturday.')
    first = draft('a1', [s], status='contradicted', reasoning_type='incompatible_rule').model_dump()
    invalid = draft('a2', [s]).model_dump()
    invalid['citations'][0]['quote'] = 'The venue is open every day.'
    requests = mock_responses(monkeypatch, [
        {'findings': [first, invalid]}, {'findings': [unresolved_draft('a2')]}])

    result = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert len(requests) == 2
    repair_state = json.loads(requests[1]['messages'][1]['content'])
    assert [a['id'] for a in repair_state['plan']['assertions']] == ['a2']
    assert repair_state['plan']['source_text'] == c.extracted_claim
    assert repair_state['plan']['as_of'] == '2026-11-03'
    assert ''.join(unit['text'] for unit in repair_state['sources'][0]['sentences']) == s.passage
    assert 'passage' not in repair_state['sources'][0]
    assert repair_state['previously_validated_findings'][0]['finding']['status'] == 'contradicted'
    assert repair_state['previously_validated_findings'][0]['finding']['citations'][0]['quote'] == s.passage
    assert 'Do not return or revise those completed IDs' in requests[1]['messages'][0]['content']
    assert [f.assertion_id for f in result.findings] == ['a1', 'a2']
    assert result.findings[0].model_dump() == first
    assert result.findings[1].status == 'unresolved'


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'unknown', 'extra_root'])
def test_invalid_envelope_cannot_seed_retained_findings(monkeypatch, defect):
    c = claim('The event is free. The venue is open.',
        [dict(id='a1', text='The event is free.'), dict(id='a2', text='The venue is open.')])
    s = source('event', 'Admission costs ten dollars. The venue is open on Saturday.')
    first = draft('a1', [s], status='contradicted').model_dump()
    broken = {'findings': [first, unresolved_draft('a2')]}
    if defect == 'missing':
        broken['findings'].pop()
    elif defect == 'duplicate':
        broken['findings'][1]['assertion_id'] = 'a1'
    elif defect == 'unknown':
        broken['findings'][1]['assertion_id'] = 'a5'
    else:
        broken['unrequested'] = 'provider-input-sentinel'
    requests = mock_responses(monkeypatch, [broken,
        {'findings': [unresolved_draft('a1'), unresolved_draft('a2')]}])

    result = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert len(requests) == 2
    repair_state = json.loads(requests[1]['messages'][1]['content'])
    assert [a['id'] for a in repair_state['plan']['assertions']] == ['a1', 'a2']
    assert 'previously_validated_findings' not in repair_state
    assert all(f.status == 'unresolved' for f in result.findings)


def test_repair_cannot_replace_completed_id_or_hide_pending_id(monkeypatch):
    c = claim('The event is free. The venue is open.',
        [dict(id='a1', text='The event is free.'), dict(id='a2', text='The venue is open.')])
    s = source('event', 'Admission costs ten dollars. The venue is open on Saturday.')
    valid = draft('a1', [s], status='contradicted').model_dump()
    invalid = {'assertion_id': 'a2', 'status': 'supported'}
    requests = mock_responses(monkeypatch, [{'findings': [valid, invalid]},
        {'findings': [unresolved_draft('a1')]}])

    with pytest.raises(PipelineComponentError) as error:
        asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert len(requests) == 2 and error.value.error_code == 'ASSESSMENT_UNAVAILABLE'


def test_invalid_causal_duplicate_uses_only_independent_exact_clause_proof(monkeypatch):
    event = 'Officials are raising the annual permit fee to 90 dollars'
    text = event + ' because the permit fund is depleted.'
    c = claim(text, [dict(id='a1', text=event, kind='change'),
                     dict(id='a2', text='the permit fund is depleted'),
                     dict(id='a3', text=text, kind='causal')])
    s = source('schedule', 'The adopted annual permit fee increase is to 50 dollars from January 2027.', scope='established')
    event_finding = draft('a1', [s], status='contradicted', reasoning_type='incompatible_rule').model_dump()
    invalid_causal = {'assertion_id': 'a3', 'status': 'contradicted', 'basis': 'none',
        'citations': [], 'explanation': 'invalid-provider-proof-sentinel'}
    requests = mock_responses(monkeypatch, [{'findings': [event_finding, unresolved_draft('a2'), invalid_causal]}])

    result = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))
    causal = result.findings[2]

    assert len(requests) == 1
    assert causal.status == 'contradicted' and causal.material_counterfact.claim_span == event
    assert causal.material_counterfact.quote == s.passage
    assert causal.citations[0].quote == s.passage
    assert 'causal relationship remains unresolved' in causal.explanation.lower()
    assert 'invalid-provider-proof-sentinel' not in causal.explanation


@pytest.mark.parametrize('defect', ['cropped_clause', 'conditional', 'different_attribution', 'scope_downgrade'])
def test_causal_derivation_requires_complete_clause_and_valid_bound_scope(monkeypatch, defect):
    event = 'Officials are raising the annual permit fee to 90 dollars'
    text = event + ' because the permit fund is depleted.'
    event_assertion = dict(id='a1', text=event, kind='change')
    causal_assertion = dict(id='a2', text=text, kind='causal')
    scope = 'established'
    if defect == 'cropped_clause':
        event_assertion['text'] = 'raising the annual permit fee to 90 dollars'
    elif defect == 'conditional':
        text = 'If approved, ' + text
        causal_assertion['text'] = text
    elif defect == 'different_attribution':
        causal_assertion['attribution'] = 'Officials'
    else:
        scope = 'different_scope'
    c = claim(text, [event_assertion, causal_assertion])
    s = source('schedule', 'The adopted annual permit fee increase is to 50 dollars from January 2027.', scope=scope)
    event_finding = draft('a1', [s], status='contradicted', reasoning_type='incompatible_rule').model_dump()
    requests = mock_responses(monkeypatch, [
        {'findings': [event_finding, {'assertion_id': 'a2', 'status': 'contradicted'}]},
        {'findings': [unresolved_draft('a2')]}])

    result = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert len(requests) == 2
    assert result.findings[1].status == 'unresolved' and result.findings[1].material_counterfact is None
    prior = json.loads(requests[1]['messages'][1]['content'])['previously_validated_findings'][0]['finding']
    assert prior['status'] == ('unresolved' if defect == 'scope_downgrade' else 'contradicted')


def test_valid_unresolved_causal_finding_is_never_replaced_by_derived_verdict(monkeypatch):
    event = 'Officials are raising the annual permit fee to 90 dollars'
    text = event + ' because the permit fund is depleted.'
    c = claim(text, [dict(id='a1', text=event, kind='change'), dict(id='a2', text=text, kind='causal')])
    s = source('schedule', 'The adopted annual permit fee increase is to 50 dollars from January 2027.', scope='established')
    requests = mock_responses(monkeypatch, [{'findings': [
        draft('a1', [s], status='contradicted', reasoning_type='incompatible_rule').model_dump(), unresolved_draft('a2')]}])

    result = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert len(requests) == 1
    assert result.findings[1].status == 'unresolved' and result.findings[1].material_counterfact is None


def test_archived_source_remains_excluded_on_pending_repair(monkeypatch):
    from datetime import datetime, timezone
    from app.pipeline.shared.context import build_claim_context
    c = claim('Officials are raising the annual permit fee to 90 dollars.')
    context = build_claim_context(c.extracted_claim, datetime(2026, 11, 3, tzinfo=timezone.utc))
    c.claim_context = context.model_copy(update={'claim_type': 'policy_change'})
    old = source('archive', 'The annual permit fee cannot exceed 50 dollars.')
    old.url = 'https://sso.agc.gov.sg/Act-Rev/EX1993/Published/20120930?DocDate=20000701'
    current = source('current', 'The current permit process accepts online applications.')
    invalid = {'findings': [draft('a1', [old], status='contradicted', reasoning_type='incompatible_rule').model_dump()]}
    requests = mock_responses(monkeypatch, [invalid, invalid])

    with pytest.raises(PipelineComponentError):
        asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[old, current])))

    assert len(requests) == 2
    assert all([s['evidence_id'] for s in json.loads(request['messages'][1]['content'])['sources']] == ['current']
               for request in requests)


def test_schema_failure_reports_independent_quote_and_complete_clause_defects():
    text = 'The annual permit fee is 90 dollars because the permit fund is depleted.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('fee', 'The annual permit fee is 40 dollars from July 2026.')
    raw = draft('a1', [s], status='contradicted').model_dump()
    raw['citations'][0]['quote'] = 'The annual permit fee is 40 dollaars from July 2026.'
    checks = {key: 'established' for key in v.VerificationScopeChecks.model_fields}
    checks['time'] = 'unknown'
    raw['material_counterfact'] = dict(evidence_id=s.evidence_id, quote=s.passage,
        claim_span='90 dollars', explanation='provider-input-sentinel', scope_checks=checks)
    def handler(request):
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps({'findings': [raw]})}})
    async def run():
        async with httpx.AsyncClient(base_url='https://ollama.com', transport=httpx.MockTransport(handler)) as client:
            return await v._call_oss(client,
                v.format_state(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    with pytest.raises(ValueError) as caught:
        asyncio.run(run())

    feedback = v._validation_feedback(caught.value)
    assert 'material_counterfact requires every scope_checks value' in feedback
    assert 'a1 citation 1 (fee): quote is not an exact contiguous span' in feedback
    assert 'copy the complete event or premise clause' in feedback
    assert 'provider-input-sentinel' not in feedback and 'dollaars' not in feedback


def test_wire_ranges_copy_original_contiguous_text_and_prompt_uses_compact_schema(monkeypatch):
    c = claim('The annual permit fee is 90 dollars.')
    s = source('policy', 'The annual fee is 40 dollars.\n\nApplications use the council\u2019s portal.\n\nThe fee rises to 50 dollars in January 2027.')
    raw = wire_finding(citations=[dict(evidence_id='policy', start_sentence=0, end_sentence=2)])
    requests = mock_responses(monkeypatch, [{'findings': [raw]}])

    result = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert result.findings[0].citations[0].quote == s.passage
    assert result.findings[0].basis == 'direct' and result.findings[0].scope == 'established'
    payload = json.loads(requests[0]['messages'][1]['content'])
    assert 'passage' not in payload['sources'][0]
    assert ''.join(unit['text'] for unit in payload['sources'][0]['sentences']) == s.passage
    schema = json.loads(requests[0]['messages'][0]['content'].split('Return JSON matching this schema:\n', 1)[1])
    assert 'DraftFinding' not in schema['$defs']
    assert not {'basis', 'scope', 'evidence_adequacy'} & set(schema['$defs']['WireFinding']['properties'])
    assert set(schema['$defs']['SourceSelection']['properties']) == {'evidence_id', 'start_sentence', 'end_sentence'}


@pytest.mark.parametrize('selection', [
    {'evidence_id': 'unknown', 'start_sentence': 0, 'end_sentence': 0},
    {'evidence_id': 'policy', 'start_sentence': 0},
    {'evidence_id': 'policy', 'start_sentence': -1, 'end_sentence': 0},
    {'evidence_id': 'policy', 'start_sentence': 0, 'end_sentence': 100},
    {'evidence_id': 'policy', 'start_sentence': 1, 'end_sentence': 0},
    {'evidence_id': 'policy', 'start_sentence': True, 'end_sentence': 0},
    {'evidence_id': 'policy', 'start_sentence': 0, 'end_sentence': 0, 'quote': 'Invented replacement text.'},
    {'evidence_id': 'policy', 'start_sentence': 0, 'end_sentence': 0, 'sentence_text': 'Tampered unit.'},
])
def test_wire_invalid_or_tampered_source_selection_is_rejected(selection):
    c = claim('The annual permit fee is 90 dollars.')
    s = source('policy', 'The annual permit fee is 40 dollars. It will rise to 50 dollars.')
    state = json.loads(v.format_state(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    with pytest.raises(ValueError):
        v._canonical_wire_finding(wire_finding(citations=[selection]), state)


def test_wire_range_length_bound_cannot_be_bypassed_by_multiple_units():
    c = claim('The annual permit fee is 90 dollars.')
    passage = 'A' * 2600
    s = source('policy', passage)
    state = json.loads(v.format_state(c, RetrievalResult(retrieval_status='completed', evidence=[s])))
    provider_state = v._wire_state(state)
    assert ''.join(unit['text'] for unit in provider_state['sources'][0]['sentences']) == passage
    assert all(len(unit['text']) <= 1200 for unit in provider_state['sources'][0]['sentences'])

    with pytest.raises(ValueError, match='10-1800'):
        v._canonical_wire_finding(wire_finding(citations=[
            dict(evidence_id='policy', start_sentence=0, end_sentence=1)]), state)


def test_wire_counterfact_copies_complete_ordered_clause_and_existing_citation(monkeypatch):
    event = 'Officials are not raising the annual permit fee to 90 dollars'
    text = event + ' because the permit fund is depleted.'
    c = claim(text, [dict(id='a1', text=text, kind='causal', negated=True)])
    s = source('policy', 'The adopted annual permit fee increase is to 90 dollars from January 2027.')
    requests = mock_responses(monkeypatch, [{'findings': [wire_finding(
        material_counterfact=dict(clause_index=0, citation_index=0))]}])

    result = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    proof = result.findings[0].material_counterfact
    assert proof.claim_span == event and 'not raising' in proof.claim_span
    assert proof.quote == s.passage == result.findings[0].citations[0].quote
    state = json.loads(requests[0]['messages'][1]['content'])
    assert state['plan']['assertions'][0]['causal_clauses'] == [
        {'id': 0, 'text': event}, {'id': 1, 'text': 'the permit fund is depleted'}]


@pytest.mark.parametrize('counterfact', [
    {'clause_index': 2, 'citation_index': 0},
    {'clause_index': 0, 'citation_index': 1},
    {'clause_index': 0, 'citation_index': 0, 'claim_span': 'raising the fee'},
    {'clause_index': 0, 'citation_index': 0, 'quote': 'Invented replacement quote.'},
])
def test_wire_counterfact_cannot_invent_clause_or_citation(counterfact):
    text = 'Officials are raising the fee because the permit fund is depleted.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('policy', 'The adopted fee remains unchanged for all residents.')
    state = json.loads(v.format_state(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    with pytest.raises(ValueError):
        v._canonical_wire_finding(wire_finding(material_counterfact=counterfact), state)


def test_wire_counterfact_has_no_clause_index_for_conditional_claim():
    text = 'If approved, officials will raise the fee because the fund is depleted.'
    c = claim(text, [dict(id='a1', text=text, kind='causal')])
    s = source('policy', 'The adopted fee remains unchanged for all residents.')
    state = json.loads(v.format_state(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert v._wire_state(state)['plan']['assertions'][0]['causal_clauses'] == []
    with pytest.raises(ValueError, match='complete causal clause'):
        v._canonical_wire_finding(wire_finding(material_counterfact=dict(clause_index=0, citation_index=0)), state)


def test_wire_unknown_scope_stays_unknown_until_explicit_valid_unresolved_repair(monkeypatch):
    c = claim('The annual permit fee will be 90 dollars in 2045.')
    s = source('policy', 'The annual permit fee is 40 dollars in 2026.')
    checks = {key: 'established' for key in v.VerificationScopeChecks.model_fields}
    checks['time'] = 'unknown'
    invalid = wire_finding(scope_checks=checks)
    repaired = wire_finding(status='unresolved', scope_checks=checks, reasoning_type='none',
        decisiveness=0., explanation='The source does not establish the fee in 2045.', gaps=['missing_future_policy'])
    requests = mock_responses(monkeypatch, [{'findings': [invalid]}, {'findings': [repaired]}])

    result = asyncio.run(v.judge(c, RetrievalResult(retrieval_status='completed', evidence=[s])))

    assert len(requests) == 2
    correction = requests[1]['messages'][0]['content'].split('Validation feedback: ', 1)[1]
    assert 'scope_checks' in correction and 'return status unresolved' in correction
    assert 'reasoning_type' in correction and 'reasoning basis' not in correction
    assert result.findings[0].status == 'unresolved' and result.findings[0].scope == 'unknown'
    assert result.findings[0].scope_checks.time == 'unknown'


@pytest.mark.parametrize('policy_year,expected', [(2027, 'insufficient_evidence'), (2045, 'contradicted')])
def test_bound_policy_finding_requires_quoted_explicit_future_period(policy_year, expected):
    from datetime import datetime, timezone
    from app.pipeline.shared.context import build_claim_context
    text = 'The council will raise the annual permit fee to 90 dollars in 2045.'
    c = claim(text, [dict(id='a1', text=text, kind='change')])
    context = build_claim_context(text, datetime(2026, 11, 3, tzinfo=timezone.utc))
    c.claim_context = context.model_copy(update={'claim_type': 'policy_change'})
    s = source('policy', f'The adopted annual permit fee is 50 dollars from 1 January {policy_year}.', scope='established')

    result = assess(c, [s], [draft('a1', [s], status='contradicted', reasoning_type='incompatible_rule')])

    assert result.assessment_outcome == expected
    finding = result.verification.findings[0]
    assert finding.citations[0].quote == s.passage
    if policy_year == 2027:
        assert finding.scope == 'unknown'
        assert 'missing_future_policy_period' in finding.gaps
        assert '2045' in finding.explanation


@pytest.mark.parametrize('kind', ['fact', 'causal'])
def test_only_irrelevant_noncausal_counterfact_metadata_is_ignored(kind):
    c = claim('The event is free.', [dict(id='a1', text='The event is free.', kind=kind)])
    s = source('a', 'The event is free for all visitors.')
    raw = draft('a1', [s], status='contradicted').model_dump()
    raw['material_counterfact'] = {'claim_span': 'x', 'quote': 'invented and irrelevant'}
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps({'findings': [raw]})}})
    async def run():
        async with httpx.AsyncClient(base_url='https://ollama.com', transport=httpx.MockTransport(handler)) as client:
            return await v._call_oss(client, v.format_state(c, RetrievalResult(retrieval_status='completed', evidence=[s])))
    if kind == 'fact':
        response = asyncio.run(run())
        assert response.findings[0].material_counterfact is None
        assert 'There are no causal assertions' in seen[0]['messages'][0]['content']
        schema = json.loads(seen[0]['messages'][0]['content'].split('Return JSON matching this schema:\n', 1)[1])
        assert 'material_counterfact' not in schema['$defs']['WireFinding']['properties']
    else:
        with pytest.raises(ValueError):
            asyncio.run(run())


@pytest.mark.parametrize('value', [True, '0.9', float('nan'), float('inf')])
def test_new_adequacy_contract_rejects_coercion_and_nonfinite_numbers(value):
    with pytest.raises(ValueError):
        draft('a1', [source('a', 'The event is free for all visitors.')], decisiveness=value)


def test_wrong_table_row_is_correctable_extraction_error_not_a_decisive_vote():
    text = 'The number of unemployed residents in Singapore doubled from 2024 to 2025.'
    c = claim(text)
    s = source('table', 'Number of unemployed residents\n\n| Population | 2024 | 2025 |\n| --- | --- | --- |\n| Singapore | 100 | 110 |\n| Australia | 400 | 800 |')
    point = dict(population='Singapore', measure='Number of unemployed residents', metric='unemployed_count', unit='people')
    wrong = dict(evidence_id='table', before=dict(**point, period='2024', value='400'),
                 after=dict(**point, period='2025', value='800'))
    with pytest.raises(ValueError, match='table labels'):
        assess(c, [s], [draft('a1', [s], comparisons=[wrong])])
    correct = dict(evidence_id='table', before=dict(**point, period='2024', value='100'),
                   after=dict(**point, period='2025', value='110'))
    result = assess(c, [s], [draft('a1', [s], comparisons=[correct])])
    assert result.assessment_outcome == 'contradicted'


@pytest.mark.parametrize('field,value', [('settles', None), ('confidence', float('nan')),
                                      ('quality', float('inf')), ('settles', -1), ('quality', True)])
def test_legacy_pool_rejects_missing_nonfinite_or_invalid_required_numbers(field, value):
    entry = dict(verdict='supporting', confidence=.9, settles=.9, quality=4)
    entry[field] = value
    with pytest.raises(ValueError):
        pool._parse_sources({'sources': {'s0': entry}}, ['s0'])


def test_legacy_pool_rejects_unknown_source_ids():
    entry = dict(verdict='supporting', confidence=.9, settles=.9, quality=4)
    with pytest.raises(ValueError):
        pool._parse_sources({'sources': {'s999': entry}}, ['s0'])


@pytest.mark.parametrize('body', [[], None, {'done': True, 'message': {'content': 17}}])
def test_invalid_provider_envelopes_are_contract_errors(body):
    async def run():
        async with httpx.AsyncClient(base_url='https://ollama.com',
                transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
            with pytest.raises(ValueError):
                await pool._call_oss(client, 'fake', 'SOURCE s0:\nA source passage.', ['s0'])
            with pytest.raises(ValueError):
                await v._call_oss(client, 'state')
    asyncio.run(run())


def test_legacy_jev_missing_numeric_field_falls_back_to_valid_oss(monkeypatch):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if 'typesafe.ai' in str(request.url):
            return httpx.Response(200, json={'answers': {'verdict_s0': {'choice': 'supporting', 'confidence': .9},
                'settles_s0': {}, 'quality_s0': {'score': 4}}})
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps({'sources': {
            's0': dict(verdict='supporting', confidence=.9, settles=.9, quality=4)}})}})
    real = httpx.AsyncClient
    monkeypatch.setattr(pool, '_provider_keys', lambda: ('fake1', 'fake2'))
    monkeypatch.setattr(pool.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    verdicts, provider = asyncio.run(pool._pool_verdicts('Claim', [('s0', 'A source passage.')]))
    assert provider == 'oss'
    assert len(calls) == 2
    assert verdicts['s0']['settles'] == .9
