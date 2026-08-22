# Sprint 1 pipeline

This package contains the real text-analysis pipeline being built during Sprint 1.

## Processing order

```text
input_preparation
    -> claim_analysis
    -> evidence_retrieval
    -> evidence_assessment
    -> orchestration
```

Each folder has one primary owner, but all changes still require review. Components must follow the agreed JSON interfaces in `C:\Dev\UIABO_SPRINT_1_TEAM_TASKS.md`.

The API now calls the Sprint 1 orchestrator. Components that have not yet been integrated return a controlled `*_NOT_READY` error; the backend no longer returns the old hard-coded risk score of 50.
