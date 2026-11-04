import { useEffect, useState } from 'react';
import { Button, ErrorBox, fmtDateTime } from './ui';
import { getReportImage } from '../services/api';
import { reportAssessmentView, safeEvidenceUrl } from '../utils/reportedAssessment';
import { researchAssessmentView } from '../utils/researchAssessment';

function ReportedImage({ user, reportId }) {
  const [image, setImage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => () => { if (image) URL.revokeObjectURL(image); }, [image]);
  async function load() {
    setBusy(true); setError(null);
    try { setImage(URL.createObjectURL(await getReportImage(user, reportId))); }
    catch (caught) { setError(caught); }
    finally { setBusy(false); }
  }
  return <div className="stack">
    <ErrorBox error={error} />
    {image ? <img src={image} alt="Image submitted with the reported check" style={{ maxWidth: '100%', maxHeight: 440, objectFit: 'contain' }} />
      : <Button secondary loading={busy} onClick={load}>Load reported image</Button>}
  </div>;
}

export default function ReportedAssessment({ assessment, reportId, user }) {
  const view = reportAssessmentView(assessment);
  const research = researchAssessmentView(assessment);
  return <>
    <dl className="definition">
      {(research?.fields || view.fields).map(([label, value]) => <div key={label}><dt>{label}</dt><dd style={{ overflowWrap: 'anywhere' }}>{value}</dd></div>)}
    </dl>
    {assessment.input_type === 'link_safety' && <p className="small muted">Reported URLs are displayed as text. The portal does not open or fetch them.</p>}
    {['image_context', 'deepfake_ai'].includes(assessment.input_type) && (assessment.has_saved_image
      ? <ReportedImage key={reportId} user={user} reportId={reportId} />
      : <p className="muted">No saved image is available for this result.</p>)}
    <h3>Explanation shown to the user</h3>
    <p>{research ? research.summary : view.explanation || 'No explanation was saved.'}</p>
    {research ? <>
      <p className="small muted">The findings below are AI assessments of cited information. They are not quotations from the sources or independent verification of their contents.</p>
      {research.findings.length > 0 && <><h3>Claims assessed</h3><ol className="evidence-list">
        {research.findings.map((finding, index) => <li key={index}>
          <strong>{finding.claim}</strong>
          <p><strong>{finding.label}</strong></p>
          <p>{finding.explanation}</p>
          {finding.inference && <p className="small muted">This finding is an inference from the available information.</p>}
          {finding.sources.length > 0 && <ul>{finding.sources.map(source => <li key={source.id}>
            <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a> <span className="small muted">({source.publisher})</span>
          </li>)}</ul>}
        </li>)}
      </ol></>}
      {research.limitations.length > 0 && <><h3>Limitations</h3><ul>{research.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
      {research.action && <p><strong>Recommended action:</strong> {research.action}</p>}
      <h3>Cited web sources ({research.sources.length})</h3>
      {research.checkedOn && <p className="small muted">Checked on {research.checkedOn} (Singapore date).</p>}
      {research.sources.length > 0 ? <ul className="evidence-list">{research.sources.map(source => <li key={source.id}>
        <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>
        <div className="small muted">{source.publisher}</div>
      </li>)}</ul> : <p className="small muted">No usable citation links were saved with this research assessment.</p>}
    </> : <>
    {view.visualEvidence.length > 0 && <><h3>Visual observations</h3><ul>{view.visualEvidence.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
    {view.limitations && <><h3>Limitations</h3><p>{view.limitations}</p></>}
    {assessment.recommended_action && <p><strong>Recommended action:</strong> {assessment.recommended_action}</p>}
    {assessment.warnings?.length > 0 && <><h3>Warnings</h3><ul>{assessment.warnings.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
    <h3>Evidence used ({view.evidence.length})</h3>
    {view.evidence.length === 0 ? <p className="muted small">No source passages were saved with this result.</p>
      : <ul className="evidence-list">{view.evidence.map((source, index) => <li key={source.evidence_id || index}>
        <strong>{source.publisher || source.title}</strong>{source.publisher && ` — ${source.title || ''}`}
        <div className="small muted">{source.stance || source.relationship} {source.source_type || ''}</div>
        <blockquote className="quote">{source.evidence_quote || source.quote || source.passage || source.summary}</blockquote>
        {source.summary && source.quote && <p>{source.summary}</p>}
        {safeEvidenceUrl(source.url) && <a href={source.url} target="_blank" rel="noreferrer">Open evidence source</a>}
      </li>)}</ul>}
    </>}
    <p className="small muted">Result created {fmtDateTime(assessment.created_at)} · user {assessment.user_mask}</p>
  </>;
}
