const labels = {
  supported: 'Supported by evidence',
  contradicted: 'Contradicted by evidence',
  unsupported: 'Not supported by policy checked',
  conflicting: 'Conflicting evidence',
  insufficient_evidence: 'Insufficient evidence',
  not_checkable: 'Not a checkable factual claim',
};

export function isProvisionalScore(result) {
  return result.processing_status !== 'failed'
    && result.checkable !== false
    && result.scoring?.version === 'evidence-v3'
    && result.scoring.status === 'provisional'
    && result.misinformation_risk_score === 50
    && ['insufficient_evidence', 'unsupported'].includes(result.assessment_outcome);
}

export function assessmentLabel(result) {
  if (result.input_type === 'link_safety') {
    if (result.processing_status === 'failed') return 'Unable to check';
    if (result.safety_status === 'threat_detected') return 'Potentially dangerous link';
    return result.safety_status === 'no_known_threats' ? 'No known threats found' : 'Unable to check';
  }
  if (result.processing_status === 'failed') return 'Failed';
  if (isProvisionalScore(result)) return 'Unverified';
  if (result.assessment_outcome === 'unsupported' && result.policy_context) return 'Claim not supported by official evidence';
  return labels[result.assessment_outcome] || result.concern_label;
}

export const comparisonAspects = {
  amount: 'Amount', frequency: 'Payment frequency', population: 'Affected people',
  start_date: 'Start date', requirement: 'Requirement', other: 'Policy detail',
};

export const comparisonFindings = {
  matches: 'Matches the quoted rule', differs: 'Differs from the quoted rule', unresolved: 'Not established',
};

export function scoreDescription(result) {
  if (isProvisionalScore(result)) return '50 is a neutral starting point because we could not confirm or disprove this claim. It does not mean a 50% chance that the claim is false.';
  if (result.misinformation_risk_score == null) {
    if (result.policy_context?.change_status === 'unverified') return 'The published rule and the alleged change are assessed separately. An unverified change is not a proven falsehood.';
    return result.assessment_outcome === 'not_checkable'
      ? 'No checkable factual claim was identified. This is not a zero-risk finding.'
      : 'The evidence does not establish a complete verdict. Missing evidence is not proof of truth or falsity.';
  }
  if (!result.scoring) return 'This saved result uses the earlier scoring rules. Submit a new check to use the updated assessment.';
  if (result.assessment_outcome === 'conflicting') return 'Applicable evidence exists on both sides. The number reflects their relative strength; read both sides before deciding.';
  if (result.misinformation_risk_score === 0) return 'No misinformation concern identified in the evidence checked. This does not guarantee the claim is true.';
  return 'Lower means stronger support; higher means stronger contradiction. This is an evidence indicator, not a percentage chance of being false.';
}

export function changeVerificationLabel(status) {
  return { unverified: 'Unverified', supported: 'Supported by evidence', contradicted: 'Contradicted by evidence', conflicting: 'Conflicting evidence' }[status] || 'Unverified';
}
