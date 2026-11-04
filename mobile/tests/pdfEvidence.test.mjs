import assert from 'node:assert/strict';
import { test } from 'node:test';
import { pdfSeriesTable } from '../src/utils/pdfEvidence.js';

test('PDF figures retain date, units and cohort in a preview table', () => {
  const table = pdfSeriesTable({points: [{date_label: "Jun'25", value: '39.0', unit: 'percent', cohort_label: '2025 cohort'}]});
  assert.ok(table.includes("Jun'25 | 39.0 % | 2025 cohort"));
});

test('source labels cannot create additional table rows or columns', () => {
  const table = pdfSeriesTable({points: [{date_label: 'A|B\nC', value: '10', unit: 'people'}]});
  assert.equal(table.split('\n').length, 3);
  assert.ok(table.includes('A\\|B C'));
  assert.ok(table.includes('Not specified'));
});
