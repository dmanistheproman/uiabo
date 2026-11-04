# Gemini PDF evidence reader

The backend can now read the visual layout of short employment-statistics PDFs. This fixes a specific retrieval problem: ordinary PDF text can mix neighbouring charts, so the assessment cannot reliably connect each number to its date and measurement.

## Setup

In the project-root `.env` used to start the backend:

```dotenv
PDF_READER_ENABLED=true
PDF_READER_MODEL=gemini-3.5-flash-lite
GEMINI_API_KEY=your-existing-gemini-key
```

Reuse the backend's existing Gemini key. Keep it out of GitHub and the mobile `.env`.

Install the updated backend requirements, then restart your usual backend command:

```powershell
cd C:\Dev\uiabo-vision\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --env-file ..\.env --host 0.0.0.0 --port 8002
```

Use your own checkout path and the port configured for your app. Stop its existing backend before starting another on the same port. Set `PDF_READER_ENABLED=false` to disable this fallback.

## What happens during a check

1. Tavily discovers and extracts sources; the existing relevance checks select useful evidence.
2. The backend chooses one relevant employment-statistics PDF after reviewing the sources.
3. It downloads the PDF from an eligible HTTPS publisher and sends its bytes to Gemini. Gemini receives an extraction instruction, not the user's claim.
4. Gemini returns separate chart series with measurements, populations, dates, values, units, cohorts and page numbers.
5. The backend validates the response and checks numbers and label tokens against text embedded in the actual PDF. These checks do **not** independently prove the chart associations are correct.
6. Assessment receives the chart reading separately from the original source quotation. Numerical comparisons use the stored chart values and decimal arithmetic, with population/period/measurement checks. Chart data alone does not establish a claimed cause.
7. The saved result contains the chart reading and source reference. In the app, open **Read source details → Figures read from the PDF** to view the tables and page numbers.

For an undated statistical comparison, the current backend assumes a recent
change and selects the newest comparable observation and its predecessor. The
explanation states the dates used. Explicit periods take priority; population and
measurement gaps are assessed separately. See the [period rules](backend/app/pipeline/evidence_assessment/README.md#undated-statistical-comparisons).

Old saved results are not recalculated. Submit a new check to use the reader.

## Limits and cost controls

- First integration: employment-statistics PDFs with URLs ending in `.pdf`, already accepted by relevance selection. Other topics keep their existing retrieval route.
- At most one PDF reading per check; five pages and 5 MB maximum; 22-second fallback deadline inside the existing retrieval deadline.
- No automatic Gemini retries. Two simultaneous PDF fallbacks per backend process; additional requests keep their normal evidence.
- Cache: validated extraction JSON only, at most 128 entries, seven-day reuse. The key includes PDF contents, model, prompt and schema. Files live in ignored `backend/.cache/pdf-readings/`.
- The PDF is downloaded again to detect changed contents. A matching cache entry avoids another Gemini request.
- Gemini calls use the existing project's quota/billing. Cache hits do not make another Gemini call. This path does not call Cloud Vision.
- Scanned PDFs without native text, encrypted documents, oversized documents, redirects, unreadable data and failed requests retain the existing extracted text with a warning. This release does not claim to read every PDF.
- Source downloads use checked public IP addresses with the original TLS hostname, no redirects, no source-host credentials and bounded downloads.
- Model output can still misinterpret a chart. It is displayed as an AI reading, never as a verbatim quotation or independent corroborating source.

## Verification

The official MOM graduate-outcomes infographic was checked against the earlier manually reviewed pilot. Its unemployment-count chart reports 4,300 in June 2024 and 6,000 in June 2025: a 39.5% increase, not a doubling for that specific comparison. This does not establish the unemployment rate for all graduates or explain hiring/pay practices.

On 3 November 2026, a live check specifying fresh university graduates and June 2024–June 2025 used the cached PDF reading and returned likely misinformation for the claimed doubling. The original message without dates remained unresolved in a separate run; live search also varies and may omit or fail to select a useful source. PDF reading improves the interpretation of a retrieved document, not every search result.

After the latest-period default was added, a live assessment replay against the
app's saved sources also returned likely misinformation for the **undated** claim
about the **number of unemployed fresh university graduates**, disclosing June
2024–June 2025. The original broader wording retains population/measurement gaps.
This replay tested assessment with fixed sources, not a guarantee of live search coverage.

Offline checks:

```powershell
cd C:\Dev\uiabo-vision\backend
.\.venv\Scripts\python.exe -B -m pytest tests/pipeline/evidence_retrieval/test_pdf_reader.py tests/pipeline/evidence_assessment/test_numeric_comparison.py -q
```

Live full-pipeline diagnostic (provider quota applies; no Firestore writes or allowance changes):

```powershell
cd C:\Dev\uiabo-vision
.\backend\.venv\Scripts\python.exe -B evaluation/retrieval_scope/run_live.py --live --case graduates --output C:\Dev\assessment-review\gemini-graduates.json
```

See [Google's document-understanding documentation](https://ai.google.dev/gemini-api/docs/document-processing) and the earlier [isolated comparison](evaluation/pdf_reading/README.md).
