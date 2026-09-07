# Matthew claim-analysis integration check - 6 September 2026

The Ollama Cloud key authenticated with all three configured models. Claim
analysis is connected to the default FastAPI pipeline. No local Ollama service
or model download is required.

## Results

| Check | Result |
| --- | --- |
| Full backend suite, with Ollama key removed and dotenv disabled | 207 passed |
| Claim-analysis regression tests within that suite | 48 passed |
| Live Matthew sample comparisons | 7 of 8 matched |
| Live opinion through FastAPI with in-memory storage | HTTP 200, Not Enough Information, no risk score |
| Live factual claim through FastAPI with in-memory storage | HTTP 503, EVIDENCE_RETRIEVAL_NOT_READY |

The seven matching samples cover two factual assertions, opinion, prediction,
personal experience, prompt injection and a greeting. Each comparison checks
category, checkability and extracted text, allowing case, whitespace and terminal
punctuation differences. Recorded claim-stage times ranged from 2.69 to 9.30 seconds.

The satire sample expected `joke_or_satire` but returned `unverifiable` with zero
agreement because the available classifiers disagreed. It remained non-checkable
and produced no extracted claim. This is a classification limitation; the expected
sample and observed result were retained without relabelling it as a pass.

## What changed

- Credentials load from the ignored project-root `.env` when analysis is called;
  environment configuration takes precedence. Importing the backend needs no key.
- Classifiers run concurrently with request and overall deadlines.
- Cloud responses are validated locally. Provider failures cannot vote for a
  category; at least two valid classifier responses are required.
- Extraction failures stop the pipeline instead of producing a completed result.
  Extracted text must be a source span rather than invented wording.
- Claim analysis now hands off to the real pipeline. Evidence retrieval remains
  the explicit pending component.

## Evidence and limits

- [Live sample results](matthew_claim_live_2026-09-06.json)
- [Live API results](matthew_api_live_2026-09-06.json)
- [Rerunnable smoke test](../../backend/scripts/claim_analysis_smoke_test.py)

These are eight synthetic team samples, not an independent accuracy benchmark.
Model agreement is not probability of correctness. The span check cannot prove
that every qualifier was preserved, and one prompt-injection sample does not
establish general resistance. This run does not validate factual truth, live
evidence retrieval, Firestore persistence, or the Android UI. API checks used the
real claim provider with an in-memory repository and made no Firestore writes.

The backend suite emitted one dependency deprecation warning about Starlette's
HTTPX test-client integration; no tests failed.
