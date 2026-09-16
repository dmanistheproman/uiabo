# Evidence scoring v3

Implemented 16 September 2026. New completed factual text checks receive a score even when the evidence cannot settle the claim.
The score describes the evidence checked; it is not a probability of falsehood.

## What the result means

| Finding | Score | Status |
| --- | --- | --- |
| Applicable evidence supports the claim | Existing continuous calculation | `evidence_based` |
| Applicable evidence contradicts the claim | Existing continuous calculation | `evidence_based` |
| Applicable evidence exists on both sides | Existing continuous calculation, possibly 50 | `evidence_based` |
| Successful search finds no decisive evidence | 50 | `provisional` |
| Related policy does not establish an alleged change | 50 | `provisional` |
| Opinion or no checkable factual claim | None | `not_applicable` |
| Technical failure | No completed assessment or score | Not applicable |

The app shows **50/100 — Unverified, provisional score** for unresolved factual
checks. Its explanation says that 50 is a neutral starting point because the
claim could not be confirmed or disproved, not a 50% chance of being false.
This midpoint is a deliberate product convention, not a measured risk estimate.
A conflict with a score of 50 is labelled as conflicting evidence instead.

## Calculation and safeguards

- Decisive scoring retains the [v2 calculation](evidence_v2.md), source grouping,
  quality limits and quotation, relevance, date and scope checks.
- No admissible supporting or contradicting evidence gives a provisional 50,
  zero supporting/contradicting strengths, zero contributing origins and
  `Insufficient` evidence strength. The verdict remains `insufficient_evidence`
  or `unsupported`; the number never upgrades it to a contradiction.
- New summaries record `version: evidence-v3` and an explicit `status`.
  Both assessment and final API models validate score/status consistency.
- A future claim remains assessed for its claimed date. A different current rule
  can provide useful context but does not alone disprove an alleged future change.
  An applicable quoted denial or rule for the relevant period can still contradict it.
- Missing announcements and provider failures are different cases. Technical
  failures remain errors and do not use a completed-check allowance.

## Saved results and the app

- The backend saves the score and its status together in the account result.
  History, detail retrieval and retries retain that stored assessment.
- Earlier records, including unscored v2 results, are not recalculated or assigned
  a number by the app. Submit a new check to get v3 scoring.
- The main result card, history label and shared result distinguish provisional
  scores from evidence-based scores. The conclusion and recommended action remain
  separate from the number.
- Link safety remains a separate Google Web Risk check and has no misinformation
  score. This change does not add image-authenticity or deepfake scores.

## Evaluation

Tests cover empty successful searches, neutral/weak/out-of-scope evidence,
unverified future policy, strong support and contradiction, conflicting evidence,
opinion/error paths, model validation, old records and account persistence/retries.
These establish implementation behaviour, not real-world accuracy. A labelled
holdout dataset is still needed to evaluate how useful the score is to users.
