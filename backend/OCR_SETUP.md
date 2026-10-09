# Read image text

Premium users can select a screenshot or photo, read its text using Unlimited-OCR,
edit the result, and submit the reviewed text to the existing fact-check pipeline.

## Run the services

Keep Docker Desktop running with its WSL 2 backend and NVIDIA GPU support enabled.
Start the OCR container in PowerShell:

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

If the container is already running, do not start another. Check readiness with:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/v1/models
```

The backend defaults to `http://127.0.0.1:8001`. For a different OCR host, set
`OCR_BASE_URL` in ignored `backend/.env` and restart the backend. The OCR model
endpoint is configured by the server, not supplied by the app user.

Install backend requirements, then run FastAPI:

```powershell
cd C:\Dev\uiabo\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, start Expo:

```powershell
cd C:\Dev\uiabo\mobile
npm.cmd install
npx.cmd expo start
```

Press `a` for Android, or `r` to reload an already open app. The photo picker is
provided by `expo-image-picker`, which is included in Expo Go. Native builds use
the image-picker config plugin with camera and microphone permissions disabled.

## App flow

1. Sign in with a Premium account and open **Read image text**.
2. Tap **Choose image** and select a screenshot or photo.
3. Review the selected image, then tap **Read text from image**.
4. Compare the extracted words with the image; edit dates, amounts, names and
   missing words. Keep the intended message within 5,000 characters.
5. Tap **Check this text** to run the existing misinformation pipeline.
6. The saved assessment appears as **Image text** in Results.

OCR is text extraction, not image authenticity or misinformation detection.
The text pipeline still supports English inputs only. Extracting other scripts
does not extend the fact-check pipeline's language support.

## API and limits

- `POST /analysis/ocr` requires verified Firebase authentication and an active
  Premium profile. The JSON body contains `image_base64`, with no data-URI prefix.
- Uploads are bounded while streaming, even without a Content-Length header.
  The decoded image limit is 8 MiB, 16 million pixels, and 12,000 pixels per edge.
- Only still JPEG, PNG and WebP images are accepted. The backend validates the
  decoded file, applies EXIF orientation, removes metadata and re-encodes it.
- A single backend worker permits one OCR inference at a time. A concurrent
  request gets `OCR_BUSY`; there is no unbounded GPU queue. Keep the prototype
  on one backend worker until a shared inference queue is added.
- The model receives the documented parsing prompt and decoding parameters.
  Layout markers and image-description blocks are removed before text review.
- Empty, malformed or truncated output is rejected. Output over 5,000 characters
  is shown in full up to 20,000 characters, with instructions to shorten it;
  it is never silently submitted or silently cut to the fact-check limit.
- The provider timeout is 120 seconds. User-facing errors do not include raw
  model responses, image bytes or server details.

## Storage and allowance

- Extraction does not modify the usage allowance or create a saved result.
- The image and raw OCR response are not written to Firestore or application
  files. They are processed in memory and sent to the configured OCR service.
- The edited text is submitted to `/analysis/text` with `input_source: ocr`.
  This route also enforces Premium access for that source.
- Completed assessments use the same atomic save/allowance transaction as typed
  text. Each uses one check; failures use none. Retrying the same idempotency key
  returns the saved result without charging twice.
- The saved record has `input_type: ocr_text` and `input_source: ocr`. This source
  is a workflow label, not proof that the reviewed words exactly match an image.
- Result/history screens show **Image text** and explain that the assessment
  concerns the reviewed words, not whether the image is authentic.

## Tests

Offline tests (new terminal; avoids private provider configuration):

```powershell
cd C:\Dev\uiabo\backend
$env:PYTHON_DOTENV_DISABLED='1'
.\.venv\Scripts\python.exe -B -m pytest -q
```

Live OCR → fact-check → Firestore test (fresh terminal with dotenv enabled):

```powershell
cd C:\Dev\uiabo\backend
.\.venv\Scripts\python.exe -B -m scripts.ocr_integration_smoke_test --report ..\evaluation\reports\ocr\live-integration.json --image ..\mobile\.expo\ocr-test.png
```

The live test uses an isolated authentication override and temporary Premium
profile. It does not test Firebase sign-in or use an existing user's allowance.
Temporary Firestore records are removed afterward. The generated image is a
synthetic screenshot suitable for emulator testing.

## References

- [Unlimited-OCR serving recipe](https://recipes.vllm.ai/baidu/Unlimited-OCR)
- [Expo 57 image picker](https://docs.expo.dev/versions/v57.0.0/sdk/imagepicker/)
- [Docker GPU support on Windows](https://docs.docker.com/desktop/features/gpu/)
