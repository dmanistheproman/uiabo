# Pipeline orchestration — Donovan

This folder is owned primarily by **Ho Sze Wei, Donovan**.

Build the component that:

- Maintains the shared schemas and interfaces.
- Calls pipeline components in the correct order.
- Skips retrieval for non-checkable content.
- Skips scoring when evidence is insufficient.
- Handles component failures without returning a false assessment.
- Combines outputs into `TextAnalysisResult`.
- Saves submissions, results, evidence, warnings, timestamps, and versions in Firestore.

Suggested future modules:

```text
service.py    # Pipeline control flow
repository.py # Firestore result persistence
errors.py     # Controlled pipeline failures
```

