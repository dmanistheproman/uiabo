"""Offline regression tests at the Ollama HTTP boundary; no API key required."""

import asyncio
import json

import httpx
import pytest

from app.pipeline.claim_analysis import service
from app.pipeline.claim_analysis.categories import CLASSIFICATION_MODELS
from app.pipeline.evidence_assessment.service import assess_evidence
from app.pipeline.input_preparation.service import prepare_text
from app.pipeline.orchestration.repository import InMemoryResultRepository
from app.pipeline.orchestration.service import PipelineOrchestrator
from app.pipeline.shared.errors import PipelineComponentError
from app.pipeline.shared.models import PreparedText


TEXT = "A new $500 community tax starts next week."
PREPARED = PreparedText(original_text=TEXT, normalised_text=TEXT, language="en", warnings=[])


def classification(category="factual"):
    return {"claim_category": category, "classification_reason": "Publicly checkable assertion."}


def response(value, **extra):
    content = value if isinstance(value, str) else json.dumps(value)
    return httpx.Response(200, json={"done": True, "message": {"content": content}, **extra})


def analyse(handler, prepared=PREPARED):
    async def run():
        async with httpx.AsyncClient(base_url="https://ollama.com", transport=httpx.MockTransport(handler)) as client:
            return await service._analyse_with_client(prepared, client)
    return asyncio.run(run())


def is_extraction(request):
    return json.loads(request.content)["messages"][0]["content"].startswith("\nExtract")


@pytest.mark.parametrize("categories,expected,confidence", [
    (["factual", "factual", "factual"], "factual", 1.0),
    (["factual", "factual", "opinion"], "factual", 0.67),
    (["factual", "opinion", "factual"], "factual", 0.67),
    (["opinion", "factual", "factual"], "factual", 0.67),
    (["opinion", "prediction", "factual"], "unverifiable", 0.0),
    (["opinion", "prediction"], "unverifiable", 0.0),
    (["unverifiable", "unverifiable"], "unverifiable", 0.67),
])
def test_valid_votes_only(categories, expected, confidence):
    result = service.select_majority_result(dict(zip(CLASSIFICATION_MODELS, map(classification, categories))))
    assert result["claim_category"] == expected
    assert result["claim_confidence"] == confidence
    if len(categories) == 2 and confidence:
        assert "unavailable" in result["classification_reason"]


@pytest.mark.parametrize("bad", [None, {}, {"claim_category": "factual"},
    classification("made_up"), {**classification(), "classification_reason": "   "},
    {**classification(), "extra": True}])
def test_invalid_classification_cannot_vote(bad):
    with pytest.raises(PipelineComponentError, match="enough valid"):
        service.select_majority_result({CLASSIFICATION_MODELS[0]: classification(), CLASSIFICATION_MODELS[1]: bad})


def test_factual_claim_http_contract_and_grounding():
    calls = []
    def handler(request):
        data = json.loads(request.content)
        calls.append(data)
        assert request.url == "https://ollama.com/api/chat"
        assert "format" not in data
        assert data["stream"] is False
        assert [m["role"] for m in data["messages"]] == ["system", "user"]
        assert json.loads(data["messages"][1]["content"])["submitted_text"] == TEXT
        if is_extraction(request):
            return response({"extracted_claim": TEXT})
        return response("```json\n" + json.dumps(classification()) + "\n```")
    result = analyse(handler, PREPARED.model_copy(update={"original_text": "DO NOT SEND THIS ORIGINAL COPY"}))
    assert result.checkable and result.extracted_claim == TEXT
    assert result.claim_confidence == 1.0
    assert len(calls) == 4


@pytest.mark.parametrize("category", ["opinion", "prediction", "personal_experience", "joke_or_satire", "unverifiable"])
def test_nonfactual_skips_extraction(category):
    def handler(request):
        assert not is_extraction(request)
        return response(classification(category))
    result = analyse(handler)
    assert not result.checkable and result.extracted_claim is None


@pytest.mark.parametrize("bad", [None, "", "  ", "...", "null", "none", {"text": TEXT},
    "A new $900 community tax starts next week.",
    "A new $500 community tax does not start next week.", "Unrelated assertion."])
def test_invalid_extraction_is_failure_not_noncheckable(bad):
    def handler(request):
        return response({"extracted_claim": bad} if is_extraction(request) else classification())
    with pytest.raises(PipelineComponentError) as caught:
        analyse(handler)
    assert caught.value.error_code == "CLAIM_EXTRACTION_FAILED"


@pytest.mark.parametrize('extracted', [
    'reach 52 C this weekend due to a record-breaking heatwave.',
    'Singapore could reach 52 C this weekend',
])
def test_extraction_cannot_drop_possible_modality_or_stated_cause(extracted):
    text = 'Singapore could reach 52 C this weekend due to a record-breaking heatwave.'
    prepared = PreparedText(original_text=text, normalised_text=text, language='en')
    def handler(request):
        return response({'extracted_claim': extracted} if is_extraction(request) else classification())
    with pytest.raises(PipelineComponentError) as caught:
        analyse(handler, prepared)
    assert caught.value.error_code == 'CLAIM_EXTRACTION_FAILED'


def test_specific_forecast_can_be_checkable_with_modality_and_cause_preserved():
    text = 'Singapore could reach 52 C this weekend due to a record-breaking heatwave.'
    prepared = PreparedText(original_text=text, normalised_text=text, language='en')
    def handler(request):
        return response({'extracted_claim': text} if is_extraction(request) else classification())
    result = analyse(handler, prepared)
    assert result.checkable and result.extracted_claim == text


def test_extraction_cannot_remove_a_cause_before_the_main_clause():
    text = 'Because of a heatwave, Singapore could reach 52 C this weekend.'
    prepared = PreparedText(original_text=text, normalised_text=text, language='en')
    with pytest.raises(ValueError, match='stated cause'):
        service._grounded_claim({'extracted_claim': 'Singapore could reach 52 C this weekend.'}, prepared)


@pytest.mark.parametrize("body", ["null", '"a string"', "[]", "not json", "```json\n{}", "{} trailing"])
def test_malformed_classifier_output_fails(body):
    with pytest.raises(PipelineComponentError) as caught:
        analyse(lambda request: response(body))
    assert caught.value.error_code == "CLAIM_ANALYSIS_UNAVAILABLE"


def test_truncated_output_cannot_vote():
    with pytest.raises(PipelineComponentError):
        analyse(lambda request: response(classification(), done_reason="length"))


@pytest.mark.parametrize("failing_models", [1, 2, 3])
def test_provider_failures_are_excluded(failing_models):
    def handler(request):
        if json.loads(request.content)["model"] in CLASSIFICATION_MODELS[:failing_models]:
            return httpx.Response(503, text="Sensitive provider details")
        return response(classification("unverifiable"))
    if failing_models == 1:
        result = analyse(handler)
        assert result.claim_confidence == 0.67
        assert "unavailable" in result.classification_reason
    else:
        with pytest.raises(PipelineComponentError) as caught:
            analyse(handler)
        assert "Sensitive" not in str(caught.value)


def test_extractor_transport_failure():
    def handler(request):
        if is_extraction(request):
            raise httpx.ConnectError("Sensitive provider details", request=request)
        return response(classification())
    with pytest.raises(PipelineComponentError) as caught:
        analyse(handler)
    assert caught.value.error_code == "CLAIM_EXTRACTION_FAILED"
    assert "Sensitive" not in str(caught.value)


def test_classifiers_run_concurrently():
    async def run():
        ready = asyncio.Event()
        started = []
        async def handler(request):
            started.append(request)
            if len(started) == 3:
                ready.set()
            await asyncio.wait_for(ready.wait(), timeout=1)
            return response(classification("opinion"))
        async with httpx.AsyncClient(base_url="https://ollama.com", transport=httpx.MockTransport(handler)) as client:
            result = await service._analyse_with_client(PREPARED, client)
        assert result.claim_confidence == 1.0
        assert len(started) == 3
    asyncio.run(run())


def test_request_deadline(monkeypatch):
    monkeypatch.setattr(service, "REQUEST_TIMEOUT_SECONDS", 0.01)
    async def handler(request):
        await asyncio.sleep(1)
        return response(classification())
    with pytest.raises(PipelineComponentError) as caught:
        analyse(handler)
    assert caught.value.error_code == "CLAIM_ANALYSIS_UNAVAILABLE"


def test_total_deadline(monkeypatch):
    monkeypatch.setattr(service, "TOTAL_TIMEOUT_SECONDS", 0.01)
    async def delayed(*args):
        await asyncio.sleep(1)
    monkeypatch.setattr(service, "_analyse_with_client", delayed)
    with pytest.raises(PipelineComponentError) as caught:
        asyncio.run(service._analyse(PREPARED, "dummy-offline-key"))
    assert caught.value.error_code == "CLAIM_ANALYSIS_TIMEOUT"


def test_missing_key_is_controlled(monkeypatch, tmp_path):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setattr(service, "PROJECT_ENV", tmp_path / "absent.env")
    with pytest.raises(PipelineComponentError) as caught:
        service.analyse_claim(PREPARED)
    assert caught.value.error_code == "CLAIM_ANALYSIS_NOT_CONFIGURED"
    assert not caught.value.retryable


def test_local_key_and_environment_precedence(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OLLAMA_API_KEY=local-test-value\n", encoding="utf-8")
    monkeypatch.setattr(service, "PROJECT_ENV", env_path)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    assert service._api_key() == "local-test-value"
    monkeypatch.setenv("OLLAMA_API_KEY", "deployment-test-value")
    assert service._api_key() == "deployment-test-value"


def test_outage_is_saved_as_failure_not_completed_nei():
    repository = InMemoryResultRepository()
    def unexpected(*args):
        pytest.fail("Downstream stage ran after claim failure")
    pipeline = PipelineOrchestrator(
        prepare_input=prepare_text,
        analyze_claim=lambda prepared: analyse(lambda request: httpx.Response(503), prepared),
        retrieve_evidence=unexpected, assess_evidence=unexpected, repository=repository,
    )
    with pytest.raises(PipelineComponentError):
        pipeline.analyze(TEXT)
    assert not repository.results
    assert len(repository.failures) == 1
    failure = next(iter(repository.failures.values()))
    assert failure.failure_stage == "claim_analysis"
    assert failure.error_code == "CLAIM_ANALYSIS_UNAVAILABLE"


def test_real_claim_stage_hands_off_to_assessment():
    from pathlib import Path
    fixture = Path(__file__).parents[2] / "fixtures/sprint_1/retrieval_result.json"
    repository = InMemoryResultRepository()
    def handler(request):
        return response({"extracted_claim": TEXT} if is_extraction(request) else classification())
    def retrieval(claim):
        assert claim.checkable and claim.extracted_claim == TEXT
        return json.loads(fixture.read_text(encoding="utf-8"))
    pipeline = PipelineOrchestrator(
        prepare_input=prepare_text, analyze_claim=lambda prepared: analyse(handler, prepared),
        retrieve_evidence=retrieval, assess_evidence=assess_evidence, repository=repository,
    )
    result = pipeline.analyze(TEXT)
    assert result.concern_label == "High Concern"
    assert result.misinformation_risk_score == 96
    assert repository.results[result.result_id] == result


def test_default_pipeline_connects_claim_stage_without_loading_key(monkeypatch):
    from app.pipeline.orchestration import dependencies
    monkeypatch.setattr(dependencies, "FirestoreResultRepository", InMemoryResultRepository)
    def unexpected():
        pytest.fail("Credentials were loaded before an analysis request")
    monkeypatch.setattr(service, "_api_key", unexpected)
    dependencies.get_pipeline_orchestrator.cache_clear()
    try:
        pipeline = dependencies.get_pipeline_orchestrator()
        assert pipeline._analyze_claim is service.analyse_claim
    finally:
        dependencies.get_pipeline_orchestrator.cache_clear()
