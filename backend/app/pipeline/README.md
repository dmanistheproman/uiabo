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

The API calls all four live text stages through the Sprint 1 orchestrator. Google Fact Check and Tavily provide retrieval; model/search failures return controlled errors. Risk scores come from Poon's lexical baseline, which still needs accuracy evaluation against real evidence.
