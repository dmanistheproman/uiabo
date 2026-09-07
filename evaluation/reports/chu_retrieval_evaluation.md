# Chu retrieval integration - 7 September 2026

Google Fact Check and Tavily keys authenticated successfully. Their live retrieval
is connected to Matthew's claim analysis, Poon's assessment and the FastAPI route.
The initial prototype can now complete factual text checks with real citations.

The full offline backend suite passed: **247 tests**, including **45 retrieval
tests**, with all three API keys removed from the test process and dotenv disabled.
One existing Starlette/HTTPX test-client deprecation warning remains.

## Changes

Implemented Google review discovery, Tavily page extraction and scoped search
fallback, citation normalisation, source filtering, relevance ranking, duplicate
removal, typed output validation and bounded provider calls. Preserved Chu's fake
search hook and original five tests. Provider failures are distinguished from
successful searches that find no evidence. Keys remain in the ignored local .env.

Live inspection exposed a passage-selection defect: the Snopes introduction
repeated the false claim while its verdict was further down the page. The selector
now preserves a labelled claim/verdict block when its rating matches the provider
metadata. A regression test covers that failure. This does not guarantee that all
source passages preserve every relevant qualification.

## Live results

[Recorded requests and outputs](text_pipeline_live_2026-09-07.json) use actual
Ollama, Google and Tavily responses through FastAPI TestClient. The repository was
in-memory: there were no live Firestore writes or Android interactions.

| Input | API result | Evidence | Time |
| --- | --- | --- | --- |
| Great Wall visible from the Moon | HTTP 200, Needs Caution, score 67 | Snopes and two NASA sources | 6.36 s |
| Singapore independence on 9 August 1965 | HTTP 200, Low Concern, score 25 | NUS and NLB | 14.90 s |
| Chicken rice preference | HTTP 200, Not Enough Information, no score | Retrieval correctly skipped | 12.89 s |

All three operational checks passed and three completed records were saved in
memory. This is an operational check, not three correct factual verdicts or an
accuracy benchmark. No live outage was deliberately caused; those paths use mocked
HTTP tests.

## Remaining observed assessment problem

Poon's lexical baseline marked NASA's Great Wall-by-moonlight passage as supporting,
even though the passage describes the visibility claim as a myth. Snopes and the
other NASA passage were marked contradicting. This produced Needs Caution instead
of consistently recognising the debunking evidence. The issue remains in semantic
stance assessment; the retrieval implementation does not rewrite source text or
hard-code verdicts to hide it. Poon's assessment code was not changed in this task.

The prototype needs a broader labelled retrieval/stance dataset, evaluation of
paraphrases and mixed claims, and Android text-check/results integration. The source
catalogue is limited; overlap scores do not measure truth. The existing claim-stage
satire limitation also remains. Historical September 6 reports describe the earlier
state where retrieval was still disconnected.
