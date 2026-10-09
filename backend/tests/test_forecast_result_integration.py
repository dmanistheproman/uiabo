"""Claim interpretation and forecast comparisons survive the account API."""

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.pipeline.evidence_assessment.scoring import provisional_summary
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.dependencies import get_pipeline_orchestrator
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.models import (
    AssessmentResult, AssessedEvidence, ClaimAnalysis, EvidenceCandidate,
    ForecastContext, ForecastData, ForecastPeriod, RetrievalResult,
    EvidenceProvenance,
)


TEXT = 'Temperatures in Singapore could reach 52°C this weekend because of a record-breaking heatwave.'
# Thursday in Singapore, Wednesday in UTC: all stages must share the same clock.
NOW = datetime(2026, 9, 16, 18, tzinfo=timezone.utc)


def test_climate_plausibility_survives_api_history_and_replay(signed_analysis):
    from app.pipeline.evidence_assessment.pool import assess_pool_evidence
    from app.pipeline.shared.climate import RECORD_URL, render_record
    from app.pipeline.shared.models import ClimateRecord, TextAnalysisResult
    now = datetime(2026, 10, 4, 8, tzinfo=timezone.utc)
    record = ClimateRecord(maximum_c=37, updated_at=date(2026, 9, 22))
    passage = render_record(record)
    source = EvidenceCandidate(evidence_id='climate', url=RECORD_URL,
        title='MSS historical extremes', publisher='MSS', source_type='government',
        retrieved_at=now, retrieval_score=.9, passage=passage, climate_record=record,
        provenance=EvidenceProvenance(source_policy='catalogue', source_reason='Fixed MSS page',
            origin_group='gov.sg', discovery_method='source_link', relevance='context',
            relevance_reason='Historical context', relevance_quote=passage,
            applicability='uncertain_time', applicability_reason='Not a forecast'))
    pipeline = PipelineOrchestrator(prepare_input=prepare_text,
        analyze_claim=lambda prepared: ClaimAnalysis(extracted_claim=prepared.normalised_text,
            claim_category='factual', checkable=True, claim_confidence=1, classification_reason='Prediction'),
        retrieve_evidence=lambda claim: RetrievalResult(retrieval_status='completed', evidence=[source]),
        assess_evidence=assess_pool_evidence, repository=InMemoryResultRepository(), clock=lambda: now)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    with TestClient(app) as client:
        response = client.post('/analysis/text', json={'text': 'Singapore will hit 50 degree celcius next Saturday.'},
                               headers={'Idempotency-Key': 'climate-check'})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['assessment_outcome'] == 'highly_unlikely'
        assert result['misinformation_risk_score'] == 85
        saved = client.get('/analysis/results/' + result['result_id']).json()
        history = client.get('/analysis/results').json()['results'][0]
        replay = client.post('/analysis/text', json={'text': result['original_text']},
                             headers={'Idempotency-Key': 'climate-check'}).json()
        for value in [saved, history, replay]:
            assert value['plausibility_context'] == result['plausibility_context']
            assert value['evidence'][0]['climate_record'] == result['evidence'][0]['climate_record']
            TextAnalysisResult.model_validate(value)
        # A saved finding cannot silently lose or replace its source.
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TextAnalysisResult.model_validate({**result, 'evidence': []})


def test_prediction_conflict_score_and_basis_survive_api_history(signed_analysis):
    from app.pipeline.evidence_assessment.pool import assess_pool_evidence
    from app.pipeline.shared.forecast_format import render_forecast
    data = ForecastData(location='Singapore', issued_at=NOW,
        periods=[ForecastPeriod(date=date(2026, 9, 19), low=25, high=34)])
    passage = render_forecast(data)
    source = EvidenceCandidate(evidence_id='official', title='Official forecast', publisher='NEA / MSS',
        url='https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook', source_type='government',
        retrieved_at=NOW, retrieval_score=.95, passage=passage, forecast=data,
        provenance=EvidenceProvenance(source_policy='catalogue', source_reason='Official API',
            origin_group='gov.sg', discovery_method='official_api', relevance='direct',
            relevance_reason='Matching forecast', relevance_quote=passage,
            applicability='established', applicability_reason='Same location, date and measurement'))
    pipeline = PipelineOrchestrator(prepare_input=prepare_text,
        analyze_claim=lambda prepared: ClaimAnalysis(extracted_claim=prepared.normalised_text,
            claim_category='factual', checkable=True, claim_confidence=1, classification_reason='Prediction'),
        retrieve_evidence=lambda claim: RetrievalResult(retrieval_status='completed', evidence=[source]),
        assess_evidence=assess_pool_evidence, repository=InMemoryResultRepository(), clock=lambda: NOW)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    with TestClient(app) as client:
        response = client.post('/analysis/text', json={'text': 'This Saturday it will be 50 degree celcius in Singapore.'},
                               headers={'Idempotency-Key': 'prediction-conflict'})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['misinformation_risk_score'] == 95
        assert result['forecast_context']['risk_basis'] == 'forecast_comparison'
        assert result['forecast_context']['deviation_c'] == 16
        saved = client.get('/analysis/results/' + result['result_id']).json()
        history = client.get('/analysis/results').json()['results'][0]
        assert saved['forecast_context'] == history['forecast_context'] == result['forecast_context']
        assert saved['scoring'] == result['scoring']


def test_relative_dates_context_and_forecast_survive_api_history_and_replay(signed_analysis):
    store, _ = signed_analysis
    seen = []
    source = EvidenceCandidate(evidence_id='official-forecast',
        title='Singapore four-day forecast', publisher='Meteorological Service Singapore',
        url='https://www.weather.gov.sg/weather-forecast-4dayoutlook/',
        source_type='government', retrieved_at=NOW, retrieval_score=.94,
        passage='Forecast for 19 and 20 September 2026: air temperature 25 to 33 degrees Celsius.',
        forecast=ForecastData(location='Singapore', issued_at=NOW,
            periods=[ForecastPeriod(date=date(2026, 9, day), low=25, high=33) for day in (19, 20)]))

    def retrieve(claim):
        seen.append(claim)
        assert claim.claim_context.as_of == date(2026, 9, 17)
        assert claim.date_context.as_of == claim.claim_context.as_of
        assert claim.claim_context.assessed_at == NOW
        assert claim.date_context.start_date == date(2026, 9, 19)
        assert claim.date_context.end_date == date(2026, 9, 20)
        return RetrievalResult(retrieval_status='completed', evidence=[source])

    def assess(claim, retrieval):
        assert claim is seen[0]
        return AssessmentResult(concern_label='Not Enough Information',
            misinformation_risk_score=None, assessment_outcome='unsupported',
            scoring=provisional_summary('The prediction remains unverified.'),
            uncertainty='High', uncertainty_reasons=['A forecast cannot establish a future event.'],
            explanation='The official forecast does not support 52°C; the claimed cause remains unresolved.',
            recommended_action='Read the latest official forecast.',
            assessed_evidence=[AssessedEvidence(evidence_id=source.evidence_id, stance='neutral',
                quality_score=.45, assessment_reason='Forecast compatibility, not proof of future weather.',
                evidence_quote=source.passage)],
            forecast_context=ForecastContext(status='not_supported_by_forecast',
                explanation='The official air-temperature forecast is 25 to 33°C for the specified dates.',
                limitations=['Does not establish the cause or record-breaking claim.'],
                evidence_ids=[source.evidence_id], start_date=claim.date_context.start_date,
                end_date=claim.date_context.end_date, issued_at=NOW, forecast_low=25, forecast_high=33))

    pipeline = PipelineOrchestrator(prepare_input=prepare_text,
        analyze_claim=lambda prepared: ClaimAnalysis(extracted_claim=prepared.normalised_text,
            claim_category='factual', checkable=True, claim_confidence=.9,
            classification_reason='A dated weather prediction can be compared with published forecasts.'),
        retrieve_evidence=retrieve, assess_evidence=assess,
        repository=InMemoryResultRepository(), clock=lambda: NOW)
    app.dependency_overrides[get_pipeline_orchestrator] = lambda: pipeline
    with TestClient(app) as client:
        response = client.post('/analysis/text', json={'text': TEXT}, headers={'Idempotency-Key': 'forecast-check'})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['original_text'] == result['extracted_claim'] == TEXT
        assert result['date_context']['basis'] == 'relative_submission_date'
        assert result['claim_context']['modality'] == 'possible'
        assert result['claim_context']['location'] == 'Singapore'
        assert result['forecast_context']['status'] == 'not_supported_by_forecast'
        assert result['evidence'][0]['forecast']['periods'][0]['date'] == '2026-09-19'
        saved = client.get('/analysis/results/' + result['result_id']).json()
        history = client.get('/analysis/results').json()['results'][0]
        replay = client.post('/analysis/text', json={'text': TEXT}, headers={'Idempotency-Key': 'forecast-check'})
        for key in ('date_context', 'claim_context', 'forecast_context', 'scoring', 'evidence'):
            assert result[key] == saved[key] == history[key]
        assert replay.json() == result
        assert len(seen) == 1
        assert store.documents['usage_allowances', 'analysis-user']['successful_submissions'] == 1
