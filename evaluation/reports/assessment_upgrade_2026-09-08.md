# UIABO assessment upgrade - 8 September 2026

## Implemented

- Added semantic evidence assessment using `gpt-oss:120b` through the existing Ollama Cloud key.
- The model reads each claim and retrieved passage together, returning supporting, contradicting or neutral, with a short explanation and source quotation.
- Claims and passages are treated as untrusted content. The development run exposed an instruction-following error; the revised prompt explicitly distinguishes commands from factual evidence.
- Quotations must match a contiguous source span. Whitespace and typographic differences are normalised only for matching; the stored quotation is copied from the original source.
- One bounded repair can select numbered source spans instead of generating quotation text. The backend validates their indices and copies the source range.
- Unrecoverable model/provider failures remain retryable technical errors and do not consume the user's allowance. No silent lexical fallback occurs.
- Added optional quotation and explanation fields to API evidence items and saved results. Older results remain readable.
- Updated the app to display quoted evidence and source-specific explanations, with an option to read the surrounding source context.
- Extended the mobile analysis timeout to 240 seconds, covering the three stage deadlines plus transport/storage. The existing analysis lease is 300 seconds.
- Preserved the lexical implementation for comparisons. Numerical risk indicators still use its heuristic aggregation rules; they are not calibrated probabilities.
- Enabled semantic mode in the ignored local `.env` and restarted the local backend on its existing `127.0.0.1:8000` address.

## Dataset and measured results

- [Dataset](../datasets/stance_seed_v1.json): 120 fictional claim/passage pairs across 40 scenarios, plus five recorded-source passages.
- [Human review spreadsheet](../datasets/stance_seed_v1_review.csv) and [labelling guide](../datasets/STANCE_LABELLING_GUIDE.md) are ready for the team.
- All labels are provisional and were authored by Codex; independent human review is pending.
- This measures interpretation of supplied passages. It does not measure end-to-end fact-checking accuracy, retrieval quality or real-world prevalence.
- Scenario groups are separated into development and holdout partitions. The dataset and prompt share an author, so this is not an independent benchmark.

Final comparison: [complete per-case report](stance_final_v2r2_2026-09-08.json).

| Partition | Examples | Lexical matches | Semantic matches | Semantic technical errors |
|---|---:|---:|---:|---:|
| Development | 72 | 24 | 70 | 0 |
| Reserved scenarios | 48 | 16 | 43 | 0 |
| Previously recorded passages | 5 | 4 | 5 | 0 |

- Reserved-scenario agreement improved from **16/48 to 43/48** against provisional labels. Do not present this as UIABO's real-world detection accuracy.
- False supporting decisions on the reserved scenarios fell from **15 to 1** in the final run.
- Final mean per-passage latency was **2.868 seconds**, with **4.991 seconds** at the 95th percentile. This is not complete-request latency; passages can run concurrently.
- The NASA moonlight passage that the lexical baseline misread was classified as contradicting in the final run.
- Results vary between runs, even with temperature zero. An earlier reserved-scenario run matched 44/48; the final run matched 43/48. Both reports are retained.
- Earlier runs exposed invalid shortened quotations. The sentence-selection repair resolved those observed failures in the final run, but finite testing does not guarantee future responses will validate.
- The reserved examples were first evaluated after development prompt changes. Subsequent repeats checked quotation-repair changes; their results are not fresh unseen evaluations. Future tuning should use a new untouched test set.

## Application verification

- **305 backend tests passed.** One existing Starlette/HTTPX deprecation warning remains.
- Tests cover malformed responses, invented quotations, invalid sentence indices, bounded repairs/deadlines, provider failures, API result/history persistence and allowance preservation on failure.
- **Android export passed** after the quotation display and timeout changes.
- [Final live API smoke test](text_pipeline_semantic_v2r2_2026-09-08.json):
  - Great Wall claim: HTTP 200, **High Concern**, five sources, 18.26 seconds.
  - Singapore independence date: HTTP 200, **Low Concern**, two sources, 15.35 seconds.
  - Opinion: HTTP 200, **Not Enough Information**, no retrieval, 4.30 seconds.
- Live smoke tests used real Ollama/Google/Tavily responses with authenticated test identities and in-memory storage. They did not write to live Firestore or run the Android emulator.
- The restarted local server returned HTTP 200 for its OpenAPI document with the new quotation fields.

## Local configuration

The project-root `.env` now contains these non-secret settings alongside the existing private keys:

```dotenv
EVIDENCE_ASSESSMENT_MODE=semantic
OLLAMA_ASSESSMENT_MODEL=gpt-oss:120b
```

- No additional API key is required.
- Other team members should add the same settings to their own local `.env` and restart their backend.
- `EVIDENCE_ASSESSMENT_MODE=lexical` restores the original baseline. Existing installations without a mode setting retain that baseline.
- New records identify the assessor as `sprint-1-semantic-v2r2:gpt-oss:120b` in `pipeline_version`.
- Existing saved results are not reassessed automatically. Submit a new check to see the updated assessment.

## Remaining accuracy work

1. **Review labels and gather real claims.** Two team members should independently annotate the spreadsheet, resolve ambiguities, and create a new version with real-world claim provenance.
2. **Improve handling of missing information.** The final errors involved uncertain quantities, unknown causes, unconfirmed schedules, ownership, registration and age eligibility. One unresolved eligibility case incorrectly received supporting.
3. **Evaluate retrieval separately.** Query formulation and word-overlap ranking are unchanged. Measure whether the right evidence is found before adding semantic reranking and better passage selection.
4. **Check multiple claims separately.** The current pipeline still extracts one principal claim. The assessor's compound-claim instructions do not provide full multi-claim coverage.
5. **Evaluate source independence and scoring.** Several pages may repeat one report. Calibrate scores only after obtaining suitable reviewed data; current scores remain heuristic.
6. **Implement and evaluate static-image/deepfake checks for final submission.** This milestone changes text assessment only; audio remains excluded.

## Retained development evidence

- [First development run](stance_development_2026-09-08.json): 67/72 matches, one false support and one validation error.
- [Revised development prompt](stance_development_v2_2026-09-08.json): 71/72 matches.
- [First reserved-scenario run](stance_holdout_v2_2026-09-08.json): 44/48 matches.
- [Quotation-repair run](stance_final_v2r1_2026-09-08.json): retained with its validation failure.
- [Sentence-selection regression run](stance_regression_v2r2_2026-09-08.json): 5/5 matches.
- No failed examples were deleted or relabelled to improve the reported results.
