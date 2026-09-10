# Retrieval failure fix — 10 September 2026

## Reproduced issue

The Android app showed `RETRIEVAL_UNAVAILABLE` for:

> From October, all Singaporeans above 60 will receive a compulsory $300 monthly deduction from CPF to fund MediShield Life.

The isolated reproduction found that Google, Tavily and Ollama requests returned HTTP 200. Three CPF pages were extracted and reviewed, but their relevance decisions rejected them because the exact allegation was absent. A fourth page was reported as inaccessible by Tavily. With no retained evidence, that single failed page made the entire retrieval result a technical failure.

## Changes

- Retrieval v4 distinguishes a provider-reported inaccessible source page from provider outages and malformed responses. If another eligible page was successfully reviewed, an inaccessible page becomes a coverage warning. If no eligible page could be reviewed, retrieval still fails.
- A failed relevance check or provider request is still a technical failure when no evidence survives. Invalid source responses are not silently converted into a completed uncertain result.
- The relevance prompt distinguishes related context from exact confirmation. A source explaining the same scheme can be retained even when it does not repeat the claimed amount or date. Missing information does not prove falsity, and an unspecified month does not establish a year.
- Search, extraction, model-call and timeout budgets remain unchanged. Source eligibility and literal-quotation validation remain in place.

## Validation

- **406 backend tests passed**, with one existing Starlette/HTTPX deprecation warning.
- Six additional test cases cover partially inaccessible sources, all sources inaccessible, preserved context, malformed extraction responses, provider outages and relevance failures.
- Tests ran with `PYTHON_DOTENV_DISABLED=1` so personal runtime configuration did not select live modes inside default-mode tests. An initial run without that isolation had two mode/configuration failures; the complete isolated suite passed.
- Final direct retrieval completed with a retained CPF context passage and an incomplete-coverage warning for an inaccessible page.
- Full API smoke checks used real cloud providers, authenticated test identities and **in-memory storage**. They did not write to user Firestore records or consume the user's allowance.

| Input | HTTP result | Assessment | Evidence entries | Time |
|---|---|---|---:|---:|
| Reported CPF/MediShield Life message | 200 | Not Enough Information | 2 | 16.73 s |
| Canberra is the capital of Australia | 200 | Low Concern | 2 | 23.38 s |
| Chocolate ice cream tastes better than vanilla | 200 | Not Enough Information; opinion | 0 | 2.42 s |

All three checks appeared in their isolated account's history. Replaying each completed request returned the same result, and each test account was charged exactly one successful check in memory.

These are debugging smoke checks, not independently labelled accuracy measurements. Retrieval/assessment judgments can still vary or misinterpret scope. The CPF message was not established as true or false by this run; the fix removes the reproduced technical failure and retains useful context.

## Local activation

The local backend was restarted after validation. Its OpenAPI endpoint returned HTTP 200; Expo remained listening on port 8081. The pipeline version used by the checks is `sprint-1-semantic-v3:gpt-oss:120b:retrieval-web-v4`.

No mobile code changed. Submit a new check to use the fix; historical results keep their original version. This verification did not include a new Android visual test or a live Firestore write.
