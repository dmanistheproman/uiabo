# Pipeline tests

Test folders match the application components:

| Folder | Primary owner | Test focus |
|---|---|---|
| `input_preparation` | Yi Da | Validation, normalisation, Unicode, and prompt injection |
| `claim_analysis` | Matthew | Claim extraction and checkability categories |
| `evidence_retrieval` | Chu | Fact-check matching, evidence relevance, failures, and deduplication |
| `evidence_assessment` | Poon | Stance, scoring, uncertainty, and grounded explanations |
| `orchestration` | Donovan | Safe exits, failures, final response, and Firestore persistence |

Use saved or mocked third-party responses in automated tests so tests are repeatable and do not consume API quota.

