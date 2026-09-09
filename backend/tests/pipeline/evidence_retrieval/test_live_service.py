"""Offline tests of real provider adapters, filtering, and pipeline integration."""

import asyncio
import json

import httpx
import pytest

from app.pipeline.evidence_retrieval import providers, service
from app.pipeline.evidence_retrieval.sources import canonical_url
from app.pipeline.shared.models import ClaimAnalysis, RetrievalResult


TEXT = "A new $500 community tax starts next week."
CLAIM = ClaimAnalysis(extracted_claim=TEXT, claim_category="factual", checkable=True,
                      classification_reason="Checkable test claim.", claim_confidence=1.0)
PASSAGE = "No new $500 community tax starts next week. The circulating message is false."
URL = "https://www.gov.sg/article/community-tax"


def search_item(**updates):
    return {"url": URL, "title": "Community tax clarification", "content": PASSAGE,
            "score": 0.95, **updates}


def google_claim(url="https://www.snopes.com/fact-check/community-tax/"):
    return {"text": TEXT, "claimReview": [{"url": url, "title": "Community tax fact check",
        "reviewDate": "2026-08-20T00:00:00Z", "textualRating": "False", "languageCode": "en"}]}


def run(handler):
    async def request():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await service._retrieve_with_client(TEXT, client, "google-test-key", "tavily-test-key")
    return asyncio.run(request())


def test_google_empty_falls_back_to_scoped_tavily_search():
    calls = []
    def handler(request):
        calls.append(request.url.host)
        assert "key=" not in str(request.url)
        if request.url.host == "factchecktools.googleapis.com":
            assert request.headers["x-goog-api-key"] == "google-test-key"
            assert "authorization" not in request.headers
            return httpx.Response(200, json={})
        assert request.headers["authorization"] == "Bearer tavily-test-key"
        assert "x-goog-api-key" not in request.headers
        payload = json.loads(request.content)
        assert payload["include_answer"] is False
        assert payload["auto_parameters"] is False
        assert "gov.sg" in payload["include_domains"]
        return httpx.Response(200, json={"results": [search_item(published_date="2026-08-20")]})
    result = run(handler)
    assert result.retrieval_status == "completed"
    assert result.evidence[0].source_type == "government"
    assert str(result.evidence[0].published_at) == "2026-08-20"
    assert calls == ["factchecktools.googleapis.com", "api.tavily.com"]


def test_google_review_requires_source_text_and_keeps_review_date():
    def handler(request):
        if request.url.host == "factchecktools.googleapis.com":
            return httpx.Response(200, json={"claims": [google_claim()]})
        if request.url.path == "/extract":
            payload = json.loads(request.content)
            return httpx.Response(200, json={"results": [{"url": payload["urls"][0], "raw_content": PASSAGE}], "failed_results": []})
        return httpx.Response(200, json={"results": []})
    result = run(handler)
    assert len(result.evidence) == 1
    assert result.evidence[0].passage == PASSAGE
    assert result.evidence[0].passage != TEXT
    assert result.evidence[0].source_type == "fact_check"
    assert str(result.evidence[0].published_at) == "2026-08-20"


def test_google_metadata_alone_is_never_evidence():
    def handler(request):
        if request.url.host == "factchecktools.googleapis.com":
            return httpx.Response(200, json={"claims": [google_claim()]})
        if request.url.path == "/extract":
            return httpx.Response(200, json={"results": [], "failed_results": [{"url": "redacted"}]})
        return httpx.Response(200, json={"results": []})
    result = run(handler)
    assert result.retrieval_status == "failed"
    assert not result.evidence


def test_two_fact_check_pages_avoid_additional_search():
    urls = ["https://snopes.com/fact-check/a", "https://fullfact.org/a"]
    def handler(request):
        if request.url.host == "factchecktools.googleapis.com":
            return httpx.Response(200, json={"claims": [google_claim(url) for url in urls]})
        assert request.url.path == "/extract"
        return httpx.Response(200, json={"results": [
            {"url": url, "raw_content": PASSAGE + f" Source number {i}."} for i, url in enumerate(urls)]})
    assert len(run(handler).evidence) == 2


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_google_failure_can_return_tavily_evidence_with_warning(status):
    def handler(request):
        if request.url.host == "factchecktools.googleapis.com":
            return httpx.Response(status, text="Sensitive key details")
        return httpx.Response(200, json={"results": [search_item()]})
    result = run(handler)
    assert result.retrieval_status == "completed" and result.warnings
    assert "Sensitive" not in result.model_dump_json()


def test_failure_plus_empty_search_is_not_normal_no_evidence():
    def handler(request):
        if request.url.host == "factchecktools.googleapis.com":
            raise httpx.ConnectError("secret URL", request=request)
        return httpx.Response(200, json={"results": []})
    assert run(handler).retrieval_status == "failed"


def test_both_successful_empty_searches_return_no_evidence():
    result = run(lambda request: httpx.Response(200, json={"claims": [], "results": []}))
    assert result.retrieval_status == "no_evidence"


@pytest.mark.parametrize("bad", [None, {}, "invalid", [None]])
def test_malformed_provider_lists_fail(bad):
    result = run(lambda request: httpx.Response(200, json={"claims": bad, "results": bad}))
    assert result.retrieval_status == "failed"


@pytest.mark.parametrize("changes", [
    {"content": ""}, {"content": None}, {"score": "0.99"}, {"score": 2},
    {"score": True}, {"score": None}, {"title": ""}, {"url": None},
])
def test_invalid_candidate_is_discarded_without_fabrication(changes):
    def handler(request):
        return httpx.Response(200, json={} if request.url.host == "factchecktools.googleapis.com"
                              else {"results": [search_item(**changes)]})
    result = run(handler)
    assert result.retrieval_status == "failed"
    assert not result.evidence


@pytest.mark.parametrize("url", ["https://gov.sg.evil.example/a", "https://evilgov.sg/a",
    "http://127.0.0.1/a", "file:///etc/passwd", "https://user:pass@gov.sg/a", "https://gov.sg:8080/a"])
def test_source_filter_checks_hostname_boundaries(url):
    with pytest.raises(ValueError):
        canonical_url(url)


def test_relevance_duplicates_and_unknown_sources():
    items = [search_item(), search_item(url=URL + "/?utm_source=test#section"),
        search_item(url="https://snopes.com/syndicated"),
        search_item(url="https://unapproved.example/a"),
        search_item(url="https://gov.sg/unrelated", content="A completely unrelated topic.", score=1.0),
        search_item(url="https://gov.sg/low-score", score=0.2)]
    def handler(request):
        return httpx.Response(200, json={} if request.url.host == "factchecktools.googleapis.com" else {"results": items})
    result = run(handler)
    assert len(result.evidence) == 1
    assert "utm_" not in str(result.evidence[0].url)


def test_canonical_url_keeps_article_identifiers():
    assert canonical_url("https://www.nlb.gov.sg/main/article?cmsuuid=abc&utm_campaign=x#top") == "https://nlb.gov.sg/main/article?cmsuuid=abc"
    assert canonical_url("https://nlb.gov.sg/main/article?cmsuuid=abc") != canonical_url("https://nlb.gov.sg/main/article?cmsuuid=def")


def test_unknown_publication_date_stays_unknown():
    candidate = service._candidate(TEXT, url=URL, title="Title", content=PASSAGE, published_at="unknown")
    assert candidate.published_at is None


def test_fact_check_passage_keeps_source_verdict_with_reviewed_claim():
    page = "Subscribe now. " + TEXT + " This is a popular rumour. Author details. Claim: " + TEXT + " Rating: False. " + PASSAGE
    passage = service.select_passage(TEXT, page, review_rating="False")
    assert passage.startswith("Claim:")
    assert "Rating: False" in passage
    assert PASSAGE in passage
    assert "Subscribe" not in passage


def test_rating_metadata_is_not_fabricated_into_source_text():
    passage = service.select_passage(TEXT, TEXT, review_rating="False")
    assert passage == TEXT
    assert "False" not in passage


def test_missing_keys_do_not_call_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "PROJECT_ENV", tmp_path / "absent")
    monkeypatch.delenv("GOOGLE_FACT_CHECK_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert service.retrieve_evidence(CLAIM).retrieval_status == "failed"


def test_noncheckable_does_not_load_credentials(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Credentials should not be loaded")
    monkeypatch.setattr(service, "load_dotenv", unexpected)
    result = service.retrieve_evidence(CLAIM.model_copy(update={"checkable": False, "claim_category": "opinion", "extracted_claim": None}))
    assert result.retrieval_status == "no_evidence"


def test_total_timeout(monkeypatch):
    monkeypatch.setattr(service, "TOTAL_TIMEOUT_SECONDS", 0.01)
    async def delayed(*args, **kwargs):
        await asyncio.sleep(1)
    monkeypatch.setattr(service, "_retrieve_with_client", delayed)
    result = asyncio.run(service._live(TEXT, "dummy", "dummy"))
    assert result.retrieval_status == "failed"
    assert "time limit" in result.warnings[0]


def test_provider_timeout(monkeypatch):
    monkeypatch.setattr(providers, "REQUEST_TIMEOUT_SECONDS", 0.01)
    async def delayed(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={})
    assert run(delayed).retrieval_status == "failed"


def test_typed_and_legacy_boundaries():
    from tests.pipeline.evidence_retrieval.test_service import fake_successful_search
    assert isinstance(service.retrieve_evidence(CLAIM, fake_successful_search), RetrievalResult)
    assert isinstance(service.retrieve_evidence(CLAIM.model_dump(), fake_successful_search), dict)


@pytest.mark.parametrize("provider_failure", [False, True])
def test_default_api_wiring_with_real_retrieval_and_assessment(monkeypatch, provider_failure, signed_analysis):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.pipeline.orchestration import dependencies
    from app.pipeline.orchestration.repository import InMemoryResultRepository
    repository = InMemoryResultRepository()
    store, _ = signed_analysis
    def handler(request):
        if provider_failure:
            return httpx.Response(503, text="secret provider details")
        return httpx.Response(200, json={} if request.url.host == "factchecktools.googleapis.com"
                              else {"results": [search_item()]})
    monkeypatch.setattr(dependencies, "analyse_claim", lambda prepared: CLAIM)
    monkeypatch.setattr(dependencies, "FirestoreResultRepository", lambda: repository)
    monkeypatch.setenv("GOOGLE_FACT_CHECK_API_KEY", "dummy-google")
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-tavily")
    original = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    dependencies.get_pipeline_orchestrator.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.post("/analysis/text", json={"text": TEXT})
        if provider_failure:
            assert response.status_code == 503
            assert response.json()["detail"]["error_code"] == "RETRIEVAL_UNAVAILABLE"
            records = [data for (collection, _), data in store.documents.items() if collection == "analysis_results"]
            assert len(records) == 1 and records[0]["processing_status"] == "failed"
        else:
            assert response.status_code == 200
            assert response.json()["concern_label"] == "High Concern"
            assert response.json()["evidence"][0]["stance"] == "contradicting"
            records = [data for (collection, _), data in store.documents.items() if collection == "analysis_results"]
            assert len(records) == 1 and records[0]["processing_status"] == "completed"
        assert "secret" not in response.text
    finally:
        dependencies.get_pipeline_orchestrator.cache_clear()
