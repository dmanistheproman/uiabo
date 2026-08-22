# Donovan's tests

This folder tests Donovan's Sprint 1 integration work.

- `test_service.py` covers a complete sample run, non-checkable content, no evidence, retrieval failure, invalid component output, evidence matching, warnings, and storage failures.
- `test_repository.py` checks the Firestore document shape and controlled persistence errors without contacting the real database.

The API dependency is replaced with a sample pipeline in `backend/tests/test_analysis.py`, so the endpoint can be tested before every teammate component is ready.
