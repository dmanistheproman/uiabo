# Pipeline orchestration - Donovan

This folder is owned primarily by **Ho Sze Wei, Donovan**.

This part is implemented. It:

- Maintains the shared schemas and interfaces.
- Calls pipeline components in the correct order.
- Skips retrieval for non-checkable content.
- Leaves completed factual checks unscored when evidence is insufficient.
- Handles component failures without returning a false assessment.
- Combines outputs into `TextAnalysisResult`.
- Saves submissions, results, evidence, source links, warnings, timestamps, and the pipeline version in Firestore.

## Files

```text
service.py       # Runs the components, checks their outputs, and builds the result
repository.py    # Saves completed and failed runs in Firestore
dependencies.py  # Connects the real component functions to the API
__init__.py      # Makes the main classes easy to import
```

Shared models and controlled errors are in `../shared/`.

Authenticated app requests use `with_repository()` to isolate intermediate output
in memory. `app/analyses/store.py` then saves the final result with its Firebase
owner and updates the allowance in one Firestore transaction. Retries with the
same idempotency key return the saved result without another charge. The standalone
repository remains available for pipeline evaluation; its legacy records without
an owner are not exposed in app history.

## How teammates connect their work

Each component can use any internal implementation, but its public function must follow these inputs and outputs:

```python
def analyze_claim(prepared: PreparedText) -> ClaimAnalysis: ...

def retrieve_evidence(claim: ClaimAnalysis) -> RetrievalResult: ...

def assess_evidence(
    claim: ClaimAnalysis,
    retrieval: RetrievalResult,
) -> AssessmentResult: ...
```

In `dependencies.py`, import each completed function and replace the matching `_..._not_ready` placeholder passed to `PipelineOrchestrator`. Do not change the shared field names just to make a component fit; adapt the component at its boundary instead.

## Important stopping rules

- A non-checkable claim skips retrieval and assessment and returns `Not Enough Information`.
- A completed search with no evidence skips semantic assessment and returns
  `Not Enough Information` with a null score (Not rated) and an explicit explanation.
- A technical retrieval failure returns a controlled API error. It is not reported as missing evidence.
- Invalid component output returns a contract error and is never shown as a normal assessment.

All four text stages are connected. Evidence retrieval uses Google Fact Check and Tavily. Retrieval failures without usable evidence return `RETRIEVAL_UNAVAILABLE`. In web mode, successful discovery with no readable eligible pages returns `SOURCE_PAGES_UNAVAILABLE` with a specific explanation. Both are retryable HTTP 503 errors; partial failures with evidence retain warnings. Claim-provider failures stop earlier with a controlled claim-analysis error rather than a completed `Not Enough Information` result. The configured semantic or lexical assessor uses evidence-v4 scoring; broader accuracy evaluation remains necessary.

## Claim interpretation and forecasts

The orchestrator gives date interpretation and grounded claim context the same
submission timestamp. Relative phrases use Singapore time: for example,
"this weekend" submitted on 17 September 2026 means 19–20 September 2026.
Explicit dates retain their stated year; a named date without a year retains the
existing current-year assumption. Ambiguous periods remain unresolved.

`claim_context` preserves literal locations and quantities, possibility wording,
and whether temperature means air, apparent or surface temperature. Any default
air-temperature interpretation is disclosed. These fields guide discovery and
assessment; they do not rewrite the original message or establish its truth.

With web retrieval and semantic assessment enabled, eligible Singapore
temperature claims can use the public NEA/MSS four-day forecast. Saved results
include the interpreted dates, structured source data and a separate
`forecast_context` explaining what the forecast supports. This is distinct from
the whole-claim verdict and score. A lower forecast alone cannot disprove a
possible future event, but the published forecast can contradict a false report
about what NEA/MSS forecasts.

The normal account API stores these optional fields with the result. History
and idempotent retries retain the original interpretation instead of recalculating
"this weekend" later. The mobile result shows the dates and a correction action;
a corrected submission creates a new check. Older saved records remain readable.

### Public credibility contract

Final assembly adds the validated `credibility-v2` rating before API output and
Firestore persistence. Higher means evidence supports the claim; lower means
evidence contradicts it. Insufficient evidence has a null score. The old risk
field retains its old direction for compatibility and is not displayed by the
mobile app. See the [assessment contract](../evidence_assessment/README.md#credibility-score-contract-6-october-2026)
for the formula, five evidence labels, unrated states and legacy handling.

Existing persisted `credibility-v1` ratings retain their original contract.
The old risk fields are not repurposed, and earlier results are not rewritten.

### Material-part assessment

With `EVIDENCE_PIPELINE_V3=1`, eligible explicit causal assertions can use
`components-v1`. The assessor checks the event, factual premise and causal link
separately in one bounded provider batch, using Jev then GPT-OSS as fallback.
Inferences requiring a written argument also go to GPT-OSS. A provider failure
without a valid assessment remains a retryable technical error.

Validated `component_assessment` travels with the final result through normal
account storage, history and idempotent replay. It records the original claim
spans, each cited finding and the aggregate reasoning. Exact-span, source and
quotation validation prevent detached or invented findings from being persisted
as an ordinary result.

A material contradiction can yield **Likely misinformation** while explicitly
identifying unresolved parts. Support for a different part does not cancel that
contradiction; whole-message support requires every essential part. Missing
evidence remains unscored, and existing-policy or funding-guarantee context alone
does not automatically refute alleged discussions or financial depletion.
