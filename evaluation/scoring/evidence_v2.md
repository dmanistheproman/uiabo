# Evidence scoring v2

Historical scoring specification. New checks now use [evidence scoring v3](evidence_v3.md),
which adds explicitly provisional midpoints for unresolved factual claims.
Existing v2 saved results retain the behaviour documented below.

Implemented 16 September 2026. This replaces the fixed 15/25/75/82 scores for
new text checks. Link safety uses Google Web Risk and is
unaffected. Earlier saved results and Sprint 1 fixtures keep their old scores.

## What users see

- **Verdict:** Supported, Contradicted, Conflicting, Insufficient evidence, or
  Not supported by policy checked. Non-checkable content is identified separately.
- **Evidence strength:** Strong, Moderate, Limited or Insufficient. This describes
  the admissible evidence, not a probability of correctness. Strong sources can
  conflict; the verdict and explanation still show that disagreement.
- **Concern indicator:** An integer from 0 to 100, shown after the verdict.
  Lower indicates support; higher indicates contradiction. Zero means no concern
  identified in the evidence checked, not guaranteed truth. It is not a percentage.
- **Assessment limitations:** Existing missing-context and uncertainty explanations.

Missing evidence, an uncheckable input or unresolved decisive details receive no
score. They are never shown as zero-risk findings. Related policy alone does not
establish that an unannounced change is false.

## Calculation

1. Retain the existing semantic quotation, complete-claim, date and applicability
   checks. Partial support is neutral; an applicable contradiction of a material
   component can refute a compound claim. Retrieval marked as context-only or
   outside the claim's scope cannot vote.
2. Evidence quality varies continuously: `min(retrieval relevance, source cap)`.
   Source caps remain government .94, fact-check .92, academic .89, news .84,
   other .70. Source type alone never establishes a stance. Neutral evidence is
   capped at .45. Quality below .60 cannot establish a verdict.
3. Do not subtract quality solely because a publication is old. Old material can
   establish historical facts. Current/future applicability must pass the existing
   scope checks; publication age does not substitute for those checks.
4. Group shared source origins, hosts, publishers and identical normalised
   passages. Take one strongest contribution per group and stance. Keep both
   stances when the same origin contradicts itself. Hostnames without recorded
   origin metadata do not earn a corroboration bonus.
5. For each side, strength is its strongest quality plus a bounded corroboration
   bonus: `.04 * sum(other eligible group qualities)`, limited to `.06`.
   Both the strongest source and bonus sources need origin metadata. Cap total
   strength at 1. Empty sides have strength 0. This is an evidence index, not a
   statistical combination of independent probabilities.
6. Determine the verdict from admissible stances first: supporting only,
   contradicting only, both, or neither. Then calculate the concern indicator:

   `round(50 * (1 - supporting_strength + contradicting_strength))`

   Floating-point noise is removed before rounding to the nearest integer
   (ties to even). Neither side means `null`, not 50. Conflicting results remain
   Conflicting/Needs Caution even when their number falls outside the old bands.
7. Evidence strength uses the stronger side: >= .90 Strong; >= .75 Moderate;
   otherwise Limited. No decisive evidence means Insufficient.

## Illustrative controlled cases

| Evidence | Verdict | Indicator |
|---|---|---:|
| One applicable supporting source, quality .94 | Supported | 3 |
| Two distinct recorded supporting origins, each .94 | Supported | 1 |
| Three distinct recorded supporting origins, each .94 | Supported | 0 |
| Copies of the same supporting source | Supported | 3 |
| One supporting source, quality .80 | Supported | 10 |
| One applicable contradicting source, quality .94 | Contradicted | 97 |
| Equal support and contradiction | Conflicting | 50 |
| Support strength 1, contradiction strength .60 | Conflicting | 30 |
| Weak, neutral, missing or inapplicable evidence | Insufficient evidence | No score |

These constants are explicit prototype design choices. Tests establish internal
behaviour, not real-world accuracy or probability calibration. Distinct recorded
origins do not prove editorial independence; paraphrased syndicated material may
still evade duplicate detection. Claim coverage depends on semantic assessment
and validated comparisons, and can still be misinterpreted.

## Storage and evaluation

- New assessments include `scoring.version = evidence-v2`, evidence strength,
  supporting/contradicting strengths, group counts and explanations.
- Orchestration copies the summary into the API response and saved account result.
  History and idempotent replay retain it. Missing summaries identify legacy results.
- `test_scoring_v2.py` covers monotonicity, near-zero support, contradictions,
  conflicts, duplicate sources, source order, weak evidence and applicability.
- Existing semantic, policy, retrieval, orchestration and account tests remain
  regression checks. Archived fixtures retain their original numbers.
- Next evaluation work: label representative full claims and complete evidence
  sets, independently review coverage and verdicts, freeze a holdout, and measure
  errors by topic and score band before claiming numerical calibration.
