# Evidence assessment — Poon

This folder is owned primarily by **Poon Chun Ping**.

The Sprint 1 component is implemented in `service.py`. It:

- Receives `ClaimAnalysis` and `RetrievalResult`.
- Marks evidence as supporting, contradicting or neutral.
- Ranks evidence using relevance and source quality, with date/scope applicability gates.
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
- For ordinary semantic checks, any unassessable passage causes a retryable technical error.
  There is no silent fallback to lexical rules, and failed checks do not consume
  allowance. Valid neutral evidence still yields Not Enough Information.
  A check with independently validated official forecast data is an exception:
  its deterministic forecast comparison survives an unavailable additional web
  assessment, with an explicit incomplete-coverage warning and neutral failed
  sources. Successfully assessed web sources still contribute their validated
  stances. A completed partial check uses allowance; a failed check does not.
- `evidence_quote` and `assessment_reason` are optional additions to final
  evidence items, preserving compatibility with old stored results. The app
  displays them and lets users expand the surrounding source context.
- New checks use [evidence scoring v3](../../../../evaluation/scoring/evidence_v3.md):
  verdict first, continuous concern indicator and a separate evidence-strength
  summary. Strong support can score near zero. Unresolved factual checks receive
  a provisional 50, explicitly labelled Unverified; opinions remain unscored.
  Semantic results do not receive Low uncertainty solely because passages agree;
  assessment accuracy is unverified. No probabilities have been calibrated.

Use the [dataset and labelling guide](../../../../evaluation/datasets/STANCE_LABELLING_GUIDE.md)
and `python -m scripts.evaluate_stance` from `backend` to compare assessors.
Recorded reports distinguish controlled stance tests from end-to-end accuracy.

The shared continuous scoring implementation is in `scoring.py`. Other possible
future module boundaries:

```text
service.py     # Coordinates assessment
stance.py      # Evidence stance
scoring.py     # Implemented: origin grouping, evidence strengths and indicator
explanation.py # Plain-language grounded explanation
```

Scoring specifications and evaluation reports belong in `evaluation/scoring`
and `evaluation/reports`.

## Future policy claims

Semantic v6 separates quoted published-policy findings from verification of an
alleged change, including passport/immigration claims. `policy_context` records
whether the findings are comparable policy or related guidance, the change's
verification status, a separate explanation and cited evidence IDs. A numeric
threshold difference is not automatically a scope mismatch; traveller category,
entry/departure, jurisdiction and effective period still matter.

A quoted explicit official denial can bypass the literal future-month/year
requirement only when retrieval marks it direct/applicable, semantic assessment
marks it as denying the same change, and the quote contains a denial. Known
publications from earlier years cannot use this exception. Ordinary existing
rules, no announcement, no comment and unestablished scope cannot establish a
contradiction. Unresolved factual checks receive a provisional 50 under v3.
Quotation and schema checks establish provenance, not correctness of the model's
interpretation. The denial signal is a conservative textual guard, not a general
negation classifier. Undated or misclassified sources remain an evaluation risk.

Comparison explanations and scope limitations are stored separately. Existing
saved records remain readable; new results save the policy context through the
API and account history. Tests: `test_future_policy.py` and date-context tests.

## Weather forecast comparisons

Semantic v7 compares official structured forecast data in `forecast.py` without
asking a model to reinterpret the API numbers. The comparison checks location,
date coverage, air-temperature measurement, explicit units, freshness and exact
agreement with the displayed API-derived passage. Celsius and Fahrenheit can be
converted; ambiguous bounds, approximate figures and every-day requirements
remain unresolved rather than being treated as an exact point.

`forecast_context` explains whether the claimed temperature fits the issued
forecast separately from the whole-message verdict. A lower forecast does not
prove a possible future temperature impossible. A specific claim about what the
identified official forecaster published can be contradicted by that forecast;
a pure matching reported maximum can be supported. Temperature agreement alone
does not establish a heatwave, record or cause.

When additional web sources were retrieved, only those passages go through the
bounded semantic stage. Valid same-claim refutations can affect the whole result;
the structured forecast comparison remains unchanged. A bare future prediction
requires literal refutation language before a web contradiction can decide it,
as well as the usual semantic relevance, applicability and quotation checks.
Historical records and different forecast ranges alone do not establish future
impossibility. This textual guard is not a complete semantic negation check.

If a web call fails, times out or lacks valid quoting, the result discloses that
coverage gap and retains any completed judgments and the official forecast.
Without a structured forecast, the existing semantic failure policy still
applies. Tests are in `test_forecast.py`.
