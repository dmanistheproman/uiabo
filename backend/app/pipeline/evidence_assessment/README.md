# Evidence assessment — Poon

This folder is owned primarily by **Poon Chun Ping**.

The Sprint 1 component is implemented in `service.py`. It:

- Receives `ClaimAnalysis` and `RetrievalResult`.
- Marks evidence as supporting, contradicting or neutral.
- Ranks evidence using relevance, authority and recency.
- Calculates risk and uncertainty using documented rules.
- Generates an evidence-grounded explanation and next action.
- Returns the agreed `AssessmentResult` through:

```python
assess_evidence(claim: ClaimAnalysis, retrieval: RetrievalResult) -> AssessmentResult
```

The implementation is an explainable rule-based baseline. It handles clear
negation, amount, date and weekday agreement or contradiction. Complex
paraphrases, sarcasm and multi-step reasoning remain later evaluation work.

The service can be separated into these modules later if it grows:

```text
service.py     # Coordinates assessment
stance.py      # Evidence stance
scoring.py     # Risk, label, and uncertainty rules
explanation.py # Plain-language grounded explanation
```

Scoring specifications and evaluation reports belong in `evaluation/scoring`
and `evaluation/reports`.
