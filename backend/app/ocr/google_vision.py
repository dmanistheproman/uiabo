"""Google Vision OCR via the official REST API and server-side credentials.

One DOCUMENT_TEXT_DETECTION feature per image; no Cloud Storage upload,
automatic provider fallback, or automatic paid-request retry.
"""

from datetime import datetime, timezone
from functools import partial
import re
from threading import BoundedSemaphore

from google.auth.transport.requests import Request
import httpx

from app.firebase import get_firebase_app
from app.ocr.service import MAX_TEXT_LENGTH, OcrError, OcrResult, prepare_image

VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"


def authenticated_headers():
    """Use the Firebase Admin identity (ADC locally and on Cloud Run)."""
    try:
        app = get_firebase_app()
        credentials = app.credential.get_credential()
        headers = {}
        credentials.before_request(partial(Request(), timeout=10), "POST", VISION_ENDPOINT, headers)
        if app.project_id:
            headers["x-goog-user-project"] = app.project_id
        return headers
    except Exception:
        raise OcrError("OCR_AUTH_UNAVAILABLE",
            "The image reader could not authenticate with Google. Please contact the team.") from None


def vision_text(annotation):
    """Preserve literal OCR text, including text resembling model delimiters."""
    full = annotation.get("fullTextAnnotation")
    if full is not None:
        if not isinstance(full, dict) or not isinstance(full.get("text"), str):
            raise ValueError("Invalid full-text annotation")
        text = full["text"]
    else:
        items = annotation.get("textAnnotations", [])
        if not isinstance(items, list):
            raise ValueError("Invalid text annotations")
        if items:
            if not isinstance(items[0], dict) or not isinstance(items[0].get("description"), str):
                raise ValueError("Invalid text annotation")
            text = items[0]["description"]
        else:
            text = ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
    if not text:
        raise OcrError("OCR_NO_TEXT", "No readable text was found. Choose a clearer image containing a message.", 422)
    if len(text) > MAX_TEXT_LENGTH:
        raise OcrError("OCR_TEXT_TOO_LONG", "There is too much text in this image. Crop it to the message you want to check.", 422)
    return text


def provider_error(code, *, http=False):
    # Embedded error codes use google.rpc.Code rather than HTTP status codes.
    if code in ({429} if http else {8}):
        return OcrError("OCR_QUOTA_EXCEEDED", "The image reader has reached its service limit. Please try again later.", 429)
    if code in ({401, 403} if http else {7, 16}):
        return OcrError("OCR_CONFIGURATION_ERROR",
            "Google Vision is not available for this project. Ask the team to check API access, billing and permissions.")
    if code in ({408, 504} if http else {4}):
        return OcrError("OCR_TIMEOUT", "Reading the image took too long. Try again or use a smaller crop.", 504)
    if code in ({400, 413} if http else {3}):
        return OcrError("OCR_PROVIDER_REJECTED_IMAGE", "Google could not read this image. Try a clearer, smaller crop.", 422)
    return OcrError("OCR_UNAVAILABLE", "The image reader is temporarily unavailable. Please try again shortly.")


class GoogleVisionOcrService:
    def __init__(self, *, transport=None, headers_factory=None):
        self.transport = transport
        self.headers_factory = headers_factory or authenticated_headers
        self.slot = BoundedSemaphore(1)

    def extract(self, encoded):
        if not self.slot.acquire(blocking=False):
            raise OcrError("OCR_BUSY", "The image reader is busy with another image. Please try again shortly.", 429)
        try:
            # Reuse the existing validation, orientation correction and metadata stripping.
            content = prepare_image(encoded).split(",", 1)[1]
            payload = {"requests": [{"image": {"content": content},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]}]}
            headers = self.headers_factory()
            try:
                with httpx.Client(timeout=httpx.Timeout(30, connect=5), transport=self.transport,
                                  follow_redirects=False, trust_env=False) as client:
                    response = client.post(VISION_ENDPOINT, json=payload, headers=headers)
            except httpx.TimeoutException:
                raise provider_error(504, http=True) from None
            except httpx.RequestError:
                raise provider_error(503, http=True) from None
            if response.status_code != 200:
                raise provider_error(response.status_code, http=True)
            try:
                body = response.json()
                responses = body["responses"]
                if not isinstance(responses, list) or len(responses) != 1 or not isinstance(responses[0], dict):
                    raise ValueError("Invalid response count")
                annotation = responses[0]
                if "error" in annotation:
                    error = annotation["error"]
                    if not isinstance(error, dict):
                        raise ValueError("Invalid error")
                    if error.get("code", 0):
                        raise provider_error(error["code"])
                text = vision_text(annotation)
            except (KeyError, TypeError, ValueError):
                raise OcrError("OCR_INVALID_RESPONSE", "The image reader returned an incomplete response. Please retry.") from None
            notes = ["Review names, dates, amounts and missing words against the image before checking the text."]
            if len(text) > 5000:
                notes.append("Keep the relevant message within 5,000 characters before starting a fact-check.")
            return OcrResult(text=text, provider="Google Cloud Vision", extracted_at=datetime.now(timezone.utc), warnings=notes)
        finally:
            self.slot.release()
