# Current-year assumption — 10 September 2026

## Behaviour

- A single named date without a year, such as **From October**, defaults to the current year in Singapore at submission.
- The result displays **Assumed date: October 2026**. This is stored separately from the unchanged submitted and extracted text, and included when sharing.
- Retrieval searches using the assumed year. Relevance and assessment receive the original claim plus separate date context.
- An explicit year takes precedence. Relative years, recurring dates, invalid dates and ambiguous multiple dates do not receive this default. Past months are not moved into next year.
- A missing year alone no longer forces a neutral result. Evidence applicable to the assumed date can support or contradict the claim.
- For an assumed future change, an existing policy alone cannot establish falsity. An explicit matching future period permits further semantic assessment; it does not independently establish the verdict.
- **Correct year** opens the original message in the text-check screen. Add the intended year and submit a new check. The previous saved result remains unchanged; normal allowance rules apply to the new completed check.

## Validation

- **461 backend tests passed**, with one existing Starlette/HTTPX deprecation warning.
- Android export passed (646 modules). Emulator visuals were not verified.
- Tests cover the Singapore New Year boundary, past months, explicit and relative years, invalid dates, future-policy safeguards, unchanged claim text, retrieval/assessment date metadata, saved history, idempotency, old records and a separate corrected-year submission.
- A live full API check of the CPF example completed in **51.54 seconds**, returned four sources, preserved the original claim, and stored October 2026 as the assumed date. The result remained **Not supported by policy checked**, because the retrieved existing rules did not establish the alleged future change.
- API tests used isolated in-memory storage and verified history, replay and allowance behaviour. No actual user allowance or Firestore documents were changed by the tests. Production serialization uses the existing shared persistence path.

Three additional live-model checks used synthetic permit passages:

| Claim and evidence | Final outcome |
| --- | --- |
| From January; an explicit applicable January 2026 rule states a different fee | Contradicted |
| From October; only an existing January 2026 schedule, with the October change unannounced | Not supported by policy checked |
| From October; an explicit October 2026 announcement states a different fee | Contradicted |

The first test pass exposed confusion between differing fee values and differing policy scope. The assessment prompt now explicitly distinguishes those, and the three targeted cases passed after that correction. These are development checks, not a general accuracy measurement. Search coverage and model interpretation remain fallible.

## Files and versions

- `shared/dates.py` and shared models: date detection and explicit metadata.
- Orchestration: one submission clock, unchanged source claim, saved assumption.
- Retrieval: dated discovery queries and separate relevance context (`retrieval-web-v6`, `relevance-v6`).
- Assessment: date-aware scope and future-change handling (`semantic-v5`).
- App: assumption card, shared-text disclosure and correction flow.

Diagnostic artifacts are under `C:\Dev\assessment-review\year-assumption-2026-09-10`.
