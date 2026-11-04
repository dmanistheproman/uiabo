export function safeEvidenceUrl(url) {
  try { return ['https:', 'http:'].includes(new URL(url).protocol); } catch { return false; }
}

export function reportAssessmentView(record) {
  const fields = [];
  const add = (name, value) => { if (value !== null && value !== undefined && value !== '') fields.push([name, String(value)]); };
  const percent = value => typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : 'Not available';
  if (record.input_type === 'deepfake_ai') {
    add('Image filename', record.filename); add('Model classification', record.label);
    add('Model confidence', percent(record.confidence));
    add('Real model score', percent(record.real_probability)); add('AI-generated model score', percent(record.fake_probability));
  } else if (record.input_type === 'image_context') {
    add('Image filename', record.image_filename); add('Caption checked', record.extracted_caption); add('Concern label', record.concern_label);
  } else if (record.input_type === 'link_safety') {
    add('Submitted link', record.submitted_url); add('Checked link', record.checked_url);
    add('Safety result', record.safety_status === 'threat_detected' ? 'Threat detected' : 'No known threats found');
    add('Threat types', record.threat_types?.join(', ') || 'None returned'); add('Provider', record.provider);
    add('Checked at', record.checked_at); add('Cached result', record.cached ? 'Yes' : 'No');
  } else {
    add('Claim checked', record.extracted_claim || record.original_text); add('Concern label', record.concern_label);
    add('Assessment outcome', record.assessment_outcome); add('Risk score (stored)', record.misinformation_risk_score);
    add('Uncertainty', record.uncertainty);
  }
  const explanation = typeof record.explanation === 'object' && record.explanation !== null
    ? record.explanation : { reasoning: record.explanation };
  return { fields, explanation: explanation.reasoning, visualEvidence: explanation.visual_evidence || [],
    limitations: explanation.limitations || record.limitations, evidence: record.evidence_links || record.evidence || [] };
}
