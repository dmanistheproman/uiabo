# uiabo

uiabo is a Final Year Project that aims to help users assess text and online content for possible misinformation. The planned system will return a concern label, misinformation risk score, uncertainty level, plain-language explanation, and supporting evidence with citations.

## Current status

The FastAPI backend and Sprint 1 pipeline structure are working. Input preparation, shared interfaces, pipeline control flow, safe stopping rules, Firestore result storage, and API error handling are implemented. The other three team components still need to be connected before the endpoint can produce a real misinformation assessment.

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
- Saving completed and failed pipeline runs to Firestore
- Unit, API, contract, orchestration, and repository tests
- Service-account credentials kept outside the repository

Not yet implemented:

- Real claim extraction and classification
- Fact-check and evidence retrieval
- Evidence assessment and ranking
- Source credibility checks
- Risk and uncertainty calculations
- Evidence-based explanations and citations
- Authentication, mobile application, and operational dashboards

## Project structure

```text
uiabo/
|-- backend/
|   |-- app/
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
|-- sprint_1_samples/        # Shared JSON interfaces for each member
`-- README.md
```

## Sprint 1 team samples

The [`sprint_1_samples`](sprint_1_samples) folder contains separate JSON examples for each member's pipeline component:

- Yi Da: input preparation and `PreparedText`
- Matthew: claim extraction and `ClaimAnalysis`
- Chu: fact-check/evidence retrieval and `RetrievalResult`
- Poon: evidence assessment and `AssessmentResult`
- Donovan: integration and the final `TextAnalysisResult`

These samples allow components to be developed in parallel before the previous component is finished. The claims, evidence and URLs are synthetic test fixtures and must not be shown to users as genuine fact checks.

## Requirements

- Python 3
- A Firebase project and Cloud Firestore database for the Firestore smoke test

## Backend setup

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

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

Until the three remaining team components are connected, valid text reaches the pipeline and returns a controlled `503` response such as:

```json
{
  "detail": {
    "error_code": "CLAIM_ANALYSIS_NOT_READY",
    "message": "Claim analysis has not been integrated yet.",
    "stage": "claim_analysis",
    "retryable": false
  }
}
```

This is intentional: the API no longer returns the old hard-coded score of `50`. When Matthew, Chu, and Poon's components are connected, the same endpoint returns the agreed `TextAnalysisResult` shown in [`sprint_1_samples/05_donovan_integration_samples.json`](sprint_1_samples/05_donovan_integration_samples.json).

## Run the tests

From the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The current tests cover:

- `GET /health`
- `POST /analysis/text`
- Input preparation and validation
- Every shared component interface
- Complete orchestration with sample component outputs
- Non-checkable claims and missing-evidence stopping rules
- Component, contract, and Firestore failures
- Firestore result serialization

## Firebase and Firestore

The backend uses Firebase Application Default Credentials. Set the path to a local service-account JSON file before running the smoke test.

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\service-account.json"
.\.venv\Scripts\python.exe -m scripts.firestore_smoke_test
```

Never commit the service-account JSON file or other credentials to the repository.

The smoke test writes and reads a document in the `system_tests` collection. The text-analysis pipeline saves completed and failed runs in the `analysis_results` collection. Tests use a fake or in-memory repository and do not require Firebase credentials.

## Next development priority

The next milestone is to connect the three teammate components to the prepared pipeline:

1. Extract and classify a factual claim.
2. Search existing fact checks.
3. Retrieve evidence from trusted sources.
4. Determine whether evidence supports or contradicts the claim.
5. Rank the evidence and assess source credibility.
6. Calculate risk and uncertainty.
7. Generate a simple explanation with citations.
8. Evaluate the pipeline using a small test dataset.

Replace the explicit `*_NOT_READY` functions in [`backend/app/pipeline/orchestration/dependencies.py`](backend/app/pipeline/orchestration/dependencies.py) with the real component functions. Each function must accept and return the shared model documented in [`backend/app/pipeline/orchestration/README.md`](backend/app/pipeline/orchestration/README.md).

## Planned later work

- Link and webpage analysis
- Firebase Authentication and account roles
- React Native Android application
- Usage limits and premium features
- Administrator and data-engineer dashboards
- OCR and image-caption analysis
- Security, accessibility, performance, deployment, and user testing

Deepfake or AI-generated-image detection is currently considered a stretch goal until its scope is confirmed.
