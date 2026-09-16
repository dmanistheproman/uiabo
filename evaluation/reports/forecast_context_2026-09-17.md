# Claim context and forecast checks — 17 September 2026

## What changed

- **Claim interpretation:** preserve the original message and its possibility wording. Extract literal locations, quantities and units into separate context.
- **Dates:** interpret supported relative phrases using Singapore time at submission. Show the dates in the app and allow the user to correct them. Explicit dates retain their stated year.
- **Retrieval:** use the public NEA/MSS four-day API for eligible Singapore air-temperature claims. Follow up on missing coverage and additional claims within the existing web-search limits.
- **Assessment:** compare the same location, dates, measurement and units. Keep forecast compatibility separate from the whole-message verdict. Additional web sources receive quotation-validated assessment.
- **App and storage:** show the forecast, its issue time, interpretation assumptions and correction action. Save these fields with the result so history and retries retain the original interpretation. The source button opens the readable latest MSS forecast; the evidence retains the exact API data used.

## Live checks

Both cases used the configured cloud claim analysis, web retrieval and semantic assessment through the real authenticated API route. Authentication and account persistence were replaced with in-memory test accounts. These checks did **not** write to production Firestore or use the user's allowance.

Pipeline: `sprint-1-semantic-v7:gpt-oss:120b:evidence-v3:retrieval-web-v10`.

| Submitted message | Result | What it demonstrates |
| --- | --- | --- |
| Temperatures in Singapore could reach 52°C this weekend because of a record-breaking heatwave. | HTTP 200; **50/100, provisional, unsupported**; 38.94 seconds; three sources. | The current forecast does not support 52°C. A lower forecast alone does not disprove a future possibility or establish the claimed cause. Related web sources did not settle the message. |
| MSS forecasts a maximum air temperature of 52°C in Singapore this weekend. | HTTP 200; **97/100, contradicted**; 6.46 seconds; one official source. | The claim attributes a specific published forecast to MSS. The matching official data contradicts that attribution. Retrieval required no Google/Tavily search requests. |

For these submissions, **“this weekend” meant 19–20 September 2026**. The API issue from **16 September 2026 at 17:07 SGT** gave 25–33°C for 19 September and 25–34°C for 20 September. The combined displayed range was 25–34°C. These values are a saved test snapshot; they are not a forecast for every later check.

Sources: [official data API](https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook), [MSS four-day outlook](https://www.weather.gov.sg/weather-forecast-4dayoutlook/), [dataset documentation](https://data.gov.sg/datasets/d_f131f6e343bf8168e4057a04c4326a0a/view).

For both live cases, fetching the result, listing account history and repeating the idempotent request preserved the score, date context, claim context, forecast comparison and evidence. The simulated allowance was charged once per original submission.

## Automated verification

- **786 backend tests passed**, including the existing OCR, link-safety, policy, account and scoring checks.
- **25 mobile presentation tests passed**.
- Android JavaScript export passed with Expo's `--no-bytecode` option. This checks bundling; it is not a Hermes/native-device test.
- New tests cover Singapore/UTC date boundaries, weekends, explicit ranges, ambiguous dates, literal quantities, Celsius/Fahrenheit, apparent/surface temperature, stale or malformed API data, incomplete forecast horizons and request limits.
- Assessment tests distinguish published-forecast attribution from a future possibility; preserve unresolved causes and additional clauses; merge direct web refutations; and retain forecast evidence with visible limitations when extra web assessment fails.
- Mobile tests ensure partial forecast agreement cannot hide a contradicted or conflicting whole-message finding.

## Limits and operating notes

- The structured adapter currently covers **Singapore air temperature within the available four-day forecast**. Other locations, apparent temperature, surface temperature and dates outside that horizon use web retrieval and may remain unresolved.
- Claim context uses conservative text parsing. It is not universal language understanding; ambiguous locations, measurements and periods remain unresolved.
- Temperature bounds, approximate values and every-day claims are not treated as exact point comparisons. A historical record is not a ceiling on future weather.
- A literal refutation guard supplements semantic assessment; it does not prove the model interpreted negation or relevance correctly.
- A completed partial forecast check uses the normal allowance and discloses missing web assessment. A check with no usable forecast retains the ordinary technical-error behavior.
- Scores remain evidence indicators, not calibrated probabilities of falsehood. A provisional 50 is an unresolved starting point; it is not a 50% probability.
- These are operational and regression checks, not a measured improvement in general detection accuracy. Labelled evaluation remains necessary.
- Restart the backend and submit a new check to use these changes in the app. Previously saved results are not rewritten. The live verification above ran in a separate test process, not the existing backend server or emulator.
