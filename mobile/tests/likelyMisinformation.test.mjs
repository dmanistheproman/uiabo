import assert from 'node:assert/strict';
import test from 'node:test';
import { assessmentLabel, credibilityScore, scoreDescription } from '../src/utils/assessment.js';
import { resultPresentation } from '../src/utils/resultPresentation.js';

test('public-change inference has the same label in results and history, without a fake midpoint', () => {
  const result = { assessment_outcome: 'likely_misinformation', misinformation_risk_score: null,
    scoring: { status: 'inference_based', version: 'evidence-v4' },
    inference_context: { explanation: 'The official baseline weighs against the announced closure.' } };
  assert.equal(assessmentLabel(result), 'Likely misinformation');
  assert.equal(resultPresentation(result).title, 'Likely misinformation');
  assert.equal(credibilityScore(result), null);
  assert.match(scoreDescription(result), /official baseline/);
  assert.doesNotMatch(scoreDescription(result), /50|probability.*50/);
});

test('weather likelihood uses consistent words without pretending it is a fact', () => {
  for (const result of [
    { assessment_outcome: 'highly_unlikely', scoring: { status: 'plausibility_based' } },
    { assessment_outcome: 'contradicted', forecast_context: { risk_basis: 'forecast_comparison' } },
  ]) {
    assert.equal(assessmentLabel(result), 'Likely misinformation');
    assert.equal(resultPresentation(result).title, 'Likely misinformation');
    assert.match(resultPresentation(result).meaning, /do not prove|not a guarantee/);
  }
});

test('pure hypothetical explains why it has no misinformation verdict', () => {
  const result = { assessment_outcome: 'not_checkable', checkable: false,
    explanation: 'This is an imagined scenario, not an assertion that the event will happen.' };
  assert.match(resultPresentation(result).meaning, /imagined scenario/);
  assert.equal(credibilityScore(result), null);
});
