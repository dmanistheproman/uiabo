# Pipeline orchestration - Donovan

This folder is owned primarily by **Ho Sze Wei, Donovan**.

This part is implemented. It:

- Maintains the shared schemas and interfaces.
- Calls pipeline components in the correct order.
- Skips retrieval for non-checkable content.
- Skips scoring when evidence is insufficient.
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
- A completed search with no evidence skips assessment and returns `Not Enough Information`.
- A technical retrieval failure returns a controlled API error. It is not reported as missing evidence.
- Invalid component output returns a contract error and is never shown as a normal assessment.

All four text stages are connected. Evidence retrieval uses Google Fact Check and Tavily. Search failures without usable evidence return `RETRIEVAL_UNAVAILABLE`; partial failures with evidence retain warnings. Claim-provider failures stop earlier with a controlled claim-analysis error rather than a completed `Not Enough Information` result. Stance/scoring remains Poon's lexical prototype and needs broader accuracy evaluation.
