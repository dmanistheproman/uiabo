# How to label the claims

## Before reviewing

- Open your own workbook. Fill your name in **B3** on the tab you are reviewing.
- Read the exact claim, including dates, place, quantity, words such as “all”, and whether it is a question.
- Research it yourself. Do not read the other reviewer's answers or either pipeline's outputs.
- [Source starters](SOURCE_STARTERS.md) provides official pages for some topics; verify the exact applicable evidence yourself.
- Use the yellow cells for the label, reason, evidence/search record and review date.
- Enter review dates as text in `YYYY-MM-DD` format. Do not reorder rows or edit the supplied claims or fingerprint.

## Labels

| Label | Use when |
| --- | --- |
| `supported` | Reliable evidence supports the precise factual proposition, including its conditions and date. |
| `contradicted` | Reliable evidence contradicts a material part of the proposition. Record the specific contradiction. |
| `unresolved` | Evidence cannot settle it, important context is missing, sources conflict, or it is an uncertain future event. Explain which applies. |
| `not_checkable` | The message expresses an opinion, an uncorroborated private experience or a purely imagined situation rather than a verifiable factual proposition. |
| `forecast_conflict` | A definite prediction conflicts with a relevant, fresh official forecast. This is a comparison with the forecast, not proof that the future event cannot happen. |

### Cases that need care

- **No search result does not automatically mean false.** Use `contradicted` only when there is an actual contradiction. A current rule may contradict an alleged current rule; silence about a future change may remain unresolved.
- **Questions can contain factual propositions.** Evaluate the proposition the user asks about. “Is Mercury closest to the Sun?” asks about a checkable fact. Do not label every question `not_checkable`.
- **Ownership and management are different relationships.** Evidence that someone owns shares does not, by itself, settle who makes operational decisions.
- **Hypotheticals and definite forecasts differ.** “What if…” imagines a situation. “Could…” asks about possibility. A definite temperature prediction can conflict with a forecast without establishing physical impossibility.
- **Missing details:** do not invent a place, person, policy, amount or company to obtain a verdict.
- **No stated year:** for the regression messages, use the comparison's recorded assessment date and note the inferred year. Do not assume an unspecified “October” necessarily means a past or future year different from that date.
- **Dated claims:** several final inputs explicitly say 29 September 2026. Use evidence applicable to that date, even if you label later.
- **Compound statements:** identify which factual part determines the label. Do not treat one correct fragment as proof of the whole message.

## What to record

- **Reason:** one or two sentences explaining the exact support, contradiction or missing context.
- **Sources:** the page URL, relevant passage or section, and publication/update date if available. Use primary sources where possible.
- **Unresolved:** record what you searched, when, and which source pages you checked. Write `Search record: ...` if there is no decisive source.
- **Not checkable:** explain why. A source link is optional for a subjective or private statement.
- **Weather:** use the same saved official snapshot and assessment timestamp for both reviews. Record issue time, location, dates, temperature bounds and whether the requested day is covered. An uncovered date stays unresolved.

Keep copies of the decisive passages or screenshots in a local evidence folder, with the case ID in the filename. A URL alone may change later.

## Agreeing on the answer

- Export both initial reviews with `collect_reviews.py`; do not overwrite one review with the other.
- Fill **final_label**, **adjudicator**, **decision_reason**, **final_sources** and **reviewed_at** in the exported CSV.
- Review agreements too. Two identical guesses do not establish a correct answer.
- Discuss disagreements using evidence. A third teammate can adjudicate when needed.
- If a candidate is already familiar from previous testing or is badly worded, replace it before freezing the final set. Update the JSON and review sheets together and regenerate their fingerprints; do not silently drop a difficult case after seeing results.

## Reviewing model results afterwards

The result-review script creates a blinded bundle and an audit CSV. Keep its private branch key away from reviewers.

For each result, mark `yes`, `no` or `na` for:

- Did it understand the intended claim?
- Do the sources apply to the correct entity, date, location and conditions?
- Do the quotations support what the explanation says?
- Is the explanation understandable without technical knowledge?
- Does the risk wording fit the evidence? A score is not a calibrated probability.

Record any critical error in plain language. A correct label with fabricated evidence is still a failed explanation/citation audit.
