const definition = 'Higher means the evidence supports the claim. Lower means the evidence contradicts it. This is an evidence indicator, not a percentage probability of truth. Even 0 or 100 is not a guarantee.';
const unresolved = ['insufficient_evidence', 'unsupported'];
const labels = {
  supported: 'Evidence suggests this is true',
  contradicted: 'Evidence suggests this is false',
  conflicting: 'Mixed evidence',
  insufficient_evidence: 'Not enough evidence',
  unsupported: 'Not enough evidence',
  not_checkable: 'Not a factual claim',
  highly_unlikely: 'Highly unlikely based on climate records',
};

export function isProvisionalScore(result) {
  return result.processing_status !== 'failed' && result.checkable !== false
    && result.scoring?.status === 'provisional'
    && unresolved.includes(result.assessment_outcome);
}

// Read old records without changing their stored risk fields. Never infer a
// credibility score from a bare legacy number or a provisional midpoint.
export function credibilityRating(result) {
  const outcome = result.assessment_outcome;
  const summary = result.scoring;
  const unscored = (status, explanation) => ({ status, score: null,
    label: labels[outcome] || 'Not enough evidence', explanation });
  if (result.processing_status === 'failed' || result.input_type === 'link_safety') {
    return unscored('not_applicable', 'No factual credibility score is assigned to this check.');
  }
  if (result.checkable === false || outcome === 'not_checkable') {
    return unscored('not_applicable', 'No checkable factual claim was identified. Not rated does not mean true or false.');
  }
  if (outcome === 'highly_unlikely' || summary?.status === 'plausibility_based') {
    return unscored('plausibility_only', 'Climate records make this prediction implausible, but do not measure its probability or prove future weather impossible. No factual credibility score is assigned.');
  }
  if (unresolved.includes(outcome) || result.concern_label === 'Not Enough Information'
      || ['provisional', 'not_applicable'].includes(summary?.status)) {
    return unscored('insufficient_evidence', 'Not rated: there is not enough relevant evidence to assess this claim. Missing evidence is not proof that it is true or false.');
  }
  const s = summary?.supporting_strength;
  const c = summary?.contradicting_strength;
  const validStrength = value => Number.isFinite(value) && (value === 0 || (value >= 0.6 && value <= 1));
  const validOrigins = (strength, count) => Number.isInteger(count) && count >= 0 && Boolean(strength) === Boolean(count);
  const expectedOutcome = s && c ? 'conflicting' : s ? 'supported' : c ? 'contradicted' : null;
  if (!['evidence-v2', 'evidence-v3', 'evidence-v4'].includes(summary?.version)
      || (summary.version !== 'evidence-v2' && summary.status !== 'evidence_based')
      || !validStrength(s) || !validStrength(c) || !expectedOutcome || outcome !== expectedOutcome
      || !validOrigins(s, summary.supporting_origins) || !validOrigins(c, summary.contradicting_origins)) {
    return unscored('legacy_unrated', 'This saved result does not contain enough evidence-scoring detail for the credibility scale. Check it again for an updated assessment.');
  }
  // Match Python's round-to-even at exact half points.
  const raw = Number((50 * (1 + s - c)).toFixed(8));
  const floor = Math.floor(raw);
  const score = raw - floor === 0.5 ? floor + (floor % 2) : Math.round(raw);
  const stored = result.credibility;
  const materialContradiction = outcome === 'contradicted'
    && summary.status === 'evidence_based'
    && result.component_assessment?.version === 'components-v1'
    && result.component_assessment.finding === 'material_contradiction';
  const label = outcome === 'conflicting' ? labels.conflicting
    : materialContradiction ? 'Likely misinformation'
    : s >= 0.9 ? 'Strong evidence this is true'
      : c >= 0.9 ? 'Strong evidence this is false'
        : outcome === 'contradicted' && stored?.version === 'credibility-v2' ? 'Likely misinformation' : labels[outcome];
  if (['credibility-v1', 'credibility-v2'].includes(stored?.version) && stored.status === 'rated'
      && stored.score === score && stored.label === label && typeof stored.explanation === 'string') return stored;
  return { status: 'rated', score, label,
    explanation: `${summary.supporting_origins} supporting and ${summary.contradicting_origins} contradicting source groups met the evidence checks. ${materialContradiction ? 'The evidence contradicts an important part of the message; this does not mean every part has been disproved. ' : ''}${outcome === 'conflicting' ? 'Credible evidence exists on both sides. Around 50 means their strengths are balanced, not that evidence is missing. ' : ''}${definition} This saved assessment is displayed in the credibility direction using its recorded evidence strengths; its original risk score has not been changed.` };
}

export function componentDetails(result) {
  const assessment = result.component_assessment;
  if (result.processing_status === 'failed' || assessment?.version !== 'components-v1'
      || !Array.isArray(assessment.components)) return [];
  const findings = Array.isArray(assessment.findings) ? assessment.findings : [];
  const evidence = Array.isArray(result.evidence) ? result.evidence : [];
  return assessment.components.filter(part => part && typeof part.text === 'string').map(part => {
    const seen = new Set();
    const partFindings = findings.filter(item => item?.component_id === part.component_id).map(finding => {
      const stance = finding.scope_matched === true && ['direct', 'inference'].includes(finding.basis)
        && ['supporting', 'contradicting'].includes(finding.stance) ? finding.stance : 'unresolved';
      const basis = stance === 'unresolved' ? '' : finding.basis === 'inference'
        ? 'This finding is an inference from the evidence, rather than an explicit statement by a source.'
        : 'The evidence directly addresses this part.';
      const quotes = (Array.isArray(finding.quotes) ? finding.quotes : [])
        .filter(item => item && typeof item.quote === 'string' && item.quote.trim())
        .map(item => ({ ...item, source: evidence.find(source => source.evidence_id === item.evidence_id) }))
        .filter(item => item.source);
      return { stance, basis, quotes,
        status: { supporting: 'Supports this part', contradicting: 'Weighs against this part',
          unresolved: 'Does not settle this part' }[stance],
        explanation: finding.explanation || 'We could not establish this part from the available evidence.',
        limitation: !finding.scope_matched
          ? 'We could not confirm that the evidence matches the circumstances of this part of the message.' : '',
      };
    }).filter(finding => {
      const key = JSON.stringify(finding);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    const supporting = partFindings.some(finding => finding.stance === 'supporting');
    const contradicting = partFindings.some(finding => finding.stance === 'contradicting');
    const status = supporting && contradicting ? 'Mixed evidence for this part'
      : supporting ? 'Evidence supports this part'
        : contradicting ? 'Evidence weighs against this part' : 'This part could not be established';
    return { id: part.component_id, text: part.text, status, findings: partFindings,
      explanation: supporting && contradicting ? 'Relevant sources disagree about this part. Read the supporting and contradicting evidence below.'
        : supporting || contradicting ? 'Read the evidence below to see the reasoning and any remaining limitations.'
          : 'We could not establish this part from the available evidence.',
    };
  });
}

export function credibilityScore(result) {
  return credibilityRating(result).score;
}

export function assessmentLabel(result) {
  if (result.input_type === 'link_safety') {
    if (result.processing_status === 'failed') return 'Unable to check';
    if (result.safety_status === 'threat_detected') return 'Potentially dangerous link';
    return result.safety_status === 'no_known_threats' ? 'No known threats found' : 'Unable to check';
  }
  if (result.processing_status === 'failed') return 'Unable to check';
  if (result.checkable === false) return labels.not_checkable;
  if (!result.assessment_outcome) {
    const previousOutcome = { 'Low Concern': 'supported', 'High Concern': 'contradicted',
      'Needs Caution': 'conflicting', 'Not Enough Information': 'insufficient_evidence' }[result.concern_label];
    return labels[previousOutcome] || 'Not enough evidence';
  }
  if (result.assessment_outcome === 'contradicted' && result.forecast_context?.risk_basis === 'forecast_comparison') return 'Conflicts with current forecast';
  return credibilityRating(result).label;
}

export function scoreDescription(result) {
  let explanation = credibilityRating(result).explanation;
  if (result.policy_context?.change_status === 'unverified' && credibilityScore(result) == null) {
    explanation += ' The published rule and the alleged change are assessed separately. An unverified change is not a proven falsehood.';
  }
  if (result.forecast_context?.risk_basis === 'forecast_comparison') {
    explanation += ' This compares the prediction with the current forecast; it is not a probability of future weather.';
  }
  return explanation;
}

export function credibilityDetails(result) {
  const score = credibilityScore(result);
  return `${score == null ? 'Credibility: Not rated.' : `Credibility score: ${score}/100.`} ${scoreDescription(result)}`;
}

export const comparisonAspects = {
  amount: 'Amount', frequency: 'Payment frequency', population: 'Affected people',
  start_date: 'Start date', requirement: 'Requirement', other: 'Policy detail',
};

export const comparisonFindings = {
  matches: 'Matches the quoted rule', differs: 'Differs from the quoted rule', unresolved: 'Not established',
};

export function changeVerificationLabel(status) {
  return { unverified: 'Unverified', supported: 'Supported by evidence', contradicted: 'Contradicted by evidence', conflicting: 'Conflicting evidence' }[status] || 'Unverified';
}
