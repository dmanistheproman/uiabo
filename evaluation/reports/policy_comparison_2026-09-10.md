# Policy comparison and retrieval gap check — 10 September 2026

## What changed

- Search for the underlying policy as well as the alleged rule. The second expanded web query may omit disputed amounts, ages or dates, without introducing numbers.
- Retain improved search rankings when the same page is found again.
- Reserve passage shortlist space for payment rules, including annual-premium wording when the claim alleges monthly deductions. All returned passages and quotes remain exact source spans.
- Separate topical relevance from whether the alleged rule is established. Use medium GPT-OSS reasoning for relevance and assessment.
- Compare amount, payment frequency, affected people, start date and other relevant policy details. The backend validates claim spans, source IDs and literal quotes.
- Display the assessment outcome and comparisons in the app. Preserve them through the existing saved-result serializer and history APIs. Old saved results remain readable.

## Result meanings

| Outcome | Meaning |
| --- | --- |
| Supported | Applicable evidence establishes the claim. |
| Contradicted | Applicable evidence establishes an incompatible fact. |
| Not supported by policy checked | Related published policy does not establish the allegation. This is not proof that an unconfirmed change is false. |
| Conflicting | Evidence supports both sides; both remain visible. |
| Insufficient evidence | Useful evidence was not established. |
| Not checkable | No checkable factual claim was identified. |

Unsupported results retain the neutral concern label and a null risk score. Provider outages remain technical errors. An unspecified start month does not establish a year. Missing traveller eligibility also prevents a personal entry-rule comparison from being treated as applicable.

## Retrieval gap found

The CPF booklet already contained annual-premium and yearly-deduction information. Earlier window ranking omitted that section in favour of passages sharing the claim's numbers. A later search also ranked the relevant premium page more highly, but the candidate pool retained its earlier lower rank.

Fixing those two issues exposed better passages, but live checks still showed the relevance model rejecting same-scheme policy because the exact allegation was absent. A shorter retrieval prompt and medium reasoning produced useful payment-rule selection in the final test. This is evidence of improvement on this example, not a measured general accuracy gain.

## Validation

- **435 backend tests passed**, with one existing Starlette/HTTPX deprecation warning.
- Android JavaScript export completed successfully. The ADB device query did not complete, so emulator visuals were not verified. The backend and Expo development server were restarted and their health/status endpoints checked.
- Full API smoke tests used the real cloud pipeline with isolated in-memory storage. History and idempotent replay preserved each result, and each completed check charged the isolated allowance once. No real account allowance or Firestore documents were changed by these checks.
- The production Firestore path already serializes model fields. The new optional fields use that path; a live Firestore write was not part of validation.

| Final full API check | Outcome | Time | Sources |
| --- | --- | --- | --- |
| CPF compulsory $300 monthly deduction, from an unspecified October | Not supported by policy checked; compares annual premium/yearly deduction with the allegation | 43.93 s | 2 |
| Canberra is the capital of Australia | Supported | 22.49 s | 2 |
| Chocolate ice cream tastes better than vanilla | Not a checkable factual claim | 6.60 s | 0 |

Four additional live-model tests used clearly synthetic permit passages: applicable fee contradiction, no fee evidence, an unconfirmed future change compared with an old schedule, and an embedded instruction pretending to state a fee. All four returned the expected outcome. These are development checks, not a labelled evaluation dataset or held-out accuracy measurement.

## Limits

- Earlier runs still produced only generic context. Search results, source availability and model interpretation can vary; the final example does not guarantee every future run will select the same passage.
- Four extracted URLs and six source windows per page remain the limits. Relevant context can still be missed, and a selected window can end mid-table or qualification.
- Medium reasoning and a larger assessment response budget can increase latency and token use. Existing timeouts still apply.
- Source scope decisions remain fallible. Literal-quote checks establish where text came from, not whether the interpretation is correct.
- There are no CPF-specific verdicts, fixed policy amounts or additional publisher exceptions in this change.

Local diagnostic artifacts, including earlier inconclusive runs and the final results, are under `C:\Dev\assessment-review\policy-comparison-2026-09-10`. Credentials are not included in this report.
