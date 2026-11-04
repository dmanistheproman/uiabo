// Present the backend's validated assertion findings without creating a verdict.
export function verificationDetails(result) {
  const plan = result.verification_plan;
  const assessment = result.verification;
  if (result.processing_status === 'failed' || plan?.version !== 'verification-v1'
      || assessment?.version !== 'verification-v1' || !Array.isArray(plan.assertions)
      || !Array.isArray(assessment.findings)) return null;
  const evidence = Array.isArray(result.evidence) ? result.evidence : [];
  return plan.assertions.filter(part => part && typeof part.text === 'string').map(part => {
    const finding = assessment.findings.find(item => item.assertion_id === part.id);
    const quotes = (Array.isArray(finding?.citations) ? finding.citations : [])
      .map(item => ({ ...item, source: evidence.find(source => source.evidence_id === item.evidence_id) }))
      .filter(item => item.source && typeof item.quote === 'string' && item.quote.trim()
        && typeof item.source.passage === 'string' && item.source.passage.includes(item.quote));
    const valid = finding?.scope === 'established' && ['direct', 'inference'].includes(finding.basis)
      && quotes.length && quotes.length === finding.citations.length;
    const status = valid ? finding.status : 'unresolved';
    const explanation = finding?.explanation || 'We could not establish this part from the available evidence.';
    const labels = { supported: 'Evidence supports this part', contradicted: 'Evidence weighs against this part',
      conflicting: 'Mixed evidence for this part', unresolved: 'This part could not be established' };
    const basis = valid && finding.basis === 'inference'
      ? 'This finding combines facts from the cited evidence. Read the explanation to see how they connect.' : '';
    return { id: part.id, text: part.text, status: labels[status] || labels.unresolved, explanation,
      findings: [{ status: labels[status] || labels.unresolved, explanation, basis, quotes,
        limitation: (Array.isArray(finding?.gaps) ? finding.gaps : []).join(' ') }] };
  });
}
