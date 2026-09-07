# Android and Firestore integration — 7 September 2026

The Android text-check flow now calls the live pipeline with the signed-in user's
Firebase ID token. Completed and failed results are saved in Firestore with their
owner, evidence snapshot and timestamps. Results history and detail are restricted
to that owner. The home screen follows the submitted TDM, PDF pages 57–58, with
text, webpage link, image + caption, OCR, image context and AI image cards. Audio
has been removed. The ownership fields follow the database design on pages 67–68.

## Verification

- Backend suite: **262 passed**; one existing Starlette/httpx deprecation warning.
- Expo Android production export passed with SDK 57 dependencies.
- [Live Firebase/Firestore check](firestore-live.json): real Firebase ID tokens,
  live claim analysis and retrieval, saved evidence, owner history/detail,
  idempotent retry, exhausted allowance rejection and another user's access denied.
  Direct Firestore reads without authentication and with another user's token
  were also denied. Tests used isolated integration accounts.
- Android emulator: signed-in home, saved history and a saved result with citations
  were opened successfully. Captures: [Premium home](home-premium.png),
  [history](history.png), [result](result.png).
- The owner's account was upgraded in Firestore at their explicit request and
  verified through the authenticated API and Android home screen: Premium,
  **60 checks available**. No payment or billing subscription was created.

## Allowance and persistence behavior

Free accounts receive one completed check per Singapore calendar day. Premium
accounts receive 60 per Singapore calendar month. Technical failures do not consume
allowance; completed Not Enough Information results do. The server reads the plan
from the account record. The app cannot set its own role, owner or allowance.

A per-user lease prevents overlapping submissions. Final persistence and charging
are atomic; an idempotency key makes a repeated successful submission return its
existing result. Saved result details can be reopened after an app restart.

## Current limits

Webpage fetching and image/deepfake pipelines remain unimplemented. Their screens
state this; the link tab offers checking copied text. Premium enables the monthly
allowance, while image tools remain marked as coming soon. Payments are not built.

Poon's current stance/scoring implementation uses lexical rules and can misread a
source describing a myth as supporting it. This integration verifies the data flow,
not assessment accuracy. The app displays uncertainty and evidence for review.

History currently queries records belonging to one user and sorts/paginates them
in the backend. This works with existing Firestore permissions but reads all that
user's records. `firestore.indexes.json` supplies an index for a future database
ordered query; it has not been deployed because the current service account lacks
index-administration permission. Larger histories will need that optimization.

## Reproduce

Run the backend with project-root `.env` provider keys and an external Firebase
Admin credential path. Run Expo from `mobile`; see its README for the Android
emulator address. Provider secrets never belong in the mobile bundle.

The live backend smoke script accepts a local file containing credentials for
isolated integration accounts (see its `--help`); keep that file outside Git:

```powershell
cd backend
.\.venv\Scripts\python.exe -B -m scripts.firestore_app_smoke_test --help
.\.venv\Scripts\python.exe -B -m pytest -q
cd ../mobile
npx.cmd expo export --platform android --output-dir .expo/export-check
```
