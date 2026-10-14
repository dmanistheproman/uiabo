import React, { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Button, ErrorBox, Field } from '../components/ui';

export function LoginScreen() {
  const { login, resetPassword } = useAuth();
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState('');

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === 'login') {
        await login(email, password);
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
        <p className="muted">Sign in with an authorised system-administrator or data-engineer account.</p>
        <Field label="Email">
          <input type="email" value={email} required autoComplete="email"
            onChange={(event) => setEmail(event.target.value)} />
        </Field>
        {mode === 'login' && (
          <Field label="Password">
            <input type="password" value={password} required autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)} />
          </Field>
        )}
        <ErrorBox error={error} />
        {notice && <p className="notice">{notice}</p>}
        <Button type="submit" disabled={busy} loading={busy}>
          {mode === 'login' ? 'Log in' : 'Send reset link'}
        </Button>
        <div className="auth-links">
          <button type="button" className="linklike" onClick={() => { setMode(mode === 'login' ? 'reset' : 'login'); setNotice(''); }}>
            {mode === 'login' ? 'Forgot password?' : 'Back to log in'}
          </button>
        </div>
      </form>
    </div>
  );
}

export function VerifyScreen() {
  const { firebaseUser, resendVerification, checkVerification, logout } = useAuth();
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
