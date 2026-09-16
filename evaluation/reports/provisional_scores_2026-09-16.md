# Provisional scores and passport retrieval verification

## Behaviour implemented

- New completed factual checks always receive a numeric score. Unresolved claims
  receive **50/100 — Unverified, provisional score**, not a truth verdict.
- Applicable support, contradiction and conflicting evidence retain their
  continuous scoring calculation. Zero remains a valid supported result.
- Opinions/non-checkable content and technical failures remain unscored.
- API models validate the v3 score, status, evidence strengths and outcome together.
- Stored v2 results and idempotent retries keep their previous assessment.
- The app explains the provisional midpoint beside the score, labels it in
  history, and includes the explanation when the user shares the result.
- Passport retrieval searches for the alleged announcement and the current entry
  requirements separately, with existing provider budgets and scope checks.

## Automated checks

- **640 backend tests passed**, with environment-file loading disabled. Coverage
  includes scoring, schema rejection, future-policy applicability, errors,
  retrieval, account persistence, history and replay.
- **19 mobile presentation tests passed**. They distinguish provisional 50 from
  a conflict that also scores 50, and retain legacy, opinion and failure behaviour.
- Android Metro export passed with `--no-bytecode`; this checks JavaScript
  bundling, not a signed release build or device interaction.

## Live API checks

Real Google/Tavily/Ollama providers were called through the application's API
routes with an in-memory account store. No live Firestore documents or actual
user allowances were changed. Saved-result retrieval, history, idempotent replay
and exactly one simulated allowance charge passed for both checks.

| Submitted claim | Outcome | Score | Time |
| --- | --- | --- | --- |
| ICA will begin rejecting passports with less than one year of validity from November | Unsupported; November 2026 assumed | 50, provisional | 35.07 s |
| Foreign visitors entering Singapore must have at least one year of passport validity. | Contradicted by applicable evidence | 97, evidence-based | 40.76 s |

The current-rule check retrieved the [ICA entry requirements](https://www.ica.gov.sg/enter-transit-depart/entering-singapore),
including the six-month requirement and Singapore-passport exception. It did not
use travel-abroad advice as a substitute for entry requirements.

The initial future-claim run discovered and extracted that entry page but the
semantic selector discarded it; it retained older travel guidance instead.
That prompted an additional passage-selection refinement. The result remained
provisional rather than converting unrelated guidance into a false verdict.

After that refinement, a complete rerun of the original future claim returned
HTTP 200 in **49.01 seconds**, with **50/provisional/unsupported** and the official
entry page retained as `context / uncertain_time`. Its literal selected passage
included the six-month rule and Singapore-passport exception. Saving, history,
replay and single-charge checks passed again. Final versions are
`semantic-v6`, `evidence-v3`, `retrieval-web-v9` and `relevance-v8`.

The generated policy summary still selected older outbound guidance (with its
scope warning); the correct entry passage is available in the returned sources.
Retaining a useful source does not guarantee that the model will prioritise it
in every summary. This remains an evaluation limitation.

## Local runtime

The app bundle includes the presentation changes. Restarting the existing local
backend was blocked by automatic approval review, so its running process was not
replaced. Restart it and submit a new check to use evidence-v3; old saved results
retain their original scores.

These are operational checks of two claims, not an accuracy benchmark or
calibration of the numeric scores. Provider results and semantic classifications
can vary between runs. The provisional midpoint is an explicit product convention.
