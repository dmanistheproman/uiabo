# Input preparation — Yi Da

This folder is owned primarily by **Wong Yi Da**.

Build the component that:

- Validates submitted text.
- Normalises spacing without changing meaning.
- Preserves dates, amounts, punctuation and negation.
- Treats submitted content as untrusted data.
- Adds basic prompt-injection safeguards.
- Returns the agreed `PreparedText` object.

Suggested future modules:

```text
service.py       # Text preparation logic
prompt_safety.py # Prompt-injection safeguards
```

