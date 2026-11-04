import test from 'node:test';
import assert from 'node:assert/strict';
import { auditDateRange } from '../src/utils/audit.js';

test('audit windows use absolute UTC dates and do not change as pages advance', () => {
  const now = new Date('2026-11-02T12:00:00+08:00');
  const range = auditDateRange(7, now);
  assert.deepEqual(range, { from_time: '2026-10-26T04:00:00.000Z', to_time: '2026-11-02T04:00:00.000Z' });
  assert.throws(() => auditDateRange(365, now));
});
