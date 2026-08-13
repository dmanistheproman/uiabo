# uiabo

uiabo is a Final Year Project that aims to help users assess text and online content for possible misinformation. The planned system will return a concern label, misinformation risk score, uncertainty level, plain-language explanation, and supporting evidence with citations.

## Current status

The initial FastAPI backend is working. It can accept text and return the planned analysis response structure, but the misinformation analysis is currently mocked.

Completed so far:

- FastAPI backend structure
- Root and health-check endpoints
- Text-analysis endpoint
- Pydantic request and response validation
- Separation of routes, schemas, and service logic
- Automated API tests
- Firebase Admin SDK setup
- Successful Firestore write-and-read smoke test
- Service-account credentials kept outside the repository

Not yet implemented:

- Real claim extraction and classification
- Fact-check and evidence retrieval
- Evidence assessment and ranking
- Source credibility checks
- Risk and uncertainty calculations
- Evidence-based explanations and citations
- Saving analysis results to Firestore
- Authentication, mobile application, and operational dashboards

## Project structure

```text
uiabo/
|-- backend/
|   |-- app/
|   |   |-- routers/        # API routes
|   |   |-- services/       # Analysis logic
|   |   |-- firebase.py     # Firestore client
|   |   |-- main.py         # FastAPI application
|   |   `-- schemas.py      # Request and response models
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

Example response:

```json
{
  "result_id": "generated-uuid",
  "extracted_claim": "Singapore is introducing a new $500 tax next week.",
  "concern_label": "Needs Caution",
  "misinformation_risk_score": 50,
  "uncertainty": "High",
  "explanation": "This is a mock analysis result. Real misinformation analysis has not been implemented yet.",
  "evidence": []
}
```

The label, score, uncertainty, and explanation above are hard-coded placeholders. They must not be treated as a real assessment.

## Run the tests

From the `backend` directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The current tests cover:

- `GET /health`
- `POST /analysis/text`

## Firebase and Firestore

The backend uses Firebase Application Default Credentials. Set the path to a local service-account JSON file before running the smoke test.

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\service-account.json"
.\.venv\Scripts\python.exe -m scripts.firestore_smoke_test
```

Never commit the service-account JSON file or other credentials to the repository.

The smoke test writes and reads a document in the `system_tests` collection. Firestore is not yet connected to the text-analysis endpoint.

## Next development priority

The next milestone is a first evidence-backed text misinformation prototype:

1. Extract and classify a factual claim.
2. Search existing fact checks.
3. Retrieve evidence from trusted sources.
4. Determine whether evidence supports or contradicts the claim.
5. Rank the evidence and assess source credibility.
6. Calculate risk and uncertainty.
7. Generate a simple explanation with citations.
8. Evaluate the pipeline using a small test dataset.

The plan is to replace one mocked stage at a time and test each stage before moving on.

## Planned later work

- Link and webpage analysis
- Firestore storage for submissions and results
- Firebase Authentication and account roles
- React Native Android application
- Usage limits and premium features
- Administrator and data-engineer dashboards
- OCR and image-caption analysis
- Security, accessibility, performance, deployment, and user testing

Deepfake or AI-generated-image detection is currently considered a stretch goal until its scope is confirmed.
