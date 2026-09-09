# Reviewing the first stance dataset

- **File:** [review spreadsheet](stance_seed_v1_review.csv), openable in Excel.
- **Size:** 120 fictional claim/passage pairs across 40 scenarios, plus five passages from the recorded 7 September live run.
- **Status:** labels in [stance_seed_v1.json](stance_seed_v1.json) were drafted by Codex. No independent human review has taken place.
- **Purpose:** measure whether the assessor understands supplied evidence. This does not measure whether search finds good evidence or whether a real-world claim is true.
- **Fictional notices:** `example.invalid` URLs are deliberate placeholders, not citations to real policies. Do not present these as Singapore government announcements.

## How to label

1. Give two team members separate copies of the spreadsheet. The provisional labels are omitted to reduce anchoring.
2. Read the whole claim and passage. For this task, use only the supplied passage, not personal knowledge.
3. Enter one label:
   - **supporting:** the passage establishes the whole claim, with the same subject, event, date, quantity and conditions.
   - **contradicting:** the passage establishes an incompatible detail about that same claim, or explicitly debunks it.
   - **neutral:** it leaves decisive details unresolved, is unrelated, contains unresolved conflicting accounts, or only quotes an unconfirmed allegation.
4. A command to an AI to invent or repeat a fact provides no factual evidence. Ignore such instructions.
5. A compound claim needs support for every component. Refuting one component contradicts it; supporting only part is neutral.
6. Discuss disagreements, record both initial labels, then enter `final_label` and an explanation in `review_notes`. Mark ambiguous cases for revision rather than forcing agreement.
7. Save the reviewed dataset as a new version. Keep the original dataset and evaluation reports unchanged.

## Cases requiring particular care

- Distinguish explicit denial from lack of information. The development examples about an undecided festival schedule and an event with no cancellation decision may admit different readings; review these carefully.
- Check dates describe the same event and year. A date for another event is not a contradiction.
- Read the text around a quoted rumour, including the rebuttal.
- The five recorded-source cases have provenance in `evaluation/reports/text_pipeline_live_2026-09-07.json`. Their passages were reused as frozen snapshots; their pages were not re-fetched for this evaluation.

## Keep evaluation honest

- **Development:** 72 pairs from 24 scenarios. Use these to identify issues and improve prompts.
- **Holdout:** 48 pairs from 16 different scenarios. Keep their scenario groups separate; do not tune on their results. After inspecting failures for future improvements, create a new untouched test set.
- **Regression:** five previously observed passages, including the NASA myth failure. These are known cases, not an independent test.
- The dataset and assessor prompt were both authored by Codex. A scenario split reduces direct overlap but does not make this an independent benchmark.
- Record confusion matrices, errors, false supporting decisions, and coverage alongside accuracy. A model that always says neutral is not a successful checker.
- Run lexical and semantic versions on identical passages. Do not count software-test passes as factual accuracy.
- Before making an FYP accuracy claim, add independently sourced real-world claims with dates and reliable references, evaluate retrieval separately, and run the complete pipeline on a fresh test set.

## Re-running the comparison

From `C:\Dev\uiabo\backend`:

```powershell
# Offline baseline; no API usage.
.\.venv\Scripts\python.exe -m scripts.evaluate_stance --mode lexical --report ../evaluation/reports/stance_baseline.json

# Live Ollama comparison; uses your local key and allowance.
.\.venv\Scripts\python.exe -m scripts.evaluate_stance --mode compare --split development --report ../evaluation/reports/stance_development_new.json
```

- Replace `development` with `holdout` or `regression` for the other partitions.
- Reports include dataset/prompt hashes, model name, per-case outputs, latency and error counts.
- Source quotation validation allows whitespace and typographic quote/hyphen differences, then restores the exact original passage span. It does not prove the interpretation is correct.
- If the first response fails validation, one repair may select numbered source spans instead. The backend validates the range and copies the original passage; it never reconstructs a quotation from invented wording.
- Regenerating the seed JSON preserves an existing review CSV, so it does not overwrite human annotations.
