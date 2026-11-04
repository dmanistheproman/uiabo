"""Authenticated Check Image Context analysis."""

from starlette.concurrency import run_in_threadpool
from app.analyses.image_execution import run_image_work
from app.analyses.images import MAX_IMAGE_BYTES, decode_image, finish_with_image

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)

from app.auth.dependencies import get_verified_user
from app.auth.models import AuthenticatedUser
from app.analyses.store import get_analysis_store

from app.image_context_analysis.extraction_service import extract_caption
from app.image_context_analysis.analysis_service import analyse_image_context

from app.image_context_analysis.models import ImageContextAnalysisResult, FailedImageContextAnalysisRecord


router = APIRouter(
    prefix="/analysis",
    tags=["Check Image Context"],
)

User = Annotated[
    AuthenticatedUser,
    Depends(get_verified_user),
]

PIPELINE_VERSION = "image-context-v2"


@router.post("/image-context")
async def analyse_image_context_post(
    user: User,
    image: UploadFile = File(...),
    filename: str | None = Form(None),
    caption: str | None = Form(None, max_length=5000),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key", max_length=64, pattern=r"^[a-zA-Z0-9-]+$",
    ),
):
    store = get_analysis_store()
    await run_in_threadpool(store.require_premium, user.uid)

    # Validate the uploaded file type.
    allowed_types = {
        "image/jpeg",
        "image/jpg",
        "image/png",
    }

    if image.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_IMAGE_TYPE",
                "message": "Only JPEG and PNG images are supported.",
            },
        )

    image_data = await image.read(MAX_IMAGE_BYTES + 1)

    if not image_data:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "EMPTY_IMAGE",
                "message": "The uploaded image is empty.",
            },
        )

    # Open the image once and keep it available for both Gemini calls.
    pil_image, stored_content_type = await run_in_threadpool(decode_image, image_data)

    image_filename = (
        filename
        or image.filename
        or "image"
    )

    request_key = (
        idempotency_key.strip()
        if idempotency_key and idempotency_key.strip()
        else str(uuid4())
    )

    reservation = await run_in_threadpool(store.reserve,
        user.uid,
        request_key,
        image_data + b"\0caption:" + (caption or "").strip().encode("utf-8"),
        input_type="image_context",
    )

    # Handle retries using the existing idempotency convention.
    if "existing" in reservation:
        existing = reservation["existing"]

        if existing.get("processing_status") == "failed":
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "PREVIOUS_ANALYSIS_FAILED",
                    "message": (
                        "This image check previously failed. "
                        "Start a new check to retry."
                    ),
                },
            )

        return existing

    try:
        def assess():
            extraction = ({"extracted_caption": caption.strip(), "main_claim": caption.strip()}
                          if caption and caption.strip() else extract_caption(pil_image))
            analysis = analyse_image_context(
                image=pil_image, extracted_caption=extraction["extracted_caption"],
                main_claim=extraction["main_claim"], image_filename=image_filename)
            return extraction, analysis

        extraction, analysis = await run_image_work(assess)
        extracted_caption = extraction["extracted_caption"]

        record = ImageContextAnalysisResult(
            result_id=reservation["result_id"],
            concern_label=analysis["concern_label"],
            explanation=analysis["explanation"],
            evidence_links=analysis["evidence_links"],
            image_filename=analysis.get(
                "image_filename",
                image_filename,
            ),
            extracted_caption=analysis.get(
                "extracted_caption",
                extracted_caption,
            ),
            pipeline_version=PIPELINE_VERSION,
            created_at=datetime.now(timezone.utc),
        )

    except Exception as error:
        failed_record = FailedImageContextAnalysisRecord(
            result_id=reservation["result_id"],
            error_code="IMAGE_CONTEXT_ANALYSIS_FAILED",
            message="The image context could not be analysed.",
            retryable=True,
            pipeline_version=PIPELINE_VERSION,
            created_at=datetime.now(timezone.utc),
        )

        try:
            await run_in_threadpool(store.finish,
                user.uid,
                reservation,
                failed_record,
                charge_allowance=False,
            )
        except Exception:
            try:
                await run_in_threadpool(store.release, user.uid, reservation)
            except Exception:
                pass  # The bounded reservation expires if storage is unavailable.

        if isinstance(error, HTTPException):
            raise error
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "IMAGE_CONTEXT_ANALYSIS_FAILED",
                "message": "The image context could not be analysed.",
            },
        ) from None

    try:
        return await run_in_threadpool(finish_with_image, store, user.uid, reservation, record, image_data, stored_content_type)

    except Exception:
        try:
            await run_in_threadpool(store.release, user.uid, reservation)
        except Exception:
            pass
        raise
