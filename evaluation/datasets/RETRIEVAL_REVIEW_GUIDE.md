# Review the real-topic retrieval test set

- **Start here:** open `retrieval_seed_v1_review.csv` in Excel.
- There are **40 paired factual claims and 3 known regressions**.
- The examples concern real topics; the false variants were deliberately written for testing. They are not a sample of 40 naturally occurring viral posts.
- All proposed labels were authored by Codex and remain **pending two human reviewers**. Do not report their agreement rate as established product accuracy.

## What each reviewer should do

1. Read the claim without looking at the app's answer or the JSON labels.
2. Open the supplied reference. Find an alternative original source if the page moved or does not establish the claim.
3. Check the **whole claim**, including dates, quantities, people, location and exceptions.
4. Enter `supported`, `refuted`, `insufficient` or `conflicting` in your own reviewer column.
5. Record the decisive source quotation, qualifications and review date.
6. Resolve disagreements together and enter the agreed `final_label`.

The reference links are starting points, not guaranteed complete evidence. They are never supplied to the retrieval pipeline by the evaluation runner.

## How to interpret uncertainty

- Missing evidence is not proof that a claim is false.
- Evidence about a different population, rule or time may be related without answering the claim.
- The Phuket personal claim is provisionally `insufficient` because nationality and entry category are missing. This does not mean that no Thai monetary requirement exists.
- The food-preference example is an opinion and should not receive a factual verdict.
- A technical provider failure counts as an error, not as a successful uncertain answer.

## Splits and limits

- **Development:** 24 claims. Use these to diagnose and change the implementation.
- **Holdout:** 16 claims. Keep these unrun until development changes are frozen. Once inspected, do not call them an untouched test set for subsequent tuning.
- **Regression:** 3 previously discussed examples. These are known cases, not independent validation.
- Related true/false variants and shared reference pages stay in the same split.
- Domains and broad topics overlap between splits. This set is deliberately small and weighted towards English government/scientific sources; it does not establish general web coverage.
- The same agent authored the prompts and provisional examples. Human review is necessary, and a future independently sampled short-form-content set is still needed.

## Comparing results

- Run both modes using `backend/scripts/evaluate_retrieval.py`.
- Reports preserve the original input, shared claim extraction, all final evidence, warnings, decisions, pipeline hashes, times and failures.
- Check **relevant evidence coverage**, **wrong decisive answers**, **unnecessary uncertainty**, **citation interpretation** and **latency**.
- Literal quotation checks only prove that text was copied from the selected passage. Reviewers must check whether it justifies the conclusion and corresponds to the live original page.
- Search/extraction/relevance call counts are recorded for web mode. They are not an exact invoice or token-cost measurement. Baseline provider usage is not instrumented by this runner.
- Existing report files cannot be overwritten. The dataset builder also preserves an existing review CSV.
- The runner currently compares the provisional JSON labels. After adjudication, create a versioned dataset containing the agreed labels; do not silently replace labels in an existing report.
