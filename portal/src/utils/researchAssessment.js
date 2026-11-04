const labels = {
  true: 'Strong evidence this is true', likely_true: 'Evidence suggests this is true',
  mixed: 'Mixed evidence', likely_false: 'Likely misinformation', false: 'Strong evidence this is false',
  insufficient_evidence: 'Not enough evidence', not_checkable: 'Not a factual claim',
};

const clean = value => typeof value === 'string'
  ? value.replace(/\uE200[^\uE201]*\uE201/g, '').replace(/[\uE200-\uE20F]/g, '').trim() : '';

function sourceUrl(value) {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value)) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password
        || !host || host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local')
        || host.startsWith('[') || /^\d+(\.\d+)*$/.test(host) || !host.includes('.')
        || (url.port && !['80', '443'].includes(url.port))) return null;
    return url.href;
  } catch { return null; }
}

function checkedDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return '';
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : '';
}

export function researchAssessmentView(assessment) {
  if (!assessment?.research_assessment) return null;
  const research = assessment.research_assessment;
  const fallback = () => ({ valid: false,
    fields: [['Claim checked', clean(assessment.extracted_claim || assessment.original_text)],
      ['Assessment label', 'Assessment details unavailable']],
    summary: 'The saved research assessment is incomplete. This is not a verdict that the claim is true or false.',
    findings: [], sources: [], limitations: [], action: '', checkedOn: '' });
  if (research.version !== 'openai-web-v1' || !Object.hasOwn(labels, research.verdict) || !clean(research.summary)) return fallback();
  const seen = new Set();
  const sources = (Array.isArray(research.sources) ? research.sources : []).flatMap(source => {
    const url = sourceUrl(source?.url);
    if (!url || !/^c(?:[1-9]|1\d|20)$/.test(source?.id) || seen.has(source.id)) return [];
    seen.add(source.id);
    return [{ id: source.id, url, title: clean(source.title) || new URL(url).hostname,
      publisher: clean(source.publisher) || new URL(url).hostname }];
  });
  if (!sources.length && !['insufficient_evidence', 'not_checkable'].includes(research.verdict)) return fallback();
  const findings = (Array.isArray(research.findings) ? research.findings : []).flatMap(finding => {
    if (!clean(finding?.claim)) return [];
    const links = sources.filter(source => Array.isArray(finding.source_ids) && finding.source_ids.includes(source.id));
    const status = ['supported', 'contradicted', 'mixed', 'unresolved'].includes(finding.status)
      && (finding.status === 'unresolved' || links.length) ? finding.status : 'unresolved';
    return [{ claim: clean(finding.claim), label: { supported: 'Supported by the sources',
      contradicted: 'Evidence weighs against this part', mixed: 'Mixed evidence for this part',
      unresolved: 'This part could not be established' }[status],
    explanation: status === finding.status ? clean(finding.explanation)
      : 'The saved evidence references for this finding are incomplete.',
    inference: status !== 'unresolved' && finding.basis === 'bounded_inference', sources: links }];
  });
  const checkedOn = checkedDate(research.as_of);
  return { valid: true, fields: [
    ['Claim checked', clean(assessment.extracted_claim || assessment.original_text)],
    ['Assessment label', labels[research.verdict]], ['Checked on (Singapore date)', checkedOn],
    ['Provider', 'OpenAI'], ['Model', clean(research.model)],
  ].filter(([, value]) => value), summary: clean(research.summary), checkedOn, findings, sources,
  limitations: (Array.isArray(research.limitations) ? research.limitations : []).map(clean).filter(Boolean),
  action: clean(research.recommended_action) };
}
