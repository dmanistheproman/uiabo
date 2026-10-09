"""Ranking discovery preserves scope and budget; eligibility never means truth."""

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.pipeline.evidence_retrieval import enhanced
from app.pipeline.evidence_retrieval.relevance import Selection, source_windows
from app.pipeline.evidence_retrieval.source_policy import classify_source, url_identity
from app.pipeline.shared.context import build_claim_context
from app.pipeline.shared.rankings import ranking_queries, political_salary_ranking

CLAIM = "Singapore prime minister is the highest paid politician"
NOW = datetime(2026, 10, 5, 10, tzinfo=timezone.utc)


def item(url, title="Highest paid world leaders", score=.9):
    return {"url": url, "title": title, "score": score, "content": "Published annual salaries comparison."}


@pytest.mark.parametrize("text", [CLAIM, "The US president is the lowest-paid world leader.",
    "Is Singapore's prime minister the highest-paid politician?", "The Swiss president has the highest salary in Europe in 2025."])
def test_salary_comparisons_preserve_original_scope_in_discovery(text):
    assert political_salary_ranking(text)
    queries = ranking_queries(text)
    assert len(queries) == 2
    assert all(text in query for query in queries)
    assert build_claim_context(text, NOW).assumptions


@pytest.mark.parametrize("text", ["Singapore's prime minister is the richest politician.",
    "The highest paid politician including private income is the US president.",
    "Singapore's prime minister earns a salary.", "Singapore will hit 50 C next Saturday."])
def test_salary_scope_never_substitutes_for_wealth_or_noncomparative_claims(text):
    assert not political_salary_ranking(text)
    assert not any("political office" in value for value in build_claim_context(text, NOW).assumptions)
    assert not classify_source("https://politicalsalaries.com/about/", text).eligible


def test_reviewed_comparison_source_is_scoped_and_host_checked():
    assert classify_source("https://politicalsalaries.com/world-leaders/", CLAIM).eligible
    assert classify_source("https://www.politicalsalaries.com/world-leaders/", CLAIM).source_type == "other"
    for domain in ["politicalsalaries.com.evil.org", "fakepoliticalsalaries.com", "user.politicalsalaries.com"]:
        assert not classify_source("https://" + domain, CLAIM).eligible
    assert classify_source("https://www.bbc.com/news/article").origin_group == classify_source("https://www.bbc.co.uk/news/article").origin_group
    assert classify_source("https://www.cnbc.com/news/article").source_type == "news"


def test_ranking_page_precedes_high_scoring_salary_policy_introduction():
    run = enhanced.RetrievalRun(CLAIM, None, "g", "t", "o")
    run.add(item("https://www.channelnewsasia.com/policy", "Political salaries review", 1), "preferred_search")
    run.add(item("https://www.bbc.com/comparison", score=.5), "preferred_search")
    assert run.next_pages(1)[0]["url"] == "https://www.bbc.com/comparison"


def test_failed_publisher_is_deprioritised_only_for_current_request():
    failed = "https://www.reuters.com/blocked"
    another = "https://www.reuters.com/another"
    available = "https://www.channelnewsasia.com/policy"
    run = enhanced.RetrievalRun(CLAIM, None, "g", "t", "o")
    for value in [item(failed), item(another, score=1), item(available, "Political salaries", .5)]:
        run.add(value, "preferred_search")
    run.attempted.add(url_identity(failed))
    run.unavailable_pages.add(failed)
    assert run.next_pages(1)[0]["url"] == available
    run.attempted.add(url_identity(available))
    assert run.next_pages(1)[0]["url"] == another  # not a permanent ban
    fresh = enhanced.RetrievalRun(CLAIM, None, "g", "t", "o")
    fresh.add(item(another), "preferred_search")
    assert fresh.next_pages(1)[0]["url"] == another


def test_explicit_comparison_survives_long_salary_policy_page():
    comparison = "Singapore's prime minister ranks first among heads of government by published annual salary."
    text = ("The salary framework covers fixed pay, variable pay and employment policies. " * 450) + comparison
    assert any(comparison in window for window in source_windows(CLAIM, text))


def test_failed_ranking_page_falls_back_to_comparisons_within_original_budget(monkeypatch):
    failed = "https://www.reuters.com/ranking-one"
    repeat = "https://www.reuters.com/ranking-two"
    bbc = "https://www.bbc.com/news/comparison"
    data = "https://politicalsalaries.com/ranking/"
    searches, extracted = [], []

    async def google(*args):
        return []

    async def search(client, query, key, **options):
        searches.append((query, options))
        if options.get("broad"):
            return [item(bbc), item(data)]
        assert "politicalsalaries.com" in options["preferred_domains"]
        return [item(failed, score=1), item(repeat, score=.99)]

    async def extract(client, urls, key, **options):
        extracted.extend(urls)
        return {"results": [{"url": url, "raw_content": "A published world leader salary ranking from " + url}
                            for url in urls if url != failed],
                "failed_results": [{"url": url} for url in urls if url == failed]}

    async def select(client, claim, text, key, **options):
        return Selection(window_id=0, relevance="direct", quote=text, reason="Comparative source",
            applicability="established", applicability_reason="Matching scope", condition_quotes=[]), text

    monkeypatch.setattr(enhanced.providers, "google_search", google)
    monkeypatch.setattr(enhanced.providers, "tavily_search", search)
    monkeypatch.setattr(enhanced.providers, "tavily_extract", extract)
    monkeypatch.setattr(enhanced, "select_with_client", select)

    async def run():
        async with httpx.AsyncClient() as client:
            return await enhanced.retrieve_with_client(CLAIM, client, "g", "t", "o",
                claim_context=build_claim_context(CLAIM, NOW))
    result = asyncio.run(run())
    assert result.retrieval_status == "completed"
    assert extracted == [failed, bbc, data]
    assert repeat not in extracted
    assert result.trace.search_requests == 3
    assert result.trace.extraction_urls == 3
    assert len(searches) == 3
    assert {item.publisher for item in result.evidence} == {"BBC", "Political Salaries"}
