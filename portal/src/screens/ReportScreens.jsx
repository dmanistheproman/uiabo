import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import {
  Badge, Button, Card, EmptyState, ErrorBox, Loading, StatusBadge,
  REPORT_REASON_LABELS, fmtDateTime, shortId,
} from '../components/ui';
import { getReport, listReports, updateReport } from '../services/api';

const STATUS_FILTERS = ['', 'open', 'reviewing', 'resolved', 'dismissed'];
const NEXT_STATUS = {
  open: ['reviewing', 'resolved', 'dismissed'],
  reviewing: ['resolved', 'dismissed'],
  resolved: ['reviewing'],
  dismissed: ['reviewing'],
};

export function ReportsScreen({ onOpenReport }) {
  const { firebaseUser } = useAuth();
  const [status, setStatus] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [reports, setReports] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (nextCursor) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listReports(firebaseUser, {
        status: status || undefined,
        from: from ? new Date(from).toISOString() : undefined,
        to: to ? new Date(to).toISOString() : undefined,
        limit: 20,
        cursor: nextCursor || undefined,
      });
      setReports((previous) => (nextCursor ? [...previous, ...data.reports] : data.reports));
      setCursor(data.next_cursor);
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [firebaseUser, status, from, to]);

  useEffect(() => { setReports([]); load(); }, [status, from, to, load]);

  return (
    <div className="stack">
      <div className="toolbar"><h1>Incorrect-result reports</h1></div>
      <Card>
        <div className="filters">
          <label className="inline-label">Status
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              {STATUS_FILTERS.map((value) => (
                <option key={value} value={value}>{value ? value : 'All'}</option>
              ))}
            </select>
          </label>
          <label className="inline-label">From
            <input type="datetime-local" value={from} onChange={(event) => setFrom(event.target.value)} />
          </label>
          <label className="inline-label">To
            <input type="datetime-local" value={to} onChange={(event) => setTo(event.target.value)} />
          </label>
        </div>
        <ErrorBox error={error} onRetry={() => load()} />
        {loading && <Loading />}
        {!loading && reports.length === 0 && (
          <EmptyState>No reports match these filters. When users report incorrect results from the app, they appear here.</EmptyState>
        )}
        {reports.length > 0 && (
          <table className="table">
            <thead>
              <tr><th>Status</th><th>Reason</th><th>Concern label</th><th>Detail</th><th>Reported</th><th>Result</th></tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.report_id} className="clickable" onClick={() => onOpenReport(report.report_id)}>
                  <td><StatusBadge value={report.status} /></td>
                  <td>{REPORT_REASON_LABELS[report.reason]}</td>
                  <td>{report.snapshot.concern_label}</td>
                  <td className="small muted clipped">{report.detail}</td>
                  <td>{fmtDateTime(report.created_at)}</td>
                  <td className="mono small">{shortId(report.result_id, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {cursor && <Button secondary small onClick={() => load(cursor)}>Load more</Button>}
      </Card>
    </div>
  );
}

export function ReportDetailScreen({ reportId, onBack }) {
  const { firebaseUser } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [nextStatus, setNextStatus] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getReport(firebaseUser, reportId));
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [firebaseUser, reportId]);

  useEffect(() => { load(); }, [load]);

  async function save(event) {
    event.preventDefault();
    if (!nextStatus && !note.trim()) {
      setError(new Error('Choose a status or write a note first.'));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await updateReport(firebaseUser, reportId, {
        status: nextStatus || undefined,
        note: note.trim() || undefined,
      });
      setData((previous) => ({ ...previous, report: updated }));
      setNextStatus('');
      setNote('');
      setNotice('Investigation update saved.');
    } catch (caught) {
      setError(caught);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={load} />;
  const { report, assessment, result_missing: resultMissing } = data;

  return (
    <div className="stack">
      <div className="toolbar">
        <Button secondary small onClick={onBack}>← Back to reports</Button>
        <h1>Report {shortId(report.report_id, 14)}</h1>
        <StatusBadge value={report.status} />
      </div>

      {resultMissing && (
        <div className="error-box">
          <p>The associated analysis result is missing. Record the finding in the investigation notes.</p>
        </div>
      )}

      <div className="split-wide">
        <Card title="User report">
          <dl className="definition">
            <div><dt>Reason</dt><dd>{REPORT_REASON_LABELS[report.reason]}</dd></div>
            <div><dt>Reported by</dt><dd className="mono">{report.user_mask}</dd></div>
            <div><dt>Reported at</dt><dd>{fmtDateTime(report.created_at)}</dd></div>
            <div><dt>Input type</dt><dd>{report.input_type}</dd></div>
          </dl>
          <h3>What the user said</h3>
          <blockquote className="user-detail">{report.detail}</blockquote>
          <h3>Reported result snapshot</h3>
          <dl className="definition">
            <div><dt>Concern label</dt><dd>{report.snapshot.concern_label}</dd></div>
            <div><dt>Claim category</dt><dd>{report.snapshot.claim_category}</dd></div>
            <div><dt>Risk score</dt><dd>{report.snapshot.misinformation_risk_score ?? '—'}</dd></div>
            <div><dt>Uncertainty</dt><dd>{report.snapshot.uncertainty}</dd></div>
            <div><dt>Pipeline version</dt><dd className="mono small">{report.snapshot.pipeline_version}</dd></div>
            <div><dt>Result created</dt><dd>{fmtDateTime(report.snapshot.result_created_at)}</dd></div>
          </dl>
        </Card>

        <Card title="Generated assessment" subtitle="What the pipeline produced for this check.">
          {!assessment ? <EmptyState>The assessment record is unavailable.</EmptyState> : (
            <>
              <dl className="definition">
                <div><dt>Claim we checked</dt><dd>{assessment.extracted_claim || assessment.original_text}</dd></div>
                <div><dt>Concern label</dt><dd>{assessment.concern_label}</dd></div>
                <div><dt>Risk score</dt><dd>{assessment.misinformation_risk_score ?? '—'}</dd></div>
                <div><dt>Uncertainty</dt><dd>{assessment.uncertainty}</dd></div>
              </dl>
              <h3>Explanation shown to the user</h3>
              <p>{assessment.explanation}</p>
              {assessment.warnings?.length > 0 && (
                <><h3>Warnings</h3><ul>{assessment.warnings.map((warning, index) => <li key={index} className="small">{warning}</li>)}</ul></>
              )}
              <h3>Evidence used ({assessment.evidence?.length || 0})</h3>
              {(assessment.evidence?.length || 0) === 0 ? (
                <p className="muted small">No evidence was saved with this result.</p>
              ) : (
                <ul className="evidence-list">
                  {assessment.evidence.map((source) => (
                    <li key={source.evidence_id}>
                      <strong>{source.publisher}</strong> — {source.title}
                      <div className="small muted">{source.stance} · {source.source_type}</div>
                      <blockquote className="quote">{source.evidence_quote || source.passage}</blockquote>
                      {source.url && <a href={source.url} target="_blank" rel="noreferrer" className="small">Open source</a>}
                    </li>
                  ))}
                </ul>
              )}
              <p className="small muted">Result created {fmtDateTime(assessment.created_at)} · user {assessment.user_mask}</p>
            </>
          )}
        </Card>
      </div>

      <Card title="Investigation">
        {notice && <p className="notice">{notice}</p>}
        {report.review_note && (
          <p><strong>Latest note:</strong> {report.review_note} <span className="muted small">({fmtDateTime(report.reviewed_at)})</span></p>
        )}
        <form onSubmit={save} className="stack-form">
          <label className="inline-label">Set status
            <select value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}>
              <option value="">Keep {report.status}</option>
              {(NEXT_STATUS[report.status] || []).map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">Investigation note</span>
            <textarea value={note} maxLength={2000} rows={3}
              placeholder="What did you find? Reference the evidence above…"
              onChange={(event) => setNote(event.target.value)} />
          </label>
          <Button type="submit" loading={saving}>Save update</Button>
        </form>
        <h3>History</h3>
        <ul className="history">
          {report.history.map((entry, index) => (
            <li key={index}>
              <span className="mono small">{entry.actor_mask}</span>{' '}
              <Badge>{entry.action.replace(/_/g, ' ')}</Badge>{' '}
              <span className="small muted">{fmtDateTime(entry.at)}</span>
              {entry.status_to && <span className="small"> → {entry.status_to}</span>}
              {entry.note && <p className="small">{entry.note}</p>}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
