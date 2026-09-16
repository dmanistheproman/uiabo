import assert from 'node:assert/strict';
import test from 'node:test';
import { resultPresentation, plainSourceStance, datePresentation } from '../src/utils/resultPresentation.js';

test('uncertainty never becomes a danger rating', () => {
  const result = resultPresentation({ assessment_outcome: 'insufficient_evidence', uncertainty: 'High' });
  assert.equal(result.title, 'We could not confirm this');
  assert.match(result.meaning, /true or false/);
  assert.doesNotMatch(result.title, /danger|incorrect|risk/i);
});

test('unsupported is visibly different from contradicted', () => {
  const unconfirmed = resultPresentation({ assessment_outcome: 'unsupported' });
  const contradicted = resultPresentation({ assessment_outcome: 'contradicted' });
  assert.equal(unconfirmed.title, 'This claim is not confirmed');
  assert.match(unconfirmed.meaning, /does not prove the claim is false/);
  assert.equal(contradicted.title, 'This claim appears incorrect');
});

test('an unverified future change keeps the date limitation in the plain explanation', () => {
  const result = resultPresentation({ assessment_outcome: 'unsupported', policy_context: { change_status: 'unverified' } });
  assert.match(result.meaning, /future change/);
  assert.match(result.action, /official announcement/);
});

test('old saved results use their verdict without reversing uncertainty', () => {
  const supported = resultPresentation({ concern_label: 'Low Concern', uncertainty: 'High' });
  assert.equal(supported.outcome, 'supported');
  assert.match(supported.action, /mistake/);
  const unknown = resultPresentation({ concern_label: 'Not Enough Information', date_context: { is_future: true } });
  assert.match(unknown.meaning, /future change/);
});

test('zero never becomes a guarantee of truth', () => {
  const result = resultPresentation({ assessment_outcome: 'supported', misinformation_risk_score: 0 });
  assert.equal(result.title, 'The sources support this claim');
  assert.match(result.action, /mistake/);
});

test('numeric score cannot override the explicit conflict verdict', () => {
  assert.equal(resultPresentation({ assessment_outcome: 'conflicting', misinformation_risk_score: 20 }).title, 'The sources disagree');
});

test('failures and opinions do not receive truth verdicts', () => {
  assert.equal(resultPresentation({ processing_status: 'failed', concern_label: 'High Concern' }).outcome, 'failed');
  assert.match(resultPresentation({ checkable: false }).title, /cannot be fact-checked/);
});

test('unknown records do not gain a verdict from their number', () => {
  assert.equal(resultPresentation({ misinformation_risk_score: 0 }).outcome, 'insufficient_evidence');
});

test('source stance is described in words', () => {
  assert.equal(plainSourceStance('neutral'), 'Does not settle the claim');
  assert.equal(plainSourceStance('contradicting'), 'Disagrees with the claim');
});

test('forecast mismatch is not presented as proof that future weather is impossible', () => {
  const result = resultPresentation({ assessment_outcome: 'unsupported', misinformation_risk_score: 50,
    forecast_context: { status: 'not_supported_by_forecast' }, date_context: { is_future: true } });
  assert.equal(result.title, 'Not supported by the current forecast');
  assert.match(result.meaning, /not a guarantee/);
  assert.doesNotMatch(result.meaning, /future change|proves|impossible/);
});

test('matching a temperature does not verify unresolved parts of a compound claim', () => {
  const partial = resultPresentation({ assessment_outcome: 'unsupported',
    forecast_context: { status: 'supported_by_forecast' } });
  assert.equal(partial.title, 'The forecast supports part of this claim');
  assert.match(partial.meaning, /does not confirm every part/);
  const supported = resultPresentation({ assessment_outcome: 'supported',
    forecast_context: { status: 'supported_by_forecast' } });
  assert.equal(supported.title, 'The reported forecast matches');
});

test('incomplete or disagreeing forecasts stay distinct from a supported forecast', () => {
  assert.equal(resultPresentation({ forecast_context: { status: 'unresolved' } }).title, 'We could not compare the full forecast');
  assert.equal(resultPresentation({ forecast_context: { status: 'mixed' } }).title, 'The forecasts differ');
  assert.equal(resultPresentation({ processing_status: 'failed', forecast_context: { status: 'supported_by_forecast' } }).outcome, 'failed');
  assert.equal(resultPresentation({ assessment_outcome: 'contradicted', forecast_context: { status: 'unresolved' } }).title, 'This claim appears incorrect');
});

test('relative dates show the submission-time assumption and can be corrected', () => {
  const date = datePresentation({ basis: 'relative_submission_date', claim_text: 'this weekend', display_date: '19–20 September 2026' });
  assert.match(date.explanation, /this weekend/);
  assert.match(date.explanation, /19–20 September 2026/);
  assert.match(date.explanation, /Singapore time when you submitted/);
  assert.match(date.caution, /older forwarded message/);
  assert.equal(date.action, 'Change the dates');
});

test('a partial forecast comparison never hides a decisive whole-claim finding', () => {
  for (const status of ['unresolved', 'supported_by_forecast', 'not_supported_by_forecast', 'mixed']) {
    assert.equal(resultPresentation({ assessment_outcome: 'contradicted', forecast_context: { status } }).title,
      'This claim appears incorrect');
    assert.equal(resultPresentation({ assessment_outcome: 'conflicting', forecast_context: { status } }).title,
      'The sources disagree');
  }
  assert.equal(resultPresentation({ assessment_outcome: 'supported',
    forecast_context: { status: 'not_supported_by_forecast' } }).title, 'The sources support this claim');
});

test('explicit dates do not claim the user omitted a year', () => {
  const date = datePresentation({ basis: 'explicit_date', display_date: '19 September 2026' });
  assert.match(date.explanation, /dates stated in your message/);
  assert.doesNotMatch(date.explanation, /did not include a year/);
  assert.equal(datePresentation({ display_date: 'November 2026' }).action, 'Change the year');
  assert.equal(datePresentation(null), null);
});
