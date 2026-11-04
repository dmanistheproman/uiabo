import assert from 'node:assert/strict';
import test from 'node:test';
import { researchAssessmentView } from '../src/utils/researchAssessment.js';

const source = { id: 'c1', title: 'Current policy', url: 'https://example.gov.sg/policy', publisher: 'Official authority' };
const record = (changes = {}) => ({ original_text: 'A new rule has been announced.', evidence: [],
  misinformation_risk_score: 99, research_assessment: { version: 'openai-web-v1', verdict: 'likely_false',
    summary: 'The current announcement weighs against this claim.', sources: [source],
    findings: [{ claim: 'A new rule has been announced.', status: 'contradicted', source_ids: ['c1'],
      explanation: 'The announcement describes a different rule.', basis: 'bounded_inference' }],
    limitations: ['This check cannot rule out unpublished discussions.'], recommended_action: 'Read the announcement.',
    provider: 'openai', model: 'research-model', as_of: '2026-11-03', research_text: 'RAW_REPORT_DO_NOT_SHOW', ...changes } });

test('research portal view retains claim findings, citation links and dates with no invented score', () => {
  const view = researchAssessmentView(record());
  assert.equal(view.valid, true);
  assert.equal(view.findings[0].sources[0].url, source.url);
  assert.equal(view.findings[0].inference, true);
  assert.equal(view.checkedOn, '2026-11-03');
  assert.equal(view.sources.length, 1);
  assert.deepEqual(view.fields.find(([label]) => label === 'Assessment label'), ['Assessment label', 'Likely misinformation']);
  assert.ok(!view.fields.some(([label]) => /score|uncertainty|outcome/i.test(label)));
  assert.doesNotMatch(JSON.stringify(view), /RAW_REPORT_DO_NOT_SHOW|research_text|source_ids|99/);
});

test('all research verdicts receive readable labels', () => {
  for (const [verdict, label] of Object.entries({ true: 'Strong evidence this is true', likely_true: 'Evidence suggests this is true',
    mixed: 'Mixed evidence', likely_false: 'Likely misinformation', false: 'Strong evidence this is false',
    insufficient_evidence: 'Not enough evidence', not_checkable: 'Not a factual claim' })) {
    const view = researchAssessmentView(record({ verdict }));
    assert.deepEqual(view.fields.find(([name]) => name === 'Assessment label'), ['Assessment label', label]);
  }
});

test('legacy image, link and text reports keep the existing rendering path', () => {
  for (const input_type of ['deepfake_ai', 'image_context', 'link_safety', 'text']) {
    assert.equal(researchAssessmentView({ input_type, evidence: [] }), null);
  }
});

test('malformed research records fail softly without a false decisive label', () => {
  for (const changes of [{ verdict: 'constructor' }, { version: 'other' }, { summary: null }, { sources: [] }]) {
    assert.equal(researchAssessmentView(record(changes)).valid, false);
  }
  const malformed = researchAssessmentView(record({ verdict: 'insufficient_evidence', sources: [null, {}],
    findings: [null, {}, { claim: 'A claim.', status: 'supported', source_ids: 'c1' }], limitations: [null, {}] }));
  assert.equal(malformed.valid, true);
  assert.equal(malformed.findings[0].label, 'This part could not be established');
});

test('unknown citation references do not manufacture supporting findings', () => {
  const view = researchAssessmentView(record({ findings: [{ claim: 'Claim', status: 'supported',
    explanation: 'Unsupported generated assertion.', source_ids: ['c99'] }] }));
  assert.equal(view.findings[0].label, 'This part could not be established');
  assert.deepEqual(view.findings[0].sources, []);
  assert.doesNotMatch(view.findings[0].explanation, /Unsupported generated assertion/);
});

test('unsafe URLs cannot become citation links and duplicate citations are removed', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,test', 'http://localhost/', 'http://127.1/',
    'https://name:password@example.com/', 'http://[::1]/', 'http://router.local/', 'https://example.com:8000/']) {
    assert.equal(researchAssessmentView(record({ sources: [{ ...source, url }] })).valid, false, url);
  }
  assert.equal(researchAssessmentView(record({ sources: [source, source] })).sources.length, 1);
});

test('native citation markup and impossible dates do not reach portal text', () => {
  const view = researchAssessmentView(record({ summary: 'Readable summary. \uE200cite\uE202turn0search0\uE201',
    as_of: '2026-02-31', sources: [{ ...source, title: null, publisher: null }] }));
  assert.equal(view.summary, 'Readable summary.');
  assert.equal(view.checkedOn, '');
  assert.equal(view.sources[0].title, 'example.gov.sg');
  assert.doesNotMatch(JSON.stringify(view), /turn0search0|\uE200/);
});
