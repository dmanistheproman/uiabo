import React from 'react';
import {
  onAuthStateChanged,
  reload,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signOut,
  updateProfile,
} from 'firebase/auth';

import { initFirebaseAuth } from '../config/firebase';
import { ensureProfile, getProfile } from '../services/api';

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
  };
  return new Error(messages[error?.code] || error?.message || 'Something went wrong. Please try again.');
}

function suggestedName(user) {
  return user.displayName || user.email?.split('@')[0] || 'UIABO operator';
}

export function AuthProvider({ children }) {
  const [firebaseUser, setFirebaseUser] = React.useState(null);
  const [initialising, setInitialising] = React.useState(true);
  const [configurationError, setConfigurationError] = React.useState('');
  const authRef = React.useRef(null);

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

  async function login(email, password) {
    try {
      await signInWithEmailAndPassword(authRef.current, email.trim(), password);
    } catch (error) {
      throw friendlyAuthError(error);
    }
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
      return authRef.current.currentUser.emailVerified;
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
        configurationError,
        firebaseUser,
        initialising,
        login,
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
