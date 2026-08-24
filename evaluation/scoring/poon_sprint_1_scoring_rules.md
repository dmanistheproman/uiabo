# Poon — Sprint 1 evidence-assessment scoring rules

## Purpose

This document records the first rule-based baseline used by Poon Chun Ping's
Sprint 1 evidence-assessment component.  The rules are intentionally simple
and explainable so the complete text misinformation pipeline can be tested
before the team evaluates more advanced methods.

The shared fixture evidence and expected scores are synthetic.  These rules
must not be presented as proof that a claim is true or false.

## Input and output

The component receives:

- `ClaimAnalysis`
- `RetrievalResult`

It returns the agreed `AssessmentResult` fields:

- `concern_label`
- `misinformation_risk_score`
- `uncertainty`
- `uncertainty_reasons`
- `explanation`
- `recommended_action`
- `assessed_evidence`

No shared field names are changed.

## 1. Evidence stance

Each evidence passage is classified as:

- `supporting` — the passage directly agrees with the important details in
  the claim.
- `contradicting` — the passage directly disagrees with an important detail,
  such as a different amount, date/day, or opposite positive/negative
  statement.
- `neutral` — the passage is related but does not answer the decisive part of
  the claim.

Sprint 1 uses direct text rules for obvious cases.  More complex semantic
contradictions are a known limitation.

## 2. Evidence quality

Quality is a value from `0.0` to `1.0`.  It is not the probability that the
claim is true.

The baseline considers:

1. Chu's `retrieval_score` as the relevance signal.
2. `source_type` as a coarse authority signal.
3. `published_at` as a recency signal.

Initial authority caps are:

| Source type | Maximum baseline quality |
| --- | ---: |
| Government | 0.94 |
| Fact check | 0.92 |
| Academic | 0.89 |
| News | 0.84 |
| Other | 0.70 |

For the current government fixture bands:

- retrieval score `>= 0.95` -> quality `0.94`
- retrieval score `>= 0.90` -> quality `0.90`
- retrieval score `>= 0.80` -> quality `0.82`

Neutral evidence is capped at `0.45` because it does not directly answer the
claim.  Evidence older than 180, 365 or 730 days receives a small recency
penalty so otherwise similar current evidence ranks higher.

## 3. Misinformation-risk score

The final risk score is from `0` to `100`.

For the Sprint 1 baseline:

| Evidence situation | Risk score |
| --- | ---: |
| Strong supporting evidence (`quality >= 0.90`) | 15 |
| Other direct supporting evidence | 25 |
| Mixed supporting and contradicting evidence | Weighted around 50 |
| Other direct contradicting evidence | 75 |
| Strong contradicting evidence (`quality >= 0.90`) | 82 |
| No useful direct evidence | `null` |

Mixed evidence is kept in the `Needs Caution` range for Sprint 1.  The exact
score is based on the relative total quality of supporting and contradicting
evidence.

## 4. Concern label

| Risk score | Concern label |
| --- | --- |
| 0–30 | Low Concern |
| 31–70 | Needs Caution |
| 71–100 | High Concern |
| `null` | Not Enough Information |

`Not Enough Information` must use a `null` risk score.  A value such as 50
would incorrectly imply that the system had enough evidence to assess the
claim.

## 5. Uncertainty

- **Low** — multiple good-quality sources give consistent direct evidence.
- **Medium** — only one strong authoritative source is available, or multiple
  sources are usable but limited.
- **High** — there is no useful direct evidence, evidence is neutral, or
  supporting and contradicting sources conflict.

## 6. Explanation and recommended action

Explanations use only the result of the retrieved evidence.  They must not add
facts that do not appear in the input or evidence.

Examples:

- Supporting: "The available evidence supports the submitted claim."
- Contradicting: "The available evidence contradicts the submitted claim."
- Neutral/no evidence: "There is not enough reliable evidence to assess this
  claim."

Recommended actions are deliberately cautious and tell the user to review the
cited or authoritative source before forwarding uncertain or high-concern
claims.

## Limitations

The Sprint 1 stance rules work best for direct statements with clear amounts,
dates, weekdays and negation.  They may fail on paraphrases, indirect
contradictions, sarcasm, complex multi-claim statements or evidence that
requires deeper reasoning.  These limitations will be measured during later
evaluation before changing the baseline rules.
