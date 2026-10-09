"""Bounded causal retrieval reaches the premise without fabricating relevance."""

import asyncio
import json
from datetime import date, datetime, timezone

import httpx

from app.pipeline.evidence_retrieval import enhanced, relevance
from app.pipeline.shared.components import component_queries


CLAIM = ("Government officials are discussing raising the retirement age to 75 "
         "because CPF reserves are running out faster than expected.")


def item(url, title, content, score=.9):
    return {"url": url, "title": title, "content": content, "score": score}


def test_premise_discovery_gets_extracted_within_existing_budget(monkeypatch):
    policy = "https://mom.gov.sg/policy"
    discussion = "https://channelnewsasia.com/discussion"
    financial = "https://mof.gov.sg/accounts"
    pages = {policy: "The published retirement age is 64.",
             discussion: "Officials explained the published retirement policy.",
             financial: "CPF reserves and funding are described in the financial statements."}
    queries, extracted = [], []

    async def google(*args):
        return []

    async def search(client, query, key, **options):
        queries.append(query)
        if query == component_queries(CLAIM)[1]:
            return [item(financial, "Funding accounts", pages[financial], .5)]
        return [item(policy, "Retirement policy", pages[policy], 1),
                item(discussion, "Retirement discussion", pages[discussion], .99)]

    async def extract(client, urls, key, **options):
        extracted.extend(urls)
        return {"results": [{"url": url, "raw_content": pages[url]} for url in urls], "failed_results": []}

    async def select(client, claim, text, key, **options):
        assert claim == CLAIM
        return relevance.Selection(window_id=0, relevance="context", quote=text,
            reason="Useful context for a component, not the entire allegation.",
            applicability="missing_context", applicability_reason="Other assertions remain unresolved.",
            condition_quotes=[]), text

    monkeypatch.setattr(enhanced.providers, "google_search", google)
    monkeypatch.setattr(enhanced.providers, "tavily_search", search)
    monkeypatch.setattr(enhanced.providers, "tavily_extract", extract)
    monkeypatch.setattr(enhanced, "select_with_client", select)
    result = asyncio.run(enhanced.retrieve_with_client(CLAIM, None, "g", "t", "o"))
    assert queries == [CLAIM, *component_queries(CLAIM)]
    assert extracted[:2] == [policy, financial]
    assert result.trace.search_requests == 3
    assert result.trace.extraction_urls <= 4
    assert result.trace.relevance_calls <= 4
    assert len(result.evidence) == 3
    assert all(evidence.provenance.relevance == "context" for evidence in result.evidence)
    assert all(evidence.provenance.applicability == "missing_context" for evidence in result.evidence)


def test_premise_scheduling_never_bypasses_source_policy():
    run = enhanced.RetrievalRun(CLAIM, None, "g", "t", "o")
    unknown = "https://financial-rumours.example/article"
    official = "https://mom.gov.sg/policy"
    run.add(item(unknown, "Financial rumour", CLAIM, 1), "web_search", component_id="premise")
    run.add(item(official, "Retirement policy", "Actual retirement policy", .5), "preferred_search")
    assert run.next_pages(1)[0]["url"] == official


def test_later_financial_passage_survives_event_heavy_document():
    financial = "CPF reserves are measured in the audited statements, with assets and liabilities reported separately."
    text = ("Government officials are discussing the retirement age and retirement policies. " * 400
            + financial)
    windows = relevance.source_windows(CLAIM, text)
    assert len(windows) <= 6
    assert any(financial in window for window in windows)


def test_selector_receives_exact_components_without_promoting_context():
    text = "CPF reserve figures are published with the accounting period and financial assumptions."

    def handler(request):
        payload = json.loads(request.content)
        data = json.loads(payload["messages"][1]["content"])
        assert [part["component_id"] for part in data["claim_components"]] == ["event", "premise", "causal_link"]
        assert all(part["text"] in CLAIM for part in data["claim_components"])
        assert data["claim_components"][0]["time_scope"] == "current"
        assert "missing implementation date is not missing timing" in payload["messages"][0]["content"]
        raw = {"window_id": 0, "relevance": "context", "quote_start": 0, "quote_end": 0,
               "reason": "Addresses the financial premise only.", "applicability": "missing_context",
               "applicability_reason": "The event and causal link remain unestablished.", "condition_ranges": []}
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(raw)}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await relevance.select_with_client(client, CLAIM, text, "test", as_of=date(2026, 10, 8))

    selection, passage = asyncio.run(run())
    assert selection.relevance == "context"
    assert selection.applicability == "missing_context"
    assert selection.quote == passage == text


def test_cpf_scope_beats_foreign_government_and_ticker_results_without_new_eligibility():
    run = enhanced.RetrievalRun(CLAIM, None, "g", "t", "o")
    run.now = datetime(2026, 10, 8, tzinfo=timezone.utc)
    financial = "https://www.mof.gov.sg/policies/reserves/what-are-the-reserves-used-for"
    stock = "https://www.sec.gov/Archives/edgar/data/701347/cpf-20260331.htm"
    foreign = "https://larson.house.gov/social-security-retirement-age"
    old = "https://www.cpf.gov.sg/CPF_AnnualReport2022_Part2.pdf"
    run.add(item(stock, "CPF financial statements", "Central Pacific Financial assets", 1), "web_search", component_id="premise")
    run.add(item(foreign, "Retirement age discussion", "US Social Security", 1), "web_search", component_id="event")
    run.add(item(old, "CPF Annual Report 2022", "Financial statements", .9), "web_search", component_id="premise")
    run.add(item(financial, "What are reserves used for", "CPF reserve funding", .4), "web_search", component_id="premise")
    pages = run.next_pages(2)
    assert pages[0]["url"] == financial
    assert pages[1]["url"] == old
    assert run.source(stock).eligible  # still allowed for a claim it actually addresses
    assert run.source(foreign).eligible
    assert "component" not in run.source(financial).reason.lower()


def test_named_fund_accounting_context_outranks_unrelated_reserve_drawdowns():
    fiscal = "National reserves are depleting after emergency spending. The treasury drew down reserves faster than expected."
    mechanism = "CPF monies are invested in government securities. Assets backing these obligations exceed the liabilities."
    assert relevance.financial_detail_score(CLAIM, mechanism) > 0
    assert relevance.financial_detail_score(CLAIM, fiscal) == 0
    # This helper ranks discovery windows only; a relevant funding mechanism is
    # not a finding that the depletion allegation is false.
    assert relevance.financial_detail_score(CLAIM, mechanism) > relevance.financial_detail_score(CLAIM, fiscal)


def test_financial_window_ranking_is_not_specific_to_cpf_or_a_stance():
    claim = "Officials are changing benefits because Cedar Pension Fund reserves are shrinking."
    increasing = "Cedar Pension Fund balances increased in the audited financial statements."
    decreasing = "Cedar Pension Fund balances decreased in the audited financial statements."
    other_fund = "Maple Pension Fund balances decreased in the audited financial statements."
    assert relevance.financial_detail_score(claim, increasing) > 0
    assert relevance.financial_detail_score(claim, increasing) == relevance.financial_detail_score(claim, decreasing)
    assert relevance.financial_detail_score(claim, other_fund) == 0


def test_navigation_does_not_supply_financial_window_priority():
    navigation = ("## CPF assets and liabilities\n"
                  "* [CPF government securities and guarantees](https://example.org/funding)\n"
                  "* [CPF audited financial statements and balances](https://example.org/report)\n")
    assert relevance.financial_detail_score(CLAIM, navigation) == 0


def test_financial_backing_sections_survive_mixed_financial_page_with_literal_window_budget():
    navigation = "* [CPF balances and audited assets](https://example.org/accounts)\n"
    fiscal = "The government drew down national reserves for emergency spending faster than expected. "
    interest = "CPF interest rates depend on the savings account. Members can read the current rates. "
    backing = ("CPF monies are invested in government securities. "
               "Assets backing these obligations exceed the liabilities. "
               "The guarantee describes the funding arrangement, not a forecast of future balances.")
    buffer = ("CPF obligations are backed by financial assets. "
              "The audited balance sheet records assets, liabilities and a buffer against investment losses.")
    text = navigation * 12 + fiscal * 100 + "\n\n" + backing + "\n\n" + interest * 60 + "\n\n" + buffer
    windows = relevance.source_windows(CLAIM, text)
    assert 1 <= len(windows) <= 6
    assert all(window in text and len(window) <= 1800 for window in windows)
    assert any(backing in window for window in windows)
    assert any(buffer in window for window in windows)


def test_financial_context_without_allegation_terms_stays_context_after_literal_selection():
    text = "CPF monies are invested in government securities. Assets back the liabilities to members."

    def handler(request):
        payload = json.loads(request.content)
        data = json.loads(payload["messages"][1]["content"])
        assert any(text in " ".join(sentence["text"].strip() for sentence in window["sentences"])
                   for window in data["windows"])
        raw = {"window_id": 0, "relevance": "context", "quote_start": 0, "quote_end": 1,
               "reason": "Describes the named scheme's funding, without settling the alleged depletion.",
               "applicability": "missing_context", "applicability_reason": "No balance period or comparator is established.",
               "condition_ranges": []}
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(raw)}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await relevance.select_with_client(client, CLAIM, text, "test", as_of=date(2026, 10, 8))

    selection, passage = asyncio.run(run())
    assert selection.quote == passage == text
    assert selection.relevance == "context"
    assert selection.applicability == "missing_context"
