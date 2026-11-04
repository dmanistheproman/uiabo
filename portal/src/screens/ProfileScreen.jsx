import React, { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Badge, Button, ErrorBox, Field, Loading, fmtDateTime } from '../components/ui';
import { PORTAL_ROLES, portalRoles } from '../utils/portalAccess';

export function ProfileScreen() {
  const { firebaseUser, refreshProfile, saveName, resetPassword, logout, portalRole } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await refreshProfile();
        if (!active) return;
        setProfile(data);
        setName(data.name || '');
      } catch (caught) {
        if (active) setError(caught);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [refreshProfile]);

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    setError(null);
    try {
      const updated = await saveName(name);
      setProfile(updated);
      setNotice('Profile updated.');
    } catch (caught) {
      setError(caught);
    } finally {
      setSaving(false);
    }
  }

  async function sendReset() {
    try {
      await resetPassword(firebaseUser.email);
      setNotice('Password-reset email sent to ' + firebaseUser.email + '.');
    } catch (caught) {
      setError(caught);
    }
  }

  async function signOut() {
    if (window.confirm('Log out of the portal?')) await logout();
  }

  if (loading) return <Loading />;
  return (
    <div className="stack">
      <div className="card">
        <h2>Account</h2>
        {error && <ErrorBox error={error} />}
        {notice && <p className="notice">{notice}</p>}
        <dl className="definition">
          <div><dt>Email</dt><dd>{firebaseUser?.email}</dd></div>
          <div><dt>Account type</dt><dd>Staff portal account</dd></div>
          <div><dt>Current portal</dt><dd><Badge tone="blue">{PORTAL_ROLES[portalRole]}</Badge></dd></div>
          <div><dt>Portal access</dt><dd>{portalRoles(profile).map(role => <Badge key={role} tone="blue">{PORTAL_ROLES[role]}</Badge>)}</dd></div>
          <div><dt>Status</dt><dd><Badge tone="green">{profile?.account_status}</Badge></dd></div>
          <div><dt>Email verified</dt><dd>{profile?.email_verified ? 'Yes' : 'No'}</dd></div>
          <div><dt>Last login</dt><dd>{fmtDateTime(profile?.last_login_at)}</dd></div>
          <div><dt>Member since</dt><dd>{fmtDateTime(profile?.created_at)}</dd></div>
        </dl>
        <form onSubmit={save} className="row-end">
          <Field label="Display name">
            <input value={name} maxLength={80} required
              onChange={(event) => setName(event.target.value)} />
          </Field>
          <Button type="submit" loading={saving}>Save</Button>
        </form>
      </div>
      <div className="card">
        <h2>Security</h2>
        <p className="muted">We send a time-limited reset link to your registered email address.</p>
        <div className="row">
          <Button secondary onClick={sendReset}>Send password-reset email</Button>
          <Button onClick={signOut}>Log out</Button>
        </div>
      </div>
    </div>
  );
}
