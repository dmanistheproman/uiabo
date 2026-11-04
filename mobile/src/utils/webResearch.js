const verdicts = {
  true: { title: 'Strong evidence this is true', outcome: 'supported', tone: 'positive' },
  likely_true: { title: 'Evidence suggests this is true', outcome: 'supported', tone: 'positive' },
  mixed: { title: 'Mixed evidence', outcome: 'conflicting', tone: 'caution' },
  likely_false: { title: 'Likely misinformation', outcome: 'likely_misinformation', tone: 'negative' },
  false: { title: 'Strong evidence this is false', outcome: 'contradicted', tone: 'negative' },
  insufficient_evidence: { title: 'Not enough evidence', outcome: 'insufficient_evidence', tone: 'caution' },
  not_checkable: { title: 'Not a factual claim', outcome: 'not_checkable', tone: 'neutral' },
};

const text = value => typeof value === 'string'
  ? value.replace(/\uE200[^\uE201]*\uE201/g, '').replace(/[\uE200-\uE20F]/g, '').trim() : '';

export function researchSourceURL(value) {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value)) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password
        || !host || host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local')
        || host.startsWith('[') || /^\d+(\.\d+)*$/.test(host)
        || !host.includes('.') || (url.port && !['80', '443'].includes(url.port))) return null;
    return url.href;
  } catch { return null; }
}

function dateLabel(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return '';
  const date = new Date(`${value}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) return '';
  return date.toLocaleDateString('en-SG', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}

const fallback = () => ({
  valid: false, title: 'Assessment details unavailable', outcome: 'insufficient_evidence', tone: 'caution',
  summary: 'We could not read the saved assessment details. This is not a verdict that the claim is true or false.',
  action: 'Check the message again to get a complete result.', findings: [], sources: [], limitations: [], checkedOn: '',
});

// Presentation only. Native search citations are bound and validated by the server.
// Never render research_text: its citation markers and raw provider output are not UI content.
export function webResearchDetails(result) {
  if (result?.processing_status === 'failed' || !result?.research_assessment) return null;
  const research = result.research_assessment;
  const verdict = Object.hasOwn(verdicts, research.verdict) ? verdicts[research.verdict] : null;
  if (research.version !== 'openai-web-v1' || !verdict || !text(research.summary)) return fallback();
  const seen = new Set();
  const sources = (Array.isArray(research.sources) ? research.sources : []).flatMap(source => {
    const url = researchSourceURL(source?.url);
    if (!source || !/^c(?:[1-9]|1\d|20)$/.test(source.id) || seen.has(source.id) || !url) return [];
    seen.add(source.id);
    return [{ id: source.id, url, title: text(source.title) || new URL(url).hostname,
      publisher: text(source.publisher) || new URL(url).hostname }];
  });
  if (!sources.length && !['insufficient_evidence', 'not_checkable'].includes(research.verdict)) return fallback();
  const findings = (Array.isArray(research.findings) ? research.findings : []).flatMap(finding => {
    if (!finding || !text(finding.claim)) return [];
    const ids = Array.isArray(finding.source_ids) ? finding.source_ids : [];
    const links = sources.filter(source => ids.includes(source.id));
    const status = ['supported', 'contradicted', 'mixed', 'unresolved'].includes(finding.status)
      && (finding.status === 'unresolved' || links.length) ? finding.status : 'unresolved';
    return [{ claim: text(finding.claim), status,
      label: { supported: 'Supported by the sources', contradicted: 'Evidence weighs against this part',
        mixed: 'Mixed evidence for this part', unresolved: 'This part could not be established' }[status],
      explanation: status !== finding.status
        ? 'The saved evidence for this part is incomplete. Read the available sources or check the message again.'
        : text(finding.explanation) || 'Read the cited sources to understand this finding.',
      inference: status !== 'unresolved' && finding.basis === 'bounded_inference', sources: links }];
  });
  return { valid: true, ...verdict, summary: text(research.summary), sources, findings,
    action: text(research.recommended_action) || 'Read the sources before sharing. Automated checks can make mistakes.',
    limitations: (Array.isArray(research.limitations) ? research.limitations : []).map(text).filter(Boolean),
    checkedOn: dateLabel(research.as_of) };
}

export function researchShareText(result) {
  const research = webResearchDetails(result);
  if (!research) return null;
  return [`UIABO result: ${research.title}`, text(result.extracted_claim || result.original_text),
    research.checkedOn ? `Checked on ${research.checkedOn} (Singapore date)` : '',
    `Why this result?\n${research.summary}`,
    ...research.findings.map((finding, index) => `${index + 1}. ${finding.claim}\n${finding.label}\n${finding.explanation}\n${finding.sources.map(source => source.url).join('\n')}`),
    research.limitations.length ? `What this check could not settle\n${research.limitations.join('\n')}` : '',
    research.action, `Sources:\n${research.sources.map(source => `${source.title}\n${source.url}`).join('\n\n')}`,
    'Automated checks can make mistakes.'].filter(Boolean).join('\n\n');
}
