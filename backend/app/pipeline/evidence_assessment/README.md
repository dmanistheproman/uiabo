# Evidence assessment — Poon

This folder is owned primarily by **Poon Chun Ping**.

Build the component that:

- Receives `ClaimAnalysis` and `RetrievalResult`.
- Marks evidence as supporting, contradicting, or neutral.
- Ranks evidence by relevance, authority, and recency.
- Calculates risk and uncertainty using documented rules.
- Generates an evidence-grounded explanation and next action.
- Returns the agreed `AssessmentResult` object.

Suggested future modules:

```text
service.py     # Coordinates assessment
stance.py      # Evidence stance
scoring.py     # Risk, label, and uncertainty rules
explanation.py # Plain-language grounded explanation
```

Scoring specifications and evaluation reports belong in `evaluation/scoring` and `evaluation/reports`.

