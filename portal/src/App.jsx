import React, { useEffect, useRef, useState } from 'react';

import { AuthProvider, useAuth } from './auth/AuthContext';
import { Badge, Button, ErrorBox, Loading } from './components/ui';
import { LoginScreen, VerifyScreen } from './screens/AuthScreens';
import { ProfileScreen } from './screens/ProfileScreen';
import { DashboardScreen, MonitoringScreen } from './screens/MonitoringScreens';
import { ReportDetailScreen, ReportsScreen } from './screens/ReportScreens';

const IDLE_TIMEOUT_MS = 30 * 60 * 1000; // UC-37 S1: auto-logout after 30 idle minutes.

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="auth-wrap">
        <div className="card auth-card">
          <h1>Something went wrong</h1>
          <p className="muted">{String(this.state.error?.message || this.state.error)}</p>
          <Button onClick={() => window.location.reload()}>Reload the portal</Button>
        </div>
      </div>
    );
  }
}

function useIdleLogout(onIdle) {
  const lastActivity = useRef(Date.now());
  useEffect(() => {
    function touch() { lastActivity.current = Date.now(); }
    const events = ['mousedown', 'keydown', 'touchstart', 'scroll'];
    events.forEach((event) => window.addEventListener(event, touch, { passive: true }));
    const timer = setInterval(() => {
      if (Date.now() - lastActivity.current > IDLE_TIMEOUT_MS) {
        lastActivity.current = Date.now();
        onIdle();
      }
    }, 60 * 1000);
    return () => {
      events.forEach((event) => window.removeEventListener(event, touch));
      clearInterval(timer);
    };
  }, [onIdle]);
}

function AuthGate({ children }) {
  const { firebaseUser, initialising, refreshProfile, logout } = useAuth();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!firebaseUser?.emailVerified) return;
    let active = true;
    setLoading(true);
    setError(null);
    refreshProfile()
      .then((data) => { if (active) setProfile(data); })
      .catch((caught) => { if (active) { setProfile(null); setError(caught); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [firebaseUser, refreshProfile]);

  useIdleLogout(() => { if (firebaseUser) logout(); });

  if (initialising) return <Loading label="Checking your session…" />;
  if (!firebaseUser) return <LoginScreen />;
  if (!firebaseUser.emailVerified) return <VerifyScreen />;
  if (loading) return <Loading label="Loading your operator profile…" />;

  if (error) {
    return (
      <div className="auth-wrap">
        <div className="card auth-card">
          <h1>Portal unavailable</h1>
          <ErrorBox error={error} onRetry={() => window.location.reload()} />
          <Button onClick={logout}>Log out</Button>
        </div>
      </div>
    );
  }

  if (profile?.account_status && profile.account_status !== 'active') {
    return (
      <div className="auth-wrap">
        <div className="card auth-card">
          <h1>Account unavailable</h1>
          <p className="muted">This account is currently {profile.account_status}. Contact a system administrator.</p>
          <Button onClick={logout}>Log out</Button>
        </div>
      </div>
    );
  }

  if (profile?.role === 'data_engineer') return children;

  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <h1>Access denied</h1>
        <p className="muted">
          {profile?.role === 'system_admin'
            ? 'This is the data-engineer portal. Use the system-administrator portal for account management.'
            : 'This portal is only for authorised operational accounts.'}
        </p>
        <p>Current role: <Badge tone="grey">{profile?.role?.replace('_', ' ') || 'unknown'}</Badge></p>
        <Button onClick={logout}>Log out</Button>
      </div>
    </div>
  );
}

function PortalShell() {
  const { firebaseUser, logout } = useAuth();
  const [tab, setTab] = useState('dashboard');
  const [reportId, setReportId] = useState(null);

  const tabs = [
    ['dashboard', 'Dashboard'],
    ['reports', 'Reports'],
    ['monitoring', 'Pipeline monitoring'],
    ['profile', 'Profile'],
  ];

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-name">UIABO</span>
          <span className="brand-role">Data-Engineer Portal</span>
        </div>
        <nav className="tabs" aria-label="Portal sections">
          {tabs.map(([key, label]) => (
            <button key={key} type="button"
              className={`tab ${tab === key || (key === 'reports' && reportId) ? 'active' : ''}`}
              aria-current={tab === key ? 'page' : undefined}
              onClick={() => { setTab(key); if (key !== 'reports') setReportId(null); }}>
              {label}
            </button>
          ))}
        </nav>
        <div className="topbar-user">
          <span className="small muted">{firebaseUser?.email}</span>
          <Button small secondary onClick={() => { if (window.confirm('Log out of the portal?')) logout(); }}>
            Log out
          </Button>
        </div>
      </header>
      <main className="content">
        {tab === 'dashboard' && (
          <DashboardScreen
            onOpenReports={() => { setReportId(null); setTab('reports'); }}
            onOpenMonitoring={() => setTab('monitoring')}
          />
        )}
        {tab === 'reports' && !reportId && (
          <ReportsScreen onOpenReport={(id) => { setReportId(id); window.scrollTo(0, 0); }} />
        )}
        {tab === 'reports' && reportId && (
          <ReportDetailScreen reportId={reportId} onBack={() => setReportId(null)} />
        )}
        {tab === 'monitoring' && <MonitoringScreen />}
        {tab === 'profile' && <ProfileScreen />}
      </main>
      <footer className="footer small muted">
        Monitoring records contain no user content. User data is only shown in an investigation and is logged.
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ErrorBoundary>
        <AuthGate>
          <PortalShell />
        </AuthGate>
      </ErrorBoundary>
    </AuthProvider>
  );
}
