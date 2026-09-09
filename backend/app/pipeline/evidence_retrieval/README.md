# Evidence retrieval - Chu

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
