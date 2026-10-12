"""Authenticated AI/deepfake image analysis."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth.dependencies import get_verified_user
from app.auth.models import AuthenticatedUser
from app.deepfakeAI_analysis.service import analyse_deepfakeAI

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from fastapi import Header
from PIL import Image

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
        alias="Idempotency-Key",
    ),
):
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

    image_data = await image.read()
    if not image_data:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "EMPTY_IMAGE",
                "message": "The uploaded image is empty.",
            },
        )

    try:
        with Image.open(BytesIO(image_data)) as opened_image:
            opened_image.load()
            pil_image = opened_image.copy()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_IMAGE",
                "message": "The uploaded file is not a valid image.",
            },
        ) from None

    store = get_analysis_store()
    request_key = (
        idempotency_key.strip()
        if idempotency_key and idempotency_key.strip()
        else str(uuid4())
    )

    reservation = store.reserve(
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
        prediction = analyse_deepfakeAI(pil_image)

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

    except Exception:
        failed_record = FailedDeepfakeAI_AnalysisRecord(
            result_id=reservation["result_id"],
            error_code="IMAGE_ANALYSIS_FAILED",
            message="The image could not be analysed.",
            retryable=True,
            pipeline_version=pipeline_version,
            created_at=datetime.now(timezone.utc),
        )

        try:
            store.finish(user.uid, reservation, failed_record)
        except Exception:
            store.release(user.uid, reservation)

        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "IMAGE_ANALYSIS_FAILED",
                "message": "The image could not be analysed.",
            },
        ) from None

    try:
        return store.finish(user.uid, reservation, record)
    except Exception:
        store.release(user.uid, reservation)
        raise