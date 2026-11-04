"""Private image attachments for completed deepfake and image-context checks."""

import logging
import os
from hashlib import sha256
from io import BytesIO
from typing import Literal

from fastapi import HTTPException
from firebase_admin import storage
from google.api_core.exceptions import NotFound
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict

from app.firebase import get_firebase_app

logger = logging.getLogger(__name__)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000


class SavedImage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_path: str
    generation: int
    content_type: Literal["image/jpeg", "image/png"]
    size_bytes: int


def storage_unavailable():
    return HTTPException(503, detail={"error_code": "IMAGE_STORAGE_UNAVAILABLE",
        "message": "The image could not be saved. Please retry; check Results first if your connection was interrupted."})


def image_prefix(uid, result_id):
    return f"analysis-images/{sha256(uid.encode()).hexdigest()}/{result_id}/"


def decode_image(data):
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, detail={"error_code": "IMAGE_TOO_LARGE",
            "message": "Choose an image smaller than 10 MB."})
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG"} or source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("Unsupported image")
            content_type = "image/jpeg" if source.format == "JPEG" else "image/png"
            source.load()
            return ImageOps.exif_transpose(source).copy(), content_type
    except Exception:
        raise HTTPException(400, detail={"error_code": "INVALID_IMAGE",
            "message": "Choose a valid JPEG or PNG image of at most 25 megapixels."}) from None


class ImageStorage:
    def __init__(self, bucket):
        self.bucket = bucket

    def upload(self, uid, reservation, data, content_type):
        # A server-issued lease token prevents one retry deleting another attempt's image.
        path = image_prefix(uid, reservation["result_id"]) + reservation["token"]
        blob = self.bucket.blob(path)
        blob.cache_control = "private, no-store"
        blob.upload_from_string(data, content_type=content_type, if_generation_match=0, timeout=30)
        return SavedImage(object_path=path, generation=int(blob.generation),
                          content_type=content_type, size_bytes=len(data))

    def _blob(self, uid, result_id, attachment):
        attachment = SavedImage.model_validate(attachment)
        if not attachment.object_path.startswith(image_prefix(uid, result_id)):
            raise ValueError("Image ownership mismatch")
        return self.bucket.blob(attachment.object_path, generation=attachment.generation)

    def read(self, uid, result_id, attachment):
        blob = self._blob(uid, result_id, attachment)
        return blob.download_as_bytes(timeout=30, if_generation_match=blob.generation)

    def delete(self, uid, result_id, attachment):
        blob = self._blob(uid, result_id, attachment)
        try:
            blob.delete(timeout=30, if_generation_match=blob.generation)
        except NotFound:
            pass


def get_image_storage():
    app = get_firebase_app()
    name = os.environ.get("FIREBASE_STORAGE_BUCKET", "").strip()
    if not name:
        raise storage_unavailable()
    return ImageStorage(storage.bucket(name, app=app))


def finish_with_image(store, uid, reservation, record, data, content_type):
    if os.environ.get("SAVE_ANALYSIS_IMAGES", "0").lower() not in {"1", "true", "yes"}:
        return store.finish(uid, reservation, record)
    attachment = None
    images = None
    try:
        images = get_image_storage()
        attachment = images.upload(uid, reservation, data, content_type)
        record = record.model_copy(update={"saved_image": attachment})
        saved = store.finish(uid, reservation, record)
        if saved.get("saved_image") != attachment.model_dump():
            images.delete(uid, reservation["result_id"], attachment)
        return saved
    except Exception:
        if attachment is not None:
            # A timed-out Firestore commit may already have saved and charged.
            # Confirm its outcome before deleting the object or reporting failure.
            try:
                saved = store.get_owned(uid, reservation["result_id"])
            except HTTPException as exc:
                if exc.status_code == 404:
                    try:
                        images.delete(uid, reservation["result_id"], attachment)
                    except Exception:
                        logger.warning("Image cleanup needs retry for result %s", reservation["result_id"])
            except Exception:
                logger.warning("Image commit outcome unknown for result %s", reservation["result_id"])
            else:
                if saved.get("saved_image") == attachment.model_dump():
                    return saved
        raise storage_unavailable() from None
