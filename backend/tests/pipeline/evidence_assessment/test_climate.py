"""Plausibility is source-grounded and separate from proof about future weather."""

import asyncio
from datetime import date, datetime, timezone, timedelta

import httpx
import pytest
from pydantic import ValidationError

from app.pipeline.evidence_assessment.pool import assess_pool_evidence
from app.pipeline.evidence_assessment.climate import apply_plausibility
from app.pipeline.evidence_retrieval.official_climate import parse_record, retrieve_record
from app.pipeline.shared.climate import RECORD_URL
from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.dates import infer_date_context
from app.pipeline.shared.models import ClaimAnalysis, RetrievalResult, AssessmentResult

NOW = datetime(2026, 10, 4, 8, tzinfo=timezone.utc)
TEXT = "Singapore will hit 50 degree celcius next Saturday."
HTML = '''<p>Updated at 22 Sep 2026</p><table class="table Annual">
<tr><th></th><th>Climate Station</th><th>All Stations</th></tr>
<tr><td>Highest Daily Maximum Temperature (°C)</td><td><h2>36.0</h2>26 Mar 1998</td>
<td><h2>37.0</h2>Tengah 17 Apr 1983; Ang Mo Kio 13 May 2023</td></tr></table>
<table class="January"><tr><td>Highest Daily Maximum Temperature (°C)</td><td>35.2</td><td>35.4</td></tr></table>'''


def make_claim(text=TEXT):
    dates = infer_date_context(text, NOW)
    return ClaimAnalysis(extracted_claim=text, checkable=True, claim_category="factual",
        claim_confidence=1, classification_reason="Test assertion", date_context=dates,
        claim_context=build_claim_context(text, now=NOW))


def make_source(html=HTML):
    claim = make_claim()
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text=html))) as client:
            return await retrieve_record(client, claim.claim_context, claim.date_context)
    return asyncio.run(run())


def test_50_c_beyond_forecast_becomes_plausibility_warning_not_falsehood():
    claim = make_claim()
    assert (claim.date_context.start_date - NOW.date()).days == 6
    source = make_source()
    result = assess_pool_evidence(claim, RetrievalResult(retrieval_status="completed", evidence=[source]))
    assert result.assessment_outcome == "highly_unlikely"
    assert 100 - result.misinformation_risk_score == 15
    assert result.scoring.status == "plausibility_based"
    assert result.plausibility_context.deviation_c == 13
    assert result.assessed_evidence[0].stance == "neutral"
    assert result.scoring.contradicting_origins == 0
    assert "not proof" in result.explanation


@pytest.mark.parametrize("text", [
    "Singapore will hit 38 C next Saturday.",
    "Singapore will hit 46.9 C next Saturday.",
    "Singapore could hit 50 C next Saturday.",
    "Could Singapore hit 50 C next Saturday?",
    "What if Singapore will hit 50 C next Saturday?",
    "Singapore will not hit 50 C next Saturday.",
    "Singapore's heat index will hit 50 C next Saturday.",
    "Singapore's surface temperature will hit 50 C next Saturday.",
    "Singapore will hit 50 C next Saturday because of climate change.",
    "Singapore will hit 50 C next Saturday and schools will close.",
    "Singapore will hit above 50 C next Saturday.",
    "Singapore will hit 50 C in 2100.",
    "Singapore will hit 50 C on 25 October 2026.",
    "Singapore will hit 50 C yesterday.",
    "Malaysia will hit 50 C next Saturday.",
    "It will hit 50 C next Saturday.",
    "MSS says Singapore will hit 50 C next Saturday.",
])
def test_context_alone_never_proves_unrelated_or_complex_claims(text):
    result = assess_pool_evidence(make_claim(text), RetrievalResult(retrieval_status="completed", evidence=[make_source()]))
    assert result.plausibility_context is None
    assert result.assessment_outcome in {"unsupported", "insufficient_evidence"}


@pytest.mark.parametrize("value", ["50 C", "122 F", "47 C"])
def test_units_and_threshold_are_compared_with_actual_record(value):
    result = assess_pool_evidence(make_claim(f"Singapore will hit {value} next Saturday."),
        RetrievalResult(retrieval_status="completed", evidence=[make_source()]))
    assert result.assessment_outcome == "highly_unlikely"


@pytest.mark.parametrize("changes", [
    {"url": "https://example.com/"}, {"passage": "Fabricated record"},
    {"provenance": None}, {"source_type": "other"},
    {"retrieved_at": NOW - timedelta(days=2)}, {"retrieved_at": NOW + timedelta(hours=1)},
])
def test_untrusted_or_stale_record_does_not_assign_plausibility_score(changes):
    source = make_source().model_copy(update=changes)
    result = assess_pool_evidence(make_claim(), RetrievalResult(retrieval_status="completed", evidence=[source]))
    assert result.plausibility_context is None


def test_record_parser_uses_annual_all_stations_and_rejects_changed_or_stale_data():
    assert parse_record(HTML, NOW.date()).maximum_c == 37
    for html in [HTML.replace('All Stations', 'Some Stations'), HTML.replace('Annual', 'January'),
                 HTML.replace('°C', '°F'), HTML.replace('37.0', 'Unknown'),
                 HTML.replace('22 Sep 2026', '22 Sep 2025'), HTML.replace('22 Sep 2026', '22 Sep 2027')]:
        with pytest.raises(ValueError):
            parse_record(html, NOW.date())
    assert parse_record(HTML.replace('37.0', '40.0'), NOW.date()).maximum_c == 40


def test_new_historical_record_changes_comparison_instead_of_hardcoding_50():
    result = assess_pool_evidence(make_claim(), RetrievalResult(retrieval_status="completed",
        evidence=[make_source(HTML.replace('37.0', '41.0'))]))
    assert result.plausibility_context is None


def test_plausibility_cannot_override_decisive_evidence_or_conflict():
    from app.pipeline.evidence_assessment import service as baseline
    from app.pipeline.shared.models import AssessedEvidence
    source = make_source()
    other = source.model_copy(update={"evidence_id": "refutation", "climate_record": None,
        "provenance": source.provenance.model_copy(update={"relevance": "direct", "applicability": "established"})})
    retrieval = RetrievalResult(retrieval_status="completed", evidence=[source, other])
    for stance in ["supporting", "contradicting"]:
        result = baseline.summarise_assessments(TEXT, retrieval, [AssessedEvidence(
            evidence_id="refutation", stance=stance, quality_score=.9,
            assessment_reason="An explicit relevant finding")])
        assert result.assessment_outcome in {"supported", "contradicted"}
        assert apply_plausibility(make_claim(), retrieval, result) is result


def test_invalid_plausibility_score_contract_is_rejected():
    result = assess_pool_evidence(make_claim(), RetrievalResult(retrieval_status="completed", evidence=[make_source()]))
    for change in [{"misinformation_risk_score": 95}, {"assessment_outcome": "contradicted"},
                   {"plausibility_context": None}]:
        with pytest.raises(ValidationError):
            AssessmentResult.model_validate({**result.model_dump(), **change})
