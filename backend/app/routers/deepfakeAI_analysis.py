"""Authenticated AI/deepfake image analysis."""

from starlette.concurrency import run_in_threadpool
from app.analyses.image_execution import run_image_work
from app.analyses.images import MAX_IMAGE_BYTES, decode_image, finish_with_image

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth.dependencies import get_verified_user
from app.auth.models import AuthenticatedUser
from app.deepfakeAI_analysis.service import analyse_deepfakeAI

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Header

from app.analyses.store import get_analysis_store
from app.deepfakeAI_analysis.models import DeepfakeAI_AnalysisResult, FailedDeepfakeAI_AnalysisRecord


router = APIRouter(
    prefix="/analysis",
    tags=["Deepfake / AI analysis"],
)


User = Annotated[
    AuthenticatedUser,
    Depends(get_verified_user),
]


@router.post("/deepfakeAI")
async def analyse_deepfakeAI_image(
    user: User,
    image: UploadFile = File(...),
    filename: str | None = Form(None),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key", max_length=64, pattern=r"^[a-zA-Z0-9-]+$",
    ),
):
    store = get_analysis_store()
    await run_in_threadpool(store.require_premium, user.uid)

    if not image.content_type:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_IMAGE",
                "message": "An image file is required.",
            },
        )

    allowed_types = {"image/jpeg", "image/jpg", "image/png"}
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

    pil_image, stored_content_type = await run_in_threadpool(decode_image, image_data)

    request_key = (
        idempotency_key.strip()
        if idempotency_key and idempotency_key.strip()
        else str(uuid4())
    )

    reservation = await run_in_threadpool(store.reserve,
        user.uid,
        request_key,
        image_data,
        input_type="deepfake_ai",
    )

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

    pipeline_version = "deepfake-ai-v1"

    try:
        # Keep the existing detector call unchanged.
        prediction = await run_image_work(lambda: analyse_deepfakeAI(pil_image))

        record = DeepfakeAI_AnalysisResult(
            result_id=reservation["result_id"],
            filename=filename or image.filename,
            label=prediction["label"],
            confidence=prediction["confidence"],
            real_probability=prediction["real_probability"],
            fake_probability=prediction["fake_probability"],
            explanation=prediction.get("explanation"),
            pipeline_version=pipeline_version,
            created_at=datetime.now(timezone.utc),
        )

    except Exception as error:
        failed_record = FailedDeepfakeAI_AnalysisRecord(
            result_id=reservation["result_id"],
            error_code="IMAGE_ANALYSIS_FAILED",
            message="The image could not be analysed.",
            retryable=True,
            pipeline_version=pipeline_version,
            created_at=datetime.now(timezone.utc),
        )

        try:
            await run_in_threadpool(store.finish, user.uid, reservation, failed_record)
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
                "error_code": "IMAGE_ANALYSIS_FAILED",
                "message": "The image could not be analysed.",
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
