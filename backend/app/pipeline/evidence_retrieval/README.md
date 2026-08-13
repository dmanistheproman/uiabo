# Evidence retrieval — Chu

This folder is owned primarily by **Chu Wai Chung**.

Build the component that:

- Receives a checkable `ClaimAnalysis`.
- Searches previous fact checks.
- Searches other trusted evidence sources.
- Removes irrelevant and repeated results.
- Returns relevant passages and working citations.
- Returns the agreed `RetrievalResult` object.

Suggested future modules:

```text
service.py          # Coordinates retrieval
fact_check_client.py
evidence_client.py
deduplication.py
```

Trusted-source records belong in `evaluation/trusted_sources`.

