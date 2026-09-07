# Claim analysis - Matthew

`analyse_claim(PreparedText) -> ClaimAnalysis` is connected to the backend pipeline.
It calls Ollama Cloud directly over HTTPS using the existing HTTPX dependency.

## Configuration

Copy the project-root `.env.instructions` to `uiabo/.env` and supply
`OLLAMA_API_KEY`. This ignored local file is loaded only when analysis is called.
Shell/deployment configuration takes precedence. Restart after changing a key.
No local Ollama installation is needed. Never include the key in the mobile app.

## Processing

1. Send the normalised text as untrusted user data with separate system instructions.
2. Classify concurrently with `gpt-oss:120b`, `gemma4:31b` and `nemotron-3-super`.
3. Validate category and non-empty reason locally; failed/invalid replies do not vote.
4. Require at least two valid replies. A majority selects the category. A split
   without a majority returns unverifiable with zero agreement.
5. For factual claims, use `gemma4:31b` to extract a source span. Validate JSON,
   reject empty/null output and require the span to occur in the submitted text
   (ignoring case, whitespace and terminal sentence punctuation).

Ollama Cloud currently does not support structured outputs, so requests omit
`format`. JSON code fences are tolerated but the contained object must still
match the strict local schema. See [Ollama structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs).

Requests have a 40-second deadline, a 10-second connection timeout, and a
90-second total claim-stage deadline. There are no automatic retries. Missing
configuration, fewer than two valid classifiers, extraction failure and overall
timeout raise controlled errors. The orchestrator saves these as failed runs;
provider failure is never a vote for unverifiable.

`claim_confidence` is winning votes divided by the three configured models
(1.0 or 0.67 for a majority), not a calibrated probability of correctness.
A failed third classifier reduces agreement to 0.67 and is noted in the reason.
Disagreement and model decisions can still be wrong. Source-span validation
cannot prove that an extraction preserved every qualifier or the intended meaning.
The prompts and span check mitigate prompt injection but do not guarantee immunity.

## Verification

Offline regression tests in `tests/pipeline/claim_analysis/test_service.py` mock
HTTP, including provider outages, malformed output, deadlines, concurrent calls
and handoff to the orchestrator. They make no cloud calls and need no key.

From `backend`, run the opt-in live smoke test:

```powershell
.\.venv\Scripts\python.exe -m scripts.claim_analysis_smoke_test --report ../evaluation/reports/claim_live_local.json
```

This uses cloud allowance and sends eight synthetic team samples. The report
compares category, checkability and the extracted span, allowing case/whitespace
and terminal punctuation differences. It does not compare explanatory wording or
fixture confidence values. These samples are not an independent accuracy benchmark.
No evidence is retrieved, no factual truth is established, and Firestore is unused.
Matthew's broader evaluation dataset belongs in `evaluation/datasets`.
