# Future policy assessment verification — 16 September 2026

## Implemented behaviour

- Passport and immigration claims now enter policy assessment.
- The result separates published-policy/related-guidance findings from the
  verification status of the alleged change.
- The summary preserves a literal official quotation and its scope limitations.
  General advice to departing travellers is not presented as an established
  entry rule for all travellers. Model paraphrases can still misinterpret scope;
  the quoted source remains visible for review.
- Current rules and an unverified future change remain unscored. A scoped,
  quoted official denial can establish contradiction without repeating the exact
  month/year. This requires retrieval and assessment agreement, a denial signal
  in the quote, and no known publication from an earlier year.
- Ordinary rules, missing announcements, no comment, unrelated denials and
  uncertain scope cannot use the exception. Literal quotations do not by
  themselves guarantee correct semantic interpretation.
- `policy_context` survives API submission, account history and idempotent replay.
  Older saved results remain unchanged.

## Automated checks

- Backend: **576 tests passed**. One pre-existing Starlette/httpx deprecation warning.
- App presentation logic: **7 tests passed**.
- Android Metro export passed with `--no-bytecode`. This verifies bundling;
  it is not an Android release build or an emulator interaction test.

Coverage includes future denials, source/date restrictions, future announcements,
conflicting announcements, unverified current rules, quoted comparison scope,
sentence-repair handling and account-result storage.

## Live checks

Original claim: “ICA will begin rejecting passports with less than one year of
validity from November”. The pipeline assumed November 2026.

- Live Google/Tavily retrieval and Ollama assessment completed twice, in 54.9 and
  32.5 seconds. Both returned **unsupported**, with **no numeric score**, from
  three retrieved evidence items.
- The retrieved pages largely concerned Singaporeans travelling overseas rather
  than a confirmed new inbound passport-rejection rule. Their limits must remain
  visible; these checks do not establish that the alleged change is false.
- The final formatter was also checked against the retained live evidence and
  is covered by deterministic regressions. It labels unestablished scope as
  related guidance and quotes the source rather than promoting a paraphrase into
  an applicable rule.
- Runtime versions: `semantic-v6`, `relevance-v7`, `retrieval-web-v7`.

Separate live-model checks used **synthetic passages**, not real announcements:

| Controlled input | Result |
|---|---|
| Explicit official denial of the same future change, without month/year wording | Contradicted; indicator 97 |
| Existing six-month rule | Unsupported; no score |
| Denial of an unrelated visa-fee change | Insufficient evidence; no score |

These controlled checks test model/aggregation behaviour, not the real-world
truth of an ICA announcement or calibrated detection accuracy. Live checks used
in-memory result storage and did not consume an account's app allowance or alter
its saved results.
