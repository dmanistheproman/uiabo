import React, { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Button, ErrorBox, Field } from '../components/ui';
import PortalChoice from '../components/PortalChoice';
import { PORTAL_ROLES } from '../utils/portalAccess';

export function LoginScreen() {
  const { login, register, resetPassword, portalRole, sessionNotice } = useAuth();
  const [selectedPortal, setSelectedPortal] = useState(portalRole);
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === 'login') {
        await login(email, password, selectedPortal);
      } else if (mode === 'register') {
        if (password !== confirmPassword) throw new Error('The passwords do not match.');
        await register(email, password, name, selectedPortal);
      } else {
        await resetPassword(email);
        setNotice('If that email is registered, a password-reset link has been sent.');
        setMode('login');
      }
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <h1>UIABO Operational Portal</h1>
        <p className="muted">Staff accounts are separate from UIABO app accounts. Use a different email for each.</p>
        {sessionNotice && <p className="error-box" role="alert">{sessionNotice}</p>}
        <p className="muted">Choose the portal you want to use, then sign in with an authorised account.</p>
        {mode === 'register' && <p className="muted">Create your staff account and verify your email. A System Admin must grant permission before you can use either portal. This account has no app membership or check allowance.</p>}
        {mode !== 'reset' && <PortalChoice value={selectedPortal} disabled={busy} onChange={value => { setSelectedPortal(value); setError(null); }} />}
        {mode === 'register' && <Field label="Your name"><input required maxLength={80} value={name} autoComplete="name" onChange={event => setName(event.target.value)} /></Field>}
        <Field label="Email">
          <input type="email" value={email} required autoComplete="email"
            onChange={(event) => setEmail(event.target.value)} />
        </Field>
        {mode !== 'reset' && (
          <Field label="Password">
            <input type="password" value={password} required minLength={mode === 'register' ? 8 : undefined} autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              onChange={(event) => setPassword(event.target.value)} />
          </Field>
        )}
        {mode === 'register' && <Field label="Confirm password"><input type="password" required minLength={8} autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} /></Field>}
        <ErrorBox error={error} />
        {notice && <p className="notice">{notice}</p>}
        <Button type="submit" disabled={busy} loading={busy}>
          {mode === 'login' ? `Log in to ${PORTAL_ROLES[selectedPortal]}` : mode === 'register' ? 'Create account' : 'Send reset link'}
        </Button>
        <div className="auth-links">
          <button type="button" className="linklike" disabled={busy} onClick={() => { setMode(mode === 'login' ? 'reset' : 'login'); setNotice(''); setError(null); }}>
            {mode === 'login' ? 'Forgot password?' : 'Back to log in'}
          </button>
          {mode === 'login' && <button type="button" className="linklike" disabled={busy} onClick={() => { setMode('register'); setError(null); setNotice(''); }}>Create an account</button>}
        </div>
      </form>
    </div>
  );
}

export function VerifyScreen() {
  const { firebaseUser, resendVerification, checkVerification, logout, registrationNotice } = useAuth();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState(null);

  async function resend() {
    setBusy(true);
    setError(null);
    try {
      await resendVerification();
      setNotice('Verification email sent. Check the inbox for ' + firebaseUser.email + '.');
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    setBusy(true);
    setError(null);
    try {
      const verified = await checkVerification();
      if (!verified) setNotice('Still not verified. Click the link in the email first, then try again.');
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <h1>Verify your email</h1>
        <p className="muted">
          A verification link was sent to <strong>{firebaseUser?.email}</strong>.
          Operational access requires a verified email address.
        </p>
        {registrationNotice && <p className="notice">{registrationNotice}</p>}
        <ErrorBox error={error} />
        {notice && <p className="notice">{notice}</p>}
        <div className="row">
          <Button secondary disabled={busy} onClick={resend}>Resend email</Button>
          <Button disabled={busy} loading={busy} onClick={check}>I have verified — continue</Button>
        </div>
        <div className="auth-links">
          <button type="button" className="linklike" onClick={logout}>Use a different account</button>
        </div>
      </div>
    </div>
  );
}
