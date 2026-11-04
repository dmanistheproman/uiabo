# Team integration testing

**2 November update:** The latest local fixes are in `C:\Dev\uiabo-vision` on `feature/evidence-label-consistency`; they have not been pushed. See [the completed fixes and connected app functions](RELIABILITY_UPDATES.md). The older combined-branch instructions below apply until those changes are shared.

Use branch `integration/jev-ocr`. This is the combined testing version, not the final release.

## Get the code

Commit your current work on your own feature branch before switching. Do not overwrite local changes.

```powershell
git fetch origin
git switch integration/jev-ocr
git pull --ff-only origin integration/jev-ocr
```

If this branch is already checked out in another Git worktree, use that folder. On Donovan's desktop it is `C:\Dev\uiabo-integration`.

## Install and configure

- Backend: activate your project virtual environment and run `python -m pip install -r requirements.txt` from `backend`.
- Mobile: run `npm ci` from `mobile`.
- Portal: run `npm ci` from `portal`.
- Keep private `.env` files local. Follow `TEAMMATE_SETUP.md` for Firebase and provider credentials.
- Root `.env`: keep `EVIDENCE_PIPELINE_V3=1` and configure `GEMINI_API_KEY` as well as the existing text/search provider keys.
- Backend OCR configuration: use `OCR_BASE_URL=http://127.0.0.1:8001` only on the desktop hosting OCR. Remote access from teammates is not set up yet.
- Mobile `.env`: Android emulator uses `EXPO_PUBLIC_API_URL=http://10.0.2.2:8002`.
- Portal `.env`: configure the public Firebase settings, leave `VITE_API_URL` empty, set `VITE_PROXY_TARGET=http://127.0.0.1:8002`.
- First backend startup loads the deepfake detector and may download model weights. Allow extra time and disk space.

## Start in three terminals

Backend, from `backend`:

```powershell
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --env-file ..\.env --host 0.0.0.0 --port 8002
```

Mobile, from `mobile`:

```powershell
npx.cmd expo start --port 8082 --android
```

Portal, from `portal`:

```powershell
npm run dev
```

Open the portal at http://localhost:5174. Use a verified operational account with the appropriate role. Do not run demo-seeding scripts against the shared database.

## Test checklist

- [ ] Register, verify email, sign in, sign out, and load allowance.
- [ ] Submit text; check label-first result, explanation, sources and credibility details.
- [ ] Reopen text and link results from history.
- [ ] Report an incorrect result and submit general feedback from Profile.
- [ ] Report completed deepfake, image-context and link results; inspect their details and saved images in the Data Engineer portal.
- [ ] Enable `DEMO_PAYMENTS_ENABLED=1`; use a Free app account to cancel checkout, then complete it and check Premium access. Retry without resetting consumed allowance. See `DEMO_PREMIUM_SETUP.md`.
- [ ] Premium account: select an image, extract OCR text, edit it and check the text.
- [ ] Run deepfake image analysis and reopen its result from history.
- [ ] Run image-context screenshot analysis and reopen its result from history.
- [ ] Check admin and data-engineer portal pages with separate test accounts.
- [ ] With a former staff test account, remove portal permissions, convert it to Free in Find users, then sign in to the app with the existing credentials. Confirm portal access is refused and repeated conversion cannot reset allowance.
- [ ] Check service-error messages, retry behaviour and allowance changes.

Use test accounts. Record the branch/commit, feature, input, expected result, actual result, error text and screenshot for each issue. Never attach API keys or tokens.

## Remaining acceptance work after the 2 November fixes

Webpage-text extraction is deferred. Copy article text into Check text. Check link safety remains available.

- Exercise the authenticated emulator journeys after restarting the updated backend.
- Check image context: compare a screenshot with no typed caption against an image with an explicit caption. Confirm Premium access and that failed requests do not reduce allowance.
- With a disposable account only, use Profile ? Delete my account. An incorrect password must not submit deletion. Cancelling confirmation must keep the account. A confirmed valid request should sign out after acceptance; check cleanup after the backend worker runs. Never use a team member's real account for this destructive test.
- While an image check is running, verify that duplicate submits and navigation are blocked. Recover a photo-picker activity interruption into its original feature.
- Confirm Help, Premium and image-result caption wording match the features now available.
- Present one image-context/image-caption feature; remove the duplicate locked tile.
- Align image labels and explanations with the team-reviewed definitions.
- Test photo-picker activity recovery across OCR and image screens.
- Evaluate detection accuracy on the agreed review set.
- Check live Firebase IAM and deletion behaviour with a disposable test account only.

The earlier image allowance/Premium checks, portal error display, run-ID/persistence ordering and administrator safeguards have been addressed locally. See `RELIABILITY_UPDATES.md` for the remaining limits and verification evidence.

## Merge verification (1 November 2026)

- Backend: 1,108 tests passed; four live-provider test cases deselected.
- Mobile result tests: 42 passed.
- Android export and portal production build passed.
- In-process backend startup: health returned 200; account and image endpoints rejected unauthenticated requests.
- JEV V3, OCR and the existing text-result presentation are retained.
- Authenticated emulator workflows and live provider accuracy still need team testing. Passing automated tests does not resolve the known issues above.
