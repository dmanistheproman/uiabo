"""Selection failures must explain lost coverage without promoting evidence."""

import asyncio

import pytest

from app.pipeline.evidence_retrieval import enhanced, relevance
from app.pipeline.evidence_retrieval.source_policy import url_identity


@pytest.mark.parametrize("decision", ["irrelevant", "context", "direct"])
def test_selection_trace_preserves_bounded_reason_and_scope(monkeypatch, decision):
    passage = "The named fund's securities and liabilities are described here."
    reason = "Substantive selection reason. " * 24
    scope = "Financial comparison remains unspecified. " * 18
    url = "https://www.mof.gov.sg/funding"
    run = enhanced.RetrievalRun("The fund is running out.", None, "g", "t", "o")
    run.add({"url": url, "title": "Fund backing", "score": .9}, "web_search")

    async def select(*args, **kwargs):
        return relevance.Selection(window_id=0, relevance=decision,
            quote="" if decision == "irrelevant" else passage,
            reason=reason, applicability="missing_context", applicability_reason=scope,
            condition_quotes=[]), passage

    monkeypatch.setattr(enhanced, "select_with_client", select)
    asyncio.run(run.select(run.pool[url_identity(url)], passage, run.source(url)))
    event = run.trace.decisions[-1]
    assert event["reason"] == reason[:600]
    assert event["applicability_reason"] == scope[:600]
    assert event["applicability"] == "missing_context"
    if decision == "irrelevant":
        assert event["decision"] == "rejected_semantically_irrelevant"
        assert run.evidence == []
    else:
        assert run.evidence[0].provenance.relevance == decision
        assert run.evidence[0].provenance.applicability == "missing_context"
        assert run.evidence[0].provenance.relevance_reason == reason.strip()
