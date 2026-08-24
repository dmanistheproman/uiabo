# Poon — Sprint 1 assessment component evaluation

## What was tested

The component is tested directly against all five shared
`04_poon_assessment_samples.json` scenarios:

1. a claim contradicted by authoritative evidence;
2. a claim supported by authoritative evidence;
3. an opinion with no checkable factual claim;
4. a factual claim with no evidence; and
5. related but neutral evidence.

Additional automated tests cover:

- a failed retrieval request;
- conflicting supporting and contradicting evidence;
- direct amount contradictions;
- direct weekday contradictions; and
- quality-score rules.

## Current result

The shared Sprint 1 sample outputs pass without changing the agreed JSON
field names.  The safe-exit cases return `Not Enough Information`, high
uncertainty and a `null` misinformation-risk score instead of guessing.

The component also keeps neutral evidence in `assessed_evidence` so the user
can see that related information was found even though it was not enough to
verify the decisive part of the claim.

## What the result means

This is a working Sprint 1 baseline, not a production truth detector.  It is
useful because the rules are visible, testable and easy to integrate with the
other team components.  The output quality still depends on Matthew's claim
analysis and Chu's evidence retrieval.

## Known limitations

The current stance classifier uses simple lexical rules.  It can recognise
clear cases such as:

- positive statement versus direct negation;
- matching or different amounts;
- matching or different weekdays; and
- evidence that mentions the topic but omits the claimed day.

It may not correctly understand complicated paraphrases, implied
contradictions, sarcasm, multi-step reasoning or multiple claims in one
sentence.  Later evaluation should use a larger labelled set before changing
or calibrating the risk-score rules.
