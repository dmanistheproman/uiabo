# uiabo

uiabo is a Final Year Project that aims to help users assess text and online content for possible misinformation. The planned system will return a concern label, misinformation risk score, uncertainty level, plain-language explanation, and supporting evidence with citations.

## Current status

The latest optional retrieval improvement is documented in [Broader retrieval prototype](backend/app/pipeline/evidence_retrieval/WEB_RETRIEVAL.md). It adds wider discovery, semantic relevance/scope checks and source provenance, with `catalogue` available for rollback. The [43-case review guide](evaluation/datasets/RETRIEVAL_REVIEW_GUIDE.md) explains the live comparison and the human review still required.

The FastAPI backend now connects all four Sprint 1 text stages: input preparation, Matthew's Ollama Cloud claim analysis, Google Fact Check/Tavily evidence retrieval, and Poon's baseline evidence assessment. It can return results with real source citations. Live testing confirms the flow works, but also exposes limitations in the lexical stance/scoring baseline; these results are not a validated accuracy claim.

Completed so far:

- FastAPI backend structure
- Root and health-check endpoints
- Text-analysis endpoint
- Pydantic request and response validation
- Separation of routes, schemas, and service logic
- Automated API tests
- Firebase Admin SDK setup
- Successful Firestore write-and-read smoke test
- Shared Pydantic contracts for every Sprint 1 handoff
- Pipeline orchestration and final result assembly
- Safe `Not Enough Information` results for non-checkable claims and missing evidence
- Controlled failures that never return a made-up score
- Live claim extraction and classification with validated model responses and timeouts
- Google Fact Check discovery, Tavily source extraction and scoped evidence search
- Saving completed and failed pipeline runs to Firestore
- Unit, API, contract, orchestration, and repository tests
- Service-account credentials kept outside the repository
- Firebase ID-token verification in FastAPI
- Protected account profile endpoints
- Free account and daily allowance creation in Firestore
- Expo/React Native Android app foundation
- Email/password registration, verification, login, password reset, profile, and logout flows
- Accessible free-user home screen with premium features visibly locked
- TDM-style mobile text checks, result details, citations and authenticated result history
- Atomic Firestore result saving and allowance charging, with idempotent request retries

Not yet implemented:

- Further evidence-assessment tuning and integration validation
- Broader source-catalogue review and coverage evaluation
- Calibrated risk/uncertainty scores and semantic evidence assessment
- Evaluation of explanation and citation accuracy
- Premium payments and operational dashboards

## Project structure

```text
uiabo/
|-- backend/
|   |-- app/
|   |   |-- accounts/       # User profiles and free usage allowances
|   |   |-- auth/           # Firebase token verification
|   |   |-- pipeline/       # Sprint 1 components and shared interfaces
|   |   |-- routers/        # API routes
|   |   |-- services/       # Compatibility service layer
|   |   |-- firebase.py     # Firestore client
|   |   |-- main.py         # FastAPI application
|   |   `-- schemas.py      # API request and error models
|   |-- scripts/
|   |   `-- firestore_smoke_test.py
|   |-- tests/
|   |   `-- test_analysis.py
|   `-- requirements.txt
|-- evaluation/              # Datasets, scoring rules and reports
|-- mobile/                  # Expo/React Native Android application
|-- submission/              # UIABO source documents and preliminary PTD/PUM
|-- sprint_1_samples/        # Shared JSON interfaces for each member
`-- README.md
```

## Submission documents

The [submission folder](submission/README.md) contains the team's PRD, URS and TDM,
plus the updated preliminary technical documentation and draft user manual.
Each preliminary document includes editable Word sections and a list of remaining
information or implementation work.

## Sprint 1 team samples

The [`sprint_1_samples`](sprint_1_samples) folder contains separate JSON examples for each member's pipeline component:

- Yi Da: input preparation and `PreparedText`
- Matthew: claim extraction and `ClaimAnalysis`
- Chu: fact-check/evidence retrieval and `RetrievalResult`
- Poon: evidence assessment and `AssessmentResult`
- Donovan: integration and the final `TextAnalysisResult`

These samples allow components to be developed in parallel before the previous component is finished. The claims, evidence and URLs are synthetic test fixtures and must not be shown to users as genuine fact checks.

## Requirements

- Python 3.11 or newer
- An Ollama Cloud API key for live claim analysis
- Google Fact Check Tools API and Tavily keys for live evidence retrieval
- A Firebase project and Cloud Firestore database for the Firestore smoke test
- Node.js and Expo Go or an Android emulator for the mobile application

## Backend setup

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy the project-root `.env.instructions` template to `uiabo/.env` and supply `OLLAMA_API_KEY`, `GOOGLE_FACT_CHECK_API_KEY`, and `TAVILY_API_KEY`. The backend loads this file automatically; existing environment variables take precedence. Enable Fact Check Tools API in the Google key's project. Supply the Tavily key itself, rather than its MCP URL. Restart the backend after changing keys. Keep `.env` local and never put these keys in the mobile app. No local Ollama installation or model download is required.

For the semantic assessment prototype, also set `EVIDENCE_ASSESSMENT_MODE=semantic`
and `OLLAMA_ASSESSMENT_MODEL=gpt-oss:120b` in that local file, then restart the backend.
It uses the same Ollama key to interpret retrieved passages and validate source
quotations. Existing installations without this setting retain the lexical
baseline; `EVIDENCE_ASSESSMENT_MODE=lexical` restores it explicitly. Model/provider
failures remain retryable errors and do not consume an allowance.
See the [assessment implementation notes](backend/app/pipeline/evidence_assessment/README.md)
and [provisional evaluation guide](evaluation/datasets/STANCE_LABELLING_GUIDE.md).
The app shows the quotation and source-specific explanation; numerical risk
indicators remain prototype rules, not calibrated probabilities.

## Run the API

From the `backend` directory with the virtual environment activated:

```powershell
uvicorn app.main:app --reload
```

Open the following pages after the server starts:

- API root: <http://127.0.0.1:8000/>
- Health check: <http://127.0.0.1:8000/health>
- Swagger documentation: <http://127.0.0.1:8000/docs>

## API endpoints

### `GET /`

Confirms that the API is running.

### `GET /health`

Example response:

```json
{
  "status": "ok"
}
```

### `POST /analysis/text`

Example request:

```json
{
  "text": "Singapore is introducing a new $500 tax next week."
}
```

The submitted text must contain between 1 and 5,000 characters.

`POST /analysis/text` now requires a verified Firebase ID token in the Bearer
header and an active profile. Send an `Idempotency-Key` header (up to 64 letters,
digits or hyphens) and reuse it when recovering an interrupted request. A completed
request is returned again without rerunning the pipeline or charging twice. Each
new check needs a new key. Free accounts receive one completed check per day;
server-granted Premium accounts receive 60 per calendar month. Periods reset at
midnight Singapore time. Failed checks are saved without charging the allowance.

With all provider keys and Firestore configured, text runs through the full pipeline. Non-checkable content skips retrieval. A successful search with insufficient evidence returns `Not Enough Information` and no risk score. A technical search failure with no usable evidence returns a controlled `503` response:

```json
{
  "detail": {
    "error_code": "RETRIEVAL_UNAVAILABLE",
    "message": "Analysis could not be completed because evidence search is temporarily unavailable.",
    "stage": "evidence_retrieval",
    "retryable": true
  }
}
```

Missing provider configuration, insufficient valid classifier responses, extraction failures, and timeouts also return controlled errors. Partial search failures can still return usable evidence with warnings. The successful response follows `TextAnalysisResult` in [`sprint_1_samples/05_donovan_integration_samples.json`](sprint_1_samples/05_donovan_integration_samples.json); those shared fixture values remain synthetic examples.

### `PUT /account/me`

Creates or refreshes the signed-in user's own free profile. It requires a Firebase ID token in the `Authorization: Bearer <token>` header. An unverified account is stored with `pending_verification` status.

### `GET /account/me`

Returns the verified user's own profile and allowance. Unverified, invalid, expired, revoked, suspended, and deactivated accounts are rejected.

### `GET /analysis/results` and `GET /analysis/results/{result_id}`

Return the signed-in user's saved completed and failed checks. The history endpoint
accepts `limit` (1-50, default 20) and a `cursor` from `next_cursor`. Other users'
records and legacy records without an owner are not exposed. Results are stored
under `analysis_results/{result_id}` with `user_id` and `input_type`, as in the TDM.

## Run the tests

From the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The current tests cover:

- `GET /health`
- `POST /analysis/text`
- Input preparation and validation
- Claim-analysis HTTP contracts, response validation, voting, failures and deadlines (mocked HTTP; no key required)
- Retrieval provider adapters, fallback, source filtering, deduplication, failure handling and real assessment integration (mocked HTTP)
- Every shared component interface
- Complete orchestration with sample component outputs
- Non-checkable claims and missing-evidence stopping rules
- Component, contract, and Firestore failures
- Firestore result serialization
- Firebase authentication token handling
- Account creation, email-verification gating, suspension, and free allowances

For an opt-in live claim-analysis check (uses Ollama Cloud allowance), run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m scripts.claim_analysis_smoke_test --report ../evaluation/reports/claim_live_local.json
```

This sends the eight synthetic Matthew samples to the configured cloud models. It checks categories, checkability and extracted spans; it does not search evidence, establish factual truth, or write to Firestore. See [`backend/app/pipeline/claim_analysis/README.md`](backend/app/pipeline/claim_analysis/README.md) for implementation limits.

To test all live text stages through FastAPI using in-memory storage:

```powershell
.\.venv\Scripts\python.exe -m scripts.text_pipeline_smoke_test --report ../evaluation/reports/text_pipeline_live_local.json
```

This consumes Ollama and Tavily allowance and Google API quota. It makes no Firestore writes. See the [retrieval implementation notes](backend/app/pipeline/evidence_retrieval/README.md) and [September 7 integration report](evaluation/reports/chu_retrieval_evaluation.md).

## Mobile app

The working authentication slice is in [`mobile`](mobile). Follow [`mobile/README.md`](mobile/README.md) to configure Firebase, select the correct backend address, run the Android app, and perform the full account test.

## Firebase and Firestore

The backend uses Firebase Application Default Credentials. Set the path to a local service-account JSON file before running the smoke test.

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\service-account.json"
.\.venv\Scripts\python.exe -m scripts.firestore_smoke_test
```

Never commit the service-account JSON file or other credentials to the repository.

The smoke test writes and reads a document in the `system_tests` collection. The text-analysis pipeline saves completed and failed runs in the `analysis_results` collection. Tests use a fake or in-memory repository and do not require Firebase credentials.

## Next development priority

The Android text-check flow and Firestore are connected. The next milestone is evaluation of real evidence and scores across the flow:

1. Extract and classify a factual claim.
2. Search existing fact checks.
3. Retrieve evidence from trusted sources.
4. Determine whether evidence supports or contradicts the claim.
5. Rank the evidence and assess source credibility.
6. Calculate risk and uncertainty.
7. Generate a simple explanation with citations.
8. Evaluate the pipeline using a small test dataset.

Runtime functions are connected in [`backend/app/pipeline/orchestration/dependencies.py`](backend/app/pipeline/orchestration/dependencies.py). They follow the shared models documented in [`backend/app/pipeline/orchestration/README.md`](backend/app/pipeline/orchestration/README.md).

## Planned later work

- Link and webpage analysis
- Premium subscriptions and role-management tools
- Usage limits and premium features
- Administrator and data-engineer dashboards
- OCR and image-caption analysis
- Security, accessibility, performance, deployment, and user testing

Deepfake detection is required for the final submission. Audio analysis is excluded. The September 12 prototype targets basic Sprint 1 text checking in the Android app; the final submission is expected in November.
