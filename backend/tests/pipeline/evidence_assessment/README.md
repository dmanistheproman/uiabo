# Poon's tests

`test_service.py` covers the five shared Sprint 1 samples and regression tests
for the typed pipeline boundary, explanation grounding, correct source
attribution, evidence-ID matching, neutral quality scoring and failed
retrieval handling.

Run this component's tests from `backend` with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\pipeline\evidence_assessment
```
