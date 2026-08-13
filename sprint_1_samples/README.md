# Sprint 1 Sample Interfaces

These files allow each member to build and test their component without waiting for the previous component.

## Files

| File | Owner | Purpose |
|---|---|---|
| `01_yi_da_input_samples.json` | Yi Da | Raw API text and expected `PreparedText` |
| `02_matthew_claim_samples.json` | Matthew | `PreparedText` and expected `ClaimAnalysis` |
| `03_chu_retrieval_samples.json` | Chu | `ClaimAnalysis` and expected `RetrievalResult` |
| `04_poon_assessment_samples.json` | Poon | Claims/evidence and expected `AssessmentResult` |
| `05_donovan_integration_samples.json` | Donovan | Component outputs and expected final API result |

## How to use the files

1. Find the file assigned to you.
2. Use each `input` object as the input to your component.
3. Make your component return the same structure as `expected_output`.
4. The exact score or wording may improve later, but field names and allowed values must follow the agreed interface.
5. Turn important samples into automated tests.

The same `scenario_id` is used across files. For example, `tax_contradicted` can be followed from raw text through the final API result.

## Important warning

All claims, sources, passages and URLs in these fixtures are **synthetic examples for software development**. They are not real fact checks and must not be presented to users as genuine evidence. Production results must use real, verified sources and working citations.

