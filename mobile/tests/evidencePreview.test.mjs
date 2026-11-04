import assert from 'node:assert/strict';
import test from 'node:test';
import { evidenceLink, evidencePlainText, inlineWords, parseEvidence, tableRows } from '../src/utils/evidenceMarkdown.js';
import { evidencePresentation } from '../src/utils/evidencePresentation.js';
import { credibilityDetails } from '../src/utils/assessment.js';

const quotation = `All Singapore Citizens are eligible for CHAS.

| CHAS Criteria | CHAS Green | CHAS Orange | CHAS Blue |
| --- | --- | --- | --- |
| **Household monthly income per person** | Above $2,300 | $1,501 - $2,300 | $1,500 and below |
| **Annual Value of home** | Above $31,000 | $21,001 - $31,000 | $21,000 and below |

*Annual Value is the estimated annual rent, excluding furnishings and maintenance fees.*`;

test('the saved CHAS quotation becomes a table without losing amounts, ranges or footnotes', () => {
  const blocks = parseEvidence(quotation);
  const rows = tableRows(blocks.find(node => node.type === 'table'));
  assert.equal(rows.length, 3);
  assert.equal(rows[0].length, 4);
  assert.equal(inlineWords(rows[0][2].children), 'CHAS Orange');
  assert.equal(inlineWords(rows[1][2].children), '$1,501 - $2,300');
  assert.equal(inlineWords(rows[2][3].children), '$21,000 and below');
  assert.equal(rows[1][0].children[0].children.find(node => node.type === 'strong').children[0].content, 'Household monthly income per person');
  assert.equal(blocks.at(-1).children[0].children[0].type, 'em');
  const plain = evidencePlainText(quotation);
  assert.match(plain, /excluding furnishings and maintenance fees/);
  assert.doesNotMatch(plain, /\*\*|---|\*Annual/);
});

test('headings, nested lists, quotations and escaped pipes retain their meaning', () => {
  const blocks = parseEvidence('# Eligibility\n\n- Not all residents qualify.\n  - Apply first.\n\n> No guarantee.\n\n| Option | Amount |\n|---|---|\n| A\\|B | $0.50 |');
  assert.deepEqual(blocks.map(node => node.type), ['heading', 'bullet_list', 'blockquote', 'table']);
  const cells = tableRows(blocks.at(-1))[1];
  assert.equal(inlineWords(cells[0].children), 'A|B');
  assert.equal(inlineWords(cells[1].children), '$0.50');
  assert.match(evidencePlainText('**Not** eligible.\n\n1. Apply.\n2. Wait.'), /Not eligible/);
});

test('links only resolve to http(s), including relative source links', () => {
  assert.equal(evidenceLink('/eligibility', 'https://www.chas.sg/FAQ'), 'https://www.chas.sg/eligibility');
  assert.equal(evidenceLink('https://moh.gov.sg/'), 'https://moh.gov.sg/');
  for (const url of ['javascript:alert(1)', 'data:text/html,hello', 'file:///test', 'intent://test', 'https://user:secret@example.com', '/relative', null]) {
    assert.equal(evidenceLink(url), null);
  }
});

test('source HTML stays inert text and image data is only a parsed reference', () => {
  const blocks = parseEvidence('<script>alert(1)</script>\n\n![Chart](https://example.com/image.png)');
  assert.equal(blocks[0].children[0].children[0].type, 'text');
  assert.equal(blocks[0].children[0].children[0].content, '<script>alert(1)</script>');
  assert.equal(blocks[1].children[0].children[0].type, 'image');
  assert.equal(evidencePlainText('[MOH](https://moh.gov.sg/)'), 'MOH');
});

function inference() {
  return { assessment_outcome: 'likely_misinformation', scoring: { status: 'inference_based' },
    explanation: `Likely misinformation. The official information states: "${quotation}". A future announcement could change this assessment.`,
    inference_context: { evidence_id: 'chas', baseline_quote: quotation, explanation: quotation },
    evidence: [{ evidence_id: 'chas', publisher: 'CHAS', title: 'Eligibility', url: 'https://www.chas.sg/Applying-for-CHAS/Eligibility' }] };
}

test('old saved inference gets a short explanation and an exact, attributed expandable quote', () => {
  const result = inference();
  const saved = structuredClone(result);
  const reading = evidencePresentation(result);
  assert.equal(reading.quote, quotation);
  assert.equal(reading.source.evidence_id, 'chas');
  assert.match(reading.explanation, /limited assessment/);
  assert.match(reading.explanation, /new information could change/);
  assert.doesNotMatch(reading.explanation, /\| CHAS|directly contradict|proves/);
  assert.ok(reading.explanation.length < 300);
  assert.deepEqual(result, saved);
  const note = credibilityDetails(result);
  assert.match(note, /Not rated/);
  assert.doesNotMatch(note, /CHAS|\| |\/100|50/);
});

test('unknown or incomplete result contracts keep the original explanation, not an invented summary', () => {
  for (const changes of [{ inference_context: null }, { evidence: [] }, { scoring: {} }, { assessment_outcome: 'supported' }]) {
    const result = { ...inference(), ...changes };
    assert.equal(evidencePresentation(result).explanation, result.explanation);
    assert.equal(evidencePresentation(result).quote, null);
  }
  assert.equal(evidencePresentation({}).explanation, '');
  assert.equal(evidencePlainText(null), '');
});

test('an unresolved credibility note does not repeat Not rated', () => {
  const note = credibilityDetails({ assessment_outcome: 'insufficient_evidence' });
  assert.equal((note.match(/not rated/ig) || []).length, 1);
  assert.match(note, /Missing evidence is not proof/);
});
