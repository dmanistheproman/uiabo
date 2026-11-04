import test from 'node:test';
import assert from 'node:assert/strict';
import { controlFindings, controlLabel } from '../src/utils/controlInterpretations.js';
import { credibilityRating, assessmentLabel } from '../src/utils/assessment.js';
import { resultPresentation } from '../src/utils/resultPresentation.js';

const result = {
  processing_status: 'completed', assessment_outcome: 'insufficient_evidence',
  control_interpretations: { version: 'control-meanings-v1',
    operations: { outcome: 'contradicting', explanation: 'The company makes independent operational decisions.',
      citations: [{ evidence_id: 'source', quote: 'The company makes independent operational decisions.' }] },
    ownership: { outcome: 'unresolved', explanation: 'The ownership chain is incomplete.', citations: [] } },
};

test('conditional verdict is qualified in headline, history label and score explanation', () => {
  assert.match(controlLabel(result), /if referring to day-to-day management/);
  assert.equal(assessmentLabel(result), resultPresentation(result).title);
  assert.equal(credibilityRating(result).score, null);
  assert.match(credibilityRating(result).explanation, /different claims/);
  assert.equal(controlFindings(result)[1].status, 'Not established from these sources');
});

test('ownership support is not erased by an operational contradiction', () => {
  const copy = structuredClone(result);
  copy.control_interpretations.ownership = { outcome: 'supporting', explanation: 'The chain is established.',
    citations: [{ evidence_id: 'owner', quote: 'The chain is established.' }] };
  assert.equal(controlFindings(copy)[1].status, 'Evidence supports this meaning');
  assert.equal(credibilityRating(copy).score, null);
});

test('missing quotations and failed checks cannot show a conditional false finding', () => {
  const copy = structuredClone(result);
  copy.control_interpretations.operations.citations = [];
  assert.equal(controlLabel(copy), 'The meaning of control matters');
  assert.equal(controlLabel({ ...result, processing_status: 'failed' }), null);
  assert.equal(controlLabel({}), null);
});
