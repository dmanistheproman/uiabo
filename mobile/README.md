# UIABO mobile application

This folder contains the first working Android app slice. It uses Expo and React Native for the screens, Firebase Authentication for email/password accounts, and the FastAPI backend for UIABO profile data.

## What works

- Create a free account with a name, email, password, and consent checkbox
- Send and resend a Firebase verification email
- Block the home screen until the email is verified
- Sign in and remain signed in after restarting the app
- Request a password-reset email without revealing whether an account exists
- View and change the user's name
- Sign out with confirmation
- Display the free daily allowance returned by FastAPI
- Show image and audio features as locked premium features
- Send a fresh Firebase ID token with every backend account request

The text checker and result history cards are placeholders. They are clearly marked **Coming next** and are not connected yet.

## One-time Firebase setup

1. Open Firebase Console and use the same project as the backend.
2. Go to **Authentication > Sign-in method** and enable **Email/Password**.
3. Go to **Project settings > Your apps** and register a **Web app**. The Firebase JavaScript SDK used by Expo needs this web configuration even though UIABO is an Android app.
4. Copy `.env.example` to `.env`.
5. Replace each Firebase placeholder with the values shown for the Firebase web app.

The `EXPO_PUBLIC_` Firebase values identify the Firebase project; they are not the Firebase Admin service-account secret. Never put the backend service-account JSON or a private key in this folder.

## Backend address

Choose the correct `EXPO_PUBLIC_API_URL` in `.env`:

- Android Studio emulator: `http://10.0.2.2:8000`
- Physical phone: `http://YOUR_COMPUTER_LAN_IP:8000`

For a physical phone, connect the phone and computer to the same network. Start FastAPI so it accepts connections from the network:

```powershell
cd C:\Dev\uiabo\backend
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\service-account.json"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0
```

Do not expose this development server directly to the internet.

## Run the app

```powershell
cd C:\Dev\uiabo\mobile
npm install
npx expo start
```

Scan the QR code using Expo Go on Android, or press `a` to open an Android emulator. Restart Expo after changing `.env`.

## End-to-end test

1. Start the FastAPI backend with Firebase credentials.
2. Start the Expo app.
3. Select **Create a free account** and enter a real email address.
4. Confirm that the app displays **Verify your email**.
5. In Firebase Console, confirm that the user appears under **Authentication > Users**.
6. In Firestore, confirm that documents with the same Firebase UID appear in `users` and `usage_allowances`.
7. Open the verification email and follow its link.
8. Return to the app and select **I have verified my email**.
9. Confirm that the home screen shows the user's name, free plan, and one remaining text check.
10. Open **Profile**, change the name, save it, and verify the `users` Firestore document changed.
11. Sign out and sign in again.
12. Use **Forgot password?** to test the reset-email flow.

## Main files

- `App.js` decides whether to show setup, authentication, verification, home, or profile.
- `src/config/firebase.js` initializes Firebase Auth and persists the login session through React Native AsyncStorage.
- `src/auth/AuthContext.js` contains registration, login, verification, reset, profile, and logout actions.
- `src/services/api.js` attaches a fresh Firebase bearer token to FastAPI requests.
- `src/screens/` contains the user-facing screens.
- `src/components/` contains reusable large, accessible buttons and screen layout.
- `.env.example` lists the local configuration values required to run the app.
