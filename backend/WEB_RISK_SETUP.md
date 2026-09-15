# Link safety checks

The **Check link safety** screen checks public HTTP(S) URLs using Google Web Risk
Lookup. Webpage text extraction and misinformation assessment are separate features.

## Local setup

1. Enable **Web Risk API** in the Google Cloud project that owns the API key.
2. Link an enabled billing account to that project. Billing is required even when
   usage falls within the free Lookup allowance.
3. Restrict a server API key to Web Risk API. Keep it in `backend/.env`:

   ```dotenv
   WEB_RISK_API_KEY=your_key_here
   ```

4. Restart the backend after changing the key or environment configuration:

   ```powershell
   cd C:\Dev\uiabo\backend
   .\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

5. Start Expo in another terminal, then press `a` for the Android emulator:

   ```powershell
   cd C:\Dev\uiabo\mobile
   npx.cmd expo start
   ```

The backend environment is ignored by Git. Never put this key in an
`EXPO_PUBLIC_*` variable: those values are bundled into the mobile application.

## Behaviour

- `POST /analysis/link-safety` accepts `{"url":"https://example.com/"}` with a
  verified Firebase bearer token and optional `Idempotency-Key` header.
- The backend sends the URL to `https://webrisk.googleapis.com/v1/uris:search`
  and checks `MALWARE`, `SOCIAL_ENGINEERING`, and `UNWANTED_SOFTWARE` together.
- It does not download the submitted page, follow redirects, call an LLM, or
  extract claims. Unknown public domains are allowed; the misinformation
  pipeline's source allowlist is not used here.
- Only a valid empty JSON object is interpreted as **No known threats found**.
  A validated threat match is **Potentially dangerous link**. Invalid responses,
  timeouts, access errors and provider quota errors produce a failed check.
- Positive matches are cached in bounded process memory until Google's
  `expireTime`. Cached results retain the time of the original lookup. The
  cache is local to each worker and is cleared on restart. Empty responses are
  not cached for new checks.
- Results are stored in `analysis_results` with `input_type: link_safety`,
  using the existing ownership checks and atomic allowance transaction.
- Text and link checks share the existing allowance. Each completed check uses
  one submission, including a no-match result. Failed checks use none.
- Repeating an idempotency key returns the same saved result without charging
  again. It does not refresh an old result. A new check requires a new key.
- History shows link-specific verdicts and check times, without misinformation
  risk scores. The result screen does not offer an action to open the URL.

## Privacy and limitations

The full submitted URL is sent to Google and saved in the owner's Firestore
history. The input screen asks users to submit public links only and avoid
password-reset links, invitations or links containing access tokens. URLs with
embedded login credentials, local IP addresses or local hostnames are rejected.
This is input validation, not a guarantee that arbitrary URLs contain no secrets.

No match does not guarantee safety. Newly created threats and destinations of
redirects/shortened links may be missed. A threat match can be a false positive.
Saved results describe the time checked and do not continuously monitor a site.

## Verification

Offline regression checks (do not load private provider settings):

```powershell
cd C:\Dev\uiabo\backend
$env:PYTHON_DOTENV_DISABLED='1'
.\.venv\Scripts\python.exe -B -m pytest tests/test_link_safety.py tests/test_owned_analyses.py -q
```

Use a fresh terminal for a live check so dotenv is enabled. Google documents
`http://testsafebrowsing.appspot.com/s/malware.html` as a malware test URL;
submit its string to the API rather than opening the page. `https://example.com/`
is a useful no-match comparison, whose live verdict can change over time.

Real Firestore smoke test with temporary documents and mock Google responses:

```powershell
.\.venv\Scripts\python.exe -B -m scripts.link_safety_firestore_smoke_test --report ..\evaluation\reports\link-safety\firestore-mock-provider.json
```

Add `--live-provider` and use a different report filename to test Google too.
The script overrides the authentication dependency with an isolated test identity;
it tests Firestore integration, not Firebase sign-in. It removes its temporary
documents and does not consume an existing user's allowance.

If Google returns `BILLING_DISABLED`, enable billing in the key's project.
`SERVICE_DISABLED` means the API must be enabled there; other access errors can
indicate key restrictions. Do not log raw provider errors or credential headers.

## Official references

- [Lookup API](https://docs.cloud.google.com/web-risk/docs/lookup-api)
- [Setup and billing prerequisite](https://docs.cloud.google.com/web-risk/docs/detect-malicious-urls)
- [Lookup pricing](https://cloud.google.com/web-risk/pricing)
- [Threat caching](https://docs.cloud.google.com/web-risk/docs/caching)
- [Google's threat advisory](https://docs.cloud.google.com/web-risk/docs/advisory)
