# Verification oracle regression pack

This pack supplies **12 fictional claims with deliberately constructed evidence**. It tests whether the new planner and verifier can use known evidence correctly. It is not a held-out real-world accuracy study, and a high pass rate does not show that live retrieval can find the right sources.

The expected outcomes and their reasons are in [oracle_cases.json](oracle_cases.json). Review those reasons before changing an expected answer. The expected answers are never sent to the model.

| Case | What it checks |
| --- | --- |
| O01 | Join two dated ownership links without requiring either document to prove the whole chain. |
| O02 | Distinguish ownership from daily management. |
| O03 | Keep rates separate from counts. |
| O04 | Use measurement dates rather than a report's publication date. |
| O05 | Preserve negation. |
| O06 | Distinguish what someone said from whether the underlying statement is true. |
| O07 | Keep an alleged private discussion unresolved when only current policy is known. |
| O08 | Recognise an explicit new announcement despite an older rule. |
| O09 | Use a material contradiction while leaving an alleged cause unresolved. |
| O10 | Ignore instructions embedded in a source page. |
| O11 | Distinguish individual savings from a collective fund's solvency. |
| O12 | Avoid treating an absent announcement as proof of falsity. |

## Run

Run these commands from the repository root. Use the project's existing backend virtual environment and configuration; no additional API is required.

Validate all fixtures offline. This makes **zero model/network calls**:

```powershell
.\backend\.venv\Scripts\python.exe -B evaluation\verification\run_oracle.py
```

Explicitly allow live calls to the real planning and verification functions, using the existing Ollama key and quota:

```powershell
.\backend\.venv\Scripts\python.exe -B evaluation\verification\run_oracle.py --live --case O01 --case O05
```

Run all 12 with live models:

```powershell
.\backend\.venv\Scripts\python.exe -B evaluation\verification\run_oracle.py --live
```

The script supplies the fictional passages directly. It does not search the web, write to Firestore, use an app account, or consume an app allowance. It calls the actual new planner and generic verifier; it does not call the classifier, specialist weather/ownership routes, or the orchestration repair loop. Results therefore isolate this part of the system. There can be up to one planning request and two verifier requests per case when a verifier response needs correction.

Reports are written to `evaluation/verification/reports/` by default. `--output <path>` chooses another JSON path. They contain the plan, fallback reason, per-assertion findings, exact citations, expected/observed categories, timing and summary counts. Provider errors are separate from factual abstentions. No credentials or raw provider error bodies are written.

## Read the results

- **Answerable abstentions:** expected supported/contradicted cases that still return unresolved. This is the main avoidable-abstention diagnostic.
- **Unsupported misinformation verdicts:** cases marked contradicted when the approved evidence does not warrant that verdict. Reducing abstention must not increase this count.
- **Correct unresolved:** evidence-limited cases for which the model preserves uncertainty.
- **Provider or contract errors:** technical failures, not evidence that a claim is unknown or false.
- **Planner fallbacks:** whole-input plans used after unavailable/invalid semantic planning. Inspect them separately.

Inspect the per-assertion findings as well as the headline. For O09, a contradicted event plus an unresolved cause is appropriate; a claim that the sources disproved the existence of illegal pipes is not. Exact quotations prevent invented citations but cannot prove that the model understood them correctly. The explanation still needs human review.

The reported `contradicted` category groups backend `contradicted`, `likely_misinformation` and `highly_unlikely` outcomes for this regression exercise; the original backend outcome remains in each row. It is not a replacement for the app's agreed label definitions. Scores are not evaluated as probabilities.

## Compare with live retrieval later

Maintain a **separate real claim review set**, labelled by the team and frozen before implementation changes. Include supported claims, material contradictions, genuine uncertainties, ambiguous input and source failures. Split by claim family, not merely spelling or paraphrase, so a tuned claim's near-duplicate cannot be presented as unseen testing.

For each real claim, run the same frozen version twice: once with reviewers' verified source passages supplied, and once end to end through live retrieval. If the oracle version succeeds but retrieval fails, investigate acquisition/coverage. If both fail despite applicable evidence, investigate interpretation or aggregation. Record sources, dates, versions and costs; the historical development runs and these fictional cases do not establish real-world accuracy.

## Policy-change regression cases

[policy_cases.json](policy_cases.json) adds seven paired fictional examples. They distinguish an asserted adopted change from a discussion, an explicitly later change, a different population, an archived rule and a genuine new announcement. A contradicted policy event can undermine a message while its alleged financial cause stays unresolved. A correct policy event does not establish an unsupported cause.

Validate the pack offline, or add `--live` to exercise the existing model services:

```powershell
.\backend\.venv\Scripts\python.exe -B evaluation\verification\run_oracle.py --pack evaluation\verification\policy_cases.json
```

The verifier compares policy substance and effective dates as of the submission date. Missing confirmation alone is not a contradiction. Explicit historical legislation URLs are marked as dated versions; an ordinary old publication date does not automatically make a source obsolete.

The model selects numbered source passages; the backend reconstructs exact quotations from the original text. It also reconstructs any selected causal clause from the submitted claim. Invalid references, unmatched scope and invented quotations still fail validation. Within the existing two-request assessment limit, valid findings are retained and only invalid findings are requested again. An explicitly later policy period must be covered by the cited evidence; a nearer-term schedule alone cannot settle it.

The verifier uses the existing Ollama model at medium reasoning effort. The assessment stage retains its 55-second deadline and the shared request budget. No new API key or database migration is required. Saved results are unchanged; submit a new check to use the updated verifier.

Recorded policy follow-up on 3 November 2026: [seven policy cases](reports/2026-11-03-policy-verification.json) matched all expected outcomes, with no provider/contract errors. The [twelve broader cases](reports/2026-11-03-indexed-verification.json) also matched their expected outcomes with indexed citations. These remain small fictional regression packs, not estimates of real-world accuracy. The final automated run passed 1,794 tests, with three skipped.

## Recorded regression run: 3 November 2026

The [saved live-model regression report](reports/2026-11-03-verification-v1.json) matched all 12 expected outcomes: seven answerable cases received a supported or contradicted finding, and five evidence-limited cases remained unresolved. No provider/contract errors or planner fallbacks occurred in this run. These fictional evidence cases test reasoning; they do not measure real-world retrieval accuracy.
