# Preparation checks

Checked on 29 September 2026.

- 20 pilot inputs, 60 final inputs and 8 regression inputs validated.
- Scenario groups do not cross splits. No exact pilot/final claim duplicates were found in the existing retrieval dataset. This automated check does not prove that the topics or wording are unfamiliar to the team.
- Both review workbooks contain all matching inputs, correct dataset fingerprints and blank labels.
- All six workbook tabs rendered and visually inspected. No Excel application interaction was required; native Excel dropdown behaviour has not been manually tested.
- 12 offline tests passed, including label-review requirements, no label leakage to workers, forecast-versus-factual outcome handling, errors in the metric denominator, timeout handling, result-review exports and report overwrite protection.
- An offline two-case simulated comparison exercised alternating branch order and checkpoint/report generation. Simulated results were temporary test fixtures, not benchmark measurements.
- Real result assembly in both local branches passed with network calls and Firestore writes blocked and a stubbed claim-analysis result.
- Both real pipeline configurations imported successfully using the shared repository-root `.env`. Required credentials were present. This preflight made zero API requests; it does not confirm remaining provider credit or live API availability.
- No full live benchmark was run and no benchmark accuracy is claimed. Independent labels and final result/citation reviews remain human tasks.

Only the evaluation package was added for this preparation task. Existing app/pipeline edits, the original working tree and OCR work were not changed, committed or pushed.
