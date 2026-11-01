"""Protected account endpoints for the Android application."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.accounts.models import ProfileUpdateRequest, UserProfile
from app.accounts.repository import (
    AccountRepository,
    get_account_repository,
)
from app.auth.dependencies import get_current_user, get_verified_user
from app.auth.models import AuthenticatedUser
from app.feedback.models import (
    FeedbackRecord,
    FeedbackSubmissionRequest,
)
from app.feedback.repository import (
    FeedbackRepository,
    get_feedback_repository,
)


router = APIRouter(prefix="/account", tags=["Account"])


def _account_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error_code": "ACCOUNT_UNAVAILABLE",
            "message": "This account is currently unavailable.",
        },
    )


def _check_account_status(profile: UserProfile) -> None:
    if profile.account_status in {"suspended", "deactivated"}:
        raise _account_unavailable()


@router.put(
    "/me",
    response_model=UserProfile,
    summary="Create or refresh the current user's profile",
)
def ensure_my_profile(
    request: ProfileUpdateRequest,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    repository: Annotated[
        AccountRepository,
        Depends(get_account_repository),
    ],
) -> UserProfile:
    """Create a free profile after sign-up or refresh it after login."""
    try:
        existing = repository.get_profile(user.uid)
        if existing is not None:
            _check_account_status(existing)
        profile = repository.ensure_free_profile(user, request.name)
        _check_account_status(profile)
        return profile
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "ACCOUNT_SERVICE_UNAVAILABLE",
                "message": "Your profile is temporarily unavailable. Please retry.",
            },
        ) from error


@router.get(
    "/me",
    response_model=UserProfile,
    summary="View the current user's profile",
)
def get_my_profile(
    user: Annotated[AuthenticatedUser, Depends(get_verified_user)],
    repository: Annotated[
        AccountRepository,
        Depends(get_account_repository),
    ],
) -> UserProfile:
    """Return only the profile belonging to the verified token UID."""
    try:
        profile = repository.get_profile(user.uid)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "ACCOUNT_SERVICE_UNAVAILABLE",
                "message": "Your profile is temporarily unavailable. Please retry.",
            },
        ) from error

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PROFILE_NOT_FOUND",
                "message": "Finish setting up your profile to continue.",
            },
        )
    _check_account_status(profile)
    return profile


def _empty_feedback() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "error_code": "FEEDBACK_EMPTY",
            "message": "Add a rating or a comment before sending feedback.",
        },
    )


@router.post(
    "/feedback",
    response_model=FeedbackRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback for administrator review",
)
def submit_feedback(
    request: FeedbackSubmissionRequest,
    user: Annotated[AuthenticatedUser, Depends(get_verified_user)],
    accounts: Annotated[
        AccountRepository,
        Depends(get_account_repository),
    ],
    feedback: Annotated[
        FeedbackRepository,
        Depends(get_feedback_repository),
    ],
) -> FeedbackRecord:
    """Store feedback from a verified, active account."""
    if request.rating is None and not (request.comments or "").strip():
        raise _empty_feedback()

    try:
        profile = accounts.get_profile(user.uid)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "ACCOUNT_SERVICE_UNAVAILABLE",
                "message": "Your profile is temporarily unavailable. Please retry.",
            },
        ) from error

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PROFILE_NOT_FOUND",
                "message": "Finish setting up your profile to continue.",
            },
        )
    _check_account_status(profile)

    comments = (request.comments or "").strip() or None
    record = FeedbackRecord(
        feedback_id=f"fb_{uuid4().hex[:16]}",
        user_id=user.uid,
        category=request.category,
        rating=request.rating,
        comments=comments,
        status="submitted",
        created_at=datetime.now(timezone.utc),
    )

    try:
        feedback.save_feedback(record)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "FEEDBACK_SERVICE_UNAVAILABLE",
                "message": (
                    "Feedback services are temporarily unavailable."
                ),
            },
        ) from error

    return record
