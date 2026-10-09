# Evidence retrieval - Chu

## Material-part retrieval update (8 October 2026)

Current web version `retrieval-web-v16` keeps the ranking and source-access fixes
below and adds discovery for conservative causal claim components. The shared
`components.py` splits one explicit asserted cause into exact event, premise and
causal-link spans. Ambiguous scope remains on the existing whole-claim route.

- The initial search still uses the original allegation. One initial extraction
  leaves room for the two existing follow-up search slots: one for the event and
  one for the material premise. Financial premises include neutral financial
  statement terms; no verdict or financial fact is inserted into the query.
- Eligible pages discovered for the premise receive a reserved extraction
  attempt so event-heavy results do not consume all the slots. Query membership
  is only a scheduling hint and never establishes relevance or truth.
- Shared entity/country context is retained across both queries. In the narrow
  retirement/savings context, CPF expands to Singapore's Central Provident Fund
  for discovery; food-company, stock-ticker and conflicting-country uses do not.
  Subject-matching CPF/MOF/MOM pages precede foreign social-security or CPF-stock
  results, with old accounts deprioritised for a current allegation. Eligibility
  and semantic applicability are still checked separately. The discovery
  interpretation is recorded in the retrieval trace, not substituted for a claim.
- `relevance-v13` receives the literal components and retains substantive
  component passages. A useful financial-premise passage can remain whole-claim
  context; it is not automatically promoted to direct/applicable evidence.
- Financial passage selection prioritises the named fund's backing or trend
  over another balance with similar words. General government reserves are not
  interchangeable with pension member balances. Useful funding context does not
  need to repeat the allegation, and retaining it does not refute the allegation.
- Accepted and rejected selections record bounded relevance and applicability
  reasons in the retrieval trace, so lost source coverage can be diagnosed.
- Current alleged discussions are interpreted separately from the future policy
  implementation date. Missing coverage, ordinary published policy and generic
  financial guarantees do not themselves prove the causal allegation false.
- Bounds remain three Tavily searches, one Google request, four relevance calls,
  four base extraction slots, at most two unavailable-page replacements and the
  existing stage deadline. No extra provider or unbounded search loop is added.

The v3 assessor can subsequently evaluate each component against the retained
passages. See the [assessment rules](../evidence_assessment/README.md#material-parts-of-causal-claims-8-october-2026).
Regression tests in `test_component_coverage.py` and `shared/test_components.py`
cover literal spans, excluded scopes, financial discovery, source-policy gates,
passage retention and request budgets. They do not establish live accuracy.

An 8 October live selector replay of the two extracted MOF reserves pages kept
their CPF backing passages as context after this change. One had previously been
rejected for not mentioning the precise allegation; the other selected general
fiscal spending instead of CPF funding. Assessment of the unchanged retirement-
age/depletion allegation with these passages still returned insufficient evidence.
This verifies improved passage retention, not a successful misinformation verdict
or an end-to-end retrieval accuracy benchmark.

## Ranking retrieval update (5 October 2026)

Web version `retrieval-web-v14` recognises superlative/ranking claims and seeks
comparative evidence. It preserves the submitted claim and adds discovery hints;
it never hard-codes a subject's rank. Ranking pages are prioritised over salary
policy introductions. Passage windows retain comparative statements and the
selector checks geography, period, population, metric and qualifications.

BBC and CNBC join the reviewed news catalogue. Political Salaries is a scoped
comparison source for political-pay ranking claims only. See the
[source review](../../../../evaluation/trusted_sources/README.md).

An explicit unavailable page lowers that publisher's priority for the rest of
the request. Subsequent extraction batches contain at most two pages, or one
when both are from the same publisher, allowing failure feedback before spending
more slots there. Alternatives are preferred, but no publisher is permanently
banned. Existing limits remain: three searches, four relevance calls, four base
extraction slots and at most two replacements for explicitly unavailable pages.

The salary diagnostic now retrieves accessible comparison articles instead of
only background about pay policy. Historical rankings with unresolved dates
remain context and cannot drive a current verdict. This is a targeted diagnostic,
not an accuracy benchmark.

The optional **web** mode adds broader search, original-page extraction, semantic relevance and applicability checks. See [the implementation and rollout guide](WEB_RETRIEVAL.md). The flow below documents the retained **catalogue** mode.

The live Sprint 1 implementation connects Google Fact Check Tools and Tavily.
It preserves Chu's filtering, deduplication, status handling and fake-search hook,
and adds the provider calls and typed pipeline handoff.

## Setup

In the ignored project-root `uiabo/.env`, configure `GOOGLE_FACT_CHECK_API_KEY`
and `TAVILY_API_KEY`. Enable Fact Check Tools API in the Google Cloud project.
Use the Tavily API key itself, not the MCP connection URL. The backend uses REST
APIs directly; no MCP client installation is required. Shell/deployment variables
take precedence. Keys load at request time; restart after changing a local key.
Neither key belongs in mobile code or an `EXPO_PUBLIC_*` variable.

## Retrieval flow

1. Accept `ClaimAnalysis`; skip non-checkable content without using credentials.
2. Search Google for up to five English fact-checked claims. The search query is
   whitespace-normalised and limited to 400 characters; relevance uses the full claim.
3. Match the reviewed claim by keyword coverage and accept review URLs only from
   the initial source catalogue. Extract up to three review pages with Tavily.
4. Select a source passage with surrounding context. Where the page contains a
   labelled rating matching Google's metadata, keep the publisher's claim/verdict
   block together. Never substitute Google's reviewed-claim field for evidence.
5. If fewer than two distinct passages survive, run one Tavily advanced search
   restricted to the catalogue, requesting up to eight results. Generated answers,
   images and automatic search parameters are disabled.
6. Validate citation fields, filter relevance, remove duplicate URLs/content,
   rank by relevance and return up to six `EvidenceCandidate` objects.

The typed call returns `RetrievalResult`. Dictionary callers retain Chu's original
JSON return format. Supplying `search_func` injects a test search and bypasses live
providers; this compatibility hook is not used by the runtime pipeline.

## Relevance and provenance

Google passage relevance is the fraction of non-stopword claim tokens found in
that passage. Tavily relevance is the smaller of its returned score and the same
local overlap. Both require at least 0.60. This conservative lexical baseline can
miss paraphrases and admit related statements that do not settle the claim. Scores
measure retrieval relevance, not truth or calibrated probability.

Citations retain publisher/domain, title, source URL, a source excerpt, known
publication/review date and a UTC retrieval timestamp. Unknown dates remain null;
claim dates and event dates are not substituted for publication dates. The catalogue
sets source types; a Google-indexed review is tagged `fact_check` only after source
text is extracted. Page extraction and search content remain untrusted source data.

URLs are checked against exact domains or real subdomains. Tracking parameters
and fragments are removed; meaningful query parameters such as NLB article IDs
are preserved. Unsupported schemes, credentials and nonstandard ports are rejected.
Duplicate content is also removed, but this does not establish source independence.

## Failures and bounds

### Web mode (`EVIDENCE_RETRIEVAL_MODE=web`)

`retrieval-web-v12` preserves discovered fetch URLs, including `www.`, trailing
slashes and query ordering. Normalised URLs are used only as duplicate keys;
citations retain the URL used for extraction.

See [claim interpretation and forecast scoring](CLAIM_INTERPRETATION.md) for
relationship-focused discovery, scoped first-party sources, long-document passage
selection, question/hypothetical handling and the forecast-conflict indicator.

Web mode allows three Tavily searches, one Google request, four semantic relevance
calls and four extracted pages. Explicitly unavailable source pages allow up to
two replacement pages from the discovered candidates (six extraction URLs total).
Provider outages and invalid responses do not increase this budget. All work
remains inside the 65-second deadline, and a failed URL is not repeatedly fetched.

If every eligible page is unreadable, the orchestrator returns a retryable HTTP
503 with `SOURCE_PAGES_UNAVAILABLE` and explains that sources were found but could
not be read. Other retrieval failures retain `RETRIEVAL_UNAVAILABLE`. Readable,
inconclusive evidence can still produce an unresolved assessment; failed page
access is not evidence that a claim is true or false.

### Catalogue baseline

- Each provider call has a 20-second deadline; connections time out after 5 seconds.
- The whole retrieval stage has a 65-second deadline. There are no automatic retries.
- Google failure triggers Tavily fallback. Failed extraction also permits fallback.
- Partial failure with usable evidence returns completed with warnings.
- Failure without usable evidence returns failed, which the orchestrator turns into
  a controlled HTTP 503. A provider outage is never a successful empty search.
- Successful searches without accepted evidence return no_evidence.
- Provider exception text and credentials are not copied into API responses.

The worst normal request makes one Google search, one Tavily extraction batch and
one Tavily advanced search. These consume the configured accounts' quota/allowance.

## Tests and limitations

Run `python -m pytest tests/pipeline/evidence_retrieval -q` from `backend` for offline
HTTP-adapter, fallback, validation, failure, deadline and integration tests. Chu's
original five tests are preserved.

For a live check of all text stages, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.text_pipeline_smoke_test --report ../evaluation/reports/text_pipeline_live_local.json
```

It uses FastAPI TestClient and in-memory storage, not Firestore or Android. See
`evaluation/reports/chu_retrieval_evaluation.md` for observed results and the remaining
stance-assessment failure. Passage windows can still omit context. This initial
English source scope and lexical ranking need a larger labelled retrieval dataset.

Provider references:

- [Google claims.search](https://developers.google.com/fact-check/tools/api/reference/rest/v1alpha1/claims/search)
- [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)
# Retrieval follow-up: natural wording and entry requirements

- Official Thai MFA and embassy domains were added after reviewing their provenance; commercial lookalike domains remain excluded.
- Currency amounts such as `20000 baht` use `20,000 baht` in search queries. Both formats match the same passage tokens. The user's claim is preserved unchanged.
- First-person helper words are excluded from lexical relevance matching.
- If ordinary retrieval succeeds but finds no accepted evidence, the existing Ollama key can generate up to two alternative discovery queries. Invalid alternatives are discarded; all accepted queries preserve the claim's numerical values.
- Query expansion is a discovery aid, never evidence and never a replacement for the original claim. Results still pass the reviewed-domain filter and are ranked against the original claim.
- Query planning has a 15-second deadline. All retrieval work, including alternative searches, stays inside the existing 65-second stage deadline.
- Search-provider results have been observed outside the requested domains, so local source validation remains necessary.
- Personal entry obligations require applicability context. The assessor abstains when the statement omits passport/nationality or visa/entry category, and now explains that missing context in the result.
- The application pipeline appends `retrieval-v2` to its version to identify this revision. Earlier evaluation reports describe their recorded versions, not a fresh accuracy benchmark for this change.
