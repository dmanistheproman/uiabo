import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Button, Card, ErrorBox, Field } from '../components/ui';
import { provisionAccount, updatePortalRoles, convertStaffToApp } from '../services/api';
import { PORTAL_ROLES, portalRoles } from '../utils/portalAccess';

export function RoleChoices({ value, onChange, disabled = false, keepAdmin = false }) {
  return <fieldset className="role-choices" disabled={disabled}>
    <legend>Portal permissions</legend>
    {Object.entries(PORTAL_ROLES).map(([role, label]) => <label className="inline-label" key={role}>
      <input type="checkbox" checked={value.includes(role)} disabled={keepAdmin && role === 'system_admin'}
        onChange={event => onChange(event.target.checked ? [...value, role] : value.filter(item => item !== role))} />
      {label}
    </label>)}
  </fieldset>;
}

export function FormerStaffConversion({ user, onSaved, onReload }) {
  const { firebaseUser } = useAuth();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const eligible = !portalRoles(user).length && user.account_status === 'active'
    && user.email_verified && user.uid !== firebaseUser.uid;
  async function convert(event) {
    event.preventDefault();
    if (!eligible || busy || !reason.trim()) return;
    if (!window.confirm(`Convert ${user.email} into a Free app account? They will use the same email and password to sign in to the app. This account will no longer be a staff account.`)) return;
    setBusy(true); setError(null);
    try { onSaved(await convertStaffToApp(firebaseUser, user.uid, reason.trim())); }
    catch (caught) { setError(caught); }
    finally { setBusy(false); }
  }
  return <Card title="Reuse a former staff account in the app">
    <p>Use this only when the person no longer needs staff access. They keep their existing email and password, receive a Free app account, and sign in instead of registering again.</p>
    {!eligible && <p className="muted">Remove all portal permissions first. The account must be active, email-verified, and different from your own account.</p>}
    <ErrorBox error={error} onRetry={onReload} />
    <form className="stack-form" onSubmit={convert}>
      <Field label="Reason for conversion"><textarea value={reason} maxLength={500}
        disabled={!eligible || busy} onChange={event => setReason(event.target.value)} /></Field>
      <Button type="submit" loading={busy} disabled={!eligible || !reason.trim()}>Convert to Free app account</Button>
    </form>
  </Card>;
}

export function RoleEditor({ user, onSaved, onReload }) {
  const { firebaseUser } = useAuth();
  const original = portalRoles(user);
  const [roles, setRoles] = useState(original);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');
  useEffect(() => { setRoles(portalRoles(user)); }, [user.updated_at]);
  const changed = [...roles].sort().join() !== [...original].sort().join();
  async function save(event) {
    event.preventDefault();
    if (!window.confirm(`Change portal access for ${user.email} to ${roles.map(role => PORTAL_ROLES[role]).join(' and ') || 'no portal access'}?`)) return;
    setBusy(true); setError(null); setNotice('');
    try {
      const updated = await updatePortalRoles(firebaseUser, user.uid, roles, original, reason.trim());
      onSaved(updated); setReason(''); setNotice('Portal permissions saved. They apply on the next request.');
    } catch (caught) { setError(caught); }
    finally { setBusy(false); }
  }
  return <Card title="Staff portal access">
    <p className="muted">Choose either role, both roles, or clear both to remove portal access. This staff account is separate from the UIABO app.</p>
    <form className="stack-form" onSubmit={save}>
      <RoleChoices value={roles} onChange={setRoles} disabled={busy}
        keepAdmin={user.uid === firebaseUser.uid} />
      {user.uid === firebaseUser.uid && <p className="small muted">Another active administrator must remove your System Admin permission.</p>}
      <Field label="Reason for this change"><textarea required maxLength={500} value={reason} disabled={busy}
        onChange={event => setReason(event.target.value)} rows={2} /></Field>
      <ErrorBox error={error} />
      {error?.code === 'PERMISSIONS_CHANGED' && <Button secondary onClick={onReload}>Reload account</Button>}
      {notice && <p className="notice" role="status">{notice}</p>}
      <Button type="submit" disabled={!changed || !reason.trim() || busy} loading={busy}>Save permissions</Button>
    </form>
  </Card>;
}

export function ProvisioningScreen({ onOpenUser }) {
  const { firebaseUser } = useAuth();
  const [email, setEmail] = useState('');
  const [roles, setRoles] = useState(['data_engineer']);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  async function submit(event) {
    event.preventDefault();
    if (!window.confirm(`Grant ${roles.map(role => PORTAL_ROLES[role]).join(' and ')} access to ${email.trim()}?`)) return;
    setBusy(true); setError(null); setResult(null);
    try { setResult(await provisionAccount(firebaseUser, email.trim(), roles, reason.trim())); }
    catch (caught) { setError(caught); }
    finally { setBusy(false); }
  }
  return <div className="stack">
    <h1>Provision staff access</h1>
    <Card title="Set up a staff member">
      <ol className="setup-steps">
        <li>Ask the staff member to choose <strong>Create an account</strong> on the portal login page using a different email from their UIABO app account. Existing staff accounts can be reused.</li>
        <li>They choose their own password and verify their email.</li>
        <li>Enter that email below and grant the permissions they need.</li>
      </ol>
      <p className="muted">This adds permissions to a verified staff account. Staff accounts have no Free/Premium membership or check allowance. App accounts cannot be provisioned as staff.</p>
      <form className="stack-form" onSubmit={submit}>
        <Field label="Staff email"><input required type="email" maxLength={254} value={email} disabled={busy}
          autoComplete="off" onChange={event => { setEmail(event.target.value); setResult(null); }} /></Field>
        <RoleChoices value={roles} onChange={value => { setRoles(value); setResult(null); }} disabled={busy} />
        <Field label="Reason for granting access"><textarea required maxLength={500} value={reason} disabled={busy}
          onChange={event => setReason(event.target.value)} rows={2} /></Field>
        <ErrorBox error={error} />
        <Button type="submit" disabled={busy || !roles.length || !reason.trim()} loading={busy}>Grant portal access</Button>
      </form>
      {result && <div className="notice" role="status">
        <p>Access granted to {result.email}: {portalRoles(result).map(role => PORTAL_ROLES[role]).join(' and ')}.</p>
        <Button secondary small onClick={() => onOpenUser(result.uid)}>View account</Button>
      </div>}
    </Card>
  </div>;
}
