import asyncio
import json

import httpx
import pytest

from app.pipeline.evidence_retrieval import query_planning as planning, service


CLAIM = "I need to have 20000 baht in cash to enter phuket"
QUERY = "Thailand entry cash requirements 20,000 baht"


def test_query_validation_preserves_amounts_and_discards_bad_alternatives():
    assert planning.validate_queries({"queries": [QUERY, "Thailand entry cash requirements 10000 baht"]}, CLAIM) == [QUERY]


@pytest.mark.parametrize("raw", [
    {"queries": ["Thailand entry requirements"]},
    {"queries": ["20000 baht site:evil.example"]},
    {"queries": ["20000 baht https://evil.example"]},
    {"queries": [QUERY], "extra": True}, {"queries": []},
    {"queries": [QUERY, QUERY, QUERY]}, {"queries": [123]},
])
def test_invalid_or_unscoped_query_plans_are_rejected(raw):
    with pytest.raises(ValueError):
        planning.validate_queries(raw, CLAIM)


def test_search_amount_formatting_does_not_rewrite_years_or_identifiers():
    text = "In 2026, policy ABC20000 requires 20000 baht or 15000 dollars."
    assert planning.format_search_amounts(text) == "In 2026, policy ABC20000 requires 20,000 baht or 15,000 dollars."
    assert planning.format_search_amounts("20,000 baht") == "20,000 baht"


def test_fallback_keeps_original_claim_and_only_accepts_reviewed_sources(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-ollama-key")
    seen_searches = []
    seen_claims = []
    passage = ("Travellers entering Thailand under the Tourist Visa Exemption Scheme "
               "must possess adequate cash of or equivalent to 20,000 Baht per person or 40,000 Baht per family.")
    def handler(request):
        if request.url.host == "factchecktools.googleapis.com":
            assert "authorization" not in request.headers
            return httpx.Response(200, json={})
        body = json.loads(request.content)
        if request.url.host == "ollama.com":
            assert request.headers["authorization"] == "Bearer test-ollama-key"
            assert "x-goog-api-key" not in request.headers
            seen_claims.append(json.loads(body["messages"][1]["content"])["claim"])
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({"queries": [QUERY]})}})
        assert request.headers["authorization"] == "Bearer test-tavily-key"
        seen_searches.append(body["query"])
        url = "https://forum.invalid/thread" if len(seen_searches) == 1 else "https://doha.thaiembassy.org/en/visa"
        return httpx.Response(200, json={"results": [{"url": url, "title": "Entry guidance", "content": passage, "score": 0.9}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await service._retrieve_with_client(CLAIM, client, "test-google-key", "test-tavily-key",
                                                       planning_key="test-ollama-key")
    result = asyncio.run(run())
    assert seen_claims == [CLAIM]
    assert seen_searches == [planning.format_search_amounts(CLAIM), QUERY]
    assert result.retrieval_status == "completed"
    assert len(result.evidence) == 1
    assert result.evidence[0].passage == passage
    assert result.evidence[0].retrieval_score == 0.6  # Ranked against original claim, not the generated query.


def test_query_planning_does_not_run_when_original_search_succeeds(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-ollama-key")
    async def unexpected(*args):
        pytest.fail("Unnecessary query expansion")
    monkeypatch.setattr(service, "plan_queries", unexpected)
    def handler(request):
        return httpx.Response(200, json={} if request.url.host == "factchecktools.googleapis.com" else {
            "results": [{"url": "https://gov.sg/article", "title": "Test", "content": CLAIM, "score": 0.9}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await service._retrieve_with_client(CLAIM, client, "google", "tavily", planning_key="test-ollama-key")
    assert asyncio.run(run()).retrieval_status == "completed"


def test_planner_failure_is_a_controlled_failed_search(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-ollama-key")
    def handler(request):
        if request.url.host == "ollama.com":
            return httpx.Response(429)
        return httpx.Response(200, json={} if request.url.host == "factchecktools.googleapis.com" else {"results": []})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await service._retrieve_with_client(CLAIM, client, "google", "tavily", planning_key="test-ollama-key")
    result = asyncio.run(run())
    assert result.retrieval_status == "failed"
    assert not result.evidence
