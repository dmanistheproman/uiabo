import assert from 'node:assert/strict';
import test from 'node:test';
import { webResearchDetails, researchShareText, researchSourceURL } from '../src/utils/webResearch.js';
import { assessmentLabel, credibilityRating, credibilityDetails } from '../src/utils/assessment.js';
import { resultPresentation } from '../src/utils/resultPresentation.js';

const source = { id: 'c1', title: 'Published policy', publisher: 'Official authority', url: 'https://example.gov.sg/policy' };
function result(verdict = 'likely_false', changes = {}) {
  return { processing_status: 'completed', original_text: 'The new policy starts in January.', checkable: true,
    assessment_outcome: 'likely_misinformation', misinformation_risk_score: 99,
    scoring: { version: 'evidence-v4', status: 'research_based' },
    research_assessment: { version: 'openai-web-v1', verdict, summary: 'The published information weighs against the claim.',
      sources: [source], as_of: '2026-11-03', recommended_action: 'Read the official announcement before sharing.',
      limitations: ['The information may change after this check.'],
      research_text: 'SECRET_RAW_REPORT \uE200cite\uE202turn0search0\uE201',
      findings: [{ claim: 'The new policy starts in January.', status: 'contradicted',
        explanation: 'The published start date differs.', source_ids: ['c1'], basis: 'bounded_inference' }],
      ...changes } };
}

for (const [verdict, label] of Object.entries({
  true: 'Strong evidence this is true', likely_true: 'Evidence suggests this is true', mixed: 'Mixed evidence',
  likely_false: 'Likely misinformation', false: 'Strong evidence this is false',
  insufficient_evidence: 'Not enough evidence', not_checkable: 'Not a factual claim',
})) {
  test(`research ${verdict} keeps its explicit headline without inventing a score`, () => {
    const record = result(verdict);
    assert.equal(assessmentLabel(record), label);
    assert.equal(resultPresentation(record).title, label);
    assert.equal(credibilityRating(record).score, null);
    assert.equal(credibilityRating(record).status, 'research_only');
    assert.doesNotMatch(credibilityDetails(record), /99|100|Not rated|Credibility score/);
  });
}

test('research findings have clickable known sources and explain inference', () => {
  const view = webResearchDetails(result());
  assert.equal(view.findings[0].label, 'Evidence weighs against this part');
  assert.equal(view.findings[0].sources[0].url, source.url);
  assert.equal(view.findings[0].inference, true);
  assert.equal(view.checkedOn, '3 November 2026');
});

test('unknown citations never create a source or decisive finding', () => {
  const view = webResearchDetails(result('likely_false', { findings: [
    { claim: 'A second claim.', status: 'supported', explanation: 'Fabricated supporting claim.', source_ids: ['c99'] },
  ] }));
  assert.equal(view.findings[0].status, 'unresolved');
  assert.deepEqual(view.findings[0].sources, []);
  assert.doesNotMatch(view.findings[0].explanation, /Fabricated/);
});

test('missing or malformed research fields fail softly without accepting a false verdict', () => {
  for (const fields of [{ verdict: 'unknown' }, { verdict: 'constructor' }, { summary: null },
    { version: 'future-schema' }, { sources: [] }]) {
    const view = webResearchDetails(result('false', fields));
    assert.equal(view.valid, false);
    assert.equal(view.title, 'Assessment details unavailable');
    assert.equal(resultPresentation(result('false', fields)).outcome, 'insufficient_evidence');
  }
  assert.doesNotThrow(() => webResearchDetails(result('insufficient_evidence', {
    findings: [null, {}, { claim: 'A claim.', source_ids: 'c1' }], sources: [null, {}], limitations: [null, {}], as_of: 'bad' })));
});

test('completed search without usable evidence can stay insufficient', () => {
  const view = webResearchDetails(result('insufficient_evidence', { sources: [], findings: [] }));
  assert.equal(view.title, 'Not enough evidence');
  assert.equal(view.valid, true);
});

test('bad and private links cannot become source buttons', () => {
  for (const url of ['javascript:alert(1)', 'file:///secrets', 'https://user:password@example.com/',
    'http://localhost/', 'http://localhost./', 'http://10.0.2.2/', 'http://127.1/', 'http://2130706433/',
    'http://[::1]/', 'http://router.local/', 'https://example.com:8000/', 'https://', null, {}]) {
    assert.equal(researchSourceURL(url), null, String(url));
  }
  assert.equal(researchSourceURL(source.url), source.url);
  assert.equal(webResearchDetails(result('false', { sources: [{ ...source, url: 'javascript:alert(1)' }] })).valid, false);
});

test('duplicate source IDs and missing source names are handled safely', () => {
  const view = webResearchDetails(result('likely_false', { sources: [{ ...source, title: null, publisher: null }, source] }));
  assert.equal(view.sources.length, 1);
  assert.equal(view.sources[0].title, 'example.gov.sg');
});

test('native citation tokens and the raw research report are never in the view or share text', () => {
  const record = result('likely_false', { summary: 'The policy differs. \uE200cite\uE202turn0search0\uE201' });
  const view = webResearchDetails(record);
  assert.equal(view.summary, 'The policy differs.');
  const shared = researchShareText(record);
  assert.match(shared, /https:\/\/example.gov.sg\/policy/);
  assert.match(shared, /3 November 2026/);
  assert.doesNotMatch(JSON.stringify(view) + shared, /SECRET_RAW_REPORT|turn0search0|\uE200|source_ids|research_only/);
});

test('failed and legacy records retain the existing rendering path', () => {
  const failed = { ...result(), processing_status: 'failed' };
  assert.equal(webResearchDetails(failed), null);
  assert.equal(resultPresentation(failed).title, 'We could not finish this check');
  assert.equal(assessmentLabel(failed), 'Unable to check');
  assert.equal(webResearchDetails({ assessment_outcome: 'supported' }), null);
  assert.equal(researchShareText({ assessment_outcome: 'supported' }), null);
});

test('invalid calendar dates are not displayed as a fabricated check date', () => {
  assert.equal(webResearchDetails(result('likely_false', { as_of: '2026-02-31' })).checkedOn, '');
});
