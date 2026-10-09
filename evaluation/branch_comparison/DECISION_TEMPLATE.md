# Pipeline comparison decision

## Fill before the final run

- Original code fingerprint / commit:
- Experimental code fingerprint / commit:
- Reviewed dataset fingerprint:
- Reviewers and adjudicator:
- Label review completed on:
- Maximum acceptable typical response time:
- Maximum acceptable slow response time (p95):
- Maximum acceptable paid API usage / cost:
- Person holding the final labels and private branch key:

## Record the result

| Measure | Original | Experimental |
| --- | --- | --- |
| Attempted claims / scenario groups | | |
| Correct / all attempted labelled claims | | |
| Macro F1 | | |
| Mean group accuracy | | |
| Wrong decisive answers | | |
| Unresolved answers | | |
| Technical failures | | |
| Median / p95 response time | | |
| Actual paid API usage / cost | | |
| Citation or explanation audit failures | | |

- Cases only the experimental branch got right:
- Cases only the original branch got right:
- Important failures and their causes:
- Initial reviewer agreement and disagreements:
- Known regression cases still failing:
- Limits of this evaluation:

## Recommended decision rule

Use this as a practical project rule, not a statistical guarantee:

- Prefer the experimental branch if it improves correct answers on the reserved set without increasing wrong decisive answers, and its time/cost stay within the limits recorded above.
- Inspect category results so overall improvement does not conceal worse scam, policy or question handling.
- Require satisfactory citation and explanation reviews. Correct labels alone are insufficient.
- If results are mixed or differences are small, keep testing on fresh, independently collected cases. Do not repeatedly tune and re-score the same final set as if it were unseen.
- If final cases reveal new bugs, reclassify those cases as regression examples after fixing them and use a fresh final set for the next unbiased comparison.

## Before merging

- [ ] Offline tests pass on the proposed code.
- [ ] Text input, loading state, result page and error/retry behaviour work on the emulator.
- [ ] Saved results belong to the correct signed-in user.
- [ ] Failed requests do not incorrectly consume allowances.
- [ ] Older saved results still open correctly.
- [ ] API keys remain local; OCR changes are handled separately as agreed.
- [ ] A rollback commit/branch is recorded.

Decision: **merge / keep testing / keep original**

Reason:

## Presentation wording

“We compared both complete text pipelines on ___ reviewed claims across ___ scenarios. Two reviewers labelled the inputs independently before seeing the outputs. The experimental pipeline achieved ___ correct answers versus ___ for the original, with ___ versus ___ wrong decisive answers. Median response time was ___ versus ___. The sample was project-authored, so these findings demonstrate performance on this test set rather than general real-world accuracy.”
