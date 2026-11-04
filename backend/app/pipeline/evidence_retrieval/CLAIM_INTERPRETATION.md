# Claim interpretation and source selection

## Undated statistics update: retrieval-web-v23-latest

Undated claims of a statistical change are interpreted as recent. Search queries
request the latest official figures; assessment uses comparable observation
periods and discloses the dates it selected. Stated dates and historical intervals
take precedence. The default does not change a population, confuse counts with
rates, or establish a claimed cause. See the [assessment period rules](../evidence_assessment/README.md#undated-statistical-comparisons).

The revision notes below describe earlier implementations.

Implemented in the experimental Jev worktree, 29 September 2026.
Retrieval revision: `retrieval-web-v12`. Forecast rule: `forecast-gap-v1`.

For the later `retrieval-web-v17` changes to hypothetical questions, Changi
assumptions and public-change inferences, see [Evidence labels](../../../../EVIDENCE_LABELS.md).

## Corporate ownership update: retrieval-web-v18

**Superseded for ambiguous wording by v19:** unqualified corporate `is controlled
by` now uses `ambiguous_control`, not the ownership default below. Explicit
ownership/voting or operational-management wording retains its specific path.
The quoted v18 live limitation is historical, not the current conditional result.

- `Singapore airline`, `Singapore Airlines` and `SIA` use the same reviewed
  company identity for discovery. The submitted claim stays unchanged. Industry
  and sector references are excluded from this alias correction.
- Unqualified `controlled by` is interpreted as ownership/voting control, including
  indirect ownership. The interpretation is shown in the saved assumptions and
  explanation. Explicit day-to-day management still uses the management path.
- Ownership searches start with the current SIA shareholder disclosure, then
  use the discovered shareholder names to look for missing parent-company links.
  The other follow-up slot checks the ultimate owner. This stays within the
  existing three-search/four-page budget.
- Regional copies of SIA's English investor page share a deduplication identity;
  the original URL is still used to fetch the page. Complementary publishers get
  priority after the first ownership page. Related companies retain their shared
  scoring origin, so this does not manufacture independent corroboration.
- Ownership passage selection prioritises ultimate owners and direct/deemed
  interests. Nationality requirements, special-share veto rights, and one direct
  holding are not sufficient by themselves to establish general control.

The 1 November live check of `Singapore airline is controlled by Singapore
government` originally returned no evidence because SIA's pages were ineligible.
After these changes it retrieves relevant shareholding and Temasek information,
but the final rerun still returned insufficient evidence: current ownership-chain
coverage and combined-source reasoning remain incomplete. This is a documented
remaining limitation, not a validated true/false result. No saved assessments
were rewritten and live checks used in-memory persistence.

## Separate meanings: retrieval-web-v19 / control-meanings-v1

- Preserve the ambiguous claim and state both interpretations in its assumptions.
- Retrieve management/governance and ownership information in the existing
  bounded search budget. For SIA, the reviewed Temasek governance/history page
  and SIA shareholder page are discovery entry points, never stored truth labels.
- A single bounded Ollama reasoning call assesses operations and ownership
  separately. Each directional finding requires exact source quotations,
  matching scope and applicable timing. Invalid or absent quotations, provider
  failure and incomplete scope leave that interpretation unresolved.
- The original ambiguous claim stays numerically unrated. Its sources remain
  contextual at whole-claim level; the two findings are not opposing votes about
  the same proposition. `control_interpretations` survives API/history/replay.
- When operations is contradicted, the public label is **Likely misinformation
  — if referring to day-to-day management**. Ownership may independently be
  supported, contradicted, or unresolved. Otherwise the headline is **The meaning
  of control matters**. Both sections are visible above the expandable explanation.
- On 1 November 2026, the live SIA example returned the conditional management
  label with a literal operational-independence quotation. Ownership remained
  unresolved. The live check used in-memory persistence, not Firestore writes.

Restart the backend and reload Expo to use the change. Recheck the message;
previously saved results are not rewritten. No new keys or packages are required.

## Singapore topic and jurisdiction retrieval: retrieval-web-v20 (3 November 2026)

- Add a separate jurisdiction and discovery topic to the saved claim context.
  Domestic policy/employment claims default to Singapore only when no explicit
  foreign location or authority blocks the assumption. The assumption is shown
  through the existing interpretation UI; the submitted claim stays unchanged.
- Reject housing descriptions such as "private property" as locations. Preserve
  a stated year such as "from 2027" without requiring a January reference in
  evidence that explicitly covers that year.
- Route policing to SPF/MHA/Statutes Online, healthcare subsidies to MOH/CHAS,
  employment to MOM/MOE/SingStat, and pension/tax topics to their agencies.
  Queries look for the alleged announcement and the neutral underlying rule.
- Check jurisdiction at discovery, extraction and passage selection. Publisher
  reputation alone is insufficient; an Australian or US rule is not evidence
  about Singapore. Comparative reporting is inspected at passage level.
- Prefer current, population-matching sources. Combined graduate surveys take
  priority over single-institution PDFs for an unqualified graduate claim.
  Unemployment, employment and full-time employment remain distinct measures.
- Permit one recovery query for a remaining scoped coverage gap. The normal
  budget remains three web searches/four semantic reviews. Recovery allows up
  to four searches, six reviews and eight extracted URLs, within the existing
  65-second retrieval deadline. Google Fact Check is a separate single request.
- Record rejected jurisdictions and unresolved gaps in the retrieval trace.
  Provider errors and unavailable pages remain visible; they are not evidence
  that an allegation is false.
- Extend the existing limited public-change inference to eligible near-term
  policing/subsidy allegations. It still needs a grounded baseline, successful
  notice searches and the existing evidence safeguards. The model selects
  sentence IDs; the backend copies the exact baseline quote. This prevents a
  paraphrased or shortened quotation from being accepted or losing a valid result.

CHAS is a scoped first-party healthcare source. Its identity is documented by
the [HealthHub CHAS description](https://www.healthhub.sg/support-and-tools/costs-and-financing/chas)
and [official eligibility page](https://www.chas.sg/Applying-for-CHAS/Eligibility).
That source registration is not a stored verdict about any claim.

Setup: install the updated `backend/requirements.txt` (adds Babel country-name
data), then restart the backend. No new API key or `.env` setting is required.
Existing saved results are not rescored. Live diagnostics and review instructions
are in [evaluation/retrieval_scope](../../../../evaluation/retrieval_scope/README.md).

## What changed

- Distinguish management, ownership and funding without rewriting the submitted claim.
- Explain that “run by” is interpreted as day-to-day management in the saved claim assumptions.
- Use relationship-focused discovery queries. Reserve extraction capacity for sources found after query expansion.
- Prefer relevant governance passages over ownership/funding articles for management claims. Publisher diversity operates within relevance tiers, after source eligibility.
- Preserve the discovered fetch URL; use normalised identities only for deduplication.
- Search up to 650,000 characters of corporate documents locally, instead of only their first 60,000. The model still receives at most six windows of 1,800 characters.
- Put the selected passage before additional page text in the pool assessor so truncation cannot discard it.
- Ask the assessor to judge the precise relationship. The existence of a board alone is insufficient; a passage assigning actual business decisions is more informative. The decisiveness thresholds are unchanged.

## Scoped first-party sources

This is a small reviewed registry, not automatic trust for every company website.
First-party statements still need extracted text, literal quotations, relevance and scope checks. They are not independent proof of all claims about a company.

| Publisher | Eligible topics | Review reference |
| --- | --- | --- |
| Temasek | Corporate relationships involving Temasek or Singapore Airlines | [Corporate governance](https://www.temasek.com.sg/en/about-us/corporate-governance) |
| Singapore Airlines | Its own ownership, funding and management | [Governance](https://www.singaporeair.com/en_UK/sg/about-us/sustainability/governance/) |
| Changi Airport Group | Changi airport operations and advisories; main website only | [Airport operations and management](https://www.changiairport.com/en/corporate.html) |

Temasek and Singapore Airlines share an origin group to avoid a corroboration bonus from related entities. Changi uses its own origin group. A general portfolio policy is contextual unless the retrieved text establishes its applicability to the named company. Unreviewed identities remain leads; adding other organisations requires an explicit registry review.

## Weather interpretation

| Input | Behaviour |
| --- | --- |
| “Singapore will reach 50 C this Saturday.” | Compare a definite prediction with the matching issued forecast. |
| “Could Singapore reach 50 C tomorrow?” | Preserve the question and possibility wording; explain forecast compatibility. Do not score it as a definite prediction. |
| “What if Singapore reaches 50 C tomorrow?” | Treat a simple imagined scenario as non-checkable, without a misinformation score. Mixed messages still go through claim extraction. |
| “MSS forecasts 50 C tomorrow.” | Verify the specific attribution to the forecast provider. |
| “This Saturday it will be 50 degree celcius.” | Recognise the temperature and spelling variant, but request the missing city/country. No silent Singapore assumption. |

“This/next/last Saturday” use the corresponding Monday-to-Sunday submission week in Singapore time. The resolved date is displayed and can be corrected. Multiple date expressions remain unresolved.

## Forecast risk scoring

Only a simple, positive, definite prediction can use this comparison. It requires:

- An official structured forecast issued within 24 hours before submission.
- Full coverage of the stated date range and the same location.
- The same measurement; air temperature is not heat index or surface temperature.
- One exact temperature, converting Fahrenheit when necessary.
- Direct, applicable source provenance.

The gap is the distance outside the forecast range, in Celsius. Inside the range, or less than 2 C outside, does not produce a decisive contradiction. At 2 C the evidence weight is 0.60; it rises linearly to 0.90 at 10 C and is capped there. Source quality can lower that weight. The existing evidence-score formula then produces the indicator (normally 80–95 for one qualifying official source).

These are explicit prototype policy thresholds, not estimated forecast errors or calibrated probabilities. They need a labelled evaluation before production use. A matching prediction is not automatically verified as a future fact.

New results retain the existing `contradicted` assessment outcome together with `forecast_context.risk_basis=forecast_comparison`, the scoring rule and deviation. The app and history label this as **“Conflicts with current forecast”**, rather than implying future impossibility. Existing saved results are not rescored.

Questions, negative statements, hypothetical scenarios, compound claims, stale data, missing dates, dates outside coverage, and different measurements do not gain this forecast-conflict score. An unverified future policy change still cannot be disproved by an unchanged current policy.

## Verification

- Backend regression tests cover URL preservation, source scope and lookalikes, governance selection beyond 60k characters, management/ownership/funding, question intent, weekday dates, temperature spelling, scoring gaps, negation, units, stale/mismatched data, and API/history persistence.
- Mobile tests cover the forecast headline, history badge and score explanation.
- Live checks use in-memory storage, without Firebase writes or app allowance consumption. Search and model results can vary; these examples are not an accuracy benchmark.
- The checked official snapshot did not cover Saturday, 3 October. A claim for tomorrow used a 25–33 C range. Coverage must be checked afresh on every submission.

Run offline checks from `backend` with `PYTHON_DOTENV_DISABLED=1` and `python -B -m pytest tests -q`; run `node --test tests/*.test.mjs` from `mobile`. Remove the dotenv-disable variable before live testing.

### Observed checks on 29 September 2026

816 backend tests and 27 mobile presentation tests passed. API/history checks use in-memory account storage; they do not test an actual Firebase deployment or the emulator UI.

| Live input | Observed result |
| --- | --- |
| SIA is ran by Singapore Government | Contradicted under the displayed operational-management interpretation; risk 93. |
| Tomorrow it will be 50 degree celcius in Singapore. | Forecast conflict; risk 95, against 25–33 C for 30 September. |
| Could Singapore reach 50 degrees Celsius tomorrow? | Forecast does not support that temperature; provisional 50, preserving the possibility question. |
| What if Singapore reaches 50 degrees Celsius tomorrow? | Hypothetical, non-checkable; no misinformation score. |
| This Saturday it will be 50 degree celcius in Singapore. | Unresolved because 3 October was outside the available snapshot. |
| Singapore Airlines is majority owned by Temasek Holdings. | Still unresolved (50): the selected passage concerned a voting commitment rather than current ownership. This remains a retrieval/evaluation case; it was not labelled false. |

The source registry is intentionally small, corporate-document scans are bounded, and relevance and verdict models can still select incomplete passages. Do not interpret these regression examples or scores as measured detection accuracy.
