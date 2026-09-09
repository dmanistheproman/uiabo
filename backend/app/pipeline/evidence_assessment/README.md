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

## Semantic prototype assessment

`semantic.py` adds an Ollama Cloud assessor using the existing backend key.
It reads each claim/passage pair and returns a stance, explanation and literal
source quotation. Up to three passages run concurrently, with at most six
passages per check. Requests have a 45-second limit and the stage has a
65-second limit. One JSON/quotation repair is allowed within the same request
deadline; the repair selects numbered source spans and the backend copies the
original text. Provider errors are not retried automatically.

- Set `EVIDENCE_ASSESSMENT_MODE=semantic` and `OLLAMA_ASSESSMENT_MODEL=gpt-oss:120b`
  in the ignored project-root `.env`, then restart the backend.
- Set the mode to `lexical` to reproduce the original baseline. Missing mode
  defaults to lexical for existing installations; unknown modes fail explicitly.
- The default orchestrator selects the configured assessor and records the
  prompt version/model in `pipeline_version`.
- User text and source passages are untrusted data, separated from instructions.
  This reduces instruction-following failures but is not a proof of immunity.
- Missing/invalid quotes fail validation. Only whitespace and typographic
  apostrophe/quote/hyphen variations are tolerated, and the original source span
  is restored before storage. Ellipses, joined fragments and invented text fail.
- Any unassessable passage causes a retryable technical error for the check.
  There is no silent fallback to lexical rules, and failed checks do not consume
  allowance. Valid neutral evidence still yields Not Enough Information.
- `evidence_quote` and `assessment_reason` are optional additions to final
  evidence items, preserving compatibility with old stored results. The app
  displays them and lets users expand the surrounding source context.
- Risk scores still use the original heuristic rules. Semantic results do not
  receive Low uncertainty solely because several passages agree; independence
  and accuracy are unverified. No probabilities have been calibrated.

Use the [dataset and labelling guide](../../../../evaluation/datasets/STANCE_LABELLING_GUIDE.md)
and `python -m scripts.evaluate_stance` from `backend` to compare assessors.
Recorded reports distinguish controlled stance tests from end-to-end accuracy.

The service can be separated into these modules later if it grows:

```text
service.py     # Coordinates assessment
stance.py      # Evidence stance
scoring.py     # Risk, label, and uncertainty rules
explanation.py # Plain-language grounded explanation
```

Scoring specifications and evaluation reports belong in `evaluation/scoring`
and `evaluation/reports`.
