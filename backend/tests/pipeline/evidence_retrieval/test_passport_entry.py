"""Passport discovery regression: entry rules versus outbound travel advice."""

import asyncio
from datetime import datetime, timezone
import json

import httpx
import pytest

from app.pipeline.evidence_retrieval import enhanced, relevance
from app.pipeline.evidence_retrieval.passport_entry import current_entry_query, entry_page_priority
from app.pipeline.shared.dates import infer_date_context


CLAIM = "ICA will begin rejecting passports with less than one year of validity from November"
ENTRY_URL = "https://ica.gov.sg/enter-transit-depart/entering-singapore"
OUTBOUND_URL = "https://ica.gov.sg/documents/passport/travel-overseas"


def test_underlying_rule_query_has_no_hardcoded_answer_or_alleged_threshold():
    query = current_entry_query(CLAIM)
    assert "Singapore ICA" in query and "entry requirements" in query
    assert all(word not in query for word in ("six", "6", "one year", "November", "false", "reject"))


@pytest.mark.parametrize("claim", [
    "ICA says Singaporeans travelling overseas need passports with six months validity",
    "ICA says passports must have one year validity to enter Thailand",
    "ICA will begin rejecting passport renewal applications from November",
    "A passport is valid for ten years after issue",
    "Thailand requires passports with six months validity to enter Thailand",
])
def test_destination_and_different_passport_topics_keep_normal_planner(claim):
    assert current_entry_query(claim) is None


def test_entry_candidate_outranks_outbound_advice_without_rejecting_either():
    run = enhanced.RetrievalRun(CLAIM, None, "g", "t", "o")
    for url, title, score in [(OUTBOUND_URL, "Advice for travel overseas", .99),
                              (ENTRY_URL, "ICA | Entering Singapore", .70)]:
        run.add({"url": url, "title": title, "score": score}, "preferred_search")
    assert [page["url"] for page in run.next_pages(2)] == [ENTRY_URL, OUTBOUND_URL]
    assert len(run.pool) == 2


def test_entry_candidate_hint_is_generic_and_does_not_change_other_topics():
    url = "https://gov.uk/entry-requirements"
    assert entry_page_priority("Visitors entering Britain need six months passport validity", "Entry requirements", url) == 1
    assert entry_page_priority("Passports issued abroad remain valid ten years", "Entry requirements", url) == 0
    assert entry_page_priority("The capital of Britain is London", "Entry requirements", url) == 0


def test_fallback_finds_current_entry_rule_preserves_future_claim_and_budget():
    context = infer_date_context(CLAIM, datetime(2026, 9, 16, tzinfo=timezone.utc))
    outbound_text = "Before travelling overseas, check the passport validity requirements of your destination."
    # Mock text is explicitly scoped and is not an answer injected by retrieval.
    entry_text = "All travellers except Singapore passport holders need at least six months of passport validity."
    searches, extractions, assessed_claims = [], [], []

    def handler(request):
        if request.url.host == "factchecktools.googleapis.com":
            return httpx.Response(200, json={})
        payload = json.loads(request.content)
        if request.url.host == "ollama.com":
            assert payload["model"] != "gemma4:31b"  # Known lookup needs no extra planner call.
            data = json.loads(payload["messages"][1]["content"])
            assessed_claims.append(data["claim"])
            assert data["date_context"]["display_date"] == "November 2026"
            raw = {"window_id": 0, "relevance": "context", "quote_start": 0, "quote_end": 0,
                   "reason": "Current passport guidance, not an announcement of the future change.",
                   "applicability": "uncertain_time", "applicability_reason": "Future period not established.",
                   "condition_ranges": []}
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(raw)}})
        if request.url.path == "/search":
            searches.append(payload)
            items = [{"url": OUTBOUND_URL, "title": "Travel overseas", "score": .99}]
            if payload["query"] == current_entry_query(CLAIM):
                items.append({"url": ENTRY_URL, "title": "Entering Singapore", "score": .60})
            return httpx.Response(200, json={"results": items})
        assert request.url.path == "/extract"
        extractions.extend(payload["urls"])
        return httpx.Response(200, json={"results": [
            {"url": url, "raw_content": entry_text if url == ENTRY_URL else outbound_text}
            for url in payload["urls"]], "failed_results": []})

    async def retrieve():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await enhanced.retrieve_with_client(CLAIM, client, "g", "t", "o", date_context=context)

    result = asyncio.run(retrieve())
    assert result.retrieval_status == "completed"
    assert len(searches) == result.trace.search_requests == 3
    assert "November 2026" in searches[1]["query"]
    assert "official announcement" in searches[1]["query"]
    assert "include_domains" in searches[0] and "include_domains" not in searches[2]
    assert ENTRY_URL in extractions and len(extractions) == 2
    assert result.trace.extraction_urls <= 4 and result.trace.relevance_calls <= 4
    assert set(assessed_claims) == {CLAIM}
    entry = next(item for item in result.evidence if str(item.url) == ENTRY_URL)
    assert entry.provenance.relevance == "context"
    assert entry.provenance.applicability == "uncertain_time"
    assert entry.provenance.relevance_quote == entry_text


@pytest.mark.parametrize("future_covered, expected", [(False, "uncertain_time"), (True, "established")])
def test_current_context_cannot_silently_establish_future_scope(future_covered, expected):
    context = infer_date_context(CLAIM, datetime(2026, 9, 16, tzinfo=timezone.utc))
    text = "Visitor passports need at least nine months validity; citizens are exempt."
    if future_covered:
        text = "From November 2026, " + text

    def handler(request):
        raw = {"window_id": 0, "relevance": "context", "quote_start": 0, "quote_end": 0,
               "reason": "The page explains the current passport rule.", "applicability": "established",
               "applicability_reason": "This is an established present rule.",
               "condition_ranges": [{"start": 0, "end": 0}]}
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(raw)}})

    async def select():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await relevance.select_with_client(client, CLAIM, text, "test-key",
                                                      as_of=context.as_of, date_context=context)

    selected, passage = asyncio.run(select())
    assert selected.relevance == "context"
    assert selected.applicability == expected
    assert selected.quote == passage == text
    assert selected.condition_quotes == [text]


def test_same_topic_retention_does_not_force_unrelated_page_into_evidence():
    context = infer_date_context(CLAIM, datetime(2026, 9, 16, tzinfo=timezone.utc))
    def handler(request):
        raw = {"window_id": None, "relevance": "irrelevant", "quote_start": None, "quote_end": None,
               "reason": "A sports club opening is unrelated to passports.", "applicability": "not_applicable",
               "applicability_reason": "Unrelated topic.", "condition_ranges": []}
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(raw)}})

    async def select():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await relevance.select_with_client(client, CLAIM, "A sports club opens in November 2026.",
                                                      "test-key", as_of=context.as_of, date_context=context)

    selected, _ = asyncio.run(select())
    assert selected.relevance == "irrelevant"
    assert selected.quote == ""
