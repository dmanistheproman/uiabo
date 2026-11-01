# Team integration testing

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
- [ ] Premium account: select an image, extract OCR text, edit it and check the text.
- [ ] Run deepfake image analysis and reopen its result from history.
- [ ] Run image-context screenshot analysis and reopen its result from history.
- [ ] Check admin and data-engineer portal pages with separate test accounts.
- [ ] Check service-error messages, retry behaviour and allowance changes.

Use test accounts. Record the branch/commit, feature, input, expected result, actual result, error text and screenshot for each issue. Never attach API keys or tokens.

## Known issues to fix after integration

- Image-context failures after caption extraction can consume allowance. Search provider failures can appear as completed insufficient-evidence results.
- Image-context and deepfake endpoints need server-side Premium checks.
- Admin suspension lacks self/last-admin protection, suspension reasons, session revocation and full audit logging. Do not suspend your only administrator.
- Data-engineer monitoring uses an undefined error setter; investigation save failures may be hidden.
- Pipeline run IDs and saved result IDs need alignment; completion must follow successful result storage.
- Access and monitoring audit trails remain incomplete; operational account creation is still CLI-based.
- Image upload limits, concurrency and provider timeouts need strengthening.
- Image + caption remains locked. Current image-context implementation extracts a caption from a screenshot; it does not provide reverse-image provenance checking or an editable caption step.
- Image result labels and supporting-citation requirements need alignment with the agreed label definitions.
- Test Android photo-picker activity recovery across OCR and the new image screens; current recovery originated in the OCR-only app.

Make fixes on feature branches and merge them into integration after review.

## Merge verification (1 November 2026)

- Backend: 1,108 tests passed; four live-provider test cases deselected.
- Mobile result tests: 42 passed.
- Android export and portal production build passed.
- In-process backend startup: health returned 200; account and image endpoints rejected unauthenticated requests.
- JEV V3, OCR and the existing text-result presentation are retained.
- Authenticated emulator workflows and live provider accuracy still need team testing. Passing automated tests does not resolve the known issues above.
