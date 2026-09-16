# UIABO teammate setup guide

Windows PowerShell · Android emulator or Android phone · Updated 17 September 2026

This guide covers the current local implementation: text checking, saved results, link safety, forecast comparisons and optional OCR. Use it as the main setup guide; older README status lists may describe earlier versions.

**Before handing over:** use the code version that includes the forecast, scoring and result-screen updates described here. A GitHub clone only contains committed and pushed files. OCR is excluded from this handoff; its optional instructions describe separate local work. Skip that section unless the project owner also supplies the OCR implementation.

## Choose how you will run it

| Your goal | What you need |
| --- | --- |
| Run the complete app on your own computer | Follow steps 1–8. Set up your backend, Firebase configuration and provider keys. |
| Work on the mobile app using a teammate's running backend | Install Git, Node.js and the emulator/Expo Go; follow steps 2, 6 and 7. Use the backend computer's LAN address and the same Firebase project. Provider keys and Admin credentials stay on that backend computer. |
| Also test reading text from images | Complete the optional OCR section after text checking works. |

Text checking does not require Docker, WSL, a GPU or a local Ollama installation. These extra tools are needed only for hosting the current OCR model locally.

## 1. Install the tools

| Tool | Version / note | Download |
| --- | --- | --- |
| Git | Git for Windows | [Download](https://git-scm.com/downloads/win) |
| Python | Use standard 64-bit Python 3.14 to match the working environment; locally tested on 3.14.3 | [Download](https://www.python.org/downloads/windows/) |
| Node.js and npm | Use Node.js 24 LTS; locally tested on 24.14.0 | [Download](https://nodejs.org/en/download) |
| Android Studio | Required for the Android emulator; optional if using a physical phone | [Download](https://developer.android.com/studio) |
| Expo Go | Install a version compatible with this project's Expo SDK 57 | [Expo Go downloads](https://expo.dev/go) |

The project uses Expo SDK 57 / React Native 0.86. The [versioned Expo documentation](https://docs.expo.dev/versions/v57.0.0/) lists Node.js 22.13.x as its minimum. Keep the versions in `mobile/package.json` and the lockfile; do not create a new Expo project or upgrade packages during setup.

After installing, open a new PowerShell terminal and check:

```powershell
git --version
py -3.14 --version
node --version
npm.cmd --version
```

For an emulator: open Android Studio's Device Manager, create an Android virtual device with a Google Play system image, download the image and start the device. Complete the normal Android setup. See [Expo environment setup](https://docs.expo.dev/get-started/set-up-your-environment/).

## 2. Get the project

The examples use `C:\Dev\uiabo`. Replace that path throughout if you clone elsewhere.

```powershell
New-Item -ItemType Directory -Force C:\Dev
cd C:\Dev
git clone https://github.com/dmanistheproman/uiabo.git
cd C:\Dev\uiabo
git branch --show-current
git log -1 --oneline
```

- Ask the owner for repository access if GitHub rejects the clone.
- Confirm the branch and commit with the owner before comparing results.
- For an existing clean checkout, use `git pull --ff-only` instead of cloning again. Check `git status` first and preserve your own edits.

## 3. Get access to Firebase and the APIs

Ask the project owner for:

- The team's Firebase project and its **Web app configuration**.
- Approved Firebase Admin credentials for running your own backend, or access to create credentials under the team's process.
- Your own provider keys or approved team keys for Ollama, Google Fact Check and Tavily.
- A Google Web Risk key if testing link safety.

All provider registration and documentation links are in [API_SERVICES.md](API_SERVICES.md).

### Firebase setup

Use the same Firebase project on the mobile app and backend. If the team project already exists, use it instead of creating a second project.

1. Open the [Firebase Console](https://console.firebase.google.com/).
2. Confirm **Authentication → Sign-in method → Email/Password** is enabled.
3. Confirm a **Cloud Firestore** database exists. For a new project, create the default database; the current backend uses the default database.
4. Under **Project settings → Your apps**, use or register a **Web app** and copy its configuration. Expo uses the Firebase JavaScript SDK even on Android.
5. For the backend, follow the [Firebase Admin setup instructions](https://firebase.google.com/docs/admin/setup). An authorized project member can generate a service-account key under **Project settings → Service accounts**.
6. Store the JSON outside the repository, for example `C:\uiabo-secrets\service-account.json`. Use your actual file path in step 4.

The mobile app does not access Firestore directly. Keep database access through the backend; opening Firestore client rules is not a fix for Admin credential errors. Using the team database means your test accounts and completed app checks will be saved there.

### Provider setup

- **Ollama:** create a cloud API key with access to the models used by the project. It is used for claim analysis, retrieval relevance and semantic assessment.
- **Google Fact Check:** enable **Fact Check Tools API** in the project that owns your key. The current code uses claim search.
- **Tavily:** copy the API key itself, not the Tavily MCP URL.
- **Web Risk:** enable **Web Risk API**, configure billing and use a key permitted to call it. See [the link-safety setup guide](backend/WEB_RISK_SETUP.md). This is separate from Google Fact Check.
- **NEA/MSS forecast:** no additional key is required by the current implementation.

## 4. Create the three environment files

These are separate files with different readers. Use the exact filenames, not `.env.txt`.

| File | Used by |
| --- | --- |
| `C:\Dev\uiabo\.env` | Text pipeline settings, provider keys and Firebase Admin credential path |
| `C:\Dev\uiabo\backend\.env` | Web Risk and local OCR configuration |
| `C:\Dev\uiabo\mobile\.env` | Expo's Firebase client configuration and backend address |

All three local `.env` files are ignored by Git. Existing terminal environment variables take precedence over dotenv values. Keep private provider keys and the Admin JSON out of `mobile/.env` and source control.

### Project root: `C:\Dev\uiabo\.env`

Create this file with your own values:

```dotenv
OLLAMA_API_KEY=replace_with_your_key
GOOGLE_FACT_CHECK_API_KEY=replace_with_your_key
TAVILY_API_KEY=replace_with_your_key

EVIDENCE_RETRIEVAL_MODE=web
EVIDENCE_ASSESSMENT_MODE=semantic
OLLAMA_ASSESSMENT_MODEL=gpt-oss:120b

GOOGLE_APPLICATION_CREDENTIALS="C:/uiabo-secrets/service-account.json"
```

Use forward slashes in the quoted credential path as shown. The tracked `.env.instructions` is another starting template, but its retrieval mode is `catalogue`; change that to **`web`** to use the current broader retrieval and forecast integration.

### Backend: `C:\Dev\uiabo\backend\.env`

```dotenv
WEB_RISK_API_KEY=replace_with_your_web_risk_key
OCR_BASE_URL=http://127.0.0.1:8001
```

If you are not testing link safety yet, leave `WEB_RISK_API_KEY` empty. Text checks can still work; link checks will report unavailable. The OCR address is used only when OCR is requested.

### Mobile: `C:\Dev\uiabo\mobile\.env`

For a fresh setup, copy `mobile/.env.example` to `mobile/.env`. Fill it with the Firebase **Web app** values:

```dotenv
EXPO_PUBLIC_FIREBASE_API_KEY=your_firebase_web_api_key
EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
EXPO_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET=copy_from_firebase_config
EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=copy_from_firebase_config
EXPO_PUBLIC_FIREBASE_APP_ID=copy_from_firebase_config
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000
```

The Firebase web API key is different from the Google Fact Check and Web Risk keys. Copy the storage bucket exactly as shown by Firebase; this configuration value does not mean OCR images are uploaded to Firebase Storage.

## 5. Install and start the backend

In PowerShell:

```powershell
cd C:\Dev\uiabo\backend
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Leave this terminal running. Using the full Python path avoids needing `Activate.ps1` or changing PowerShell's execution policy. On later runs, skip creating the environment and reinstalling dependencies unless they changed.

In another terminal, check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected: `status` is `ok`. API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

**A healthy server does not prove provider keys or Firebase credentials work.** Those are exercised by authenticated app requests. Analysis routes require a verified Firebase token, so an unauthenticated request in Swagger returning 401 is expected.

## 6. Set the right backend address

| App location | `EXPO_PUBLIC_API_URL` | Backend host argument |
| --- | --- | --- |
| Android emulator on the backend PC | `http://10.0.2.2:8000` | `--host 127.0.0.1` |
| Physical phone on the same Wi-Fi | `http://BACKEND_PC_LAN_IP:8000` | `--host 0.0.0.0` |
| Emulator on a different teammate's PC | `http://BACKEND_PC_LAN_IP:8000` | `--host 0.0.0.0` |

`10.0.2.2` is the Android emulator's address for its host computer. Inside the emulator, `127.0.0.1` refers to the emulator itself. See [Android emulator networking](https://developer.android.com/studio/run/emulator-networking).

For a phone or another computer, find the backend PC's active Wi-Fi/Ethernet IPv4 address with `ipconfig`. Stop the existing backend with **Ctrl+C** and restart it with:

```powershell
cd C:\Dev\uiabo\backend
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use the actual LAN address in the mobile configuration, such as `http://192.168.1.50:8000`, never `0.0.0.0`. Both devices must be able to reach the same network. Allow Python and Node.js through Windows Firewall on the trusted private network when prompted. Do not forward development ports to the public internet.

## 7. Install and start the mobile app

Start the Android emulator first, then open a separate PowerShell terminal:

```powershell
cd C:\Dev\uiabo\mobile
npm.cmd ci
npx.cmd expo start --lan
```

- Press **a** to open the Android emulator.
- On a physical Android phone, open Expo Go and scan the QR code.
- Press **r** to reload the app.
- Leave both the Expo terminal and backend terminal running.
- On subsequent runs, `npx.cmd expo start --lan` is enough unless dependencies changed.

If Expo Go reports an incompatible SDK, install the SDK 57-compatible Android version from [Expo Go downloads](https://expo.dev/go). Do not change the project's Expo version just to match a different client.

For same-PC emulator bundle connection problems, open `exp://10.0.2.2:8081` in Expo Go. Port **8081** serves the mobile JavaScript; port **8000** serves the backend. An Expo tunnel does not automatically expose your backend.

## 8. Verify the complete app flow

1. Create an account in the app using an email address you can access.
2. Open the Firebase verification email and follow its link.
3. Return to the app and select **I have verified my email**.
4. Confirm the home screen shows your name and remaining allowance. This checks Firebase identity and backend account access.
5. Open **Check text** and submit a short factual English statement, for example: `Singapore is located in Southeast Asia.`
6. Confirm a completed result appears. Read the explanation and sources; the exact score is not a setup pass/fail criterion.
7. Open **Results** and reopen the saved result. This checks result persistence and ownership.
8. If Web Risk is configured, submit `https://example.com/` using **Check link safety**. A successful no-match means no known threat was found, not guaranteed safety.

New free accounts have **one completed check per day**. Premium accounts have **60 per calendar month**, using Singapore reset times. For repeated testing or OCR access, ask the project owner to grant your test account Premium. The app cannot grant itself that role. Failed checks do not consume allowance; a completed partial assessment can.

If the text check works but link safety fails, check the Web Risk key, API enablement and billing separately.

## Optional: run OCR on your PC

Skip this section if you only need text and link checking. To use OCR through a teammate's backend, that backend can host OCR; your own computer does not need a GPU.

For the current local Docker setup, you need a supported NVIDIA GPU with enough available VRAM, current NVIDIA drivers, WSL 2 and Docker Desktop's WSL 2 backend. Model readiness and available GPU memory must be checked on that machine; installing Docker alone is not enough. See [Docker GPU requirements](https://docs.docker.com/desktop/features/gpu/).

1. Install WSL/Ubuntu from an Administrator PowerShell terminal if it is not already installed:

   ```powershell
   wsl --install -d Ubuntu
   ```

2. Restart Windows if requested, open Ubuntu and finish creating its Linux user. Run `wsl --update`. See [Microsoft's WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install).
3. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), enable its WSL 2 backend and Ubuntu integration, and start Docker Desktop.
4. Start the OCR server from PowerShell:

   ```powershell
   docker run --rm --name uiabo-ocr --gpus all --ipc=host `
     -p 127.0.0.1:8001:8000 `
     -v uiabo-ocr-models:/root/.cache/huggingface `
     vllm/vllm-openai:unlimited-ocr `
     baidu/Unlimited-OCR `
     --trust-remote-code `
     --logits_processors vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor `
     --no-enable-prefix-caching `
     --mm-processor-cache-gb 0
   ```

5. Wait for the image/model downloads and model loading to finish. Leave that terminal running. In a separate terminal:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8001/v1/models
   ```

6. Confirm the response lists `baidu/Unlimited-OCR`. If the container is already running, do not start a second one.
7. Keep `OCR_BASE_URL=http://127.0.0.1:8001` in `backend/.env` and restart the backend after configuration changes.
8. Sign in with a Premium test account, select **Read image text**, choose a screenshot, review/correct the extracted text, then submit it for checking.

You do not need to clone Unlimited-OCR separately when using this container command. The image and model are downloaded by Docker/the model server. The local OCR API uses an OpenAI-compatible request format but does **not** require an OpenAI API key.

See [OCR_SETUP.md](backend/OCR_SETUP.md) for limits and troubleshooting details, and the [model repository](https://github.com/baidu/Unlimited-OCR) for upstream instructions. OCR checks the extracted words, not image authenticity. Deepfake detection remains pending.

## Daily startup commands

Once setup is complete, open two terminals.

**Terminal 1 — backend, same-PC emulator:**

```powershell
cd C:\Dev\uiabo\backend
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — mobile:**

```powershell
cd C:\Dev\uiabo\mobile
npx.cmd expo start --lan
```

Press **a**. Start the optional OCR container as well only when needed. For a phone or shared backend, use `--host 0.0.0.0` and the LAN configuration from step 6.

After editing backend configuration or pulling backend changes, stop it with **Ctrl+C** and run its command again. After editing `mobile/.env`, stop Expo and run `npx.cmd expo start --clear --lan`, then reload the app. Saved results keep their original assessment; submit a new check to test new pipeline behavior.

## Common problems

| Problem | Check / action |
| --- | --- |
| `python`, `py`, `node` or `git` is not recognized | Finish installation, open a new terminal and check the versions. Use `py -3.14` for the backend environment. |
| PowerShell blocks `npm.ps1` | Use `npm.cmd` and `npx.cmd` as shown. |
| `No module named ...` | Install `backend/requirements.txt` with `.venv\Scripts\python.exe`; run the server using that same interpreter. |
| Port 8000 is already in use | Check the existing backend terminal. Stop your own older server with Ctrl+C rather than launching another copy. |
| App cannot reach the backend | Check `/health`, the address table in step 6, network access and firewall. Restart Expo after changing its environment file. |
| Login works but profile loading fails | Check Firebase Admin JSON path, its project and permissions. Mobile and backend must use the same Firebase project. |
| Verification email has not arrived | Check spam, resend in the app and confirm Email/Password sign-in is enabled. |
| Text check says a provider is unavailable | Check the three root-level provider keys, API enablement, provider quotas/model availability and backend error code. A health check does not test these. |
| Old retrieval or scoring behavior | Set `EVIDENCE_RETRIEVAL_MODE=web` and `EVIDENCE_ASSESSMENT_MODE=semantic`, verify the code version, restart the backend and submit a new check. |
| Link safety is not available | Check `backend/.env`, Web Risk API enablement, key restrictions and billing. Restart the backend. |
| OCR is locked | The verified test account needs a server-managed Premium role. |
| OCR is unavailable / connection closes | Check Docker Desktop, container logs, GPU memory and `/v1/models`. Wait until the model is ready. |
| An edited key seems ignored | Check for an old value exported in that terminal. Shell variables take precedence. Open a fresh terminal and restart. |

## Optional developer checks

Run offline backend tests without loading local dotenv credentials:

```powershell
cd C:\Dev\uiabo\backend
$env:PYTHON_DOTENV_DISABLED = '1'
.\.venv\Scripts\python.exe -B -m pytest -q
Remove-Item Env:\PYTHON_DOTENV_DISABLED
```

Mobile presentation tests:

```powershell
cd C:\Dev\uiabo\mobile
node --test tests/assessment.test.mjs tests/resultPresentation.test.mjs
```

The local implementation passed 786 backend tests and 25 mobile tests on 17 September 2026. These are regression checks, not proof of detection accuracy or of a fresh installation on every computer. Do not run live smoke-test scripts merely to check installation: some consume provider quotas and some write Firestore test data; read each script's instructions first.
