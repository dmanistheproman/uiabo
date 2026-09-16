"""Policy differences, missing context and literal grounding across the API."""
from copy import deepcopy
import pytest
from app.pipeline.evidence_assessment import policy, semantic
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, RetrievalResult, TextAnalysisResult
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.input_preparation.service import prepare_text

CLAIM="From October, all residents over 60 must pay a compulsory $300 monthly permit fee."
PASSAGE="The annual permit fee for residents aged 61 to 65 is $120. This schedule applies from 1 January 2024."


def claim(text=CLAIM):
    return ClaimAnalysis(extracted_claim=text,claim_category="factual",checkable=True,
                         classification_reason="A policy claim.",claim_confidence=1)


def source(id="one",text=PASSAGE):
    return EvidenceCandidate(evidence_id=id,title="Permit policy",url=f"https://gov.sg/{id}",
        publisher="Test authority",source_type="government",passage=text,retrieval_score=.9,
        retrieved_at="2026-09-10T00:00:00Z")


def comparison(**changes):
    return {"aspect":"amount","claim_text":"$300 monthly", "finding":"differs",
        "applies_to_claim":True,"evidence_quote":PASSAGE.split(' This')[0],
        "explanation":"The quoted rule charges $120 annually rather than $300 monthly.",**changes}


def judgment(parts=None,**changes):
    return {"stance":"neutral","evidence_quote":"","reason":"The future change is unconfirmed.",
            "comparisons": [comparison()] if parts is None else parts,**changes}


def assess(raw=None,text=CLAIM,item=None):
    item=item or source()
    result=semantic.validate_judgment(raw or judgment(),item.passage,claim=text,evidence=item)
    return semantic.aggregate(claim(text),RetrievalResult(retrieval_status="completed",evidence=[item]),[result])


def test_unspecified_october_does_not_turn_an_old_fee_into_a_false_verdict():
    result=assess(judgment(stance="contradicting",evidence_quote=PASSAGE))
    assert result.assessment_outcome=="unsupported"
    assert result.concern_label=="Not Enough Information" and result.misinformation_risk_score == 50
    assert result.scoring.status == "provisional"
    assert result.claim_comparisons[0].finding=="differs"
    assert not result.claim_comparisons[0].applies_to_claim
    assert result.claim_comparisons[-1].aspect=="start_date"
    assert result.claim_comparisons[-1].evidence_id is None
    assert "start month has no year" in ' '.join(result.uncertainty_reasons)
    assert "Not supported by the published policy checked" in result.explanation


@pytest.mark.parametrize('prefix',['From October','Starting in October','Effective October 1','Beginning on October 1st'])
def test_missing_start_year_is_detected_without_inventing_one(prefix):
    assert policy.unspecified_start_date(prefix+", the permit fee is $300.")==prefix


@pytest.mark.parametrize('text',[
    'From October 2027, the permit fee is $300.',
    'Effective October 1, 2027, the permit fee is $300.',
    'The permit renews every October.',
    'October is my favourite month.',
])
def test_explicit_year_and_recurring_dates_do_not_trigger_the_missing_year_gate(text):
    assert policy.unspecified_start_date(text) is None


def test_positive_applicable_contradiction_can_refute_without_an_exact_rumour_match():
    text="Residents over 60 must pay a $300 monthly permit fee in 2027."
    passage="In 2027, all residents over 60 pay a $120 annual permit fee."
    raw=judgment([comparison(evidence_quote=passage,explanation="The applicable 2027 fee is $120 annually.")])
    result=assess(raw,text,source(text=passage))
    assert result.assessment_outcome=="contradicted" and result.concern_label=="High Concern"
    assert result.assessed_evidence[0].evidence_quote==passage


@pytest.mark.parametrize('finding',['unresolved','differs'])
def test_silence_or_different_period_never_establishes_contradiction(finding):
    text="From October 2027, residents pay a $300 monthly permit fee."
    part=comparison(finding=finding,applies_to_claim=False,
        evidence_quote='' if finding=='unresolved' else PASSAGE,
        explanation='The passage does not establish the alleged 2027 change.')
    result=assess(judgment([part]),text)
    assert result.concern_label=="Not Enough Information"
    assert result.assessment_outcome==('insufficient_evidence' if finding=='unresolved' else 'unsupported')


@pytest.mark.parametrize('changes',[
    {'claim_text':'$900 monthly'}, {'evidence_quote':'Everyone pays $300.'},
    {'finding':'differs','evidence_quote':''}, {'aspect':'invented'},
    {'finding':'false'}, {'applies_to_claim':'true'},
    {'finding':'unresolved','applies_to_claim':True}, {'evidence_id':'invented-source'},
])
def test_comparisons_reject_invented_claims_quotes_labels_or_source_ids(changes):
    with pytest.raises(ValueError):
        assess(judgment([comparison(**changes)]))


def test_policy_comparison_cannot_override_retrieval_scope_checks():
    from app.pipeline.shared.models import EvidenceProvenance
    item=source()
    item.provenance=EvidenceProvenance(source_policy='catalogue',source_reason='Catalogue',origin_group='gov.sg',
        discovery_method='preferred_search',relevance='context',relevance_reason='An earlier fee schedule.',
        relevance_quote=PASSAGE,applicability='different_scope',applicability_reason='This is a different period.')
    result=assess(text="The 2027 permit fee is $300 monthly.",item=item)
    assert result.assessment_outcome=='unsupported'
    assert not result.claim_comparisons[0].applies_to_claim


def test_no_search_evidence_is_insufficient_not_false_or_unsupported_policy():
    result=semantic.assess_evidence(claim(),RetrievalResult(retrieval_status='no_evidence'))
    assert result.concern_label=='Not Enough Information'
    assert result.claim_comparisons==[]
    assert result.assessment_outcome!='unsupported'


def test_personal_entry_comparisons_keep_missing_traveller_scope_unresolved():
    text='I need 20000 baht in cash to enter Phuket.'
    passage='Visa-exempt visitors with eligible passports must carry 10000 baht in cash.'
    part=comparison(claim_text='20000 baht', evidence_quote=passage,
                    explanation='The quoted entry amount differs.')
    result=assess(judgment([part]),text,source(text=passage))
    assert result.concern_label=='Not Enough Information'
    assert not result.claim_comparisons[0].applies_to_claim
    assert 'passport or nationality' in result.claim_comparisons[0].explanation


def test_comparison_sentence_repair_copies_source_and_keeps_date_uncertainty():
    part=comparison(); part.pop('evidence_quote')
    part.update(sentence_start=0,sentence_end=0)
    raw={'stance':'neutral','sentence_start':None,'sentence_end':None,'reason':'Unknown change.', 'comparisons':[part]}
    value=semantic.validate_sentence_judgment(raw,PASSAGE,semantic.sentence_spans(PASSAGE),claim=CLAIM,evidence=source())
    assert value.comparisons[0].evidence_quote==PASSAGE.split(' This')[0]
    result=semantic.aggregate(claim(),RetrievalResult(retrieval_status='completed',evidence=[source()]),[value])
    assert result.assessment_outcome=='unsupported'


def test_app_api_history_replay_and_old_records_preserve_policy_comparisons(signed_analysis):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
    pipeline=PipelineOrchestrator(prepare_input=prepare_text,analyze_claim=lambda _:claim(),
        retrieve_evidence=lambda _:RetrievalResult(retrieval_status='completed',evidence=[source()]),
        assess_evidence=lambda *_:assess(),repository=InMemoryResultRepository())
    app.dependency_overrides[get_pipeline_orchestrator]=lambda:pipeline
    store,_=signed_analysis
    with TestClient(app) as client:
        first=client.post('/analysis/text',json={'text':CLAIM},headers={'Idempotency-Key':'policy-test'})
        assert first.status_code==200,first.text
        body=first.json()
        assert body['assessment_outcome']=='unsupported'
        assert client.get('/analysis/results').json()['results'][0]['claim_comparisons']==body['claim_comparisons']
        assert client.get('/analysis/results/'+body['result_id']).json()['assessment_outcome']=='unsupported'
        assert client.post('/analysis/text',json={'text':CLAIM},headers={'Idempotency-Key':'policy-test'}).json()==body
        assert store.documents['usage_allowances','analysis-user']['successful_submissions']==1
        old=deepcopy(body);old.pop('assessment_outcome');old.pop('claim_comparisons')
        old.pop('scoring');old['misinformation_risk_score']=None
        assert TextAnalysisResult.model_validate(old).claim_comparisons==[]
        for changes in [{'evidence_id':'unknown'}, {'evidence_quote':'Invented quote'}, {'claim_text':'Invented claim'}]:
            invalid=deepcopy(body);invalid['claim_comparisons'][0].update(changes)
            with pytest.raises(ValueError): TextAnalysisResult.model_validate(invalid)


def test_conflicting_applicable_policy_sources_keep_both_comparisons():
    text='The annual permit fee in 2027 is $300.'
    passages=['The annual permit fee in 2027 is $300.','The annual permit fee in 2027 is $120.']
    items=[source(str(i),p) for i,p in enumerate(passages)]
    judgments=[]
    for i,item in enumerate(items):
        part=comparison(claim_text='$300',finding='matches' if i==0 else 'differs',evidence_quote=item.passage,
            explanation='The 2027 amount matches.' if i==0 else 'The 2027 amount differs.')
        raw=judgment([part],stance='supporting' if i==0 else 'contradicting',evidence_quote=item.passage)
        judgments.append(semantic.validate_judgment(raw,item.passage,claim=text,evidence=item))
    result=semantic.aggregate(claim(text),RetrievalResult(retrieval_status='completed',evidence=items),judgments)
    assert result.assessment_outcome=='conflicting'
    assert {c.finding for c in result.claim_comparisons}=={'matches','differs'}
