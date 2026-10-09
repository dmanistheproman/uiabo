import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const missing = Object.entries(config).filter(
  ([, value]) => !value || value.startsWith('replace_me') || value.startsWith('your-'),
);

export function initFirebaseAuth() {
  if (missing.length) {
    throw new Error(
      `Firebase web config is incomplete. Copy .env.example to .env and fill in: ${missing
        .map(([key]) => key.replace('VITE_', ''))
        .join(', ')}. Use the same values as mobile/.env.`,
    );
  }
  return getAuth(initializeApp(config));
}
