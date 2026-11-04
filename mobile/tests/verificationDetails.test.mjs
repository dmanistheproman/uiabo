import assert from 'node:assert/strict';
import test from 'node:test';
import { componentDetails } from '../src/utils/assessment.js';

function result() {
  return { verification_plan: { version: 'verification-v1', assertions: [
    { id: 'a1', text: 'The library closes at six.' },
    { id: 'a2', text: 'This is because funding was cut.' },
  ] }, verification: { version: 'verification-v1', findings: [
    { assertion_id: 'a1', status: 'contradicted', basis: 'direct', scope: 'established',
      explanation: 'The published closing time is eight.',
      citations: [{ evidence_id: 'hours', quote: 'Closes at eight.' }] },
    { assertion_id: 'a2', status: 'unresolved', basis: 'none', scope: 'unknown',
      explanation: 'The source does not establish a funding cut.', gaps: ['Funding decision'], citations: [] },
  ] }, evidence: [{ evidence_id: 'hours', publisher: 'Library', passage: 'Closes at eight.', url: 'https://example.org/hours' }] };
}

test('shows a material contradiction and unresolved cause separately', () => {
  const parts = componentDetails(result());
  assert.equal(parts.length, 2);
  assert.equal(parts[0].status, 'Evidence weighs against this part');
  assert.equal(parts[1].status, 'This part could not be established');
  assert.equal(parts[1].findings[0].limitation, 'Funding decision');
  assert.equal(parts[0].findings[0].quotes[0].source.publisher, 'Library');
});

test('a citation to a missing source cannot produce a decisive card', () => {
  const r = result();
  r.verification.findings[0].citations[0].evidence_id = 'invented';
  const part = componentDetails(r)[0];
  assert.equal(part.status, 'This part could not be established');
  assert.equal(part.findings[0].quotes.length, 0);
});

test('a fabricated quote is not displayed as evidence', () => {
  const r = result();
  r.verification.findings[0].citations[0].quote = 'Closes at six.';
  assert.equal(componentDetails(r)[0].findings[0].quotes.length, 0);
  assert.equal(componentDetails(r)[0].status, 'This part could not be established');
});

test('linked-source inference retains each quotation and explains the connection', () => {
  const r = result();
  r.verification.findings[0].basis = 'inference';
  r.evidence.push({ evidence_id: 'definition', passage: 'Eight means 20:00.', publisher: 'Library' });
  r.verification.findings[0].citations.push({ evidence_id: 'definition', quote: 'Eight means 20:00.' });
  const finding = componentDetails(r)[0].findings[0];
  assert.equal(finding.quotes.length, 2);
  assert.match(finding.basis, /combines facts/);
});

test('legacy results retain their existing presentation and failed results have no findings', () => {
  assert.deepEqual(componentDetails({}), []);
  assert.deepEqual(componentDetails({ ...result(), processing_status: 'failed' }), []);
});
