# Compare the original and Jev pipelines

**Goal:** find out whether the experimental branch produces more correct, useful answers before deciding to merge it.

## What is prepared

| Set | Inputs | Use it for |
| --- | ---: | --- |
| Pilot | 20 | Find problems and improve the pipeline |
| Final | 60 | Compare the finished versions once tuning is complete |
| Regression | 8 | Check the SIA, passport, CPF and weather issues already discussed |

- [Pilot claims](datasets/PILOT_CLAIMS.md)
- [Reserved final claims](datasets/FINAL_CLAIMS.md)
- [Known regression claims](datasets/REGRESSION_CLAIMS.md)
- [Reviewer A workbook](outputs/review_pack_20260929/Reviewer_A.xlsx)
- [Reviewer B workbook](outputs/review_pack_20260929/Reviewer_B.xlsx)
- [How to label](REVIEW_GUIDE.md)
- [Official sources to start researching](SOURCE_STARTERS.md)
- [Commands to run the comparison](RUN_GUIDE.md)
- [Decision and presentation template](DECISION_TEMPLATE.md)

## What your group does

1. **Choose two reviewers.** Give each person their own workbook and the review guide. Start with the Pilot tab. They must work independently.
2. **Research the expected answers.** Enter a label, reason, source links and review date. Do not run the app to obtain the expected answer.
3. **Agree on the final labels.** Preserve both initial reviews. Discuss disagreements and complete the adjudication CSV using the commands in the run guide.
4. **Run the pilot on both branches.** Fix problems using pilot and known regression cases. Record what changed.
5. **Freeze the code and final labels.** Finish labelling the Final tab without seeing pipeline outputs. Avoid changing prompts or source rules to fit these claims.
6. **Run the 60 final cases.** Review accuracy, wrong confident answers, unresolved cases, failures, citations, explanations and time taken.
7. **Decide whether to merge.** Use the decision template. Keep the original branch available until the app and saved-result checks also pass.

## Important distinctions

- The claims are **AI-authored candidate test inputs**, including deliberate misinformation and invented scenarios. They are not confirmed answers or advice.
- No expected labels have been filled in. The final runner requires a completed review CSV.
- Related questions share scenario groups. Report both claim count and group count; 60 claims are not 60 independent situations.
- The initial files contain 15 pilot groups, 46 final groups and 5 regression groups. Group names are an organisational aid; they do not establish statistical independence.
- These new examples are separate from the existing provisional datasets. Have a reviewer flag any examples your group has already used; replace them before freezing the final set.
- This compares the **two complete working trees**, including retrieval and scoring changes. It does not isolate Jev's model quality by itself.
- Accuracy is unavailable until your group supplies reviewed labels. There are no live benchmark results yet.

## What the runner does

- Runs both complete pipelines with the same input and shared credential file, each in its own Python process.
- Uses original mode for `C:\Dev\uiabo` and V3 mode for `C:\Dev\uiabo-jev-test`.
- Uses web retrieval and semantic assessment. Records code hashes, configuration, provider attempts, outputs and timings.
- Alternates which branch goes first. Saves progress after every result.
- Writes results to local files using in-memory storage. It does not write to Firestore or use app allowances.
- Uses paid API usage only when `--execute` is supplied. A pilot run means 40 pipeline runs; the final set means 120. Each pipeline run can make several API calls.

**Start now:** send out the two workbooks and ask your reviewers to complete the Pilot tab independently.
