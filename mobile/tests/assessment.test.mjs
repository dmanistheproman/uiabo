import assert from 'node:assert/strict';
import test from 'node:test';
import { assessmentLabel, credibilityRating, credibilityScore, scoreDescription, credibilityDetails, changeVerificationLabel } from '../src/utils/assessment.js';

function rated(s, c = 0) {
  return { assessment_outcome: s && c ? 'conflicting' : s ? 'supported' : 'contradicted',
    scoring: { version: 'evidence-v4', status: 'evidence_based', supporting_strength: s,
      contradicting_strength: c, supporting_origins: Number(Boolean(s)), contradicting_origins: Number(Boolean(c)) } };
}

test('five labels follow admitted evidence, never arbitrary score bands', () => {
  for (const [s, c, score, label] of [
    [.94, 0, 97, 'Strong evidence this is true'], [.7, 0, 85, 'Evidence suggests this is true'],
    [.94, .94, 50, 'Mixed evidence'], [0, .7, 15, 'Evidence suggests this is false'],
    [0, .94, 3, 'Strong evidence this is false'], [1, .6, 70, 'Mixed evidence'],
    [.6, 1, 30, 'Mixed evidence'], [.93, 0, 96, 'Strong evidence this is true'],
    [0, .93, 4, 'Strong evidence this is false'],
  ]) {
    assert.equal(credibilityScore(rated(s, c)), score);
    assert.equal(assessmentLabel(rated(s, c)), label);
  }
});

test('high means support and low means contradiction, including endpoints', () => {
  for (const [s, c, expected] of [[1, 0, 100], [0, 1, 0]]) {
    assert.equal(credibilityScore(rated(s, c)), expected);
    assert.match(credibilityDetails(rated(s, c)), new RegExp(`Credibility score: ${expected}/100`));
    assert.match(scoreDescription(rated(s, c)), /Higher means the evidence supports/);
    assert.match(scoreDescription(rated(s, c)), /not a guarantee/);
  }
});

test('both reported claims remain unrated for old and new unresolved records', () => {
  for (const original_text of [
    'Government officials are discussing raising the retirement age to 75 because CPF reserves are running out faster than expected.',
    'Singapore will begin giving new citizens priority over locally born Singaporeans for selected BTO flats from January 2027.',
  ]) for (const version of ['evidence-v3', 'evidence-v4']) {
    const result = { original_text, assessment_outcome: 'insufficient_evidence',
      misinformation_risk_score: version === 'evidence-v3' ? 50 : null,
      scoring: { version, status: 'provisional' } };
    assert.equal(credibilityScore(result), null);
    assert.equal(assessmentLabel(result), 'Not enough evidence');
    assert.match(credibilityDetails(result), /Not rated/);
    assert.doesNotMatch(credibilityDetails(result), /50|\/100/);
  }
});

test('bare legacy risk values cannot become credibility scores', () => {
  for (const risk of [0, 15, 50, 93, 100, null, undefined, '50', NaN, Infinity, -1, 101]) {
    const result = { assessment_outcome: 'supported', misinformation_risk_score: risk };
    assert.equal(credibilityScore(result), null);
    assert.match(scoreDescription(result), /Check it again/);
  }
});

test('old concern-only badges keep their verdict without inventing a rating', () => {
  const result = { concern_label: 'Low Concern', misinformation_risk_score: 10 };
  assert.equal(assessmentLabel(result), 'Evidence suggests this is true');
  assert.equal(credibilityScore(result), null);
});

test('legacy evidence strengths can be displayed without mutating stored scores', () => {
  const result = { ...rated(0, .94), misinformation_risk_score: 97 };
  result.scoring.version = 'evidence-v2';
  delete result.scoring.status;
  const original = structuredClone(result);
  assert.equal(credibilityScore(result), 3);
  assert.match(scoreDescription(result), /original risk score has not been changed/);
  assert.deepEqual(result, original);
});

test('failures, opinions, link checks and unresolved states are never rated', () => {
  for (const change of [
    { processing_status: 'failed' }, { checkable: false }, { input_type: 'link_safety' },
    { concern_label: 'Not Enough Information' }, { assessment_outcome: 'unsupported' },
    { assessment_outcome: 'not_checkable' }, { assessment_outcome: 'insufficient_evidence' },
    { scoring: { version: 'evidence-v4', status: 'provisional' } },
  ]) assert.equal(credibilityScore({ ...rated(.94), ...change }), null);
});

test('malformed and weak metadata cannot produce a number', () => {
  for (const change of [
    { supporting_strength: .2 }, { supporting_strength: '0.9' }, { supporting_strength: NaN },
    { supporting_strength: 1.1 }, { supporting_origins: 0 }, { supporting_origins: -1 },
    { supporting_origins: 1.5 }, { version: 'future-unknown' }, { status: 'provisional' },
  ]) {
    const result = rated(.94);
    Object.assign(result.scoring, change);
    assert.equal(credibilityScore(result), null);
  }
});

test('canonical API rating is consumed with the recorded evidence explanation', () => {
  const result = rated(.94);
  result.credibility = { version: 'credibility-v1', status: 'rated', score: 97,
    label: 'Strong evidence this is true', explanation: 'One supporting source group met the checks.' };
  assert.equal(credibilityRating(result), result.credibility);
  result.credibility.score = 3;
  assert.equal(credibilityScore(result), 97);
});

test('climate warning is not converted from arbitrary risk85 into credibility15', () => {
  const result = { assessment_outcome: 'highly_unlikely', misinformation_risk_score: 85,
    scoring: { status: 'plausibility_based' } };
  assert.equal(credibilityScore(result), null);
  assert.match(assessmentLabel(result), /Highly unlikely/);
  assert.match(scoreDescription(result), /do not measure its probability/);
  assert.doesNotMatch(credibilityDetails(result), /15|85|\/100/);
});

test('forecast comparisons preserve their basis instead of proving future weather', () => {
  const result = { ...rated(0, .94), forecast_context: { risk_basis: 'forecast_comparison' } };
  assert.equal(assessmentLabel(result), 'Conflicts with current forecast');
  assert.match(scoreDescription(result), /not a probability of future weather/);
});

test('unverified policy changes and link safety retain their separate meanings', () => {
  const result = { assessment_outcome: 'unsupported', policy_context: { change_status: 'unverified' } };
  assert.equal(assessmentLabel(result), 'Not enough evidence');
  assert.match(scoreDescription(result), /assessed separately/);
  assert.equal(changeVerificationLabel('contradicted'), 'Contradicted by evidence');
  assert.equal(assessmentLabel({ input_type: 'link_safety', safety_status: 'no_known_threats' }), 'No known threats found');
});
