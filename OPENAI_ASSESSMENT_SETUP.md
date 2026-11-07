# OpenAI claim research experiment

**Branch:** `feature/openai-claim-assessment`

**Folder:** `C:\Dev\uiabo-openai`

This branch can send the original message to OpenAI to research and assess using web search. It is separate from `C:\Dev\uiabo-vision`.

## How the new mode works

1. UIABO checks the input length and language.
2. The backend sends the original message, the assessment date and the default Singapore context to OpenAI.
3. OpenAI searches for supporting and contradictory evidence, then writes cited evidence notes covering the original assertions, populations, periods, comparisons and limitations. This collection step does not choose the final verdict. Public-policy checks prioritise applicable official rules and announcements.
4. If citations cannot be matched to the recorded web sources, the backend can make one fresh research attempt within the remaining time and web-action budget. It researches the original message again; it does not reuse the rejected verdict or report.
5. One tool-free OpenAI assessment call explicitly decides each original assertion's scope, evidence applicability, status, reasoning basis and limitations, then chooses a consistent overall verdict. It also writes the plain-language explanations. It cannot search, invent sources or add facts from memory.
6. If those decisions fail validation, one bounded assessment review can correct the scope, finding status or overall verdict using the same evidence. It must retain the original assertions and their material flags. The backend validates all decisions and source references, then copies them directly into the existing app result. There is no later model formatter that can reclassify a finding.
7. The app shows a clear label, a short explanation, findings for each part of the message, limitations and clickable sources.

Text analysis in this mode bypasses the old claim extraction, JEV planning, Tavily retrieval and specialist adjustments. Other app features retain their own services. Authentication, allowances, history, incorrect-result reporting and Firestore storage keep their existing boundaries.

This uses the OpenAI API, rather than a ChatGPT conversation. Similar prompts can still produce different results. Native citation metadata establishes where the links came from; it does not independently prove every factual interpretation. Generated explanations are presented as summaries, not source quotations.

## Labels and limits

| Verdict | App label |
| --- | --- |
| true | Strong evidence this is true |
| likely_true | Evidence suggests this is true |
| mixed | Mixed evidence |
| likely_false | Likely misinformation |
| false | Strong evidence this is false |
| insufficient_evidence | Not enough evidence |
| not_checkable | Not a factual claim |

The first five labels describe the direction of the evidence. The last two are exceptions: lack of evidence and non-factual input do not become a middle score. This experimental mode does not invent a numerical credibility score.

- A relevant official baseline and a successful targeted search can justify a qualified **Likely misinformation** inference, with its limitations explained.
- No search hit alone does not establish that a claim is false. A failed search is a technical error, not evidence against a claim.
- A contradicted material assertion is not cancelled by an unresolved cause or another supported detail.
- **Mixed evidence** means conflicting evidence about the same material assertion.
- Initial research and citation recovery share a total limit of **12 web tool actions** (including searches, page opens and find-in-page actions). The initial request gets at most **10**, reserving at least two for citation recovery. Recovery receives the actual remaining allowance, so it may have more than two actions if the first attempt stopped early. Each request explicitly states its own numeric action limit, which the backend also checks.
- The action allowance is a ceiling. The model is instructed to stop when evidence adequately covers the claim, and to spend additional actions on specific gaps, applicable comparisons, primary sources and counterevidence for challenging claims. There is no automatic difficulty classifier or guaranteed number of actions per claim, and an insufficient-evidence label does not trigger an extra search by itself.
- All research and assessment calls still share one **180-second deadline**, with output limits of 6,000 per research response and 4,000 per assessment response. A normal check uses two logical model requests; citation recovery and assessment review can increase that to four. Temporary transport failures can retry a logical request at most twice, within the same deadline and available research budget. Citation recovery requires at least 20 seconds and one web action remaining. The connection allowance is 15 seconds and the HTTP read-inactivity timeout is 120 seconds; neither extends the shared deadline. Provider billing units may differ from action counts. More research can cost more or take longer without guaranteeing a decisive or more accurate label.
- There is no silent fallback to the old provider. Unfinished or invalid responses produce an error and do not consume an app check.
- Assessment review can correct either a finding or the overall verdict when the supplied evidence warrants it. It cannot add sources, fabricate a contradiction, or drop/demote an original material assertion to force validation. A result that remains inconsistent is still rejected.
- Mismatched or unknown evidence scope cannot support a decisive finding. A qualified inference needs explicit applicability reasoning and local limitations. A valid narrower counterexample can still contradict a genuinely universal claim; a different population or salary measure does not automatically contradict the actual allegation.
- Finding-specific limitations are retained in the public result's limitations, with a maximum of eight unique limitations. Detailed scope records guide validation; their relevant reasoning must also appear in the saved plain-language explanation. Internal scope objects are not separate public response fields.
- Citation comparison ignores only the exact known tracking pair `utm_source=openai`, while preserving the displayed URL. Article IDs, other query parameters, paths and domains still matter. Tracking aliases share one source ID. A citation recovery must corroborate its citations with its own search/open metadata; missing metadata cannot bypass this check.
- Failed citation parsing still records the search activity already performed. Ordinary diagnostics contain fingerprints and counts, not raw source URLs, private query values or provider response text.
- Backend validation diagnostics record the failed phase and safe constraint codes. They do not log the claim, provider response, credentials or raw exception payload.

## Recovery after startup or idle

The backend creates a fresh OpenAI HTTP client for each claim. A failure after idle does not by itself prove that an old connection or an unloaded model caused it. The connection allowance is now 15 seconds to accommodate slower fresh connections.

- Connection failures, eligible timeouts, HTTP 408/409/429 and temporary server errors receive up to two retries with increasing delays. Retry-After is honoured when present. Retries stop if the overall deadline, attempt limit or research budget prevents another attempt.
- Only the failed request is retried. If evidence collection succeeded and assessment failed, the retry assesses the same collected evidence without searching again.
- Authentication failures, invalid request settings, rejected schemas and exhausted credits or spending limits are not retried. Quota failures have a separate `OPENAI_QUOTA_EXCEEDED` code.
- When a lost research response may already have used search tools, its full grant is reserved against the 12-action budget. A later retry receives only the remaining allowance. Pre-connection failures and HTTP 429 responses do not consume that reservation. This conservative accounting can leave less search capacity after a service failure.
- Safe diagnostics record the phase, attempt, HTTP status, known error code, network exception category, request ID and timing. They are stored in `pipeline_runs.provider_diagnostics` and failed `analysis_results.provider_diagnostics`, and included in monitoring API responses. Claims, credentials and raw provider messages are excluded from these diagnostics.
- Retries do not create additional app submissions. Only a successfully saved result uses one check. Repeated provider requests can still incur API usage, particularly when the original response was lost; there is no assumption of provider-side deduplication.

Restart the backend after updating the code. The recovery applies to direct `openai_web` text checks and reviewed OCR text sent through that flow. No paid background warmup requests are made. Assessments and citation validation retain the same rules.

Validation on 7 November 2026: **2,202 backend tests passed, 3 skipped**. Coverage includes recovery after connection/service failures, retry limits and deadlines, search-budget reservations, secret-free diagnostics, authenticated text/OCR failure persistence, idempotency and single allowance deduction. A live check of “Singapore became an independent country on 9 August 1965” deliberately injected one connection failure before sending the first request. The retry then completed real research and assessment in **20.56 seconds**, returning “Strong evidence this is true.” This used in-memory results and no app allowance. It verifies recovery from the simulated interruption; it does not establish the cause of the earlier idle-related failures. The local diagnostic is in `C:\Dev\assessment-review\openai-recovery-20261107`.

## Configure the private backend environment

Edit `C:\Dev\uiabo-openai\.env`:

```dotenv
TEXT_ANALYSIS_MODE=openai_web
OPENAI_API_KEY=your_private_api_key
OPENAI_ASSESSMENT_MODEL=gpt-6.1-sol
OPENAI_REASONING_EFFORT=medium
```

The key already saved for this experiment is reused. Create a key at <https://platform.openai.com/api-keys> if setting up another computer.

- Keep the key in the root `.env`, which is ignored by Git. Never put it in `mobile/.env` or an `EXPO_PUBLIC_*` variable.
- Keep Firebase credentials and settings for the app's other features.
- This direct text mode does not require Ollama, Tavily or Google Fact Check API keys. Those services may still be needed by other configured features or the comparison mode below.
- Shell environment values take precedence over `.env`. Restart the backend after changing settings.
- OpenAI model access and available API credit depend on your account. Web search and model usage can both incur charges.

## Test one claim without using the app allowance

Run in PowerShell:

```powershell
cd C:\Dev\uiabo-openai\backend
& C:\Dev\uiabo-vision\backend\.venv\Scripts\python.exe -B scripts\check_openai_assessment.py --text "Singapore will begin giving new citizens priority over locally born Singaporeans for selected BTO flats from January 2027."
```

This uses the existing Python environment with the new folder's code and `.env`. It makes live API calls, but uses in-memory storage and disables monitoring writes. It does not save to Firestore or charge the app allowance. Its output reports the verdict, source links, elapsed time, completed OpenAI responses and token usage. A completed response does not by itself demonstrate factual accuracy.

## Start the separate backend

```powershell
cd C:\Dev\uiabo-openai\backend
& C:\Dev\uiabo-vision\backend\.venv\Scripts\python.exe -B -m uvicorn app.main:app --env-file ..\.env --host 0.0.0.0 --port 8003
```

The experiment uses **8003**; the original backend can remain on **8002**. Check <http://127.0.0.1:8003/health>.

For a separate Python environment, follow `TEAMMATE_SETUP.md` and install `backend/requirements.txt`. No additional OpenAI SDK dependency is required.

## Test through the emulator

The experiment's `mobile\.env` should contain:

```dotenv
EXPO_PUBLIC_API_URL=http://10.0.2.2:8003
```

```powershell
cd C:\Dev\uiabo-openai\mobile
npm ci
npx expo start --port 8083 --android
```

Reload the app after changing its environment. Open this Expo instance to see the new result layout. Existing saved results keep their original assessments; submit a new check to use the new mode. Normal app checks save to the configured Firebase project and apply the usual allowance rules.

If Expo Go stays on its loading spinner when opening the localhost address, open the emulator's direct host address:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" -s emulator-5554 shell am start -W -a android.intent.action.VIEW -d exp://10.0.2.2:8083 host.exp.exponent
```

This resolved loading on the local Pixel 7 emulator. The backend URL remains `http://10.0.2.2:8003`.

## Switch back to the evidence-only comparison

Set the following in the experiment's root `.env`, then restart its backend:

```dotenv
TEXT_ANALYSIS_MODE=pipeline
EVIDENCE_PIPELINE_V3=1
EVIDENCE_RETRIEVAL_MODE=web
EVIDENCE_VERIFICATION_ENABLED=true
EVIDENCE_VERIFICATION_PROVIDER=openai
```

This restores the previous experiment: existing extraction, assertion planning and retrieval select the evidence, and OpenAI replaces the joint verifier. Citation/scope checks and specialist adjustments remain. Some specialist adjustments still use Ollama, so the final result can combine providers. Existing provider keys are required for this mode.

To compare with the original verifier, use `EVIDENCE_VERIFICATION_PROVIDER=ollama` with `TEXT_ANALYSIS_MODE=pipeline`. Omitting `TEXT_ANALYSIS_MODE` defaults to `pipeline`; new research is an explicit opt-in.

## Evaluate before merging

- Use the team's reviewed claims, including correct claims, misinformation and genuine evidence gaps.
- Compare label agreement, wrong misinformation labels, citation relevance, material-assertion coverage, failures, latency and API cost.
- Keep some claims out of prompt development for a final independent evaluation.
- Compare direct research as a complete system: it chooses different evidence. It is not an isolated test of one model on identical passages.
- For an isolated verifier comparison, use the older `pipeline` mode with identical saved evidence and assessment dates.

## Git state

This worktree includes the original folder's tracked and untracked project changes, which remain **uncommitted**. Review and commit the intended work before sharing it. Pushing only a branch does not transfer uncommitted files. Never add `.env` or credentials.

## Validation on 3 November 2026

| Live input | Returned label | Time | Cited sources |
| --- | --- | --- | --- |
| New citizens getting priority over locally born Singaporeans for selected BTO flats from January 2027 | Likely misinformation | 36.18 seconds | 2 HDB pages |
| Singapore became an independent country on 9 August 1965 | Strong evidence this is true | 19.19 seconds | 3 official pages |

Both checks completed research and formatting calls. Neither wrote to Firestore nor used app allowance. These are smoke tests, not an accuracy benchmark. The BTO run used 31,579 input and 1,320 output tokens; the true control used 14,658 input and 682 output tokens. Web-search charges are additional. The first run preceded a search-counter fix and logged zero search calls incorrectly; its actual count was not retained. The control recorded one search action and one billable search request.

- Full backend suite: **1,972 passed, 3 skipped**; two existing deprecation warnings.
- Selected mobile research and legacy regression tests: **78 passed**; JSX parsing passed.
- Portal research and legacy tests: **14 passed**; rendered research and legacy markup checked.
- Ownership, quota/idempotency, reported-result provenance and crossing-midnight persistence are covered by backend tests.
- Subsequent setup check: backend `/health` returned 200, the Android bundle compiled, and the emulator loaded the home screen with the signed-in account and its allowance through port 8003. The new result layout still needs a live emulator walkthrough.
- The original project's Git-visible files remained unchanged against the pre-copy snapshot.

### Response-validation reliability follow-up

The retirement-age/CPF claim intermittently produced `OPENAI_RESEARCH_INVALID`. Its original rejected payload was not retained, so the exact failed rule could not be confirmed. A diagnostic retry succeeded. The backend now accepts harmless bold verdict headers and overlapping native citation spans, records safe validation-phase diagnostics, and allows one report-preserving formatting retry.

After the changes, the exact claim completed in **44.02 seconds**, returning **Likely misinformation** with four official source links. It used three search actions and two completed model responses; this run did not need the formatting retry. In-memory testing used no app allowance and made no Firestore writes. The full backend suite passed **1,993 tests**, with 3 skipped. Recovery tests cover preserving true and insufficient-evidence verdicts and stopping after the second invalid format attempt.

## Citation-reliability validation on 4 November 2026

The citation checker now tolerates the known `utm_source=openai` tracking suffix while preserving the displayed URL. Other query parameters, paths and article identifiers must still match a discovered source. A genuine citation mismatch can trigger one fresh research attempt within the existing shared deadline and web-action limit. Diagnostics record validation codes, counts and URL fingerprints rather than rejected reports or raw URLs.

| Check | Result |
| --- | --- |
| Original 20-claim run | 16 completed; 4 citation-validation failures |
| Initial targeted retest of those four | 3 completed; one recovery returned an unfinished search and was rejected |
| Full 20-claim retest after the fixes | 19 completed; 1 result-consistency failure |
| Identical-response parser comparison in the full retest | 4 responses rejected by the previous URL check were accepted by the corrected check; 16 passed both |
| Full backend automated suite | 2,079 passed; 3 skipped; 2 existing deprecation warnings |

All four originally failing claims completed in the full retest. The remaining failure was C11, the leaked-report allegation about graduate unemployment and foreign-worker salaries. Both formatting attempts combined an `insufficient_evidence` verdict with a contradicted material finding. The consistency check rejected that combination (`research_unresolved_cannot_erase_contradiction`). The rejected report was not retained, so the diagnostics do not establish whether the research conclusion or its formatted findings were at fault. Citation matching is not the cause of this remaining failure.

The full retest took 374 seconds with two concurrent workers; median claim time was 34.52 seconds. It returned 12 likely-false, 1 false and 6 insufficient-evidence results, plus the one technical failure. Live tests incurred OpenAI API usage, but made no Firestore writes and used no app allowance. The original results and pre-change files were preserved.

These are completion and reliability results, not an accuracy score: the sample file has no per-claim adjudicated labels or supporting references. Fresh research can change a result independently of this patch. The identical-response parser comparison isolates the URL-matching improvement; a single completed retest does not guarantee future requests will succeed.

The local report and detailed diagnostics are in `C:\Dev\assessment-review\openai-citation-fix-20261104` (`REPORT.html` and `REPORT.txt`). Restart the OpenAI backend to load the changes, then submit a new check; saved assessments retain their original results.

## Assessment-consistency follow-up on 4 November 2026

The C11 investigation reproduced a formatting-stage inconsistency using identical evidence: two formatter calls kept the salary allegation unresolved, while a third called it contradicted but retained the overall insufficient-evidence verdict. The new flow removes that second judgement. Evidence collection supplies cited notes, one structured assessment decides the findings and overall verdict, and Python copies the validated decisions into the app result. A bounded assessment review can correct an inconsistent decision using the same evidence; it does not force a particular label.

| Validation | Observed result |
| --- | --- |
| Same saved C11 evidence, three new assessments | 3/3 completed as insufficient evidence; all public decision fields exactly matched the validated assessments |
| True control: Singapore's independence on 9 August 1965 | Strong evidence this is true; 25.58 seconds |
| Full 20-claim run with the new decision flow | 17/20 completed; C11 completed with no assessment inconsistency |
| Remaining failures in that full run | C07 and C09 failed search-response validation; C16 failed citation provenance validation, all before assessment |
| Targeted retest after making the initial numeric search budget explicit | C07, C09 and C16 all completed; 3/3 likely misinformation |
| Final full backend suite | 2,140 passed; 3 skipped; 2 existing deprecation warnings |

The full 20-claim run preceded the numeric-budget instruction clarification. Its result remains **17/20**, not a later combined 20/20. The subsequent three-case run used the final code and a fresh set of research responses. A successful retry does not prove future requests cannot fail or that the instruction alone caused the improvement.

The full run returned four likely-false, one false and twelve insufficient-evidence assessments. Some labels changed from the earlier run and need review against the team's agreed definitions and adjudicated examples. These completion results are not a factual-accuracy benchmark. Median latency in this run was 68.63 seconds, compared with 34.52 seconds in the preceding citation-fix run; this is an observed cost of the tested flow and live conditions, not an isolated performance measurement. C11 took 121.57 seconds because it needed a citation-recovery search before assessment. The app's existing 240-second text-request timeout accommodates the backend's 180-second research/assessment deadline.

All evaluations used in-memory results with no Firestore writes or app-allowance deductions. Live model and search calls incur API usage. The original sample, earlier results and pre-change files were preserved. No environment settings or mobile screens changed.

The report, cases, C11 replay captures and implementation patch are in `C:\Dev\assessment-review\openai-consistency-fix-20261104` (`REPORT.html` and `REPORT.txt`). Restart the OpenAI backend on port 8003 before submitting new app checks. Existing saved assessments keep their original findings and labels.

## Expanded research allowance on 4 November 2026

The shared action ceiling increased from six to 12, with an initial grant of ten and at least two actions reserved for citation recovery. A recovery receives the actual remainder. This is available capacity rather than a requirement to spend every action, and it does not add an automatic second search for unresolved claims. The model, reasoning effort, assessment rules, four-response cap and 180-second deadline remain unchanged.

| Live check | Completed web actions | Result | Time |
| --- | --- | --- | --- |
| C07: foreign-student school-place quota | 4 | Likely misinformation | 71.47 seconds |
| C09: fines for widely viewed policy criticism | 5 | Likely misinformation | 80.08 seconds |
| C11: graduate unemployment and half-salary hiring | 4 | Not enough evidence | 97.30 seconds |
| C16: encrypted-message access requirement | 3 | Likely misinformation | 58.92 seconds |
| True control: Singapore independence date | 1 | Strong evidence this is true | 18.64 seconds |

All five checks completed. None used more than six actions, so this small run does not demonstrate that the larger ceiling improves accuracy or resolves a claim that the former ceiling could not. C11 still has unresolved scope and causal-evidence issues; extra available searches do not establish the missing comparison. Fresh research, sources and latency can vary between runs.

The final backend suite passed **2,146 tests**, with 3 skipped and two existing deprecation warnings. Tests cover the initial ten-action cap, total twelve-action cap, recovery after ten actions, reuse of an early-stopping attempt's unused allowance, per-response overspend rejection and the unchanged time/response limits. No environment changes are required. Live checks used API credit but made no Firestore writes or app-allowance deductions.

The comparison report and preserved results are in `C:\Dev\assessment-review\openai-expanded-budget-20261104` (`REPORT.html` and `REPORT.txt`). Restart the OpenAI backend to load the expanded allowance.

## API references

- [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
