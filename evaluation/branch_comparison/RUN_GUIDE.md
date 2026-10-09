# Run the branch comparison

## 1. Open PowerShell

```powershell
cd C:\Dev\uiabo-jev-test
$py = '.\backend\.venv\Scripts\python.exe'
$pack = '.\evaluation\branch_comparison'
```

- Both repositories need their backend virtual environments and dependencies installed.
- You do not need Expo, an emulator or a running backend server.
- Use `-B` as shown so these checks do not update Python bytecode files.
- Both processes use `C:\Dev\uiabo-jev-test\.env` at the repository root as their shared credential profile by default. They do not edit it. This is the file used by the pipeline, not a `backend\.env` file.
- Required: `OLLAMA_API_KEY`, `TAVILY_API_KEY`, `JEV_API_KEY`. Google Fact Check is optional but must be configured consistently if used.
- The runner records whether credentials exist, never their values. Do not put credentials in commands or review files.

## 2. Check the setup without API calls

```powershell
& $py -B "$pack\compare.py" --split pilot
& $py -B "$pack\compare.py" --split final
```

These dry runs validate the datasets and locate both working trees. Before a live run, the runner also imports both pipelines and checks credential availability without making API calls.

Optional offline infrastructure tests:

```powershell
& $py -B -m unittest discover -s "$pack\tests" -v
```

## 3. Combine your group's independent pilot reviews

After each reviewer has filled their own Pilot tab:

```powershell
& $py -B "$pack\collect_reviews.py" --split pilot --a "$pack\outputs\review_pack_20260929\Reviewer_A.xlsx" --b "$pack\outputs\review_pack_20260929\Reviewer_B.xlsx" --output "$pack\local_runs\pilot_labels.csv"
```

- Open `local_runs\pilot_labels.csv` in Excel.
- Preserve both reviewers' initial answers.
- Fill the five final decision columns explained in the review guide.
- Save as CSV UTF-8 and close it before running the comparison.
- Blank CSV templates also exist in `reviews` if you prefer filling them directly.

## 4. Run the pilot

**This makes real API calls and consumes provider usage.**

```powershell
& $py -B "$pack\compare.py" --split pilot --labels "$pack\local_runs\pilot_labels.csv" --execute --report "$pack\local_runs\pilot_01.json"
```

For a small technical check before labelling, use two pilot cases. This produces diagnostics, not accuracy:

```powershell
& $py -B "$pack\compare.py" --split pilot --limit 2 --execute --report "$pack\local_runs\pilot_smoke_01.json"
```

Review the report:

```powershell
& $py -B "$pack\review_results.py" "$pack\local_runs\pilot_01.json" --output "$pack\local_runs\pilot_review_01"
```

- Open `SUMMARY.md` for metrics.
- Give reviewers `blinded_results.json` and `result_audit.csv`.
- Keep `PRIVATE_branch_key.json` and the original report with the person coordinating the evaluation.
- Fix issues using pilot and regression cases. Keep each report under a new filename.

## 5. Check the known weather cases consistently

Capture one public forecast snapshot:

```powershell
& $py -B "$pack\snapshot_weather.py" "$pack\local_runs\weather_01.json"
```

This requests the public data.gov.sg forecast API once. Review its timestamp and dates before labelling the weather cases. The runner replays this exact response to either branch that requests that endpoint, and uses the snapshot's assessment time for both pipelines. It does not manufacture a forecast.

```powershell
& $py -B "$pack\compare.py" --split regression --forecast-fixture "$pack\local_runs\weather_01.json" --execute --report "$pack\local_runs\regression_01.json"
```

Add `--labels` with a completed regression adjudication CSV to calculate label agreement. Without it, this is a diagnostic run. Older pipeline versions may not request the structured forecast API at all; that is a product capability difference.

## 6. Run the final comparison after tuning

- Finish both Final review tabs independently and adjudicate them.
- Record the maximum acceptable response time and paid usage in the decision template before seeing results.
- Freeze both code versions. Keep copies of labels and reference passages.
- Do not edit either pipeline while the run is active.

```powershell
& $py -B "$pack\collect_reviews.py" --split final --a "$pack\outputs\review_pack_20260929\Reviewer_A.xlsx" --b "$pack\outputs\review_pack_20260929\Reviewer_B.xlsx" --output "$pack\local_runs\final_labels.csv"
```

Complete the final decision columns, then:

```powershell
& $py -B "$pack\compare.py" --split final --labels "$pack\local_runs\final_labels.csv" --execute --report "$pack\local_runs\final_01.json"
& $py -B "$pack\review_results.py" "$pack\local_runs\final_01.json" --output "$pack\local_runs\final_review_01"
```

The runner refuses unlabelled final runs, partial final sets and report overwrites. It saves progress after each branch result. If interrupted, keep the partial report. There is no automatic resume: use a new filename and record why a repeat was needed. Never cherry-pick the better run.

## How to interpret the output

- **Accuracy including errors:** correct labels divided by all attempted, labelled cases. Provider failures remain in the denominator.
- **Wrong decisive:** supported, contradicted or forecast-conflict answers that disagree with the reviewed label.
- **Decisive precision:** correct decisive answers divided by all decisive answers.
- **Decisive coverage:** decisive answers divided by all attempted cases. It is not the percentage of all useful answers; a justified unresolved answer can be correct.
- **Macro F1:** averages F1 across classes present in the reviewed answers or predictions. The JSON includes class counts, precision, recall and F1.
- **Mean group accuracy:** average within each scenario group, then average groups equally. Related paraphrases do not gain extra weight here.
- **Latency:** median and nearest-rank p95 including errors and Python startup. Artificial pauses between calls are excluded.
- **HTTP attempts:** outgoing HTTPX send attempts, including fetches, retries and failures; replayed forecast requests are marked. These are not billable credits. Token counters appear only where providers return recognised usage fields.
- **Actual cost:** compare provider dashboards before and after the run. Keep other usage quiet. The runner does not estimate money from request counts.

## Limits to record in the report

- Live search results and remote model aliases can change. Only the official weather response is replayed; this is not full deterministic evidence replay.
- These are AI-authored candidate claims, not an independent published benchmark or a random sample of user messages.
- Two humans reviewing AI-authored claims improves label quality but does not make the sampling independent of the developer. For stronger final-year-project evidence, add a separately held-out collection of real public messages gathered by teammates who did not tune the pipeline.
- “Unresolved” combines insufficient, unsupported and conflicting evidence for headline metrics. Inspect their original outcomes and explanations in the JSON.
- Current deployment behaviour, UI readability, Firestore access controls, malicious-link checks, OCR and deepfake detection are outside this text-pipeline comparison.

## If reviewers replace a candidate before the final set is frozen

- Change the relevant `datasets\*.json` claim and its readable Markdown list together. Keep its ID stable unless adding/removing rows, and keep related cases in one split.
- Update that exact input cell in both review workbooks and clear any old labels/reasons for the changed case. Changes to row order or count need corresponding workbook rows.
- Run the matching dry-run command to get the new `dataset_sha256`. Put that value in **H2** of the matching tab in both workbooks.
- Re-export the adjudication CSV so it carries the new fingerprint. Keep earlier review files as versioned copies.
- Run the offline tests again to detect mismatched claims, counts or fingerprints.
- Do this before viewing final outputs. The existing final set must become a regression set if you tune against its results.
