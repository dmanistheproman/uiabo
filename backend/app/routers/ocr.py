"""Premium OCR preparation; images and drafts are not stored or charged."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.ocr.service import MAX_BODY_BYTES, OcrError, OcrRequest, OcrResult, OcrService, get_ocr_service
from app.routers.analysis import Store, User, unavailable


router = APIRouter(prefix="/analysis", tags=["OCR"])


@router.post("/ocr", response_model=OcrResult)
async def read_image(request: Request, user: User, store: Store,
                     service: Annotated[OcrService, Depends(get_ocr_service)]):
    try:
        await run_in_threadpool(store.require_premium, user.uid)
    except HTTPException:
        raise
    except Exception:
        raise unavailable() from None
    try:
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise OcrError("OCR_INVALID_UPLOAD", "Upload the image using the image selection screen.", 415)
        declared = request.headers.get("content-length")
        if declared and (not declared.isdigit() or int(declared) > MAX_BODY_BYTES):
            raise OcrError("OCR_IMAGE_TOO_LARGE", "Choose an image smaller than 8 MB.", 413)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                raise OcrError("OCR_IMAGE_TOO_LARGE", "Choose an image smaller than 8 MB.", 413)
            body.extend(chunk)
        try:
            upload = OcrRequest.model_validate_json(body)
        except ValidationError:
            # Do not echo image bytes in FastAPI validation errors or logs.
            raise OcrError("OCR_INVALID_UPLOAD", "The image upload could not be read. Please choose the image again.", 422) from None
        return await run_in_threadpool(service.extract, upload.image_base64)
    except OcrError as error:
        raise HTTPException(error.status, detail={"error_code": error.code, "message": error.message}) from None
