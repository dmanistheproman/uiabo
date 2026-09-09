# Broader retrieval prototype

## Enable or roll back

Set `EVIDENCE_RETRIEVAL_MODE=web` in the ignored repository-root `.env` and restart the backend. `catalogue` selects the previous retrieval path and is the default when the setting is absent. The template defaults to `catalogue` until evaluation/review is complete.

The web mode uses the existing Google Fact Check, Tavily and Ollama keys, all on the server. No new provider, local model download or mobile API key is needed. Its pipeline version includes `retrieval-web-v3`.

## Flow

1. Search Google Fact Check and the preferred Tavily domains concurrently.
2. Extract up to two eligible original pages. Search snippets and Google's repeated claims are discovery metadata, never final evidence.
3. Select a relevant passage and assess its scope using Ollama. The model selects numbered source sentences and the backend copies exact original text, including formatting. Word overlap ranks a bounded set of windows but does not determine acceptance.
4. If fewer than two origin groups provide direct, applicable evidence, generate up to two alternative queries and search the wider web. If query planning fails, still try the original query broadly.
5. Extract remaining candidates within a four-URL budget. An unfamiliar page can supply a literal link to an eligible original, which must itself be extracted. Major social platforms are not extracted.
6. Send accepted passages to the existing semantic stance assessor. Context-only, inapplicable or temporally unresolved evidence is forced neutral during aggregation, even if stance assessment says supporting.
7. Return the result through the existing API and save optional evidence provenance through the normal Firestore repository. Existing app screens already display the assessment explanation and quote. Old records without provenance remain readable.

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

- Maximum three Tavily searches, one Google request, four extracted URLs and four relevance assessments; at most six final evidence passages (currently at most one per extracted eligible page).
- Relevance assessment receives at most six overlapping windows of 1,800 characters from the first 60,000 characters of a page. It can still miss decisive context outside those windows.
- One 65-second retrieval deadline; existing assessment and app deadlines are retained. Already validated evidence survives a later retrieval timeout with a warning.
- Failures to extract eligible evidence or validate relevance are reported as technical failures when no evidence survives. Failed optional lead extraction alone does not turn a successful empty search into an outage.
- Missing context, wrong population and unresolved current/future applicability cannot drive a verdict. These semantic decisions still require evaluation; the prototype does not prove dates or scope infallibly.
- Exact duplicate passages/URLs are removed. Repeated pages from the same origin contribute at most once per stance. Conflicting pages from that origin remain represented.
- Government families are conservatively grouped. Independence across copied/reworded articles is not established; complete syndication/attribution tracing remains future work.
- Risk weights remain prototype heuristics, not calibrated truth probabilities.
- URL checks reject malformed URLs, IP literals, credentials, nonstandard ports and obvious local hostnames. The backend never fetches arbitrary website URLs directly; extraction uses Tavily's fixed HTTPS API. These checks are not a claim of DNS/redirect validation inside Tavily.

## Evaluate

From `backend`, using the virtual environment:

```powershell
.\.venv\Scripts\python.exe -B scripts/evaluate_retrieval.py --split development --report ../evaluation/reports/my_development_run.json
.\.venv\Scripts\python.exe -B scripts/evaluate_retrieval.py --split regression --report ../evaluation/reports/my_regression_run.json
```

The runner shares actual claim analysis between the two modes, alternates their order, and writes results incrementally. It uses in-memory persistence, not Firestore or the user's allowance. Only run `--split holdout` after freezing development changes. Follow `evaluation/datasets/RETRIEVAL_REVIEW_GUIDE.md` for human adjudication and measurement limits.
