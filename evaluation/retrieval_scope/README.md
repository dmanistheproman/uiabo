# Singapore retrieval checks

This set reproduces three recent messages that returned **Not enough evidence**.
It checks claim interpretation, source discovery and assessment together. It is
a diagnostic set, not an accuracy benchmark or a list of required verdicts.

## What should work

- Domestic policy claims with no country use Singapore, with a visible assumption.
- An explicitly named country takes priority. General facts and locationless
  weather claims do not silently receive the domestic-policy default.
- Private property is an eligibility condition, not a city or country.
- A stated year such as 2027 survives interpretation and evidence selection.
- Searches prioritise the responsible agencies and reject evidence about a
  different jurisdiction. International reporting about Singapore is still usable.
- Graduate unemployment stays distinct from full-time employment and general
  unemployment. Foreign-worker minimum salaries are not actual pay comparisons.
- Missing coverage triggers at most one additional targeted search. A failure
  to find evidence does not automatically produce a false label.

## Run offline tests

From `C:\Dev\uiabo-vision\backend`:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q tests/pipeline/evidence_retrieval/test_jurisdiction_retrieval.py tests/pipeline/evidence_assessment/test_public_changes.py
```

The wider backend suite also checks API/history persistence, provider failures,
date handling and the existing forecast, corporate and component paths.

## Run the live checks

From `C:\Dev\uiabo-vision`:

```powershell
.\backend\.venv\Scripts\python.exe -B evaluation\retrieval_scope\run_live.py --live --output C:\Dev\assessment-review\retrieval-scope-live.json
```

Add `--case policing`, `--case subsidies` or `--case graduates` to run one case.

- Uses the existing ignored root `.env` and consumes search/model provider quota.
- Sends only the three public test messages. Does not write to Firestore or use
  an app account's allowance.
- Mirrors the orchestrator's date/context attachment before retrieval. It starts
  with prepared English text, so it does not test language detection or the UI.
- Saves selected passages, scope decisions, coverage gaps and the final result.
  Full extracted pages and credentials are excluded from the output.
- Use a new output filename to keep a previous run. Search results and model
  decisions can change between runs.

## How to review the result

1. Check `claim.claim_context`: country, basis, topic and assumptions.
2. Check `claim.date_context`: stated or assumed dates.
3. Read `retrieval.evidence`: the exact quote must concern the right population,
   rule, period and measurement.
4. Read `retrieval.trace.decisions` and warnings: distinguish missing evidence,
   rejected sources, inaccessible pages and failed model responses.
5. Check the assessment against those passages. Do not pass a test simply
   because it gives the label expected by the reviewer.

For a near-term public policy allegation, the limited **Likely misinformation**
inference still requires an applicable current official baseline, completed
announcement searches, sufficient official-source coverage and no unresolved
material coverage failures or supporting announcement. It copies exact source sentences. A
current rule alone cannot conclusively disprove an unannounced future change.

The graduate claim also needs the comparison period, graduate population, actual
foreign/local salary comparison and evidence for the alleged causal connection.
General employment figures cannot fill those gaps.

## Observed run — 3 November 2026

The final guarded run used the configured live providers and took 21–28 seconds
per case. These are observed results, not guaranteed outputs or accuracy scores.

| Case | Latest outcome | What the check established or still lacked |
| --- | --- | --- |
| Private-property households lose all subsidies from 2027 | Likely misinformation | MOH/CHAS material and completed announcement searches supported a limited inference. No numerical probability was assigned. |
| Police fine criticism once a post exceeds 10,000 views | Not enough evidence | Current-law excerpts did not establish the alleged view-count rule; an official page was also unreadable. An exception in one statute was prevented from becoming a conclusive denial of all possible fines. |
| Graduate unemployment doubled because foreigners earn half the salary | Not enough evidence | Singapore employment/work-pass sources were retrieved, but the actual pay comparison and the complete causal allegation remained unsupported. |

Earlier runs of the same messages produced different passage selections and
labels. The fixes improve source relevance and prevent known scope mistakes;
they do not establish stable classification accuracy. In particular, the two
remaining unresolved cases still need better applicable evidence. A missing
search result must not be substituted for that evidence.

Local full output: `C:\Dev\assessment-review\retrieval-scope-final-guarded-v20-20261103.json`.
Full backend regression result: **1,411 passed, 3 skipped**. Local log:
`C:\Dev\assessment-review\retrieval-scope-tests-guarded-20261103.log`.

## Follow-up retrieval and numerical checks (v21)

- Failed SSO PDF-view links can use the same document's HTML view. Old MHA article
  routes can use the corresponding current route. The replacement must be read
  and reviewed; scheduling it does not clear the failure.
- `retrieval.trace.coverage_issues` records each warning, whether it blocks a
  limited inference, and any reviewed replacement. Unknown warnings and failed
  searches still block the inference. The original warning remains visible.
- At most two PDF/statistical pages use advanced extraction, within the existing
  extraction and 65-second retrieval budgets. Short statistical documents retain
  their headings and chart labels alongside the selected passage.
- Numerical parts of compound claims use a structured model response and checked
  source labels. Decimal arithmetic determines the ratio/change. Missing dates,
  incompatible populations, rate/count confusion and ungrounded figures cannot
  vote. No missing period is silently filled with a convenient comparison.
- Rejected findings expose `reason_codes` and `scope_status`. An insufficient
  confidence value no longer displays a false claim that the scope is wrong.
- Salary minima cannot establish actual foreign/local pay. A statistic rejected
  for the event cannot bypass the checks by being used to reject its cause;
  an alternative explanation does not disprove the alleged explanation.

### What the live checks showed

| Check | Observed result | Remaining limitation |
| --- | --- | --- |
| Police/view-count message | Likely misinformation in the guarded run | Limited inference from official baseline and completed searches, not proof about all laws or future announcements. The failed MHA URL was recovered. |
| Original graduate message | Not enough evidence | Missing comparison dates/measurement and actual pay evidence. Some chart labels could not be bound reliably to figures. |
| Same graduate statistic with dates and paraphrases | Still unresolved in the final frozen-source replay | Adding dates alone does not fix ambiguous PDF chart extraction or supply the alleged salary/causal evidence. |
| Subsidies regression | One likely-misinformation run, one unresolved run | A semantic-selection failure correctly blocked the second run. This is not stable end-to-end accuracy. |
| Synthetic 100 to 200 control, live reasoning provider | Supports the doubling component | The invented control data tests reasoning only; it is not real Singapore data. |
| Synthetic 100 to 130 control, live reasoning provider | Contradicts the doubling component | The unproved cause remains unresolved in both controls. |

Local diagnostic artifacts:

- `C:\Dev\assessment-review\retrieval-numeric-guarded-v21-20261103.json`
- `C:\Dev\assessment-review\retrieval-graduate-final-v21-20261103.json`
- `C:\Dev\assessment-review\numeric-replay-v21-20261103.json`
- `C:\Dev\assessment-review\numeric-provider-controls-v21-20261103.json`

These checks do not write Firestore results or consume app allowances. A live
model's chart interpretation and search coverage can still vary. Do not mark the
project's evaluation claims correct merely because a desired label appears.

Verification: the full backend run passed **1,445 tests**, with **3 skipped**.
After the final integer-count rounding guard, **87 targeted tests** passed.
All **78 mobile tests** passed. Backend health was checked on port **8002** and
Expo was reloaded on **8082**. Full-suite log:
`C:\Dev\assessment-review\retrieval-numeric-final-tests-v21-20261103.log`.
