# Broader retrieval implementation — 9 September 2026

## What changed

- Added an optional `web` retrieval mode. `catalogue` retains the previous implementation and remains the repository template/default.
- Searches Google Fact Check and preferred Tavily domains, then uses broader queries when evidence remains insufficient.
- Extracts actual candidate pages instead of treating search snippets as final evidence.
- Removes the hard 60% word-overlap acceptance requirement in web mode. A bounded semantic selector checks relevance, quantities, dates and applicability.
- Uses numbered source sentences so the backend copies exact quotations and conditions. Invalid selections are rejected.
- Accepts the existing reviewed catalogue and registration-restricted `.gov`, `.gov.uk` and `.gov.au` namespaces for assessment. Publisher names and model opinions do not establish trust.
- Keeps unverified publishers as leads; follows literal links to eligible originals within the same four-URL extraction budget. Skips extraction of major social platforms.
- Forces context-only and unresolved-scope evidence to neutral during verdict aggregation.
- Removes exact duplicates and counts each source origin once per stance. Preserves disagreement from the same origin.
- Saves optional source/relevance/applicability provenance through the existing result API and Firestore serialization. Old saved results remain readable.
- Adds an evaluation runner, 43 provisional cases and a blank human-review spreadsheet.

## Validation

- **400 backend tests passed**, with one pre-existing Starlette/HTTPX deprecation warning.
- New tests cover domain lookalikes, public URL boundaries, unrelated pages, paraphrases, source-link discovery, extraction/LLM limits, provider failures, literal sentence selection, scope gates, duplicates and mode switching.
- API tests cover submission, owned-history retrieval and idempotent replay with provenance. Firestore serialization uses a fake client; no user records or allowances were changed by evaluation.
- No new mobile code changes were needed: the existing result screen renders reasons, source context, quotations and warnings.
- No known configured API-key values were found in changed text files. No tracked bytecode changes were generated.

## Live results — keep the versions separate

The provisional labels and small, deliberately selected samples do **not** establish general app accuracy. Every report contains code/dataset hashes. Expected labels and reference URLs never enter the retrieval/model prompts.

| Run | Cases | Catalogue label matches | Web label matches | Catalogue / web technical errors |
| --- | ---: | ---: | ---: | ---: |
| [Initial regression, v1](retrieval_web_regression_v1_2026-09-09.json) | 3 | 3 | 2 | 0 / 1 |
| [Development, v1](retrieval_web_development_v1_2026-09-09.json) | 24 | 11 | 11 | 11 / 13 |
| [Regression, v2 during rate limiting](retrieval_web_regression_v2_2026-09-09.json) | 3 | — | 0 | — / 3 |
| [Slower paired comparison, v2](retrieval_web_comparison_v2_2026-09-09.json) | 8 | 6 | 7 | 1 / 1 |
| [Final targeted regression, v3](retrieval_web_final_v3_2026-09-09.json) | 4 | — | 3 | — / 0 |

- The large first run encountered provider throttling and relevance-response validation failures. A separate Ollama request confirmed HTTP 429 with `Retry-After`. These errors are preserved, not excluded from the totals.
- The evaluation runner now defaults to one worker with cooldowns. It does not automatically hide failures through unbounded retries.
- The slower v2 comparison had **zero wrong decisive answers in either mode**, and zero literal-quote integrity failures. These are observations on eight provisional cases, not guarantees.
- Mean processing time in that comparison was **11.56 seconds catalogue / 17.83 seconds web**, excluding evaluator cooldowns. Claim-analysis time is included in each mode; it was performed once and shared between modes.
- Web mode returned evidence in **6/8 cases**, versus **5/8** for catalogue mode. This is evidence presence, not independently reviewed evidence recall.
- Web mode found NOAA evidence for the altered ocean-water claim, CDC/NIH-hosted evidence for the antibiotic claim and an Australian government source for Canberra without adding those individual domains to the catalogue.
- The v2 Moon-rings error was an unrelated page using `irrelevant` as its applicability value. V3 explicitly handles that only for already-irrelevant pages, which are discarded. Direct/context evidence still requires a substantive scope decision.
- The final v3 checks correctly refuted the Great Wall/Moon claim, retained uncertainty for the personal Phuket requirement, and treated the food preference as non-factual. The false Moon-rings claim remained uncertain because retrieval did not find adequate evidence. **That coverage gap is still unresolved.**
- Final v3 checks had **no technical errors, no wrong decisive answers and no invalid literal quotes** across four cases. V3's additional duplicate check and irrelevant-page handling were also covered by offline tests. The eight-case v2 results must not be presented as a full v3 evaluation.

## App rollout

- Local prototype mode: `EVIDENCE_RETRIEVAL_MODE=web`; restart the backend to activate.
- Activated locally and restarted on 9 September. The backend serves `127.0.0.1:8000`; its OpenAPI endpoint returned HTTP 200. Expo was listening on port 8081, but no Android emulator/device was connected at the final check.
- Pipeline version: `sprint-1-semantic-v3:gpt-oss:120b:retrieval-web-v3`.
- The repository template/default remains `catalogue`. Set that value and restart to roll back.
- Local activation is for prototype testing. Wider default rollout and accuracy claims need a clean full evaluation plus human review.
- Re-run a claim to use the new pipeline. Saved results retain their original version and explanation.

## Still incomplete

- **Human review:** [43-case spreadsheet](../datasets/retrieval_seed_v1_review.csv) and [review instructions](../datasets/RETRIEVAL_REVIEW_GUIDE.md). All labels remain provisional. The 16 holdout cases have not been run.
- **General source verification:** unfamiliar commercial, academic and international-organisation websites are not automatically promoted to decisive evidence. Coverage remains incomplete outside recognised namespaces/catalogue entries.
- **Retrieval coverage:** the four-page budget and six-window selector can miss an original document or its decisive qualification. Search providers sometimes return sources outside their requested domain filter.
- **Applicability:** model scope judgments can still be wrong. The existing personal-entry gate remains useful; a general interactive clarification flow is future work.
- **Independence:** copied or paraphrased articles across different publishers are not fully traced to their original source.
- **Confidence:** risk scores remain uncalibrated prototype heuristics.
- **Runtime verification:** live evaluations use real providers and in-memory persistence. They are not Android visual tests or live Firestore-write tests.

Implementation details and registry references: [Broader retrieval guide](../../backend/app/pipeline/evidence_retrieval/WEB_RETRIEVAL.md).
