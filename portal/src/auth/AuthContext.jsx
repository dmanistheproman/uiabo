import React from 'react';
import {
  onAuthStateChanged,
  reload,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut,
  updateProfile,
  createUserWithEmailAndPassword,
} from 'firebase/auth';

import { initFirebaseAuth } from '../config/firebase';
import { ensureProfile, getProfile } from '../services/api';
import { isPortalRole, storedPortalChoice } from '../utils/portalAccess';

const AuthContext = React.createContext(null);

function friendlyAuthError(error) {
  const messages = {
    'auth/invalid-credential': 'The email or password is incorrect.',
    'auth/invalid-email': 'Enter a valid email address.',
    'auth/network-request-failed': 'Network error. Check your connection and try again.',
    'auth/too-many-requests': 'Too many attempts. Please wait and try again.',
    'auth/user-disabled': 'This account is unavailable.',
    'auth/user-not-found': 'The email or password is incorrect.',
    'auth/weak-password': 'Use a password with at least 8 characters.',
    'auth/email-already-in-use': 'This email already has an account. Use your staff login, or a different email from your UIABO app account.',
  };
  return new Error(messages[error?.code] || error?.message || 'Something went wrong. Please try again.');
}

function suggestedName(user) {
  return user.displayName || user.email?.split('@')[0] || 'UIABO operator';
}

async function syncPortalProfile(user) {
  let name = suggestedName(user);
  if (user.emailVerified) {
    try { name = (await getProfile(user)).name; }
    catch (error) { if (error.code !== 'PROFILE_NOT_FOUND') throw error; }
  }
  return ensureProfile(user, name);
}

export function AuthProvider({ children }) {
  const [firebaseUser, setFirebaseUser] = React.useState(null);
  const [initialising, setInitialising] = React.useState(true);
  const [authRevision, setAuthRevision] = React.useState(0);
  const [configurationError, setConfigurationError] = React.useState('');
  const [accountSetupBusy, setAccountSetupBusy] = React.useState(false);
  const [registrationNotice, setRegistrationNotice] = React.useState('');
  const [sessionNotice, setSessionNotice] = React.useState('');
  const authRef = React.useRef(null);
  const [portalRole, setPortalRole] = React.useState(() => {
    try { return storedPortalChoice(window.sessionStorage); } catch { return 'data_engineer'; }
  });

  function selectPortal(role) {
    if (!isPortalRole(role)) throw new Error('Choose a portal to continue.');
    setPortalRole(role);
    try { window.sessionStorage.setItem('uiabo.portalChoice', role); } catch { /* In-memory choice still works. */ }
  }

  React.useEffect(() => {
    let unsubscribe = () => {};
    try {
      const auth = initFirebaseAuth();
      authRef.current = auth;
      unsubscribe = onAuthStateChanged(auth, (user) => {
        setFirebaseUser(user);
        setInitialising(false);
      });
    } catch (error) {
      setConfigurationError(error.message);
      setInitialising(false);
    }
    return unsubscribe;
  }, []);

  async function login(email, password, selectedRole) {
    selectPortal(selectedRole);
    setSessionNotice('');
    setAccountSetupBusy(true);
    try {
      const credential = await signInWithEmailAndPassword(authRef.current, email.trim(), password);
      await syncPortalProfile(credential.user);
    } catch (error) {
      if (error.code === 'APP_ACCOUNT_ONLY') {
        setSessionNotice(error.message);
        await signOut(authRef.current);
      }
      throw friendlyAuthError(error);
    } finally {
      setAccountSetupBusy(false);
    }
  }

  async function register(email, password, name, selectedRole) {
    selectPortal(selectedRole);
    setAccountSetupBusy(true); setRegistrationNotice(''); setSessionNotice('');
    let user;
    try {
      const credential = await createUserWithEmailAndPassword(authRef.current, email.trim(), password);
      user = credential.user;
      await updateProfile(user, { displayName: name.trim() });
      await ensureProfile(user, name.trim());
      await sendEmailVerification(user);
      setRegistrationNotice('Account created. Verify your email, then ask a System Admin to grant portal access.');
    } catch (error) {
      if (!user) throw friendlyAuthError(error);
      setRegistrationNotice('Your account was created, but setup did not finish. Use Resend email below if needed, then verify and continue.');
    } finally { setAccountSetupBusy(false); }
  }

  async function resetPassword(email) {
    try {
      await sendPasswordResetEmail(authRef.current, email.trim());
    } catch (error) {
      // A neutral response prevents account-email discovery (UC-38).
      if (error?.code !== 'auth/user-not-found') throw friendlyAuthError(error);
    }
  }

  async function resendVerification() {
    try {
      await sendEmailVerification(authRef.current.currentUser);
    } catch (error) {
      throw friendlyAuthError(error);
    }
  }

  async function checkVerification() {
    try {
      await reload(authRef.current.currentUser);
      const verified = authRef.current.currentUser.emailVerified;
      if (verified) {
        // Firebase reload mutates the same User object; force the gate to rerender.
        await authRef.current.currentUser.getIdToken(true);
        await syncPortalProfile(authRef.current.currentUser);
        setFirebaseUser(authRef.current.currentUser);
        setAuthRevision(value => value + 1);
      }
      return verified;
    } catch (error) {
      throw friendlyAuthError(error);
    }
  }

  async function refreshProfile() {
    return getProfile(authRef.current.currentUser);
  }

  async function saveName(name) {
    const user = authRef.current.currentUser;
    await updateProfile(user, { displayName: name.trim() });
    return ensureProfile(user, name.trim());
  }

  async function logout() {
    await signOut(authRef.current);
  }

  return (
    <AuthContext.Provider
      value={{
        checkVerification,
        authRevision,
        configurationError,
        firebaseUser,
        initialising,
        login,
        register,
        accountSetupBusy,
        registrationNotice,
        sessionNotice,
        portalRole,
        selectPortal,
        logout,
        refreshProfile,
        resendVerification,
        resetPassword,
        saveName,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = React.useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider.');
  return context;
}
