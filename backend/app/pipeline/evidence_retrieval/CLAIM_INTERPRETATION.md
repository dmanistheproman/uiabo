# Claim interpretation and source selection

Implemented in the experimental Jev worktree, 29 September 2026.
Retrieval revision: `retrieval-web-v12`. Forecast rule: `forecast-gap-v1`.

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

The two publishers share an origin group to avoid a corroboration bonus from related entities. A general portfolio policy is contextual unless the retrieved text establishes its applicability to the named company. Unreviewed identities remain leads; adding other organisations requires an explicit registry review.

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
