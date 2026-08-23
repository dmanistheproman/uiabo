# Input preparation — Yi Da

This folder is owned primarily by **Wong Yi Da**.

Build the component that:

- Validates submitted text.
- Normalises spacing without changing meaning.
- Preserves dates, amounts, punctuation and negation.
- Treats submitted content as untrusted data.
- Adds basic prompt-injection safeguards.
- Confirms submitted text is English before it continues.
- Returns the agreed `PreparedText` object.

Modules:

```text
service.py             # Text preparation logic
language_validation.py # English detection (Lingua), supported/unsupported/uncertain
```

## Language handling

Sprint 1 processes English only, but the language is a **detection result**,
not an assumption. `language_validation.py` wraps the offline Lingua library
(all models are bundled with the package; no network calls) and returns one
of three outcomes:

| Status        | Meaning                                   | Pipeline behavior |
| ------------- | ----------------------------------------- | ----------------- |
| `supported`   | Confidently English                       | Continue          |
| `unsupported` | Confidently another language              | Reject, 422 `UNSUPPORTED_LANGUAGE` |
| `uncertain`   | Too short or ambiguous to label reliably  | Reject, 422 `LANGUAGE_UNCERTAIN` |

Detection needs at least 4 alphabetic characters, a minimum confidence of
0.10 and a margin of 0.05 over the runner-up. Lingua's scores are relative,
not calibrated probabilities, so the margin is the stronger signal.

Only text that passes the gate reaches claim analysis, so every
`PreparedText.language` is `"en"` and the shared interface is unchanged.

## Unicode normalisation

The normalisation order matters: every recognised whitespace character
(including U+0085 NEXT LINE, which Unicode categorises as a control) becomes
a plain space *before* invisible formatting characters are removed —
otherwise deleting such a separator silently joins two words. Zero-width
joiner/non-joiner are preserved (emoji sequences, Indic scripts).
Non-whitespace control characters are rejected (`UNSAFE_CONTROL_CHARACTER`)
instead of deleted, because their intended boundary is ambiguous.

Reference implementations and their rationale were provided in
`docs/input_preparation_additionals/`.
