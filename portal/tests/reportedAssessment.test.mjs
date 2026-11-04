import assert from 'node:assert/strict';
import test from 'node:test';
import { reportAssessmentView, safeEvidenceUrl } from '../src/utils/reportedAssessment.js';

test('deepfake explanation object and model scores are preserved without a misinformation score', () => {
  const view = reportAssessmentView({ input_type: 'deepfake_ai', label: 'Fake', confidence: .94,
    real_probability: .06, fake_probability: .94, explanation: { reasoning: 'Artifact present', visual_evidence: ['Edge'], limitations: 'Can be wrong' } });
  assert.equal(view.explanation, 'Artifact present');
  assert.deepEqual(view.visualEvidence, ['Edge']);
  assert.equal(view.limitations, 'Can be wrong');
  assert.deepEqual(view.fields.find(([key]) => key === 'Model confidence'), ['Model confidence', '94.0%']);
  assert.ok(!view.fields.some(([key]) => key.includes('Risk')));
});

test('image context retains quoted evidence and the caption checked', () => {
  const evidence = [{ quote: 'Exact quote', relationship: 'contradicts' }];
  const view = reportAssessmentView({ input_type: 'image_context', extracted_caption: 'Claim', concern_label: 'High Concern', evidence_links: evidence });
  assert.deepEqual(view.evidence, evidence);
  assert.deepEqual(view.fields.find(([key]) => key === 'Caption checked'), ['Caption checked', 'Claim']);
});

test('link reports distinguish no known threats from guaranteed safety and retain provider details', () => {
  const view = reportAssessmentView({ input_type: 'link_safety', submitted_url: 'https://example.org', safety_status: 'no_known_threats', provider: 'Google Web Risk' });
  assert.ok(view.fields.some(([, value]) => value === 'No known threats found'));
  assert.ok(view.fields.some(([, value]) => value === 'https://example.org'));
  assert.equal(safeEvidenceUrl('javascript:alert(1)'), false);
  assert.equal(safeEvidenceUrl('data:text/html,test'), false);
  assert.equal(safeEvidenceUrl('https://example.org/source'), true);
});
