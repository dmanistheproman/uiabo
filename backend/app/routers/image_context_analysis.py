"""Authenticated Check Image Context analysis."""

from datetime import datetime, timezone
from io import BytesIO
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
from PIL import Image

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

PIPELINE_VERSION = "image-context-v1"


@router.post("/image-context")
async def analyse_image_context_post(
    user: User,
    image: UploadFile = File(...),
    filename: str | None = Form(None),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
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

    image_data = await image.read()

    if not image_data:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "EMPTY_IMAGE",
                "message": "The uploaded image is empty.",
            },
        )

    # Open the image once and keep it available for both Gemini calls.
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

    image_filename = (
        filename
        or image.filename
        or "image"
    )

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

    caption_extraction_succeeded = False
    try:
        # Stage 1: extract the full caption and main factual claim.
        extraction = extract_caption(pil_image)

        extracted_caption = extraction["extracted_caption"]
        main_claim = extraction["main_claim"]

        caption_extraction_succeeded = True

        # Stage 2: search for evidence and analyse the image/caption.
        # The service handles empty claims and unavailable Tavily
        # evidence by returning "Not enough information".
        analysis = analyse_image_context(
            image=pil_image,
            extracted_caption=extracted_caption,
            main_claim=main_claim,
            image_filename=image_filename,
        )

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

    except Exception:
        failed_record = FailedImageContextAnalysisRecord(
            result_id=reservation["result_id"],
            error_code="IMAGE_CONTEXT_ANALYSIS_FAILED",
            message="The image context could not be analysed.",
            retryable=True,
            pipeline_version=PIPELINE_VERSION,
            created_at=datetime.now(timezone.utc),
        )

        try:
            store.finish(
                user.uid,
                reservation,
                failed_record,
                charge_allowance=caption_extraction_succeeded,
            )
        except Exception:
            store.release(user.uid, reservation)

        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "IMAGE_CONTEXT_ANALYSIS_FAILED",
                "message": "The image context could not be analysed.",
            },
        ) from None

    try:
        return store.finish(
            user.uid,
            reservation,
            record,
        )

    except Exception:
        store.release(user.uid, reservation)
        raise