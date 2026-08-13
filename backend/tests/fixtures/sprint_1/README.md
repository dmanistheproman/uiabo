# Sprint 1 fixtures

Stable JSON inputs and mocked component outputs are stored here so every component can be developed and tested without waiting.

The files form one synthetic scenario through the entire pipeline:

```text
prepared_text.json
    -> claim_analysis.json
    -> retrieval_result.json
    -> assessment_result.json
    -> text_analysis_result.json
```

`not_enough_information.json` provides the required no-score safe-exit example.

More extensive working examples currently exist in `C:\Dev\sprint_1_samples`.

Fixture evidence must be clearly marked as synthetic. Never present fixture URLs as real citations.
