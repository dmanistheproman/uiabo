import assert from 'node:assert/strict';
import test from 'node:test';
import { reportOptions, canReport } from '../src/utils/resultReporting.js';

test('reports are available only for completed saved results', () => {
  for (const input_type of ['text', 'image_text', 'deepfake_ai', 'image_context', 'link_safety']) {
    assert.equal(canReport({ result_id: 'a', input_type, processing_status: 'completed' }), true);
    assert.equal(canReport({ result_id: 'a', input_type, processing_status: 'failed' }), false);
  }
  assert.equal(canReport({ processing_status: 'completed' }), false);
});

test('report reasons distinguish model confidence from credibility and do not invent link/image-context scores', () => {
  assert.ok(reportOptions({ input_type: 'deepfake_ai' }).find(item => item.value === 'wrong_score').label.includes('confidence'));
  assert.ok(reportOptions({ input_type: 'text' }).find(item => item.value === 'wrong_score').label.includes('credibility'));
  for (const input_type of ['image_context', 'link_safety']) {
    assert.equal(reportOptions({ input_type }).some(item => item.value === 'wrong_score'), false);
  }
});
