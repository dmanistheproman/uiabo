import React from 'react';

export function Badge({ tone = 'grey', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

const STATUS_TONES = {
  open: 'blue', reviewing: 'amber', resolved: 'green', dismissed: 'grey',
  completed: 'green', failed: 'red',
  running: 'blue', succeeded: 'green', incomplete: 'amber',
  healthy: 'green', stale: 'amber', failing: 'red', never_run: 'grey',
};

export function StatusBadge({ value }) {
  return <Badge tone={STATUS_TONES[value] || 'grey'}>{String(value || '—').replace('_', ' ')}</Badge>;
}

export function Card({ title, subtitle, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || subtitle) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {subtitle && <p className="muted">{subtitle}</p>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, tone }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ''}`}>
      <span className="stat-value">{value ?? '—'}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

export function Button({ children, onClick, secondary, disabled, loading, type = 'button', small }) {
  return (
    <button
      type={type}
      className={`btn ${secondary ? 'btn-secondary' : ''} ${small ? 'btn-small' : ''}`}
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading ? '…' : children}
    </button>
  );
}

export function Field({ label, children, hint }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="muted small">{hint}</span>}
    </label>
  );
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <p>{error.message || String(error)}</p>
      {onRetry && <Button secondary small onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function EmptyState({ children }) {
  return <p className="empty-state">{children}</p>;
}

export function Loading({ label = 'Loading…' }) {
  return <p className="loading">{label}</p>;
}

export function TimeRange({ value, onChange, disabled }) {
  const ranges = [
    ['24h', 1], ['7d', 7], ['30d', 30],
  ];
  return (
    <div className="segmented" role="group" aria-label="Time range">
      {ranges.map(([label, days]) => (
        <button
          key={label}
          type="button"
          disabled={disabled}
          aria-pressed={value === days}
          className={`segment ${value === days ? 'active' : ''}`}
          onClick={() => onChange(days)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function daysToFrom(days) {
  if (!days) return undefined;
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

export function fmtDateTime(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

export function fmtDuration(ms) {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function shortId(value, size = 10) {
  if (!value) return '—';
  return value.length <= size ? value : `${value.slice(0, size)}…`;
}

export function TrendBars({ trend }) {
  if (!trend?.length) return <EmptyState>No activity in this range.</EmptyState>;
  const max = Math.max(...trend.map((point) => point.count), 1);
  return (
    <div className="trend" role="img" aria-label="Activity per day">
      {trend.map((point) => (
        <div key={point.date} className="trend-column" title={`${point.date}: ${point.count}`}>
          <div className="trend-bar" style={{ height: `${Math.max(8, (point.count / max) * 100)}%` }} />
          <span className="small muted">{point.date.slice(5)}</span>
          <span className="small">{point.count}</span>
        </div>
      ))}
    </div>
  );
}

export function Distribution({ title, counts, emptyText = 'Nothing recorded yet.' }) {
  const entries = Object.entries(counts || {}).filter(([, count]) => count > 0);
  return (
    <div className="distribution">
      <h3>{title}</h3>
      {entries.length === 0 ? <p className="muted small">{emptyText}</p> : (
        <ul>
          {entries.map(([key, count]) => (
            <li key={key}><span>{key.replace(/_/g, ' ')}</span><strong>{count}</strong></li>
          ))}
        </ul>
      )}
    </div>
  );
}

export const REPORT_REASON_LABELS = {
  wrong_label: 'The concern label is wrong',
  wrong_score: 'The risk score is wrong',
  wrong_evidence: 'The evidence or sources are wrong',
  other: 'Something else',
};
