"""Behavioural checks of broad discovery, provenance, scope and failure boundaries."""

import asyncio
import json

import httpx
import pytest

from app.pipeline.evidence_retrieval import enhanced, service
from app.pipeline.evidence_retrieval.relevance import source_windows, validate_selection, validate_span_selection
from app.pipeline.evidence_retrieval.source_policy import classify_source, public_url
from app.pipeline.evidence_assessment import semantic
from app.pipeline.shared.models import ClaimAnalysis, EvidenceCandidate, EvidenceProvenance, RetrievalResult
from app.pipeline.orchestration.service import _combine_evidence


CLAIM = "Canberra is Australia's capital."
TEXT = "The Australian federal government sits in Canberra. Sydney is not its seat."


def selection(**changes):
    return {"window_id": 0, "relevance": "direct", "quote": TEXT,
        "reason": "The passage identifies the capital using different wording.",
        "applicability": "established", "applicability_reason": "Same country and capital.",
        "condition_quotes": [], **changes}


def result_item(url="https://australia.gov.au/capital", **changes):
    return {"url": url, "title": "National capital", "content": TEXT, "score": 0.95, **changes}


def run(handler):
    async def request():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await enhanced.retrieve_with_client(CLAIM, client, "google-test", "tavily-test", "ollama-test")
    return asyncio.run(request())


class Provider:
    def __init__(self, *, preferred=None, broad=None, pages=None, judgment=None, fail=None):
        self.preferred = preferred or []
        self.broad = broad or []
        self.pages = pages or {}
        self.judgment = judgment or selection()
        self.fail = fail
        self.searches, self.extractions = [], []

    def __call__(self, request):
        if request.url.host == "factchecktools.googleapis.com":
            assert request.headers["x-goog-api-key"] == "google-test"
            assert "authorization" not in request.headers
            return httpx.Response(503 if self.fail == "google" else 200, json={})
        payload = json.loads(request.content)
        if request.url.host == "ollama.com":
            assert request.headers["authorization"] == "Bearer ollama-test"
            assert "x-goog-api-key" not in request.headers
            if payload["model"] == "gemma4:31b":
                raw = {"queries": ["Australia capital city official information", "Australian federal seat of government"]}
            else:
                if self.fail == "relevance":
                    return httpx.Response(429, json={"error": "secret-provider-value"})
                raw = self.judgment
                data = json.loads(payload["messages"][1]["content"])
                raw = {key: value for key, value in raw.items() if key not in {"quote", "condition_quotes"}}
                raw.update(quote_start=0, quote_end=len(data["windows"][0]["sentences"]) - 1,
                           condition_ranges=[])
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(raw)}})
        assert request.url.host == "api.tavily.com"
        assert request.headers["authorization"] == "Bearer tavily-test"
        assert "x-goog-api-key" not in request.headers
        if request.url.path == "/search":
            self.searches.append(payload)
            assert payload["include_answer"] is False
            return httpx.Response(200, json={"results": self.preferred if "include_domains" in payload else self.broad})
        assert request.url.path == "/extract"
        self.extractions.extend(payload["urls"])
        if self.fail == "extract":
            return httpx.Response(503, json={"error": "secret-provider-value"})
        return httpx.Response(200, json={"results": [
            {"url": url, "raw_content": self.pages.get(url, TEXT)} for url in payload["urls"]], "failed_results": []})


@pytest.mark.parametrize("url", ["https://cdc.gov/a", "https://gov.uk/a", "https://ons.gov.uk/a",
    "https://health.gov.au/a", "https://moh.gov.sg/a"])
def test_new_government_domains_are_eligible_without_catalogue_additions(url):
    assert classify_source(url).eligible


@pytest.mark.parametrize("url", ["https://cdc.gov.evil.com/a", "https://fakegov.uk/a",
    "https://official-travel.com/a", "https://thaiembassy.com/a", "https://university.edu/a"])
def test_appearance_or_generic_academic_suffix_does_not_establish_identity(url):
    assert not classify_source(url).eligible


@pytest.mark.parametrize("url", ["http://127.0.0.1/a", "http://[::1]/a", "http://169.254.169.254/a",
    "https://localhost/a", "https://name.internal/a", "https://gov.uk@evil.com/a",
    "https://gov.uk:8000/a", "file:///secrets", "https://gov.uk\\@evil.com/a",
    "https://bad..gov.uk/a", "https://-bad.gov.uk/a", "https://gov.uk/\nsecret"])
def test_invalid_or_nonpublic_urls_are_rejected(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_broad_search_finds_new_authority_and_ignores_word_overlap_threshold():
    assert service.relevance(CLAIM, TEXT) < 0.6
    provider = Provider(broad=[result_item()])
    result = run(provider)
    assert result.retrieval_status == "completed"
    evidence = result.evidence[0]
    assert evidence.provenance.source_policy == "government_namespace"
    assert evidence.provenance.discovery_method == "web_search"
    assert evidence.provenance.relevance_quote in evidence.passage
    assert len(provider.searches) == 3
    assert "include_domains" in provider.searches[0]
    assert all("include_domains" not in item for item in provider.searches[1:])


def test_existing_but_inconclusive_evidence_still_triggers_broad_search():
    provider = Provider(preferred=[result_item("https://gov.sg/a")],
        judgment=selection(relevance="context", applicability="missing_context"))
    result = run(provider)
    assert len(provider.searches) == 3
    assert result.evidence[0].provenance.applicability == "missing_context"


def test_sufficient_distinct_origins_skip_more_searches():
    # Different passages prevent exact duplicate removal from obscuring the test.
    provider = Provider(preferred=[result_item("https://gov.sg/a"), result_item("https://nasa.gov/a")],
        pages={"https://nasa.gov/a": TEXT + " Further explanation."})
    result = run(provider)
    assert len(provider.searches) == 1
    assert len(result.evidence) == 2


def test_unverified_search_results_are_only_leads():
    provider = Provider(broad=[result_item("https://random-travel.com/a")])
    result = run(provider)
    assert result.retrieval_status == "no_evidence"
    assert not result.evidence
    assert result.trace.relevance_calls == 0
    assert any("only as leads" in warning for warning in result.warnings)


def test_social_results_do_not_consume_page_extraction_budget():
    provider = Provider(broad=[result_item("https://facebook.com/groups/a"), result_item("https://reddit.com/r/test/a")])
    result = run(provider)
    assert result.retrieval_status == "no_evidence"
    assert provider.extractions == []


def test_failed_optional_lead_extraction_is_not_a_pipeline_outage():
    result = run(Provider(broad=[result_item("https://random-travel.com/a")], fail="extract"))
    assert result.retrieval_status == "no_evidence"
    assert not result.evidence


def test_failed_query_planning_still_runs_broad_literal_search():
    provider = Provider(broad=[result_item()])
    def handler(request):
        if request.url.host == "ollama.com" and json.loads(request.content)["model"] == "gemma4:31b":
            return httpx.Response(429, json={"error": "private-provider-detail"})
        return provider(request)
    result = run(handler)
    assert result.retrieval_status == "completed"
    assert provider.searches[-1]["query"] == CLAIM
    assert "include_domains" not in provider.searches[-1]
    assert "private-provider-detail" not in result.model_dump_json()


def test_unknown_page_can_lead_to_literal_original_source():
    provider = Provider(broad=[result_item("https://random-travel.com/a")], pages={
        "https://random-travel.com/a": "See [official guidance](https://australia.gov.au/capital)."})
    result = run(provider)
    assert result.evidence[0].provenance.discovery_method == "source_link"
    assert str(result.evidence[0].url) == "https://australia.gov.au/capital"
    assert result.trace.extraction_urls == 2


@pytest.mark.parametrize("failure", ["extract", "relevance"])
def test_provider_failure_is_not_presented_as_valid_uncertainty(failure):
    result = run(Provider(broad=[result_item()], fail=failure))
    assert result.retrieval_status == "failed"
    assert "secret-provider-value" not in result.model_dump_json()


@pytest.mark.parametrize("relevance,expected", [("irrelevant", "no_evidence"), ("context", "completed")])
def test_one_inaccessible_page_does_not_erase_successful_reviews(relevance, expected):
    accessible, broken = "https://gov.sg/readable", "https://gov.sg/broken"
    base = Provider(preferred=[result_item(accessible), result_item(broken)],
        judgment=selection(relevance=relevance, applicability="missing_context"))
    def handler(request):
        response = base(request)
        if request.url.path == "/extract":
            payload = response.json()
            payload["results"] = [item for item in payload["results"] if item["url"] != broken]
            payload["failed_results"] = [{"url": broken, "error": "private-provider-detail"}]
            return httpx.Response(200, json=payload)
        return response
    result = run(handler)
    assert result.retrieval_status == expected
    assert any("coverage is incomplete" in warning for warning in result.warnings)
    assert any(event["decision"] == "source_page_unavailable" for event in result.trace.decisions)
    assert "private-provider-detail" not in result.model_dump_json()
    if relevance == "context":
        assert str(result.evidence[0].url) == accessible
        assert result.evidence[0].provenance.applicability == "missing_context"


def test_no_readable_eligible_pages_remains_a_technical_failure():
    base = Provider(preferred=[result_item()])
    def handler(request):
        if request.url.path == "/extract":
            urls = json.loads(request.content)["urls"]
            return httpx.Response(200, json={"results": [], "failed_results": [
                {"url": url, "error": "Could not fetch"} for url in urls]})
        return base(request)
    assert run(handler).retrieval_status == "failed"


@pytest.mark.parametrize("failure", ["http", "missing_result", "relevance"])
def test_valid_irrelevant_review_does_not_hide_provider_or_contract_failure(failure):
    first, second = "https://gov.sg/first", "https://nasa.gov/second"
    base = Provider(preferred=[result_item(first)], broad=[result_item(second)],
        pages={second: "Second source. " + TEXT}, judgment=selection(relevance="irrelevant"))
    def handler(request):
        if request.url.path == "/extract" and second in json.loads(request.content)["urls"]:
            if failure == "http":
                return httpx.Response(503, json={"error": "private-provider-detail"})
            if failure == "missing_result":
                return httpx.Response(200, json={"results": [], "failed_results": []})
        if request.url.host == "ollama.com" and "Second source." in request.content.decode():
            if failure == "relevance":
                return httpx.Response(429, json={"error": "private-provider-detail"})
        return base(request)
    result = run(handler)
    assert result.retrieval_status == "failed"
    assert not result.evidence
    assert "private-provider-detail" not in result.model_dump_json()


def test_google_failure_does_not_prevent_broad_fallback():
    result = run(Provider(broad=[result_item()], fail="google"))
    assert result.retrieval_status == "completed"
    assert result.warnings


def test_extraction_and_model_calls_have_fixed_limits():
    provider = Provider(preferred=[result_item(f"https://gov.sg/{i}") for i in range(8)],
        broad=[result_item(f"https://australia.gov.au/{i}") for i in range(8)],
        judgment=selection(relevance="context"))
    result = run(provider)
    assert result.trace.extraction_urls == 4
    assert result.trace.relevance_calls == 4
    assert result.trace.search_requests == 3


def test_unrequested_extracted_url_is_never_attached_to_requested_metadata():
    base = Provider(broad=[result_item()])
    def handler(request):
        if request.url.path == "/extract":
            return httpx.Response(200, json={"results": [
                {"url": "https://evil.com/a", "raw_content": TEXT}]})
        return base(request)
    result = run(handler)
    assert result.retrieval_status == "failed"
    assert not result.evidence


@pytest.mark.parametrize("change", [
    {"window_id": 99}, {"quote": "Made up facts"}, {"quote": ""},
    {"condition_quotes": ["Invented qualification"]}, {"applicability": "probably"},
    {"window_id": True}, {"extra": "instruction"},
])
def test_unvalidated_model_output_cannot_become_evidence(change):
    with pytest.raises(ValueError):
        validate_selection(selection(**change), [TEXT])


def test_selected_windows_preserve_source_text_and_size_bounds():
    page = "Navigation menu. " * 500 + TEXT + " Background. " * 300
    windows = source_windows(CLAIM, page)
    assert 1 <= len(windows) <= 6
    assert all(len(window) <= 1800 and window in page for window in windows)


def test_payment_windows_retain_counterevidence_without_matching_alleged_numbers():
    claim = 'From October, residents above 60 pay a $300 monthly permit deduction.'
    boilerplate = ('October information for residents above 60 about the $300 monthly permit deduction. ' * 100)
    rule = 'The permit premium is payable once a year. Annual premiums are deducted each year.'
    page = boilerplate + ' Background. ' * 200 + rule + ' Conditions apply. ' * 100
    windows = source_windows(claim, page)
    assert any(rule in window for window in windows)
    assert len(windows) <= 6
    assert all(window in page and len(window) <= 1800 for window in windows)


def test_later_query_can_improve_a_duplicate_pages_discovery_rank():
    run = enhanced.RetrievalRun(CLAIM, None, 'g', 't', 'o')
    run.add(result_item(score=.6), 'preferred_search')
    run.add(result_item(url='https://australia.gov.au/overview',score=.7), 'preferred_search')
    run.add(result_item(score=.9,content='More useful search metadata'), 'web_search')
    assert len(run.pool)==2
    assert run.next_pages(1)[0]['url']=='https://australia.gov.au/capital'
    run.attempted.add('https://australia.gov.au/capital')
    assert run.next_pages(1)[0]['url']=='https://australia.gov.au/overview'


@pytest.mark.parametrize("changes", [{"quote_start": None}, {"quote_end": 900},
    {"quote_start": 1, "quote_end": 0}, {"quote_start": True},
    {"condition_ranges": [{"start": 0, "end": 99}]}])
def test_invalid_sentence_selections_cannot_become_evidence(changes):
    raw = {key: value for key, value in selection().items() if key not in {"quote", "condition_quotes"}}
    raw.update(quote_start=0, quote_end=1, condition_ranges=[])
    raw.update(changes)
    with pytest.raises(ValueError):
        validate_span_selection(raw, [TEXT])


def test_sentence_selection_copies_original_markdown_and_conditions():
    raw = {key: value for key, value in selection().items() if key not in {"quote", "condition_quotes"}}
    raw.update(quote_start=0, quote_end=1, condition_ranges=[{"start": 1, "end": 1}])
    text = "**Entry** is free. Registration is required."
    result, passage = validate_span_selection(raw, [text])
    assert result.quote == text
    assert result.condition_quotes == ["Registration is required."]


def test_irrelevant_page_can_decline_to_select_any_source_span():
    raw = {key: value for key, value in selection().items() if key not in {"quote", "condition_quotes"}}
    raw.update(window_id=None, relevance="irrelevant", quote_start=None, quote_end=None, condition_ranges=[])
    result, _ = validate_span_selection(raw, [TEXT])
    assert result.relevance == "irrelevant" and result.quote == ""
    raw["relevance"] = "direct"
    with pytest.raises(ValueError):
        validate_span_selection(raw, [TEXT])


@pytest.mark.parametrize("scope", ["not_applicable", "irrelevant"])
def test_nonapplicable_scope_is_only_valid_for_discarded_unrelated_pages(scope):
    raw = {key: value for key, value in selection().items() if key not in {"quote", "condition_quotes"}}
    raw.update(window_id=None, relevance="irrelevant", applicability=scope,
               quote_start=None, quote_end=None, condition_ranges=[])
    assert validate_span_selection(raw, [TEXT])[0].relevance == "irrelevant"
    raw.update(window_id=0, relevance="direct", quote_start=0, quote_end=0)
    with pytest.raises(ValueError):
        validate_span_selection(raw, [TEXT])


def provenance(**changes):
    return EvidenceProvenance(source_policy="government_namespace", source_reason="Restricted namespace.",
        origin_group="gov.au", discovery_method="web_search", relevance="direct",
        relevance_reason="Same topic.", relevance_quote=TEXT, applicability_reason="Same country.",
        **{"applicability": "established", **changes})


def evidence(identifier="one", **changes):
    return EvidenceCandidate(evidence_id=identifier, url=f"https://australia.gov.au/{identifier}",
        title="Capital", publisher="Australian government", source_type="government",
        passage=TEXT, retrieval_score=0.9, retrieved_at="2026-09-09T00:00:00Z",
        provenance=provenance(**changes))


def assess(items):
    claim = ClaimAnalysis(extracted_claim=CLAIM, checkable=True, claim_category="factual",
        claim_confidence=1, classification_reason="Factual.")
    retrieval = RetrievalResult(retrieval_status="completed", evidence=items)
    judgments = [semantic.Judgment(stance="supporting", evidence_quote=TEXT,
        reason="The source supports the claim.") for item in items]
    return semantic.aggregate(claim, retrieval, judgments), retrieval


@pytest.mark.parametrize("scope", ["missing_context", "different_scope", "uncertain_time"])
def test_scope_gate_overrides_even_a_supporting_stance(scope):
    result, retrieval = assess([evidence(applicability=scope)])
    assert result.concern_label == "Not Enough Information"
    assert result.misinformation_risk_score is None
    assert result.assessed_evidence[0].stance == "neutral"
    assert "supports the claim" not in result.explanation
    combined = _combine_evidence(retrieval, result.assessed_evidence)
    assert combined[0].provenance.applicability == scope
    assert combined[0].evidence_quote in combined[0].passage


def test_many_pages_from_one_origin_do_not_raise_confidence():
    single, _ = assess([evidence()])
    multiple, _ = assess([evidence("one"), evidence("two"), evidence("three")])
    assert multiple.uncertainty == single.uncertainty
    assert multiple.uncertainty_reasons == single.uncertainty_reasons
    assert len(multiple.assessed_evidence) == 3


def test_identical_passages_across_origins_do_not_stop_fallback():
    first, second = evidence("one"), evidence("two")
    second.provenance.origin_group = "another-publisher"
    assert not enhanced.enough_evidence([first, second])


def test_mode_switch_is_explicit_and_defaults_to_previous_pipeline(monkeypatch):
    monkeypatch.delenv("EVIDENCE_RETRIEVAL_MODE", raising=False)
    assert service.configured_retriever()[1] == service.RETRIEVAL_VERSION
    monkeypatch.setenv("EVIDENCE_RETRIEVAL_MODE", "web")
    assert service.configured_retriever()[1] == enhanced.VERSION


def test_timeout_preserves_already_validated_evidence(monkeypatch):
    base = Provider(preferred=[result_item("https://gov.sg/a")])
    async def handler(request):
        if request.url.path == "/search" and "include_domains" not in json.loads(request.content):
            await asyncio.sleep(1)
        return base(request)
    monkeypatch.setattr(enhanced, "TOTAL_TIMEOUT_SECONDS", 0.05)
    result = run(handler)
    assert result.retrieval_status == "completed"
    assert result.evidence and result.warnings
