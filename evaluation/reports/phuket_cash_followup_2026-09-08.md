# Phuket cash-claim follow-up - 8 September 2026

## Actual saved result

- Input: `I need to have 20000 baht in cash to enter phuket`.
- Claim classification: factual, checkable; extracted wording preserved.
- Evidence: none. The semantic assessor never ran for this saved result.
- The original Not Enough Information result was caused by retrieval failure to find an accepted source, not a factual decision about Thai entry rules.

## Changes

- Added the reviewed `mfa.go.th` and `thaiembassy.org` domain families.
- Normalised grouped numbers for matching and formatted large currency amounts in search queries, preserving the submitted claim.
- Removed first-person helper words from relevance matching.
- Added a bounded alternative-query fallback using the existing Ollama key when the initial search returns no accepted evidence. Only valid queries preserving numerical values are used; the original claim and source restrictions remain unchanged.
- Search results outside the requested catalogue were observed during diagnosis. These remain excluded, including social posts and commercial sites whose names resemble embassy sites.
- A repeat exposed an assessment error: a passage specifying 20,000 baht per family was incorrectly treated as supporting the user's personal requirement. That unsuccessful run is retained in `phuket_cash_query_fallback_final_2026-09-08.json`.
- Added a conservative applicability check for first-person entry obligations. Missing passport/nationality or visa/entry category keeps the result neutral rather than treating a category-specific amount as universally applicable.
- Neutral results now explain the evidence limitation instead of displaying only a generic insufficient-evidence sentence.

## Verification

- **337 backend tests passed**, including source lookalikes, number formatting, query validation/fallback, provider failures and the family-versus-person applicability regression.
- [Final live replay](phuket_cash_context_guard_2026-09-08.json) found one official source for the original wording and returned Not Enough Information with this explanation:
  - Related evidence was found.
  - The statement does not specify passport/nationality and visa/entry category.
  - The evidence cannot establish the user's personal entry requirement.
- [A separately qualified claim](phuket_cash_retrieval_2026-09-08.json) about tourists under the visa-exemption scheme returned Low Concern with four official sources.
- Diagnostic runs used live providers with in-memory results or direct component calls. They did not consume the user's app allowance or modify existing saved results.
- This is a case-level retrieval/applicability fix, not a new real-world accuracy benchmark. Provider results and model interpretations vary; broader retrieval and assessment evaluation is still needed.

## Official reference and limits

- The [Royal Thai Embassy in Budapest](https://budapest.thaiembassy.org/en/publicservice/tourist-visa-exemption?menu=698b49659c095935352c7913&page=6984988f8adfb526cf0c38f3) lists a cash requirement equivalent to 20,000 baht per person or 40,000 per family for the Tourist Visa Exemption Scheme. Its page was updated in February 2026.
- That supports a claim about the stated scheme, but does not establish the correct entry category for the person making an unspecified first-person statement.
- Other official pages describe different schemes, older policies and different individual/family amounts. The system must preserve those distinctions and check dates; a matching number alone is insufficient.
- The new context gate covers explicit first-person entry-obligation wording. It is not a complete detector of every possible implicit condition or paraphrase.

New runtime version: `sprint-1-semantic-v3:gpt-oss:120b:retrieval-v2`.
Existing saved results retain their original output. Submit a new check to use the updated pipeline.
