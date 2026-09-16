import assert from 'node:assert/strict';
import test from 'node:test';
import { assessmentLabel, scoreDescription, isProvisionalScore, changeVerificationLabel } from '../src/utils/assessment.js';

test('zero is a valid score with an explicit meaning', () => {
  const result = { assessment_outcome: 'supported', misinformation_risk_score: 0, scoring: { version: 'evidence-v2' } };
  assert.equal(assessmentLabel(result), 'Supported by evidence');
  assert.match(scoreDescription(result), /No misinformation concern identified/);
  assert.match(scoreDescription(result), /does not guarantee/);
});

test('missing evidence is not presented as a zero score', () => {
  assert.match(scoreDescription({ misinformation_risk_score: null }), /Missing evidence is not proof/);
  assert.match(scoreDescription({ assessment_outcome: 'not_checkable' }), /not a zero-risk finding/);
});

test('legacy saved scores are not silently reinterpreted', () => {
  assert.match(scoreDescription({ misinformation_risk_score: 15 }), /earlier scoring rules/);
});

test('a conflict keeps its verdict even with a low indicator', () => {
  const result = { assessment_outcome: 'conflicting', misinformation_risk_score: 30, scoring: {} };
  assert.equal(assessmentLabel(result), 'Conflicting evidence');
  assert.match(scoreDescription(result), /both sides/);
});

test('link safety still has its own outcome', () => {
  assert.equal(assessmentLabel({ input_type: 'link_safety', safety_status: 'no_known_threats' }), 'No known threats found');
});

test('policy evidence and an unverified change have a specific headline', () => {
  const result = { assessment_outcome: 'unsupported', misinformation_risk_score: null,
    policy_context: { change_status: 'unverified' } };
  assert.equal(assessmentLabel(result), 'Claim not supported by official evidence');
  assert.match(scoreDescription(result), /assessed separately/);
  assert.equal(changeVerificationLabel(result.policy_context.change_status), 'Unverified');
});

test('a contradicted change is not called merely unverified', () => {
  assert.equal(changeVerificationLabel('contradicted'), 'Contradicted by evidence');
  assert.equal(changeVerificationLabel('conflicting'), 'Conflicting evidence');
});

const provisional = {
  processing_status: 'completed', checkable: true, assessment_outcome: 'insufficient_evidence',
  misinformation_risk_score: 50, scoring: { version: 'evidence-v3', status: 'provisional' },
};

test('provisional midpoint is unverified, not a probability of falsehood', () => {
  assert.equal(isProvisionalScore(provisional), true);
  assert.equal(assessmentLabel(provisional), 'Unverified');
  assert.match(scoreDescription(provisional), /neutral starting point/);
  assert.match(scoreDescription(provisional), /does not mean a 50% chance/);
  assert.equal(isProvisionalScore({ ...provisional, assessment_outcome: 'unsupported' }), true);
});

test('balanced conflicting evidence is distinct from a provisional midpoint', () => {
  const conflict = { ...provisional, assessment_outcome: 'conflicting',
    scoring: { version: 'evidence-v3', status: 'evidence_based' } };
  assert.equal(isProvisionalScore(conflict), false);
  assert.equal(assessmentLabel(conflict), 'Conflicting evidence');
  assert.match(scoreDescription(conflict), /both sides/);
});

test('legacy results, failures and nonfactual content do not gain provisional scores', () => {
  for (const overrides of [
    { scoring: undefined }, { scoring: { version: 'evidence-v2' } },
    { misinformation_risk_score: null }, { misinformation_risk_score: 75 },
    { processing_status: 'failed' }, { checkable: false }, { assessment_outcome: 'not_checkable' },
  ]) assert.equal(isProvisionalScore({ ...provisional, ...overrides }), false);
  assert.match(scoreDescription({ ...provisional, scoring: undefined }), /earlier scoring rules/);
});
