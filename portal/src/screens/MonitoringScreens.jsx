import React, { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import {
  Badge, Button, Card, Distribution, EmptyState, ErrorBox, Loading, Stat,
  TimeRange, TrendBars, daysToFrom, fmtDateTime, fmtDuration, shortId,
} from '../components/ui';
import {
  getRun, getReportSummary, getRunSummary, listIngestionRuns,
  addFollowUp, listRuns, triggerIngestionJob,
} from '../services/api';

export function DashboardScreen({ onOpenReports, onOpenMonitoring }) {
  const { firebaseUser } = useAuth();
  const [days, setDays] = useState(7);
  const [from, setFrom] = useState(() => daysToFrom(7));
  const [reportData, setReportData] = useState(null);
  const [runData, setRunData] = useState(null);
  const [ingestionData, setIngestionData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { from: daysToFrom(days) };
      const [reports, runs, ingestion] = await Promise.all([
        getReportSummary(firebaseUser, params),
        getRunSummary(firebaseUser, params),
        listIngestionRuns(firebaseUser, { limit: 50 }),
      ]);
      setReportData(reports);
      setRunData(runs);
      setIngestionData(ingestion);
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [firebaseUser, days]);

  useEffect(() => { setFrom(daysToFrom(days)); load(); }, [days, load]);

  return (
    <div className="stack">
      <div className="toolbar">
        <h1>Dashboard</h1>
        <div className="toolbar-controls">
          <TimeRange value={days} onChange={setDays} />
          <Button secondary small onClick={load}>Refresh</Button>
        </div>
      </div>
      <ErrorBox error={error} onRetry={load} />
      {loading && <Loading />}
      {!loading && reportData && (
        <>
          <Card title="Incorrect-result reports" subtitle="User reports awaiting investigation (UC-41).">
            <div className="stats">
              <Stat label="Total reports" value={reportData.total} />
              {Object.entries(reportData.by_status).map(([status, count]) => (
                <Stat key={status} label={status.replace('_', ' ')} value={count} />
              ))}
            </div>
            <div className="split">
              <Distribution title="By concern label" counts={reportData.by_concern_label} />
              <Distribution title="By pipeline version" counts={reportData.by_pipeline_version} />
              <Distribution title="By input type" counts={reportData.by_input_type} />
            </div>
            <h3>Report volume per day</h3>
            <TrendBars trend={reportData.trend} />
            <Button secondary small onClick={onOpenReports}>Open report list</Button>
          </Card>

          <Card title="Analysis requests" subtitle="Pipeline runs with timing and failures (UC-43).">
            <div className="stats">
              <Stat label="Runs" value={runData?.total} />
              <Stat label="Completed" value={runData?.completed} tone="green" />
              <Stat label="Failed" value={runData?.failed} tone={runData?.failed ? 'red' : undefined} />
              <Stat label="Avg duration" value={fmtDuration(runData?.avg_duration_ms)} />
              <Stat label="p95 duration" value={fmtDuration(runData?.p95_duration_ms)} />
            </div>
            <Distribution title="Failures by stage" counts={runData?.failure_by_stage} emptyText="No failures in this range." />
            <Button secondary small onClick={onOpenMonitoring}>Open pipeline monitoring</Button>
          </Card>

          <Card title="Data-ingestion health" subtitle="Scheduled data feeds, kept separate from analysis requests.">
            <div className="job-grid">
              {Object.values(ingestionData?.jobs || {}).map((job) => (
                <div key={job.job} className="job-card">
                  <div className="job-title">
                    <strong>{job.label}</strong>
                    <Badge tone={job.health === 'healthy' ? 'green' : job.health === 'stale' || job.health === 'failing' ? 'red' : 'grey'}>
                      {job.health.replace('_', ' ')}
                    </Badge>
                  </div>
                  <p className="muted small">Source: {job.source}</p>
                  <p className="small">Last run: {fmtDateTime(job.last_run_at)} — <Badge>{job.last_status?.replace('_', ' ') || 'never'}</Badge></p>
                </div>
              ))}
            </div>
            <Button secondary small onClick={onOpenMonitoring}>Open ingestion runs</Button>
          </Card>
        </>
      )}
    </div>
  );
}

const RUN_STATUS_FILTERS = ['', 'completed', 'failed'];
const INGESTION_STATUS_FILTERS = ['', 'running', 'succeeded', 'incomplete', 'failed'];

export function MonitoringScreen() {
  const { firebaseUser } = useAuth();
  const [days, setDays] = useState(7);
  const [runStatus, setRunStatus] = useState('');
  const [runs, setRuns] = useState([]);
  const [summary, setSummary] = useState(null);
  const [runsCursor, setRunsCursor] = useState(null);
  const [runsLoading, setRunsLoading] = useState(true);
  const [expandedRun, setExpandedRun] = useState(null);

  const [ingestion, setIngestion] = useState(null);
  const [ingestionStatus, setIngestionStatus] = useState('');
  const [ingestionLoading, setIngestionLoading] = useState(true);
  const [ingestionError, setIngestionError] = useState(null);
  const [busyJob, setBusyJob] = useState(null);
  const [followUpFor, setFollowUpFor] = useState(null);
  const [followUpNote, setFollowUpNote] = useState('');

  const loadRuns = useCallback(async (cursor) => {
    setRunsLoading(true);
    try {
      const params = {
        status: runStatus || undefined,
        from: daysToFrom(days),
        limit: 20,
        cursor: cursor || undefined,
      };
      const data = await listRuns(firebaseUser, params);
      setRuns((previous) => (cursor ? [...previous, ...data.runs] : data.runs));
      setRunsCursor(data.next_cursor);
    } catch (caught) {
      setError(caught);
    } finally {
      setRunsLoading(false);
    }
  }, [firebaseUser, days, runStatus]);

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await getRunSummary(firebaseUser, { from: daysToFrom(days) }));
    } catch (caught) {
      setError(caught);
    }
  }, [firebaseUser, days]);

  const loadIngestion = useCallback(async () => {
    setIngestionLoading(true);
    setIngestionError(null);
    try {
      setIngestion(await listIngestionRuns(firebaseUser, {
        status: ingestionStatus || undefined, limit: 20,
      }));
    } catch (caught) {
      setIngestionError(caught);
    } finally {
      setIngestionLoading(false);
    }
  }, [firebaseUser, ingestionStatus]);

  useEffect(() => { setRuns([]); loadRuns(); }, [days, runStatus, loadRuns]);
  useEffect(() => { loadSummary(); }, [days, loadSummary]);
  useEffect(() => { loadIngestion(); }, [loadIngestion]);

  async function openRun(runId) {
    setExpandedRun(expandedRun === runId ? null : runId);
    if (expandedRun !== runId && !runs.find((run) => run.run_id === runId)?.stage_timings_ms) {
      try {
        const fresh = await getRun(firebaseUser, runId);
        setRuns((previous) => previous.map((run) => (run.run_id === runId ? fresh : run)));
      } catch {
        /* the list already carries the summary fields */
      }
    }
  }

  async function trigger(job) {
    setBusyJob(job);
    try {
      await triggerIngestionJob(firebaseUser, job);
      await Promise.all([loadIngestion(), loadSummary()]);
    } catch (caught) {
      setIngestionError(caught);
    } finally {
      setBusyJob(null);
    }
  }

  async function saveFollowUp(runId) {
    try {
      await addFollowUp(firebaseUser, runId, followUpNote);
      setFollowUpFor(null);
      setFollowUpNote('');
      await loadIngestion();
    } catch (caught) {
      setIngestionError(caught);
    }
  }

  return (
    <div className="stack">
      <div className="toolbar">
        <h1>Pipeline monitoring</h1>
        <TimeRange value={days} onChange={setDays} />
      </div>

      <Card title="Analysis requests"
        subtitle="One record per user check through the text pipeline. Timing is measured per stage.">
        <div className="stats">
          <Stat label="Runs" value={summary?.total} />
          <Stat label="Completed" value={summary?.completed} tone="green" />
          <Stat label="Failed" value={summary?.failed} tone={summary?.failed ? 'red' : undefined} />
          <Stat label="Avg duration" value={fmtDuration(summary?.avg_duration_ms)} />
          <Stat label="p95 duration" value={fmtDuration(summary?.p95_duration_ms)} />
        </div>
        <Distribution title="Failures by stage" counts={summary?.failure_by_stage} emptyText="No failures in this range." />
        <TrendBars trend={summary?.trend} />
        <div className="toolbar">
          <label className="inline-label">Status
            <select value={runStatus} onChange={(event) => setRunStatus(event.target.value)}>
              {RUN_STATUS_FILTERS.map((value) => (
                <option key={value} value={value}>{value ? value : 'All'}</option>
              ))}
            </select>
          </label>
        </div>
        {runs.length === 0 && !runsLoading ? (
          <EmptyState>No analysis runs recorded in this range.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Run</th><th>Status</th><th>Type</th><th>Duration</th><th>Started</th><th>Failure</th></tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <React.Fragment key={run.run_id}>
                  <tr className="clickable" onClick={() => openRun(run.run_id)}>
                    <td className="mono">{shortId(run.run_id, 12)}</td>
                    <td><Badge tone={run.status === 'completed' ? 'green' : 'red'}>{run.status}</Badge></td>
                    <td>{run.input_type.replace('_', ' ')}</td>
                    <td>{fmtDuration(run.duration_ms)}</td>
                    <td>{new Date(run.created_at).toLocaleString()}</td>
                    <td className="small muted">{run.failure_stage ? `${run.failure_stage} · ${run.error_code}` : ''}</td>
                  </tr>
                  {expandedRun === run.run_id && (
                    <tr className="detail-row">
                      <td colSpan={6}>
                        {Object.keys(run.stage_timings_ms || {}).length === 0 ? (
                          <p className="muted small">No stage timings recorded for this run.</p>
                        ) : (
                          <table className="table nested">
                            <thead><tr><th>Stage</th><th>Duration</th></tr></thead>
                            <tbody>
                              {Object.entries(run.stage_timings_ms).map(([stage, ms]) => (
                                <tr key={stage}><td>{stage.replace(/_/g, ' ')}</td><td>{fmtDuration(ms)}</td></tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                        {run.message && <p className="small muted">Failure message: {run.message}</p>}
                        <p className="small muted">Pipeline version: {run.pipeline_version || '—'}</p>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        )}
        {runsCursor && <Button secondary small onClick={() => loadRuns(runsCursor)}>Load more</Button>}
      </Card>

      <Card title="Data-ingestion runs"
        subtitle="Scheduled data feeds that support analysis — forecast snapshots and the trusted-source catalogue.">
        <div className="job-grid">
          {Object.values(ingestion?.jobs || {}).map((job) => (
            <div key={job.job} className="job-card">
              <div className="job-title">
                <strong>{job.label}</strong>
                <Badge tone={job.health === 'healthy' ? 'green' : job.health === 'never_run' ? 'grey' : 'red'}>
                  {job.health.replace('_', ' ')}
                </Badge>
              </div>
              <p className="muted small">{job.source}</p>
              <p className="small">Last run {fmtDateTime(job.last_run_at)} — <Badge>{job.last_status?.replace('_', ' ') || 'never'}</Badge></p>
              <p className="small muted">Last success {fmtDateTime(job.last_success_at)}</p>
              <Button small loading={busyJob === job.job} onClick={() => trigger(job.job)}>
                Run now
              </Button>
            </div>
          ))}
        </div>
        <div className="toolbar">
          <label className="inline-label">Status
            <select value={ingestionStatus} onChange={(event) => setIngestionStatus(event.target.value)}>
              {INGESTION_STATUS_FILTERS.map((value) => (
                <option key={value} value={value}>{value ? value.replace('_', ' ') : 'All'}</option>
              ))}
            </select>
          </label>
        </div>
        <ErrorBox error={ingestionError} onRetry={loadIngestion} />
        {ingestionLoading && <Loading />}
        {!ingestionLoading && (ingestion?.runs?.length === 0 ? (
          <EmptyState>No ingestion runs recorded yet. Use “Run now” to start one.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Run</th><th>Job</th><th>Status</th><th>Items</th><th>Duration</th><th>Started</th><th>Detail</th></tr>
            </thead>
            <tbody>
              {ingestion?.runs.map((run) => (
                <tr key={run.run_id}>
                  <td className="mono">{shortId(run.run_id, 12)}</td>
                  <td>{run.job.replace(/_/g, ' ')}</td>
                  <td><Badge tone={run.status === 'succeeded' ? 'green' : run.status === 'failed' ? 'red' : run.status === 'incomplete' ? 'amber' : 'blue'}>{run.status}</Badge></td>
                  <td>{run.items_processed ?? '—'}</td>
                  <td>{fmtDuration(run.duration_ms)}</td>
                  <td>{new Date(run.started_at).toLocaleString()}</td>
                  <td className="small">
                    {run.error_code && <p className="mono small">{run.error_code}</p>}
                    {run.message && <p className="muted small">{run.message}</p>}
                    {run.affected_range?.forecast_dates && <p className="small">Dates: {run.affected_range.forecast_dates.join(', ')}</p>}
                    {run.affected_range?.domains != null && <p className="small">Domains: {run.affected_range.domains}</p>}
                    {run.follow_ups?.length > 0 && (
                      <details>
                        <summary className="small">{run.follow_ups.length} follow-up(s)</summary>
                        {run.follow_ups.map((entry, index) => (
                          <p key={index} className="small muted">{new Date(entry.at).toLocaleString()} — {entry.note}</p>
                        ))}
                      </details>
                    )}
                    {followUpFor === run.run_id ? (
                      <div className="followup">
                        <textarea value={followUpNote} maxLength={1000} placeholder="Describe the issue for follow-up…"
                          onChange={(event) => setFollowUpNote(event.target.value)} />
                        <div className="row">
                          <Button small onClick={() => saveFollowUp(run.run_id)}>Save</Button>
                          <Button small secondary onClick={() => setFollowUpFor(null)}>Cancel</Button>
                        </div>
                      </div>
                    ) : (
                      <Button small secondary onClick={() => { setFollowUpFor(run.run_id); setFollowUpNote(''); }}>
                        Record follow-up
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      </Card>
    </div>
  );
}
