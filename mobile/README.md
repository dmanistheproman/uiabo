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
- TDM home grid: text, webpage link, image + caption, OCR, image context and AI image; no audio
- Free/premium allowance display, with upcoming image tools clearly marked
- Submit English text to the live pipeline, display progress/errors, and show cited results
- View and reopen the signed-in user's saved results from Firestore
- Share a result through the Android share sheet and open its source links
- Send a fresh Firebase ID token with every backend account request

Text checking and result history are connected. Webpage analysis and image features remain explicitly unavailable in this prototype; the webpage tab offers a way to check copied text. Premium accounts have 60 checks per calendar month. Image eligibility does not mean those pipelines are implemented.

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
npx.cmd expo start --lan
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
9. Confirm that the home screen shows the user's name, plan and server-provided allowance. Free users receive one completed check per day; premium users receive 60 per calendar month. Both reset at midnight Singapore time.
10. Open **Check text**, enter a short English claim, and submit. Verify progress, a result with uncertainty and citations, and a reduced allowance.
11. Open **Results**, refresh and reopen the saved result. Verify that an interrupted request can be recovered without charging twice when the same request key is retried.
12. Verify the Firestore `analysis_results` document contains the authenticated `user_id`, `input_type`, evidence snapshot and timestamps. Failed checks should leave the allowance unchanged.
13. Open **Profile**, change the name, save it, and verify the `users` Firestore document changed.
14. Sign out and sign in again.
15. Use **Forgot password?** to test the reset-email flow.

## Main files

- `App.js` handles authentication and Home, Results, Help and Profile navigation, including the text and result screens.
- `src/config/firebase.js` initializes Firebase Auth and persists the login session through React Native AsyncStorage.
- `src/auth/AuthContext.js` contains registration, login, verification, reset, profile, and logout actions.
- `src/services/api.js` attaches a fresh Firebase bearer token to FastAPI requests. Text submissions also carry an idempotency key and a 180-second client timeout.
- `src/screens/` contains the user-facing screens.
- `src/components/` contains reusable large, accessible buttons and screen layout.
- `.env.example` lists the local configuration values required to run the app.

## Local Android development

On this Windows machine, `npx.cmd` avoids PowerShell script execution-policy issues.
If Expo's localhost mode binds only to IPv6 and the emulator cannot download the
bundle, start Metro with `--lan` and open `exp://10.0.2.2:8081` in Expo Go. The backend
address remains `http://10.0.2.2:8000`. No provider API keys belong in this app.

The backend reads the project-root `.env`, including the service-account path.
Text checks and result routes require verified Firebase tokens and active accounts;
the client cannot choose the result owner, role or allowance. Shared results contain
an explanation and citation URLs, not a publicly accessible Firestore record.

The September 7 integration report and emulator captures are in
`../evaluation/reports/app-integration/`. Source interpretation remains a prototype:
review citations before treating any concern label as reliable.
