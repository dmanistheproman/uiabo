"""A retrieved historical edition must not become proof of current policy."""
from datetime import datetime, timezone
import json

import pytest

from app.pipeline.evidence_assessment import verification as v
from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.dates import infer_date_context
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, RetrievalResult
from app.pipeline.shared.verification import VerificationAssertion, VerificationPlan


NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)
ARCHIVE = 'https://sso.agc.gov.sg/Act-Rev/EX1993/Published/20120930?DocDate=20000701'


def inputs(text='The government is raising the retirement age to 75.'):
    context = build_claim_context(text, NOW, original_text=text)
    # This test exercises an already classified policy claim, not classification.
    context = context.model_copy(update={'claim_type': 'policy_change'})
    claim = ClaimAnalysis(extracted_claim=text, checkable=True, claim_category='factual',
        classification_reason='A policy assertion.', claim_confidence=1,
        claim_context=context, date_context=infer_date_context(text, NOW),
        verification_plan=VerificationPlan(source_text=text, as_of=NOW.date(), assertions=[
            VerificationAssertion(id='a1', text=text, kind='change',
                evidence_questions=['What is the official schedule?'], queries=['retirement schedule'])]))
    archived = EvidenceCandidate(evidence_id='old', title='Archived policy', url=ARCHIVE,
        publisher='Official publisher', passage='The prescribed retirement age may be up to 67 years.',
        source_type='government', retrieval_score=.9, retrieved_at=NOW)
    current = EvidenceCandidate(evidence_id='current', title='Current schedule',
        url='https://example.gov/current-policy', publisher='Official publisher',
        passage='The adopted retirement-age change is to 65 on 1 January 2029.',
        source_type='government', retrieval_score=.9, retrieved_at=NOW)
    return claim, RetrievalResult(retrieval_status='completed', evidence=[archived, current])


def test_current_policy_prompt_omits_archive_but_preserves_retrieval():
    claim, retrieval = inputs()
    state = json.loads(v.format_state(claim, retrieval))
    assert [s['evidence_id'] for s in state['sources']] == ['current']
    assert len(retrieval.evidence) == 2


def test_archived_current_policy_citation_is_rejected_even_if_model_invents_it():
    claim, retrieval = inputs()
    raw = v.Draft(findings=[v.DraftFinding(assertion_id='a1', status='contradicted',
        explanation='The historical cap is asserted to be current.', basis='direct', scope='established',
        scope_checks={k: 'established' for k in v.VerificationScopeChecks.model_fields},
        citations=[{'evidence_id': 'old', 'quote': retrieval.evidence[0].passage}],
        decisiveness=.9, reasoning_type='incompatible_rule')])
    with pytest.raises(ValueError):
        v.validate_draft(claim, retrieval, raw)


def test_historical_policy_claim_can_still_use_its_historical_edition():
    claim, retrieval = inputs('In July 2000 the retirement age was 67.')
    assert set(v._proof_sources(claim, retrieval)) == {'old', 'current'}


def test_old_unversioned_publication_and_docdate_only_edition_remain_eligible():
    claim, retrieval = inputs()
    for url in ['https://example.gov/policy/published-in-2000',
                'https://sso.agc.gov.sg/Act/EX1993?DocDate=20000701']:
        retrieval.evidence[0] = retrieval.evidence[0].model_copy(update={'url': url})
        assert set(v._proof_sources(claim, retrieval)) == {'old', 'current'}
