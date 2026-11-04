import React, { useEffect, useRef, useState } from 'react';

import { AuthProvider, useAuth } from './auth/AuthContext';
import { Button, ErrorBox, Loading } from './components/ui';
import { LoginScreen, VerifyScreen } from './screens/AuthScreens';
import { ProfileScreen } from './screens/ProfileScreen';
import { DashboardScreen, MonitoringScreen } from './screens/MonitoringScreens';
import { ReportDetailScreen, ReportsScreen } from './screens/ReportScreens';
import { FeedbackScreen, UsersScreen } from './screens/AdminScreens';
import { ProvisioningScreen } from './screens/StaffScreens';
import { AuditScreen } from './screens/AuditScreen';

import PortalChoice from './components/PortalChoice';
import { getPortalSession } from './services/api';
import { PORTAL_ROLES, validatePortalSession } from './utils/portalAccess';

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

function AuthGate() {
  const { firebaseUser, initialising, accountSetupBusy, portalRole, selectPortal, authRevision, logout } = useAuth();
  const [access, setAccess] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const key = `${firebaseUser?.uid}:${portalRole}:${authRevision}:${attempt}`;

  useEffect(() => {
    if (!firebaseUser?.emailVerified || accountSetupBusy) {
      setAccess(null);
      return;
    }
    let active = true;
    setAccess({ key, loading: true });
    getPortalSession(firebaseUser, portalRole)
      .then(data => validatePortalSession(data, firebaseUser.uid, portalRole))
      .then(session => { if (active) setAccess({ key, session }); })
      .catch(error => { if (active) setAccess({ key, error }); });
    return () => { active = false; };
  }, [firebaseUser, firebaseUser?.emailVerified, portalRole, key, accountSetupBusy]);

  useIdleLogout(() => { if (firebaseUser) logout(); });

  if (initialising) return <Loading label="Checking your session..." />;
  if (!firebaseUser) return <LoginScreen />;
  if (accountSetupBusy) return <Loading label="Setting up your account..." />;
  if (!firebaseUser.emailVerified) return <VerifyScreen />;
  if (access?.key !== key || access.loading) return <Loading label="Checking portal access..." />;

  if (access.error) {
    const unavailable = access.error.code === 'ACCOUNT_UNAVAILABLE';
    const denied = access.error.code === 'PORTAL_ACCESS_DENIED';
    return <div className="auth-wrap"><div className="card auth-card">
      <h1>{unavailable ? 'Account unavailable' : denied ? 'Portal access denied' : 'Portal unavailable'}</h1>
      <ErrorBox error={access.error} />
      {denied && <p className="muted">Use a staff account with a different email from your UIABO app account. A System Admin must grant its portal permissions.</p>}
      {!unavailable && <>
        <PortalChoice value={portalRole} onChange={selectPortal} />
        <Button onClick={() => setAttempt(value => value + 1)}>Try selected portal</Button>
      </>}
      <Button secondary onClick={logout}>Log out</Button>
    </div></div>;
  }

  return <PortalShell key={`${firebaseUser.uid}:${portalRole}`} role={access.session.portal_role} />;
}

function PortalShell({ role }) {
  const { firebaseUser, logout } = useAuth();
  const [tab, setTab] = useState(role === 'system_admin' ? 'users' : 'dashboard');
  const [reportId, setReportId] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [auditUser, setAuditUser] = useState('');

  const tabs = role === 'system_admin'
    ? [
        ['users', 'Find users'],
        ['provision', 'Provision staff'],
        ['audit', 'Audit history'],
        ['feedback', 'User feedback'],
        ['profile', 'Profile'],
      ]
    : [
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
          <span className="brand-role">{PORTAL_ROLES[role]} Portal</span>
        </div>
        <nav className="tabs" aria-label="Portal sections">
          {tabs.map(([key, label]) => (
            <button key={key} type="button"
              className={`tab ${tab === key || (key === 'reports' && reportId) ? 'active' : ''}`}
              aria-current={tab === key ? 'page' : undefined}
              onClick={() => { setTab(key); if (key !== 'reports') setReportId(null); if (key === 'users') setSelectedUser(null); if (key === 'audit') setAuditUser(''); }}>
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
        {role === 'system_admin' ? (
          <>
            {tab === 'users' && <UsersScreen key={selectedUser || 'search'} initialUid={selectedUser} onAudit={uid => { setAuditUser(uid); setTab('audit'); }} />}
            {tab === 'provision' && <ProvisioningScreen onOpenUser={uid => { setSelectedUser(uid); setTab('users'); }} />}
            {tab === 'audit' && <AuditScreen key={auditUser} initialUserId={auditUser} />}
            {tab === 'feedback' && <FeedbackScreen />}
            {tab === 'profile' && <ProfileScreen />}
          </>
        ) : (
          <>
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
          </>
        )}
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
        <AuthGate />
      </ErrorBoundary>
    </AuthProvider>
  );
}
