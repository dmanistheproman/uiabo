# PDF reader comparison

This is an isolated experiment comparing **Gemini PDF understanding** with
**Google Cloud Vision PDF OCR** on the MOM graduate-outcomes infographic that
caused ambiguous extraction. It does not change the app's live retrieval path.

## Results from 3 November 2026

- The existing root `.env` contains a working `GEMINI_API_KEY`.
- The existing Firebase Admin identity can call Cloud Vision's PDF OCR endpoint.
- Gemini used the same model as the image features: `gemini-3.5-flash-lite`.
- Gemini extracted all **12 reviewed measure/date/value/unit associations**
  correctly in both successful live runs. There were no extra or duplicate points.
- Cloud Vision found all 12 values and supplied word locations. Its plain text
  still interleaves the unemployment and outside-the-labour-force charts.
- The title, publication month, population descriptions and cohort assignments
  were also checked visually against the original page. Year-to-year graduate
  counts compare different cohorts; June-to-July rates concern the 2025 cohort.
- Observed provider times were about **4.4-4.9 seconds for Gemini** and **3.1 seconds
  for Vision**. These are small-sample measurements, not latency guarantees.
- The first Gemini response reported 1,551 input tokens and 1,266 output tokens.
- All **11 isolated offline tests** passed.

The rendered original was reviewed before the expected association fixture was
written. The fixture is tied to the PDF SHA-256, so a changed source document
cannot silently be scored against old values. This one-page test does not
establish general PDF accuracy or fact-checking accuracy.

The successful result is stored locally at:
`C:\Dev\assessment-review\pdf-reader-pilot\run-1\comparison.json`.
The source image is at:
`C:\Dev\assessment-review\pdf-reader-pilot\mom-graduates-page-1.png`.

## What the comparison proves and does not prove

Gemini correctly kept these distinctions in this test:

| Measurement | First observation | Second observation |
| --- | --- | --- |
| Employed graduates | June 2024: 8,600 | June 2025: 9,300 |
| Unemployed graduates | June 2024: 4,300 | June 2025: 6,000 |
| Outside the labour force | June 2024: 5,100 | June 2025: 2,700 |
| Permanent employment share | June 2024: 36.9% | June 2025: 44.1% |
| Employment rate, 2025 cohort | June 2025: 51.9% | July 2025: 55.6% |
| Unemployment rate, 2025 cohort | June 2025: 39.0% | July 2025: 34.8% |

This resolves a document-reading problem. It does not establish the original
claim's unspecified comparison period or its allegation about foreign/local pay
and causation. The document covers **fresh university graduates**, not every
Singapore graduate.

OCR agreement on the digits is only corroboration that a number was printed.
It does **not** independently verify which chart/date/population it belongs to.
Tests explicitly check that swapping chart labels fails association scoring even
when every number is present in the OCR output.

## Run the experiment

Use the existing backend virtual environment from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -B evaluation\pdf_reading\compare.py --live --pdf C:\Dev\assessment-review\pdf-reader-pilot\mom-graduates.pdf --output-dir C:\Dev\assessment-review\pdf-reader-pilot\run-2
```

- `--live` explicitly allows provider usage charges on a cache miss.
- Reuse an output directory to reuse its successful extractions. The cache key
  includes PDF contents, provider, model, prompt, schema and reader version.
- `--refresh` explicitly repeats requests instead of using that cache.
- No automatic paid retries. Failed calls are not cached as successful readings.
- No Firestore writes, Firebase Storage uploads or app allowance deductions.
- Credentials stay in the existing ignored `.env`; they are not copied into
  outputs. The PDF is sent inline to each provider.
- This fixture processes one known public PDF, at most 5 MB. It is not an
  arbitrary public-URL downloader or a production PDF processing endpoint.

Run the isolated offline checks from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -B -m pytest -q evaluation\pdf_reading\tests
```

## Integration recommendation

Use Gemini as a bounded fallback for PDF charts/tables that normal extraction
cannot preserve. Keep regular text extraction for straightforward pages. Before
enabling it for app checks:

- Test additional layouts, incorrect dates, wrong populations and missing labels.
- Preserve original PDF/page references and label all reconstructed tables as
  extracted data; never present them as verbatim source quotations.
- Admit a numerical comparison only after the existing population, date, measure
  and arithmetic checks pass. Missing context must remain visible.
- Keep strict download, page, size, latency and spending limits, plus caching.
- Treat extracted document content as untrusted data, never instructions.

The installed Gemini SDK/model rejected the first API-level schema configurations.
The successful request uses JSON mode, supplies the schema in the extraction
prompt and validates the response with Pydantic afterward. Invalid, incomplete or
truncated output is rejected. No dependency or environment changes were needed.

## References

- [Official MOM source PDF](https://stats.mom.gov.sg/iMAS_Infographics/mrsd-Labour-market-outcomes-of-fresh-univ-grads.pdf)
- [Gemini PDF understanding](https://ai.google.dev/gemini-api/docs/document-processing)
- [Cloud Vision synchronous PDF annotation](https://docs.cloud.google.com/vision/docs/reference/rest/v1/files/annotate)
