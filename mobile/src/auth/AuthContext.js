import React from 'react';
import {
  createUserWithEmailAndPassword,
  EmailAuthProvider,
  reauthenticateWithCredential,
  onAuthStateChanged,
  reload,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut,
  updateProfile,
} from 'firebase/auth';

import { getFirebaseAuth } from '../config/firebase';
import { ensureProfile, getProfile, completeDemoPayment } from '../services/api';

const AuthContext = React.createContext(null);

function friendlyAuthError(error) {
  const messages = {
    'auth/email-already-in-use': 'This email already has an account. Sign in instead. If it was a staff account, ask a System Admin to convert it to an app account first, or register with a different email.',
    'auth/wrong-password': 'The password is incorrect. Please try again.',
    'auth/invalid-credential': 'The email or password is incorrect.',
    'auth/invalid-email': 'Enter a valid email address.',
    'auth/network-request-failed': 'Network error. Check your connection and try again.',
    'auth/too-many-requests': 'Too many attempts. Please wait and try again.',
    'auth/user-disabled': 'This account is unavailable.',
    'auth/weak-password': 'Use a password with at least 8 characters.',
  };
  return new Error(messages[error?.code] || error?.message || 'Something went wrong. Please try again.');
}

function suggestedName(user) {
  return user.displayName || user.email?.split('@')[0] || 'UIABO user';
}

export function AuthProvider({ children }) {
  const [firebaseUser, setFirebaseUser] = React.useState(null);
  const [profile, setProfile] = React.useState(null);
  const [initialising, setInitialising] = React.useState(true);
  const [configurationError, setConfigurationError] = React.useState('');
  const authRef = React.useRef(null);
  const authGeneration = React.useRef(0);
  const [sessionNotice, setSessionNotice] = React.useState('');
  const [deletionPending, setDeletionPending] = React.useState(false);

  React.useEffect(() => {
    let unsubscribe = () => {};
    try {
      const auth = getFirebaseAuth();
      authRef.current = auth;
      unsubscribe = onAuthStateChanged(auth, async (user) => {
        const generation = ++authGeneration.current;
        setFirebaseUser(user);
        setProfile(null);
        if (user?.emailVerified) {
          try {
            const account = await ensureProfile(user, suggestedName(user));
            if (generation === authGeneration.current && auth.currentUser?.uid === user.uid) setProfile(account);
          } catch (error) {
            if (generation === authGeneration.current && error.code === "ACCOUNT_UNAVAILABLE") {
              setSessionNotice("This account is unavailable. If you requested deletion, cleanup may still be in progress.");
              await signOut(auth).catch(() => {});
            }
            if (generation === authGeneration.current && error.code === 'STAFF_ACCOUNT_ONLY') {
              setSessionNotice(error.message);
              await signOut(auth).catch(() => {});
            }
            // A retry button is shown after the app opens for service outages.
          }
        }
        setInitialising(false);
      });
    } catch (error) {
      setConfigurationError(error.message);
      setInitialising(false);
    }
    return unsubscribe;
  }, []);

  async function register({ email, name, password }) {
    setDeletionPending(false); setSessionNotice('');
    try {
      const credential = await createUserWithEmailAndPassword(
        authRef.current,
        email.trim(),
        password,
      );
      await updateProfile(credential.user, { displayName: name.trim() });
      await sendEmailVerification(credential.user);
      setProfile(await ensureProfile(credential.user, name.trim()));
      setFirebaseUser(authRef.current.currentUser);
    } catch (error) {
      throw friendlyAuthError(error);
    }
  }

  async function login(email, password) {
    setDeletionPending(false); setSessionNotice('');
    try {
      await signInWithEmailAndPassword(
        authRef.current,
        email.trim(),
        password,
      );
    } catch (error) {
      throw friendlyAuthError(error);
    }
  }

  async function resetPassword(email) {
    try {
      await sendPasswordResetEmail(authRef.current, email.trim());
    } catch (error) {
      // A neutral response prevents account-email discovery.
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
      const user = authRef.current.currentUser;
      await reload(user);
      const refreshed = authRef.current.currentUser;
      if (!refreshed.emailVerified) return false;
      setProfile(await ensureProfile(refreshed, suggestedName(refreshed)));
      setFirebaseUser(refreshed);
      return true;
    } catch (error) {
      throw friendlyAuthError(error);
    }
  }

  async function refreshProfile() {
    const account = await getProfile(authRef.current.currentUser);
    setProfile(account);
    return account;
  }

  async function upgradeWithDemoPayment() {
    const user = authRef.current.currentUser;
    const receipt = await completeDemoPayment(user);
    if (authRef.current.currentUser?.uid === user.uid) setProfile(receipt.profile);
    return receipt;
  }

  async function saveName(name) {
    const user = authRef.current.currentUser;
    await updateProfile(user, { displayName: name.trim() });
    const account = await ensureProfile(user, name.trim());
    setProfile(account);
    return account;
  }

  async function verifyPassword(password) {
    const user = authRef.current.currentUser;
    if (!user?.email) throw new Error('Please sign in again before deleting your account.');
    try {
      await reauthenticateWithCredential(user, EmailAuthProvider.credential(user.email, password));
    } catch (error) {
      throw friendlyAuthError(error);
    }
  }

  function markDeletionRequested(message) {
    setSessionNotice(message);
    setDeletionPending(true);
    setProfile(null);
  }

  async function logout() {
    await signOut(authRef.current);
    setProfile(null);
  }

  return (
    <AuthContext.Provider
      value={{
        checkVerification,
        verifyPassword,
        markDeletionRequested,
        sessionNotice,
        deletionPending,
        configurationError,
        firebaseUser,
        initialising,
        login,
        logout,
        profile,
        refreshProfile,
        upgradeWithDemoPayment,
        register,
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
