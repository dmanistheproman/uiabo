# Evidence labels and hypothetical questions

Implemented on `feature/evidence-label-consistency`, based on the Google Vision branch.
Enable the existing JEV pipeline with `EVIDENCE_PIPELINE_V3=1`. No new API keys are needed.

## What changes

| Input | Behaviour |
|---|---|
| What if Singapore reached 50°C? | Not checkable: an imagined scenario. |
| If CPF did not exist, how would people save? | Not checkable: a conditional imagined scenario. |
| Imagine Changi closed. How would travellers be affected? | Not checkable: an imagined scenario and consequence question. |
| Could / will Singapore reach 50°C tomorrow? | A factual question. Compare the proposed event with official weather evidence. |
| Singapore will reach 50°C this Saturday. | Likely misinformation when the official forecast or historical-extremes checks establish a strong mismatch. |
| The airport will close next Friday. | Interpret an otherwise unnamed airport as Changi. State that assumption and check official notices. |
| ICA will begin rejecting passports with less than one year of validity. | State the foreign-visitor entry interpretation and check the current rule and announcements. |
| Singapore will win the World Cup in 2038. | No automatic likelihood verdict from missing news. |

Mixed messages still go through claim extraction. A factual question is not labelled hypothetical just because it contains a question mark or the word “if”. An explicit different airport is never replaced by Changi.

## What “likely misinformation” means

Relevant evidence weighs against the claim, without establishing a conclusive contradiction of every possible interpretation. The explanation identifies the evidence and remaining limits.

- Weather: reuse the official forecast comparison and MSS historical-extremes reader. The climate rule requires a single ambient-air temperature, Singapore, dates within 14 days, a recently retrieved official record, and a gap of at least 10°C above that record. It does not hard-code a 24–35°C November range or treat an average as an upper bound.
- Public changes: two successful official-domain searches, at least two readable official pages, no retrieval warnings, a quoted current baseline, matching subject/population and a structured explanation are required. Any returned support for the alleged change blocks this inference. Search failure and empty evidence never count as proof of falsity.
- The first public-change profiles cover an imminent airport-wide Changi closure and the one-year ICA entry rule. Other policies, private discussions, compound allegations and distant outcomes keep their existing assessment paths. Extend profiles with scope and negative tests, not a generic “no news means false” rule.
- The optional public-change reasoning call uses the existing Ollama cloud key with a 25-second timeout. Failure leaves the result unresolved. Discovery stays within the existing search/page budgets.

## Scores and saved results

The main result and history use the same likelihood label. Public-change inferences have `assessment_outcome=likely_misinformation`, `scoring.status=inference_based`, and a null score. Their `inference_context` preserves the baseline quotation, searches, assessment time and limits through API/history/idempotent replay.

Climate findings retain the existing `highly_unlikely` internal outcome and legacy risk field for compatibility. Their public credibility score remains unrated; the visible label is now “Likely misinformation”. A missing score is never replaced with 50. Old database entries are not rewritten. Recheck a claim to run the new retrieval and reasoning.

## Evaluation

The comparison tool reports label policy `evidence-labels-v2` and accepts `likely_misinformation`. Climate outliers, forecast-based conflicts and public-change inferences map to this category, separately from `contradicted`. Directional coverage includes likelihood findings so wrong likelihood labels are not hidden.

Do not directly compare these metrics with the old label policy. Keep independent reviewer answers and team adjudication separate. The team workbook is a proposed revision, not a substitute for the missing second review. Its F49/R03 dated verification and R05 text mismatch still need resolving before use as benchmark ground truth. Held-out cases used to design these changes should be disclosed and replaced for an unbiased final accuracy estimate.

## Try it locally

Restart the backend and reload Expo from this worktree. Use the existing port configuration; do not start another backend on an occupied port.

```powershell
cd C:\Dev\uiabo-vision\backend
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --env-file ..\.env --host 0.0.0.0 --port 8002

cd C:\Dev\uiabo-vision\mobile
npx.cmd expo start --port 8082 --android
```

Test the examples above, plus controls: 32°C tomorrow, heat index 50°C, a negated claim, Heathrow closure, a pure hypothetical and a failed search. Outcomes depend on the actual retrieved evidence, not the example text matching a target label.

## Verification on 1 November 2026

Live checks used the configured providers and an in-memory result store, without
writing to Firestore or charging an app user's allowance.

| Live input | Observed result |
|---|---|
| Could Singapore reach 50 degrees Celsius tomorrow? | Likely misinformation, based on the retrieved MSS historical maximum. |
| Singapore will reach 50 degrees Celsius next Saturday. | Likely misinformation, based on the retrieved MSS historical maximum. |
| What would happen if all MRT rides were free? | Not a factual claim. |
| The airport will close next Friday. Everyone needs to change their flights. | Likely misinformation after reading the official operating baseline and completing the notice searches. The Changi assumption is retained. |
| ICA will begin rejecting passports with less than one year of validity. | Likely misinformation after reading the current foreign-visitor entry rule and checking announcements. |

Earlier airport runs stayed unresolved when a page or semantic extraction failed.
That fallback is intentional: successful retrieval is required for the inference.
Source availability and model selection can still vary between runs. These are
development checks, not a measured accuracy rate or a promise of identical outputs.

Automated verification covers label display, hypothetical versus factual inputs,
scope exclusions, failed discovery, literal quotations, API/history/replay, and
forecast passages that must not become conclusive refutations. Android export
also completed. Live Gemini deepfake tests are outside this change's checks.
