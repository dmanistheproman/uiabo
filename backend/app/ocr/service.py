import base64
import binascii
import io
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import re
from threading import BoundedSemaphore
import warnings

from dotenv import load_dotenv
import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_BASE64_LENGTH = 4 * ((MAX_IMAGE_BYTES + 2) // 3)
MAX_BODY_BYTES = MAX_BASE64_LENGTH + 1024
MAX_PIXELS = 16_000_000
MAX_TEXT_LENGTH = 20000


class OcrError(Exception):
    def __init__(self, code, message, status=503):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class OcrRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_base64: str = Field(min_length=1, max_length=MAX_BASE64_LENGTH)


class OcrResult(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    provider: str = "Unlimited-OCR"
    extracted_at: datetime
    warnings: list[str] = Field(default_factory=list)
    max_check_characters: int = 5000


def prepare_image(encoded):
    """Decode a bounded still image, apply orientation and strip metadata."""
    if len(encoded) > MAX_BASE64_LENGTH:
        raise OcrError("OCR_IMAGE_TOO_LARGE", "Choose an image smaller than 8 MB.", 413)
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise OcrError("OCR_INVALID_IMAGE", "The image could not be read. Choose another screenshot or photo.", 422) from None
    if len(data) > MAX_IMAGE_BYTES:
        raise OcrError("OCR_IMAGE_TOO_LARGE", "Choose an image smaller than 8 MB.", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or getattr(source, "n_frames", 1) != 1:
                    raise OcrError("OCR_UNSUPPORTED_IMAGE", "Choose a still JPEG, PNG or WebP image.", 422)
                if source.width * source.height > MAX_PIXELS or max(source.size) > 12000:
                    raise OcrError("OCR_IMAGE_TOO_LARGE", "This image has too many pixels. Crop it to the message and try again.", 413)
                if min(source.size) < 32:
                    raise OcrError("OCR_IMAGE_TOO_SMALL", "Choose a larger, clearer image of the message.", 422)
                source.load()
                oriented = ImageOps.exif_transpose(source).convert("RGBA")
                background = Image.new("RGBA", oriented.size, "white")
                image = Image.alpha_composite(background, oriented).convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=95)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except OcrError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise OcrError("OCR_INVALID_IMAGE", "The image could not be read. Choose another screenshot or photo.", 422) from None


def clean_ocr_text(raw):
    """Remove documented layout markers, never interpret the extracted text."""
    raw = re.sub(r"<\|(?:endoftext|im_end|end_of_sentence)\|>|<｜end▁of▁sentence｜>", "", raw)
    # Current model emits <|det|>category [coordinates]<|/det|> blocks.
    blocks = re.split(r"<\|det\|>(.*?)<\|/det\|>", raw, flags=re.DOTALL)
    if len(blocks) > 1:
        selected = [blocks[0]]
        for index in range(1, len(blocks), 2):
            category = blocks[index].strip().split(" ", 1)[0].lower()
            if category not in {"image", "figure", "picture"}:
                selected.append(blocks[index + 1])
        raw = "\n\n".join(part.strip() for part in selected if part.strip())
    raw = re.sub(r"<\|ref\|>(.*?)<\|/ref\|>", r"\1", raw, flags=re.DOTALL)
    if "<|" in raw or "|>" in raw:
        raise OcrError("OCR_INVALID_RESPONSE", "The image reader returned incomplete text. Try a clearer crop.")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    if not raw:
        raise OcrError("OCR_NO_TEXT", "No readable text was found. Choose a clearer image containing a message.", 422)
    if len(raw) > MAX_TEXT_LENGTH:
        raise OcrError("OCR_TEXT_TOO_LONG", "There is too much text in this image. Crop it to the message you want to check.", 422)
    return raw


class OcrService:
    def __init__(self, base_url="http://127.0.0.1:8001", *, transport=None):
        self.base_url, self.transport = base_url.rstrip("/"), transport
        self.slot = BoundedSemaphore(1)

    def extract(self, encoded):
        # Avoid queuing multiple large requests on the prototype's single GPU.
        if not self.slot.acquire(blocking=False):
            raise OcrError("OCR_BUSY", "The image reader is busy with another image. Please try again shortly.", 429)
        try:
            image_uri = prepare_image(encoded)
            payload = {"model": "baidu/Unlimited-OCR", "messages": [{"role": "user", "content": [
                {"type": "text", "text": "<image>document parsing."},
                {"type": "image_url", "image_url": {"url": image_uri}},
            ]}], "temperature": 0, "max_tokens": 4096, "skip_special_tokens": False,
                "vllm_xargs": {"ngram_size": 35, "window_size": 128}}
            try:
                with httpx.Client(timeout=httpx.Timeout(120, connect=5), transport=self.transport,
                                  follow_redirects=False, trust_env=False) as client:
                    response = client.post(self.base_url + "/v1/chat/completions", json=payload)
            except httpx.TimeoutException:
                raise OcrError("OCR_TIMEOUT", "Reading the image took too long. Try cropping it to a shorter message.", 504) from None
            except httpx.RequestError:
                raise OcrError("OCR_UNAVAILABLE", "The image reader is unavailable. Please try again when the service is running.") from None
            if response.status_code != 200:
                raise OcrError("OCR_UNAVAILABLE", "The image reader could not complete this request. Please try again.")
            try:
                data = response.json()
                choices = data["choices"]
                if not isinstance(choices, list) or len(choices) != 1:
                    raise ValueError()
                choice = choices[0]
                if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                    raise ValueError()
                if choice.get("finish_reason") == "length":
                    raise OcrError("OCR_TRUNCATED", "The image contains too much text to read completely. Crop it to a shorter message.", 422)
                if choice.get("finish_reason") != "stop":
                    raise ValueError()
                raw = choice["message"]["content"]
                if not isinstance(raw, str) or len(raw) > 100000:
                    raise ValueError()
            except (KeyError, TypeError, ValueError):
                raise OcrError("OCR_INVALID_RESPONSE", "The image reader returned an incomplete response. Please try again.") from None
            text = clean_ocr_text(raw)
            notes = ["Review names, dates, amounts and missing words against the image before checking the text."]
            if len(text) > 5000:
                notes.append("Keep the relevant message within 5,000 characters before starting a fact-check.")
            return OcrResult(text=text, extracted_at=datetime.now(timezone.utc), warnings=notes)
        finally:
            self.slot.release()


@lru_cache
def get_ocr_service():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    return OcrService(os.getenv("OCR_BASE_URL", "http://127.0.0.1:8001"))
