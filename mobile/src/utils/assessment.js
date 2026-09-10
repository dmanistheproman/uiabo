const labels = {
  supported: 'Supported by evidence',
  contradicted: 'Contradicted by evidence',
  unsupported: 'Not supported by policy checked',
  conflicting: 'Conflicting evidence',
  insufficient_evidence: 'Insufficient evidence',
  not_checkable: 'Not a checkable factual claim',
};

export function assessmentLabel(result) {
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
