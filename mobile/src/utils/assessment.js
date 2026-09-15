const labels = {
  supported: 'Supported by evidence',
  contradicted: 'Contradicted by evidence',
  unsupported: 'Not supported by policy checked',
  conflicting: 'Conflicting evidence',
  insufficient_evidence: 'Insufficient evidence',
  not_checkable: 'Not a checkable factual claim',
};

export function assessmentLabel(result) {
  if (result.input_type === 'link_safety') {
    if (result.processing_status === 'failed') return 'Unable to check';
    if (result.safety_status === 'threat_detected') return 'Potentially dangerous link';
    return result.safety_status === 'no_known_threats' ? 'No known threats found' : 'Unable to check';
  }
  if (result.processing_status === 'failed') return 'Failed';
  return labels[result.assessment_outcome] || result.concern_label;
}

export const comparisonAspects = {
  amount: 'Amount', frequency: 'Payment frequency', population: 'Affected people',
  start_date: 'Start date', requirement: 'Requirement', other: 'Policy detail',
};

export const comparisonFindings = {
  matches: 'Matches the quoted rule', differs: 'Differs from the quoted rule', unresolved: 'Not established',
};
