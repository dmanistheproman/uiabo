# Google Cloud Vision OCR

Branch: `feature/google-vision-ocr`, based on `integration/jev-ocr` at `d29d332`.
Local folder: `C:\Dev\uiabo-vision`.

This branch replaces the OCR server call when `OCR_PROVIDER=google_vision`. The existing image-selection, text-review and fact-checking screens stay the same. Unlimited-OCR is retained as an explicitly selectable alternative. The separate, uncommitted image-storage work is not included.

## Enable Google Vision

1. Open [Cloud Vision API for UIABO](https://console.cloud.google.com/apis/library/vision.googleapis.com?project=uiabo-69497).
2. Click **Enable**. Billing must be enabled for the project.
3. Keep the backend's existing Google credentials configured. Locally this is the external service-account file referenced by `GOOGLE_APPLICATION_CREDENTIALS`; never commit or send its contents in chat.
4. If a different runtime service account is used, it needs permission to consume the enabled API in this project, such as `roles/serviceusage.serviceUsageConsumer`. API enablement is an administrator action, not a runtime permission.
5. Set this in the project root `.env`:

```dotenv
OCR_PROVIDER=google_vision
```

Keep `EVIDENCE_PIPELINE_V3=1` and the existing text-pipeline configuration. No new Vision API key is needed. Start with `--env-file ..\.env` so root configuration takes precedence over backend defaults. The local Vision worktree already has private configuration copied and the provider selected.

## Run on Donovan's desktop

Stop the other branch's backend/Expo terminals first; these commands use the same ports. Docker, WSL and Unlimited-OCR are unnecessary for Google OCR. The backend still loads the separate deepfake image detector.

Backend:

```powershell
cd C:\Dev\uiabo-vision\backend
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --env-file ..\.env --host 0.0.0.0 --port 8002
```

Mobile:

```powershell
cd C:\Dev\uiabo-vision\mobile
npx.cmd expo start --port 8082 --android
```

For a fresh checkout, install `backend/requirements.txt` in a virtual environment and run `npm ci` in `mobile`. No additional Python dependencies are required by this adapter.

## Behaviour

- POST `/analysis/ocr` retains the same request and response structure; `provider` becomes `Google Cloud Vision`.
- One `DOCUMENT_TEXT_DETECTION` feature is requested per image, suitable for dense message screenshots.
- Existing file-size/pixel limits, image orientation handling and metadata removal apply before sending to Google.
- Literal extracted text is preserved, including words that look like instructions or model markers.
- Empty, oversized and malformed output is rejected. Partial text accompanying a Google error is not treated as a successful extraction.
- Premium, verified and active-account checks run before OCR processing.
- OCR images and preview text are not saved to Firestore or Firebase Storage. The image is sent to Google for processing.
- Extraction uses no UIABO allowance; Google API usage can still be billable.
- Requests have a timeout and one active OCR slot per backend process. There is no automatic paid-request retry or fallback to desktop OCR.
- Missing API access, quota exhaustion and outages have clear app errors without exposing credentials or provider messages.

## Test

- Read a clear English screenshot containing names, a date and a currency amount.
- Compare extracted text with the image, edit it, then submit a fact-check.
- Try a blank image, an unsupported image and a free account.
- Check that extraction does not change allowance or create an image object.
- Compare representative screenshots against Unlimited-OCR before deciding which provider to merge into integration.

To return to desktop OCR, set `OCR_PROVIDER=unlimited` and the existing `OCR_BASE_URL`, restart the backend, and start the OCR server. Provider selection is cached until restart.

Hosting this adapter does not itself deploy the backend. Google OCR no longer depends on your desktop GPU, but the mobile app still needs a running backend until that backend is hosted.

## Cost and references

One screenshot with one OCR feature is one feature unit. Monitor Vision usage and configure suitable service quotas in Google Cloud; a billing budget is an alert, not a spending cap. The existing per-process concurrency limit is not a monthly budget limit.

- [OCR features](https://docs.cloud.google.com/vision/docs/ocr)
- [Official REST endpoint](https://docs.cloud.google.com/vision/docs/reference/rest/v1/images/annotate)
- [Setup](https://docs.cloud.google.com/vision/docs/setup)
- [Current pricing](https://cloud.google.com/vision/pricing)


## Validation ? 1 November 2026

- 1,140 backend tests passed; four unrelated live-provider cases deselected.
- 60 OCR tests passed across Unlimited-OCR and Google Vision (32 new Vision test cases).
- Live Vision: generated English notice extracted correctly in 0.92 seconds.
- Live Vision: generated name/date/amount notice extracted correctly in 0.69 seconds.
- Live Vision: blank image returned `OCR_NO_TEXT` in 0.58 seconds.
- These three calls did not write Firestore/Storage data or consume user allowances.
- The Vision API is now enabled and the existing backend service account successfully authenticated.
- These are smoke tests, not an accuracy benchmark. Representative screenshots and authenticated emulator testing remain to be done.
