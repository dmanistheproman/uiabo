# Claim analysis — Matthew

This folder is owned primarily by **Matthew Alexander Peeris**.

Build the component that:

- Receives `PreparedText`.
- Extracts the principal factual claim.
- Classifies the content category.
- Decides whether the claim is checkable.
- Returns the agreed `ClaimAnalysis` object.

Suggested future modules:

```text
service.py    # Claim extraction and classification
categories.py # Allowed categories and helper rules
```

Matthew's evaluation dataset belongs in `evaluation/datasets` rather than inside the application package.

