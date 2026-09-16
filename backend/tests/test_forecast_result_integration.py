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
)


TEXT = 'Temperatures in Singapore could reach 52°C this weekend because of a record-breaking heatwave.'
# Thursday in Singapore, Wednesday in UTC: all stages must share the same clock.
NOW = datetime(2026, 9, 16, 18, tzinfo=timezone.utc)


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
            misinformation_risk_score=50, assessment_outcome='unsupported',
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
