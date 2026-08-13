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

The existing `app/services/analysis_service.py` remains the active mock implementation until the new components are ready to be connected safely.

