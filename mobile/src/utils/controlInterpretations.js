export function controlFindings(result) {
  const context = result.control_interpretations;
  if (result.processing_status === 'failed' || context?.version !== 'control-meanings-v1') return [];
  return ['operations', 'ownership'].map(key => {
    const finding = context[key] || {};
    const decisive = ['supporting', 'contradicting'].includes(finding.outcome)
      && finding.citations?.length > 0;
    return { key,
      title: key === 'operations' ? 'If you mean day-to-day management' : 'If you mean ownership or voting control',
      status: !decisive ? 'Not established from these sources'
        : finding.outcome === 'contradicting' ? 'Likely misinformation under this meaning'
          : 'Evidence supports this meaning',
      explanation: finding.explanation || 'We could not assess this meaning.',
      citations: finding.citations || [],
    };
  });
}

export function controlLabel(result) {
  const findings = controlFindings(result);
  if (!findings.length) return null;
  return findings[0].status === 'Likely misinformation under this meaning'
    ? 'Likely misinformation — if referring to day-to-day management'
    : 'The meaning of control matters';
}
