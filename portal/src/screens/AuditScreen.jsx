import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Badge, Button, Card, EmptyState, ErrorBox, Field, fmtDateTime, Loading } from '../components/ui';
import { listAuditHistory } from '../services/api';
import { AUDIT_ACTIONS, auditDateRange } from '../utils/audit';

function Person({ event, prefix }) {
  const name = event[`${prefix}_name`], email = event[`${prefix}_email`], mask = event[`${prefix}_mask`];
  return <div>{name || (mask ? 'Account no longer available' : 'Not identified')}
    {email && <div className="small muted">{email}</div>}
    {mask && <div className="small mono">{mask}</div>}
  </div>;
}

export function AuditScreen({ initialUserId = '' }) {
  const { firebaseUser } = useAuth();
  const [filters, setFilters] = useState({ days: '7', action: '', outcome: '', user_id: initialUserId });
  const [request, setRequest] = useState(() => ({ ...filters, ...auditDateRange(7) }));
  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(null); setPage(null);
    const { days, ...params } = request;
    listAuditHistory(firebaseUser, Object.fromEntries(Object.entries(params).filter(([, value]) => value !== '')))
      .then(data => { if (active) setPage(data); })
      .catch(caught => { if (active) setError(caught); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [firebaseUser, request, attempt]);
  function field(name, value) { setFilters(current => ({ ...current, [name]: value })); }
  return <div className="stack">
    <h1>Audit history</h1>
    <p className="muted">Read-only records of portal access and administrative actions. Names reflect current accounts; historical records retain a masked identifier.</p>
    <Card title="Filter activity">
      <form className="row-end" onSubmit={event => { event.preventDefault(); setRequest({ ...filters, user_id: filters.user_id.trim(), ...auditDateRange(Number(filters.days)) }); }}>
        <Field label="Date range"><select value={filters.days} onChange={event => field('days', event.target.value)}>
          <option value="1">Last 24 hours</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option>
        </select></Field>
        <Field label="Action"><select value={filters.action} onChange={event => field('action', event.target.value)}>
          <option value="">All actions</option>{Object.entries(AUDIT_ACTIONS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></Field>
        <Field label="Outcome"><select value={filters.outcome} onChange={event => field('outcome', event.target.value)}>
          <option value="">All outcomes</option><option value="succeeded">Succeeded</option><option value="denied">Denied</option><option value="failed">Failed</option><option value="started">Outcome pending</option>
        </select></Field>
        <Field label="User ID" hint="Actor or affected account"><input value={filters.user_id} maxLength={128} onChange={event => field('user_id', event.target.value)} /></Field>
        <Button type="submit" disabled={loading}>Apply / refresh</Button>
      </form>
    </Card>
    <ErrorBox error={error} onRetry={() => setAttempt(value => value + 1)} />
    {loading && <Loading label="Loading audit history..." />}
    {page && <>
      {!page.items.length ? <EmptyState>No matching events in this page.{page.next_cursor ? ' Continue to older events or adjust the filters.' : ''}</EmptyState>
        : <Card title="Recorded events"><div className="table-scroll"><table className="table">
          <thead><tr><th>Time / action</th><th>Performed by</th><th>Affected account</th><th>Outcome / details</th></tr></thead>
          <tbody>{page.items.map(event => <tr key={event.event_id}>
            <td>{fmtDateTime(event.started_at)}<div><strong>{AUDIT_ACTIONS[event.action] || event.action}</strong></div><div className="small muted">{event.method} {event.path}</div></td>
            <td><Person event={event} prefix="actor" /><div className="small">{event.actor_role?.replaceAll('_', ' ')}</div></td>
            <td><Person event={event} prefix="target" /></td>
            <td><Badge tone={event.outcome === 'succeeded' ? 'green' : event.outcome === 'started' ? 'amber' : 'red'}>{event.outcome === 'started' ? 'Outcome pending' : event.outcome}</Badge>
              {event.change_applied && event.outcome !== 'succeeded' && <p className="small">Account change was saved; request outcome may be incomplete.</p>}
              {event.action_details.reason && <p>{event.action_details.reason}</p>}
              {event.action_details.before && <p className="small">Before: {event.action_details.before.join(', ') || 'No portal access'}<br />After: {event.action_details.after?.join(', ') || 'No portal access'}</p>}
              {event.action_details.account_status && <p className="small">Account status: {event.action_details.account_status}</p>}
              {event.action_details.account_type_to && <p className="small">Account type: {event.action_details.account_type_from} → {event.action_details.account_type_to} ({event.action_details.membership})</p>}
              <div className="small mono">{event.event_id}</div>
            </td>
          </tr>)}</tbody>
        </table></div></Card>}
      {page.next_cursor && <Button secondary onClick={() => setRequest(current => ({ ...current, cursor: page.next_cursor }))}>Older events</Button>}
    </>}
  </div>;
}
