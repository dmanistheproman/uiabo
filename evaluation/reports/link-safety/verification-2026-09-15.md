# Link safety implementation verification — 15 September 2026

- **Backend regression suite:** 501 tests passed, including 40 new link safety
  cases. Coverage includes URL validation, three threat categories, positive
  cache expiry, malformed responses, timeouts, provider errors, authentication,
  ownership, saved history, idempotent retries and allowance charging.
- **Real Firestore:** the link API route saved and reopened threat/no-match
  results with mock Web Risk responses. Replays did not charge twice. A different
  identity could not read the result. Temporary documents were removed. The
  authentication dependency was overridden with a temporary test identity;
  this was not a Firebase sign-in test. See `firestore-mock-provider.json`.
- **Live Google requests:** both the documented malware test URL and example.com
  returned access errors. A credential-safe diagnostic identified HTTP 403,
  `PERMISSION_DENIED`, reason `BILLING_DISABLED`, service
  `webrisk.googleapis.com`. Live threat/no-match detection is not yet verified.
- **Android:** JavaScript export passed using `--no-bytecode`. Standard Hermes
  bytecode export failed because Windows Application Control blocked
  `hermesc.exe`. No operating-system security settings were changed.
- **Emulator:** reloaded the app and visually checked the updated home tile and
  link input screen. The new screen renders its URL field, provider/privacy
  explanation, shared allowance information and navigation correctly. A live
  successful result could not be exercised while Google billing was disabled.
- **Runtime:** restarted the existing local backend and verified that its
  OpenAPI document includes `/analysis/link-safety`.
- **Secrets:** the supplied key is in ignored `backend/.env`, under
  `WEB_RISK_API_KEY`; it is not included in app code or tracked documentation.

## Remaining verification

Enable billing on the Google Cloud project that owns the Web Risk API key, then
run the live-provider Firestore smoke test described in `backend/WEB_RISK_SETUP.md`.
Use the emulator to review both a threat result and a no-match result afterward.
