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
- New checks use evidence-v4 metadata and the public credibility-v2 contract
  documented below: verdict first, a continuous higher-is-more-supported
  credibility indicator and a separate evidence-strength summary. Unresolved
  factual checks and opinions remain unscored. The earlier
  [evidence-v3 specification](../../../../evaluation/scoring/evidence_v3.md)
  describes legacy risk values, including the retired provisional midpoint.
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
contradiction. Unresolved factual checks receive a null score under evidence-v4. Legacy v3 midpoints remain readable but are not displayed.
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


## Comparative claims (5 October update)

The pool judge uses the actual claim's interpretation. Corporate-management
guidance is supplied only for corporate-relationship claims, rather than in
every question sent to Jev. Both judges receive ranking guidance when appropriate:
an explicit same-scope comparison can suffice, while a large salary alone,
"one of the highest", an unresolved old ranking, or a proposed future salary
does not establish a current absolute ranking.

For an unqualified national-leader pay claim, the declared interpretation is
published political-office pay among heads of government. Explicit regions,
periods and populations still take precedence. The result explains this scope,
including limits around private income, undisclosed pay, allowances and bonuses.
The explanation and interpretation survive saved-result/history responses.

Diagnostics on 5 October 2026: the exact submitted claim "Singapore prime minister
is the highest paid politician" returned Supported, with stored risk 8/100,
after a complete live retrieval and assessment. A cached-evidence control changing
highest to lowest returned Contradicted, with stored risk 94/100. These are rule-based
indicators, not measured truth probabilities, and individual diagnostics do not
establish overall accuracy. Recheck existing submissions after restarting the
backend; their previous saved verdicts are not rewritten.

## Material parts of causal claims (8 October 2026)

The v3 pool assessor now separates eligible causal statements into an event, a
material factual premise and their claimed causal connection. For example,
retirement discussions, alleged reserve depletion and the explanation connecting
them receive separate findings. This is implemented in `components.py`, with
the exact-span decomposition and persisted contracts in `../shared/components.py`
and `../shared/component_assessment.py`.

- Decomposition is conservative and deterministic: one explicit causal connector,
  three original text spans, no invented factual assertions. Ambiguous hypotheses,
  negation, quoted/reporting scope and chained causes keep the whole-claim path.
  Weather claims retain the specialised forecast/plausibility assessment.
- A present-tense allegation that officials **are discussing** a change concerns
  current discussion. A missing implementation date is not itself a reason to
  reject evidence of that discussion. An explicitly stated period takes priority.
  This interpretation does not establish that a discussion occurred.
- One bounded batch judges every component/source pair. Jev is tried first and
  GPT-OSS is the fallback. A Jev finding based on inference also goes to GPT-OSS
  so an actual written argument can be retained. Exhausted provider/validation
  failures remain retryable technical errors, not completed missing-evidence results.
- Findings preserve their component, scope, reasoning basis, source IDs and exact
  quoted passages. Inferences have a bounded evidence quality of at most 0.70;
  this is an admission/weighting policy, not a calibrated probability.
- A context-only whole-claim passage can address a material premise, but only
  through explicit per-part scope and evidence checks. Its original retrieval
  provenance is retained; it is not promoted to whole-claim direct evidence.

An admitted contradiction of an essential part can produce **Likely
misinformation** even when another part remains unresolved. Support for a
different part does not cancel that contradiction. **Mixed evidence** requires
opposing evidence about the same part; support and contradiction concerning
different parts are not an artificial 50/50 split. Support for the whole message
requires all three essential parts, including the causal connection, to be
supported. The weakest essential part limits its overall supporting strength.

Missing coverage still cannot prove falsity. General statements about guarantees
or fully funded accounts do not by themselves contradict reserve depletion
relative to an expected baseline. The relevant financial measure, period and
comparison must be addressed. A published retirement target likewise does not
alone disprove alleged discussions of another target. This implementation does
not preassign a false verdict to the retirement-age/CPF example.

## Credibility score contract (6 October 2026)

The original contract was introduced on 6 October. New results use
`credibility-v2` from 8 October; the `credibility-v1` reader is retained for saved
records, including its original labels and explanations.

**Meaning:** how strongly relevant evidence supports or contradicts the accuracy
of the claim, for the time and context assessed. Higher means more support;
lower means stronger contradiction. It is an evidence index, not a percentage
probability of truth, model confidence, evidence quantity, or the likelihood of
future weather. Even the endpoints do not guarantee truth or falsity.

### Decide whether to rate before calculating a number

- Only decisive evidence admitted by the relevance, scope, date and
  minimum-quality checks counts. Whole-claim checks still apply to ordinary
  claims; eligible causal claims use the explicit material-part rules above.
  Related background without a supported per-part finding remains neutral.
- No admitted evidence: **Not enough evidence**, with a null credibility score.
  Silence is not a contradiction. The retirement-age/CPF and BTO-priority
  records inspected on 5 October were unrated; saved outcomes are not rewritten.
- Both credible support and contradiction: **Mixed evidence**. Near 50 means
  approximately balanced evidence strengths, never a lack of evidence.
- Partial support for a compound claim cannot verify its unresolved assertions.
  The causal path now records separate material-part findings. Other complex
  claim structures retain the existing whole-claim gates. No retrieval provider
  is added by this change.
- Non-factual inputs, failures and malicious-link checks do not get this score.
- Climate-only plausibility warnings retain their specific headline and cited
  explanation, without converting the old fixed risk 85 into credibility 15.
  Direct forecast comparisons can be rated but must retain the forecast basis.

### Five rated labels, selected from evidence before the number

| Evidence finding | Label |
| --- | --- |
| Support only, strength at least 0.90 | Strong evidence this is true |
| Support only, strength below 0.90 | Evidence suggests this is true |
| Admitted evidence on both sides | Mixed evidence |
| Contradiction only, strength below 0.90 | Likely misinformation |
| Contradiction only, strength at least 0.90 | Strong evidence this is false |

The minimum admitted quality remains 0.60. The 0.90 strong-evidence boundary is
an explicit prototype policy choice, not a validated confidence threshold.
Labels are not five equal score buckets: a conflict can be 70 and still be mixed.
An accepted material-part contradiction uses **Likely misinformation** even when
the cited contradiction is strong, because other assertions may remain unresolved.
The explanation identifies the contradicted part instead of claiming every part
was disproved. Saved `credibility-v1` ratings retain **Evidence suggests this is
false** for their weaker contradiction label.

For admitted supporting strength `S` and contradicting strength `C`:

`credibility = round(50 * (1 + S - C))`

Each side uses its strongest independent source group plus the existing bounded
corroboration bonus. Repeated publishers, hosts and copied passages do not add
votes. Python rounding is applied after eight-decimal normalisation; the mobile
legacy adapter uses the same tie-to-even rounding. A lone quality-0.70 support
is 85, a lone quality-0.94 contradiction is 3, and equal 0.94 strengths are 50.
This preserves the continuous evidence weighting in the higher-is-better
orientation; it does not claim a newly calibrated statistical model.

### API, Firestore and saved history

- New final results include `credibility: {version: "credibility-v2", status,
  score, label, explanation}`. The backend validates it against recorded evidence
  metadata before persistence and returns it in history and replay responses.
- `misinformation_risk_score` and `scoring` keep their previous meanings for
  compatibility. Never store a credibility number in the old risk field.
- New unresolved risk fields remain null under evidence-v4. Old evidence-v3
  provisional 50s remain readable and always display **Not rated**.
- Old rated records with adequate evidence-strength metadata are adapted for
  display, with an explanation of the direction change and no database rewrite.
  A bare old number is not converted; the app asks for another check.
- Existing persisted `credibility-v1` ratings retain their version and meaning.
  Component findings require `credibility-v2`; they are not attached to v1 records.
- Optional `component_assessment` preserves each part, cited findings, reasoning
  basis and aggregate conclusion through API responses, Firestore, history and
  replay. Validators check the exact original spans, source IDs, quotations and
  agreement between component findings and the final outcome.
- The main result card and history show the evidence label. The number appears
  only inside **Why this result?**, beside its explanation. Shared text uses the
  same order. Forecast and plausibility headlines preserve their specific basis.
- Production pipeline versions include `credibility-v2`; the v3 assessment path
  also records `components-v1`. Changes to this
  persisted rating contract require a new version and a legacy reader.

Regression tests cover all five labels, missing versus balanced evidence,
continuous score direction, duplicates and scope gates, legacy conversion,
invalid ratings, JSON round trips, API/storage/history/replay, and mobile copy.
Component regressions include material refutation with other parts unresolved,
partial support, same-part disagreement, source independence, financial-scope
guards, quoted provenance, provider failures and legacy compatibility.
These tests check behavior, not real-world accuracy. Human-labelled evaluation
and user comprehension testing are still required before claiming calibration.

### Extreme Singapore temperature predictions

With `EVIDENCE_PIPELINE_V3=1`, `climate.py` can return `highly_unlikely` with `scoring.status=plausibility_based` when an otherwise unresolved claim meets every condition:

- A simple, positive assertion about Singapore air temperature; one Celsius or Fahrenheit quantity.
- A grounded date range from today through the next 14 days.
- A freshly retrieved official MSS annual **all-stations** historical maximum. Retrieval validates the table headers, Celsius unit, value, source update date (at most 90 days old), response size and timeout. A changed/unavailable page produces no climate score.
- The claimed temperature exceeds that retrieved record by at least 10 degrees Celsius.

The legacy internal prototype indicator remains **risk 85/100** for backward
compatibility. It is not displayed as a factual credibility score; the app shows
the climate plausibility warning and explains its limitations. The 10-degree margin, 14-day horizon and indicator value are design choices awaiting labelled evaluation, not meteorological probability estimates. The initial request budget guard only fetches climate records for temperatures of at least 45 C; the final comparison always uses the retrieved maximum.

The record remains a **neutral** evidence source: it does not become a fabricated contradiction vote. The new context, comparison and source survive API responses and saved history. Matching official forecast comparisons and decisive web findings take precedence. Questions, possibility statements, hypotheses, negations, heat index, surface temperature, causal/compound claims and long-term projections do not receive this rule's score. Other countries and domains are not covered yet.

Example, assessed 4 October 2026: "Singapore will hit 50 degree celcius next Saturday" refers to 10 October. A live in-memory pipeline check returned `highly_unlikely`, citing the MSS table updated 22 September 2026 with a 37 C maximum. This is one diagnostic, not a measured accuracy improvement. Recheck old submissions to run the new rule; their stored outcomes are not rewritten.

Source: https://www.weather.gov.sg/climate-historical-extremes-temperature/

The branch comparison benchmark retains `highly_unlikely` as unresolved for its existing factual-truth labels. Inspect the separate `plausibility_context` when reviewing this feature; do not count an outlier warning as a proven falsehood.


### Live diagnostic on 8 October 2026

The exact retirement-age-75/CPF-depletion allegation was tested through the live
v3 pipeline using an in-memory repository. An initial run exposed loss of
Singapore context: broad component searches returned US retirement material and
a company whose ticker is CPF. The discovery scope fix now carries the relevant
Singapore/Central Provident Fund anchor and prioritises in-scope original pages.

After that fix, the live allegation returned **Not enough evidence**, with three
explicit component findings. Its accepted official policy page did not establish
the alleged discussions, depletion trend or causal connection. No result was
forced to false, and no Firestore result or allowance was changed.

A second live assessment reused that real CPF evidence for this control:
"The retirement age increased to 64 in July 2026 because the CPF payout
eligibility age is linked to the retirement age." It returned **Likely
misinformation**, credibility **5/100**: the event was supported, but the source
explicitly said the payout eligibility age is not linked to the retirement age.
This verifies the material-premise path with a real model and real evidence; it
is a single diagnostic, not an accuracy measurement.

Source used: https://www.cpf.gov.sg/member/infohub/educational-resources/does-raising-the-singapore-retirement-age-affect-the-cpf-payout-eligibility-age

Whole-claim context pages carry the retrieval layer's fixed ranking weight 0.5.
When a separate component judgment establishes applicable decisive evidence, the
component weight can use the existing direct-relevance value 0.9, bounded by the
source-type cap. This applies only to explicitly contextual provenance at that
fixed rank; original provenance and retrieval score are not rewritten. Inferred
findings remain capped at 0.70. These weights require labelled evaluation.
