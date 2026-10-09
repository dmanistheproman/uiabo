import assert from 'node:assert/strict';
import test from 'node:test';
import { assessmentLabel, componentDetails, credibilityDetails, credibilityRating, credibilityScore } from '../src/utils/assessment.js';
import { resultPresentation } from '../src/utils/resultPresentation.js';

function materialResult() {
  return {
    assessment_outcome: 'contradicted',
    scoring: { version: 'evidence-v4', status: 'evidence_based', supporting_strength: 0,
      contradicting_strength: .94, supporting_origins: 0, contradicting_origins: 1 },
    credibility: { version: 'credibility-v2', status: 'rated', score: 3, label: 'Likely misinformation',
      explanation: 'The evidence contradicts the stated financial premise; the alleged discussions remain unresolved.' },
    component_assessment: { version: 'components-v1', finding: 'material_contradiction',
      components: [
        { component_id: 'event', text: 'Officials are discussing a change.', kind: 'event', material: true },
        { component_id: 'premise', text: 'The fund is running out.', kind: 'premise', material: true },
        { component_id: 'cause', text: 'The fund problem is causing the change.', kind: 'causal_link', material: true },
      ],
      findings: [
        { component_id: 'event', stance: 'unresolved', basis: 'none', scope_matched: false,
          evidence_ids: [], quotes: [], explanation: 'The available sources do not establish the alleged discussion.' },
        { component_id: 'premise', stance: 'contradicting', basis: 'inference', scope_matched: true,
          evidence_ids: ['report'], quotes: [{ evidence_id: 'report', quote: 'The fund remains fully backed.' }],
          explanation: 'The relevant figures weigh against the alleged shortfall.' },
      ],
    },
    evidence: [{ evidence_id: 'report', publisher: 'Example official source', url: 'https://example.org/report' }],
  };
}

test('an important contradicted premise displays likely misinformation without asserting every part is false', () => {
  const result = materialResult();
  assert.equal(assessmentLabel(result), 'Likely misinformation');
  assert.equal(credibilityRating(result), result.credibility);
  assert.equal(credibilityScore(result), 3);
  assert.match(credibilityDetails(result), /financial premise.*remain unresolved/);
  const view = resultPresentation(result);
  assert.equal(view.title, 'Likely misinformation');
  assert.match(view.meaning, /Other parts may remain unresolved/);
  assert.match(view.action, /Do not share/);
  assert.doesNotMatch(view.meaning, /3\/100|Credibility score/);
});

test('each part shows evidence, inference and unresolved limitations separately', () => {
  const parts = componentDetails(materialResult());
  assert.equal(parts.length, 3);
  assert.equal(parts[0].status, 'This part could not be established');
  assert.equal(parts[0].findings[0].basis, '');
  assert.match(parts[0].findings[0].limitation, /matches the circumstances/);
  assert.equal(parts[1].status, 'Evidence weighs against this part');
  assert.match(parts[1].findings[0].basis, /inference/);
  assert.equal(parts[1].findings[0].quotes[0].source.publisher, 'Example official source');
  assert.equal(parts[2].status, 'This part could not be established');
  assert.match(parts[2].explanation, /could not establish/);
});

test('out of scope findings cannot be presented as decisive or fabricate sources', () => {
  const result = materialResult();
  result.component_assessment.findings[1].scope_matched = false;
  result.component_assessment.findings[1].quotes.push({ evidence_id: 'missing', quote: 'An unavailable quote.' });
  const premise = componentDetails(result)[1];
  assert.equal(premise.status, 'This part could not be established');
  assert.equal(premise.findings[0].basis, '');
  assert.equal(premise.findings[0].quotes.length, 1);
});

test('an unresolved first source does not hide a later contradiction of the same part', () => {
  const result = materialResult();
  result.component_assessment.findings.unshift({ component_id: 'premise', stance: 'unresolved', basis: 'none',
    scope_matched: false, evidence_ids: [], quotes: [], explanation: 'This source does not address the financial premise.' });
  const premise = componentDetails(result)[1];
  assert.equal(premise.status, 'Evidence weighs against this part');
  assert.equal(premise.findings.length, 2);
  assert.equal(premise.findings[0].status, 'Does not settle this part');
  assert.equal(premise.findings[1].status, 'Weighs against this part');
});

test('opposing sources for the same component both remain visible', () => {
  const result = materialResult();
  result.evidence.push({ evidence_id: 'support', publisher: 'Another source', url: 'https://example.org/other' });
  result.component_assessment.findings.push({ component_id: 'premise', stance: 'supporting', basis: 'direct',
    scope_matched: true, evidence_ids: ['support'], quotes: [{ evidence_id: 'support', quote: 'The fund has a shortfall.' }],
    explanation: 'A comparable report describes a shortfall.' });
  const premise = componentDetails(result)[1];
  assert.equal(premise.status, 'Mixed evidence for this part');
  assert.match(premise.explanation, /supporting and contradicting evidence/);
  assert.deepEqual(premise.findings.map(f => f.stance), ['contradicting', 'supporting']);
  assert.equal(premise.findings[1].quotes[0].source.publisher, 'Another source');
});

test('support for the event does not hide contradiction of the stated premise', () => {
  const result = materialResult();
  result.component_assessment.findings[0] = { component_id: 'event', stance: 'supporting', basis: 'direct',
    scope_matched: true, evidence_ids: ['report'], quotes: [{ evidence_id: 'report', quote: 'Officials are discussing the change.' }],
    explanation: 'The source confirms the discussion.' };
  const parts = componentDetails(result);
  assert.equal(parts[0].status, 'Evidence supports this part');
  assert.equal(parts[1].status, 'Evidence weighs against this part');
  assert.equal(assessmentLabel(result), 'Likely misinformation');
});

test('duplicate source findings are collapsed without dropping differing explanations', () => {
  const result = materialResult();
  const finding = result.component_assessment.findings[1];
  result.component_assessment.findings.push(structuredClone(finding), { ...finding, explanation: 'A distinct limitation applies.' });
  assert.equal(componentDetails(result)[1].findings.length, 2);
});

test('unresolved compound claims do not become misinformation merely because they were decomposed', () => {
  const result = materialResult();
  result.assessment_outcome = 'insufficient_evidence';
  result.scoring.status = 'provisional';
  result.component_assessment.finding = 'unresolved';
  assert.equal(assessmentLabel(result), 'Not enough evidence');
  assert.equal(credibilityScore(result), null);
  assert.equal(resultPresentation(result).title, 'Not enough evidence');
  assert.doesNotMatch(credibilityDetails(result), /\/100/);
});

test('a material contradiction flag cannot override missing or invalid scoring evidence', () => {
  for (const scoring of [undefined, { version: 'evidence-v4', status: 'provisional' },
    { version: 'evidence-v4', status: 'evidence_based', supporting_strength: 0,
      contradicting_strength: .2, supporting_origins: 0, contradicting_origins: 1 }]) {
    const result = { ...materialResult(), scoring };
    assert.equal(credibilityScore(result), null);
    assert.notEqual(assessmentLabel(result), 'Likely misinformation');
    assert.doesNotMatch(resultPresentation(result).meaning, /Other parts may remain unresolved/);
  }
});

test('new moderate contradiction label does not relabel old rated records', () => {
  const result = materialResult();
  delete result.component_assessment;
  result.scoring.contradicting_strength = .7;
  result.credibility.score = 15;
  assert.equal(assessmentLabel(result), 'Likely misinformation');
  result.credibility.version = 'credibility-v1';
  result.credibility.label = 'Evidence suggests this is false';
  assert.equal(assessmentLabel(result), 'Evidence suggests this is false');
  assert.equal(credibilityRating(result), result.credibility);
  delete result.credibility;
  assert.equal(assessmentLabel(result), 'Evidence suggests this is false');
});

test('new strong whole-claim contradiction stays separate from partial contradiction', () => {
  const result = materialResult();
  delete result.component_assessment;
  result.credibility.label = 'Strong evidence this is false';
  assert.equal(assessmentLabel(result), 'Strong evidence this is false');
  assert.equal(credibilityRating(result), result.credibility);
});

test('forecast and climate qualifications take precedence over component headlines', () => {
  const result = materialResult();
  result.forecast_context = { risk_basis: 'forecast_comparison' };
  assert.equal(assessmentLabel(result), 'Conflicts with current forecast');
  assert.match(resultPresentation(result).title, /conflicts with the forecast/);
  result.assessment_outcome = 'highly_unlikely';
  result.scoring.status = 'plausibility_based';
  assert.match(assessmentLabel(result), /Highly unlikely/);
  assert.equal(credibilityScore(result), null);
  assert.equal(resultPresentation(result).title, 'This prediction is highly unlikely');
});

test('failed, older and unknown component records remain readable', () => {
  assert.deepEqual(componentDetails({}), []);
  assert.deepEqual(componentDetails({ ...materialResult(), processing_status: 'failed' }), []);
  assert.deepEqual(componentDetails({ component_assessment: { version: 'future', components: [] } }), []);
});
