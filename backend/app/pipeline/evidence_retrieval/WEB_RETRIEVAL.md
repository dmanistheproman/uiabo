# Broader retrieval prototype

## Enable or roll back

Set `EVIDENCE_RETRIEVAL_MODE=web` in the ignored repository-root `.env` and restart the backend. `catalogue` selects the previous retrieval path and is the default when the setting is absent. The template defaults to `catalogue` until evaluation/review is complete.

The web mode uses the existing Google Fact Check, Tavily and Ollama keys, all on the server. Singapore air-temperature forecasts can additionally use the public NEA/MSS API without a key. No local model download or mobile API key is needed. Its pipeline version includes `retrieval-web-v10`.

## Flow

1. For an eligible Singapore air-temperature claim with explicit interpreted dates, first request the public NEA/MSS four-day forecast. A complete validated match can finish retrieval with that official source. Additional causal, heatwave or record-breaking clauses still need web discovery. Otherwise search Google Fact Check and the preferred Tavily domains concurrently.
2. Extract up to two eligible original pages. Search snippets and Google's repeated claims are discovery metadata, never final evidence.
3. Select a relevant passage and assess its scope using Ollama. The model selects numbered source sentences and the backend copies exact original text, including formatting. The bounded shortlist retains opening context, literal matches and payment-rule passages that can use a different amount or frequency. These discovery ranks do not determine acceptance. The relevance prompt (`relevance-v9`) distinguishes the subject from the alleged rule, forecast versus observation, and air versus apparent or surface temperature. It uses medium reasoning.
4. If fewer than two origin groups provide direct, applicable evidence, use up to two alternative queries and search the wider web. The first retains the discovery claim's numbers, including any visibly assumed year; the second may omit disputed numbers to find the underlying policy but cannot introduce new numbers. A repeated page can receive an improved discovery rank without receiving another extraction slot. If query planning fails, still try the original query broadly. Passport queries separate the alleged announcement from current entry rules; the known ICA/Singapore lookup uses two deterministic discovery hints within the same budget instead of an extra planner call.
5. Extract remaining candidates within a four-URL budget. An unfamiliar page can supply a literal link to an eligible original, which must itself be extracted. Major social platforms are not extracted.
6. Send accepted passages to the existing semantic stance assessor. Context-only, inapplicable or temporally unresolved evidence is forced neutral during aggregation, even if stance assessment says supporting.
7. Return the result through the existing API and save optional evidence provenance, assessment outcome and grounded claim comparisons through the normal Firestore persistence path. The app displays policy comparisons and quoted sources. Old records without these optional fields remain readable.

## Explicit source decisions

- **Reviewed catalogue:** keep the existing source catalogue as preferred publishers.
- **Restricted government namespace:** accept discovered `.gov`, `.gov.uk` and `.gov.au` hostnames for assessment based on their registries' eligibility policies. Exact hostname boundaries prevent suffix lookalikes.
- **Unverified publisher:** use only as a lead to original sources. Neither an LLM trust score nor an academic-looking `.edu`/`.org` name can promote it.

Registry evidence consulted on 2026-09-09:

- [US .gov eligibility](https://get.gov/domains/eligibility/)
- [UK .gov.uk eligibility](https://www.gov.uk/guidance/check-if-your-organisation-can-get-a-govuk-domain-name)
- [Australian government domain administration](https://www.domainname.gov.au/)

Namespace eligibility does not establish topical expertise, page authorship, truth or independence. A government-hosted allegation or consultation response still needs passage assessment. Other countries and publishers are not automatically recognised. This broadens discovery and some evidence coverage; it is not universal website verification.

## Limits and failures

- Maximum three Tavily searches, one Google request, four extracted URLs and four relevance assessments; at most six final evidence passages (one per extracted eligible page, plus at most one official forecast). A relevant Singapore temperature check may make one additional public forecast request, bounded to six seconds inside the existing 65-second deadline. Complete forecast coverage skips the paid retrieval providers for a pure temperature claim.
- Relevance assessment receives at most six overlapping windows of 1,800 characters from the first 60,000 characters of a page. It can still miss decisive context outside those windows.
- One 65-second retrieval deadline; existing assessment and app deadlines are retained. Already validated evidence survives a later retrieval timeout with a warning.
- Failures to extract eligible evidence or validate relevance are reported as technical failures when no evidence survives. Failed optional lead extraction alone does not turn a successful empty search into an outage.
- A provider-reported inaccessible page is a coverage warning when another eligible page was successfully reviewed, including a valid irrelevant result. If no eligible page could be reviewed, retrieval remains a technical failure. Provider outages, malformed responses and failed relevance checks are still errors when no evidence survives.
- Relevance does not require a source to repeat an alleged amount or date. An explanation of the same scheme can be retained as context with unresolved conditions; absence of the allegation does not prove it false. A named date without a year uses a visible current-year assumption from the Singapore submission date; it is not treated as a source fact.
- Missing context, wrong population and unresolved current/future applicability cannot drive a verdict. These semantic decisions still require evaluation; the prototype does not prove dates or scope infallibly.
- Exact duplicate passages/URLs are removed. Repeated pages from the same origin contribute at most once per stance. Conflicting pages from that origin remain represented.
- Government families are conservatively grouped. Independence across copied/reworded articles is not established; complete syndication/attribution tracing remains future work.
- Risk weights remain prototype heuristics, not calibrated truth probabilities.
- Semantic assessment uses medium reasoning for GPT-OSS and up to 4,096 output tokens to accommodate individual policy comparisons. The existing request deadlines and one bounded validation repair remain. This can increase latency and token usage; it does not add an extra assessment stage.
- A policy mismatch is decisive only when it applies to the claim's circumstances. Related published policy that leaves the allegation unresolved yields `unsupported`, with the existing neutral concern label and a clearly provisional score of 50 under evidence-v3. The score is a neutral starting point, not a 50% probability of falsehood. An assumed year is supplied separately to relevance and assessment. An existing rule cannot refute an assumed future change without evidence explicitly covering its period. Empty successful searches remain insufficient evidence with the same provisional score; technical outages remain errors and receive no score.
- URL checks reject malformed URLs, IP literals, credentials, nonstandard ports and obvious local hostnames. The backend never fetches arbitrary website URLs directly; extraction uses Tavily's fixed HTTPS API. These checks are not a claim of DNS/redirect validation inside Tavily.

## Passport entry discovery

- Entry-validity claims prioritise discovered pages labelled as immigration entry requirements above passport renewal pages or advice for travel overseas. The page title and final URL path segment determine this discovery rank; shared navigation paths do not. Source eligibility and diversity rules remain in force.
- The query planner is instructed to seek an actual announcement with the alleged timing and threshold, then the current entry rule and its exceptions without those disputed details. A narrow ICA/Singapore lookup supplies those queries directly. An explicit overseas journey, passport issuance/renewal topic or entry to another country does not use that lookup.
- No rule value, source URL, nationality or verdict is inserted by this helper. Candidates must still be discovered by providers, extracted, quoted and reviewed against the unchanged original claim. Ranking is not proof that a page applies to the user.
- Relevance selection explicitly retains current rules about the same obligation as context for an unresolved future change, including quoted exceptions. A context-only passage cannot be marked applicable to an assumed future period unless the passage covers that period: an `established` selection is reduced to `uncertain_time` when it does not. This safeguard does not promote irrelevant material or change the direct-evidence/official-denial path.
- This targets the observed gap where an ICA entry claim returned Singaporeans' outbound-travel advice. The [official ICA entry page](https://www.ica.gov.sg/enter-transit-depart/entering-singapore), checked on 16 September 2026, distinguishes its passport-validity requirement from the exception for Singapore passport holders. Its current rule alone does not settle a claimed future policy change.
- Mock-provider regression tests check current-rule discovery, retention of the future date and original claim, exact quotations, unchanged scope decisions, irrelevant-topic boundaries and the existing search/extraction limits. These tests do not measure live retrieval accuracy.

## Singapore temperature forecasts

- The fixed endpoint is `https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook`. The [official dataset description](https://data.gov.sg/datasets/d_f131f6e343bf8168e4057a04c4326a0a/view) identifies NEA/MSS, a four-day outlook and twice-daily updates. Its JSON identifies each day's `Degrees Celsius` range, the issue timestamp and update timestamp. The [MSS forecast page](https://www.weather.gov.sg/weather-forecast-4dayoutlook/) provides the corresponding human-readable outlook. Documentation and the live public response were checked on 17 September 2026.
- This adapter only accepts grounded location `Singapore`, measurement `air_temperature`, and a resolved date interval. Missing geography, another country, heat index, apparent temperature and surface temperature use the ordinary web path; they are not silently treated as Singapore air temperature.
- Validation rejects stale issues over 24 hours old, issue/update times after the submission clock, timestamps without time zones, wrong units, malformed or non-finite values, duplicate dates, inverted ranges and days outside the issue's four-day horizon. The 24-hour maximum is a conservative prototype freshness limit, not a provider guarantee.
- The evidence contains structured `forecast` fields and a canonical readable rendering of those API values, including actual issue time and each day's date and temperature range. This is an API-derived rendering, not a verbatim quotation from a web article. Forecast metadata and passage must agree before assessment uses them.
- Full requested-date coverage establishes the forecast's scope, not certainty about future weather. Partial overlap is retained as context with an explicit time limitation; missing, stale, unavailable or out-of-horizon data triggers bounded web fallback. An optional forecast failure alone does not turn an otherwise successful empty web search into a technical outage.
- The second weather query targets the actual location, date interval and measurement without repeating the disputed temperature. General query planning receives structured claim context and source coverage gaps. Neither route invents missing dates, geography or units, and neither expands the existing two-query fallback budget.
- A live operational check on 17 September 2026 returned HTTP 200 and a fresh issue from 16 September 17:07 SGT covering 17–20 September. This confirms the provider contract at that time; mocked regression tests cover malformed data, scope exclusions, partial horizons, fallback and request budgets. Forecast accuracy itself has not been evaluated by these checks.

## Evaluate

From `backend`, using the virtual environment:

```powershell
.\.venv\Scripts\python.exe -B scripts/evaluate_retrieval.py --split development --report ../evaluation/reports/my_development_run.json
.\.venv\Scripts\python.exe -B scripts/evaluate_retrieval.py --split regression --report ../evaluation/reports/my_regression_run.json
```

The runner shares actual claim analysis between the two modes, alternates their order, and writes results incrementally. It uses in-memory persistence, not Firestore or the user's allowance. Only run `--split holdout` after freezing development changes. Follow `evaluation/datasets/RETRIEVAL_REVIEW_GUIDE.md` for human adjudication and measurement limits.

## Date interpretation

- Before retrieval, the orchestrator records optional `date_context` for one unambiguous named date without a year, such as "From October" or "On October 1". The year comes from Singapore time at submission, even around the UTC New Year boundary.
- Relative phrases such as "tomorrow", "this weekend" and "next week" resolve to visible inclusive dates using the same submission clock. Explicit dates and supported ranges retain their stated year. Weekends mean Saturday–Sunday; an older forwarded message may refer to a different period, so the app offers a correction action.
- Original text and extracted claim are unchanged. A dated copy is used only for search. Relevance and assessment receive the original claim plus separate date metadata.
- Explicit years, relative years, recurring dates, invalid calendar dates and ambiguous multiple dates do not receive this default. Past months stay in the current year; they are not rolled forward.
- A missing year alone no longer forces a neutral verdict when context has been supplied. Applicable evidence may resolve an assumed date. Future dates still need evidence for that period; an existing schedule alone cannot disprove an unannounced change.
- The result, saved history and shared text show the interpretation. The app's **Change the year** or **Change the dates** button opens the original message for editing. Adding the intended dates and submitting creates a separate check under the normal allowance rules; it does not change the previous saved result.
- Old results without `date_context` are displayed as originally saved. Their assumed dates are not retrospectively recalculated.
