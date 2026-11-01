import React, { useCallback, useEffect, useState } from 'react';

import {
  Badge, Button, Card, EmptyState, ErrorBox, Field, fmtDateTime, Loading, StatusBadge,
} from '../components/ui';
import { useAuth } from '../auth/AuthContext';
import {
  getFeedback, getUser, listFeedback, reviewFeedback, searchUsers, updateUserStatus,
} from '../services/api';

const ROLE_LABELS = {
  free: 'Free user', premium: 'Premium user', system_admin: 'System admin', data_engineer: 'Data engineer',
};

const FEEDBACK_CATEGORY_LABELS = {
  general_feedback: 'General feedback',
  service_review: 'Service review',
};

function Rating({ value }) {
  if (value == null) return <span className="muted small">No rating</span>;
  return <span aria-label={`Rated ${value} of 5`}>{'★'.repeat(value)}{'☆'.repeat(5 - value)}</span>;
}

export function UsersScreen() {
  const { firebaseUser } = useAuth();
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedUid, setSelectedUid] = useState(null);

  const runSearch = useCallback(async (text) => {
    setLoading(true);
    setError(null);
    try {
      setUsers(await searchUsers(firebaseUser, text ? { query: text } : {}));
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [firebaseUser]);

  useEffect(() => { runSearch(''); }, [runSearch]);

  if (selectedUid) {
    return (
      <UserDetailScreen
        uid={selectedUid}
        onBack={() => { setSelectedUid(null); runSearch(query); }}
      />
    );
  }

  return (
    <div className="stack">
      <header className="toolbar">
        <h1>Find users</h1>
        <p className="muted">Search accounts by name or email address, then open one to review or change its access.</p>
      </header>
      <Card title="Search">
        <form className="row-end" onSubmit={(event) => { event.preventDefault(); runSearch(query); }}>
          <Field label="Name or email">
            <input
              value={query}
              placeholder="e.g. Tan or tan@example.com"
              onChange={(event) => setQuery(event.target.value)}
            />
          </Field>
          <Button type="submit" loading={loading}>Search</Button>
        </form>
      </Card>
      <ErrorBox error={error} onRetry={() => runSearch(query)} />
      {loading && <Loading label="Searching accounts…" />}
      {!loading && !error && users && users.length === 0 && (
        <EmptyState>No accounts match this search.</EmptyState>
      )}
      {!loading && users?.length > 0 && (
        <Card title={`Accounts (${users.length})`}>
          <table className="table">
            <thead>
              <tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Last login</th></tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.uid} className="clickable"
                  onClick={() => { setSelectedUid(user.uid); window.scrollTo(0, 0); }}>
                  <td>{user.name}</td>
                  <td className="muted">{user.email}</td>
                  <td><Badge tone="grey">{ROLE_LABELS[user.role] || user.role}</Badge></td>
                  <td><StatusBadge value={user.account_status} /></td>
                  <td className="muted small">{user.last_login_at ? fmtDateTime(user.last_login_at) : 'Never'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function UserDetailScreen({ uid, onBack }) {
  const { firebaseUser } = useAuth();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setUser(await getUser(firebaseUser, uid));
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [firebaseUser, uid]);

  useEffect(() => { load(); }, [load]);

  async function setStatus(account_status, confirmTitle) {
    if (!window.confirm(confirmTitle)) return;
    setBusy(true);
    setActionError(null);
    try {
      setUser(await updateUserStatus(firebaseUser, uid, account_status));
    } catch (caught) {
      setActionError(caught);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading label="Loading account…" />;
  if (error) {
    return (
      <div className="stack">
        <ErrorBox error={error} onRetry={load} />
        <Button secondary onClick={onBack}>Back to search</Button>
      </div>
    );
  }

  const suspended = user.account_status === 'suspended';

  return (
    <div className="stack">
      <header className="toolbar">
        <Button secondary small onClick={onBack}>← Back to search</Button>
        <h1>{user.name}</h1>
        <p className="muted">{user.email} · <StatusBadge value={user.account_status} /></p>
      </header>
      <Card title="Account details">
        <dl className="definition">
          <div><dt>User ID</dt><dd>{user.uid}</dd></div>
          <div><dt>Role</dt><dd>{ROLE_LABELS[user.role] || user.role}</dd></div>
          <div><dt>Email verified</dt><dd>{user.email_verified ? 'Yes' : 'No'}</dd></div>
          <div><dt>Created</dt><dd>{fmtDateTime(user.created_at)}</dd></div>
          <div><dt>Last login</dt><dd>{user.last_login_at ? fmtDateTime(user.last_login_at) : 'Never'}</dd></div>
          <div><dt>Profile updated</dt><dd>{fmtDateTime(user.updated_at)}</dd></div>
        </dl>
      </Card>
      {user.allowance && (
        <Card title="Check allowance">
          <dl className="definition">
            <div><dt>Tier</dt><dd>{user.allowance.tier}</dd></div>
            <div><dt>Period</dt><dd>{user.allowance.period_type}</dd></div>
            <div><dt>Used</dt><dd>{user.allowance.successful_submissions} of {user.allowance.submission_limit}</dd></div>
            <div><dt>Remaining</dt><dd>{user.allowance.remaining_submissions}</dd></div>
            <div><dt>Resets</dt><dd>{fmtDateTime(user.allowance.reset_at)}</dd></div>
          </dl>
        </Card>
      )}
      <Card title="Access control">
        <p className="muted">
          {suspended
            ? 'This account cannot sign in for checks while suspended. Restoring returns it to normal use.'
            : 'Suspending blocks this account from submitting checks. The user keeps their saved results.'}
        </p>
        <ErrorBox error={actionError} />
        {suspended ? (
          <Button loading={busy} onClick={() => setStatus('active', `Restore access for ${user.email}?`)}>Restore access</Button>
        ) : (
          <Button loading={busy} onClick={() => setStatus('suspended', `Suspend ${user.email}? They will no longer be able to submit checks.`)}>Suspend account</Button>
        )}
      </Card>
    </div>
  );
}

export function FeedbackScreen() {
  const { firebaseUser } = useAuth();
  const [filter, setFilter] = useState('');
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  const load = useCallback(async (status) => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listFeedback(firebaseUser, status ? { status } : {}));
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [firebaseUser]);

  useEffect(() => { load(filter); }, [load, filter]);

  if (selectedId) {
    return <FeedbackDetailScreen feedbackId={selectedId} onBack={() => { setSelectedId(null); load(filter); }} />;
  }

  return (
    <div className="stack">
      <header className="toolbar">
        <h1>User feedback</h1>
        <p className="muted">Ratings and comments submitted from the app. Review them so users know their feedback was read.</p>
      </header>
      <div className="segmented" role="group" aria-label="Feedback status filter">
        {[
          ['', 'All'],
          ['submitted', 'Awaiting review'],
          ['reviewed', 'Reviewed'],
        ].map(([value, label]) => (
          <button
            key={value || 'all'}
            type="button"
            aria-pressed={filter === value}
            className={`segment ${filter === value ? 'active' : ''}`}
            onClick={() => setFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <ErrorBox error={error} onRetry={() => load(filter)} />
      {loading && <Loading label="Loading feedback…" />}
      {!loading && !error && items && items.length === 0 && (
        <EmptyState>No feedback in this view yet.</EmptyState>
      )}
      {!loading && items?.length > 0 && (
        <Card title={`Feedback (${items.length})`}>
          <table className="table">
            <thead>
              <tr><th>Category</th><th>Rating</th><th>Comments</th><th>Status</th><th>Received</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.feedback_id} className="clickable"
                  onClick={() => { setSelectedId(item.feedback_id); window.scrollTo(0, 0); }}>
                  <td>{FEEDBACK_CATEGORY_LABELS[item.category] || item.category}</td>
                  <td><Rating value={item.rating} /></td>
                  <td className="muted">{item.comments ? (item.comments.length > 60 ? `${item.comments.slice(0, 60)}…` : item.comments) : '—'}</td>
                  <td><StatusBadge value={item.status} /></td>
                  <td className="muted small">{fmtDateTime(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function FeedbackDetailScreen({ feedbackId, onBack }) {
  const { firebaseUser } = useAuth();
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItem(await getFeedback(firebaseUser, feedbackId));
    } catch (caught) {
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [firebaseUser, feedbackId]);

  useEffect(() => { load(); }, [load]);

  async function markReviewed() {
    if (!window.confirm('Mark this feedback as reviewed?')) return;
    setBusy(true);
    setActionError(null);
    try {
      setItem(await reviewFeedback(firebaseUser, feedbackId));
    } catch (caught) {
      setActionError(caught);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Loading label="Loading feedback…" />;
  if (error) {
    return (
      <div className="stack">
        <ErrorBox error={error} onRetry={load} />
        <Button secondary onClick={onBack}>Back to feedback</Button>
      </div>
    );
  }

  return (
    <div className="stack">
      <header className="toolbar">
        <Button secondary small onClick={onBack}>← Back to feedback</Button>
        <h1>{FEEDBACK_CATEGORY_LABELS[item.category] || item.category}</h1>
        <p className="muted">Received {fmtDateTime(item.created_at)} · <StatusBadge value={item.status} /></p>
      </header>
      <Card title="What the user said">
        <p className="rating-line"><Rating value={item.rating} /></p>
        {item.comments
          ? <blockquote className="user-detail">{item.comments}</blockquote>
          : <p className="muted">The user gave a rating without comments.</p>}
      </Card>
      <Card title="Review">
        {item.status === 'reviewed' ? (
          <p className="muted">Reviewed {fmtDateTime(item.reviewed_at)} by <strong>{item.reviewed_by?.slice(0, 10)}…</strong>.</p>
        ) : (
          <>
            <p className="muted">Marking as reviewed records who read it and when. It stays available for later reference.</p>
            <ErrorBox error={actionError} />
            <Button loading={busy} onClick={markReviewed}>Mark as reviewed</Button>
          </>
        )}
      </Card>
    </div>
  );
}
