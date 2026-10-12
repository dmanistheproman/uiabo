"""System Administrator endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.accounts.dependencies import get_system_admin
from app.accounts.models import (
    AdminStatusUpdateRequest,
    UserProfile,
)
from app.accounts.repository import (
    AccountRepository,
    get_account_repository,
)
from app.feedback.models import (
    FeedbackCategory,
    FeedbackRecord,
    FeedbackReviewRequest,
    FeedbackStatus,
)
from app.feedback.repository import (
    FeedbackRepository,
    get_feedback_repository,
)


router = APIRouter(
    prefix="/admin",
    tags=["System Admin"],
)


AdminUser = Annotated[
    UserProfile,
    Depends(get_system_admin),
]


Repository = Annotated[
    AccountRepository,
    Depends(get_account_repository),
]


FeedbackStore = Annotated[
    FeedbackRepository,
    Depends(get_feedback_repository),
]


def _user_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "USER_NOT_FOUND",
            "message": "The requested user could not be found.",
        },
    )


def _admin_service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "ADMIN_SERVICE_UNAVAILABLE",
            "message": (
                "Administrator services are temporarily unavailable."
            ),
        },
    )


def _feedback_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "FEEDBACK_NOT_FOUND",
            "message": "The requested feedback could not be found.",
        },
    )


def _feedback_service_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "FEEDBACK_SERVICE_UNAVAILABLE",
            "message": (
                "Feedback services are temporarily unavailable."
            ),
        },
    )


# =========================================================
# Account Management
# =========================================================


@router.get(
    "/users",
    response_model=list[UserProfile],
    summary="Search user accounts",
)
def search_users(
    admin: AdminUser,
    repository: Repository,
    query: Annotated[
        str | None,
        Query(max_length=100),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,
) -> list[UserProfile]:
    del admin

    try:
        return repository.search_profiles(
            query=query,
            limit=limit,
        )
    except Exception as error:
        raise _admin_service_unavailable() from error


@router.get(
    "/users/{uid}",
    response_model=UserProfile,
    summary="View a user account",
)
def get_user(
    uid: str,
    admin: AdminUser,
    repository: Repository,
) -> UserProfile:
    del admin

    try:
        profile = repository.get_profile(uid)
    except Exception as error:
        raise _admin_service_unavailable() from error

    if profile is None:
        raise _user_not_found()

    return profile


@router.patch(
    "/users/{uid}/status",
    response_model=UserProfile,
    summary="Suspend or restore a user account",
)
def update_user_status(
    uid: str,
    request: AdminStatusUpdateRequest,
    admin: AdminUser,
    repository: Repository,
) -> UserProfile:
    del admin

    try:
        profile = repository.update_account_status(
            uid,
            request.account_status,
        )
    except Exception as error:
        raise _admin_service_unavailable() from error

    if profile is None:
        raise _user_not_found()

    return profile


# =========================================================
# Feedback Management
# =========================================================


@router.get(
    "/feedback",
    response_model=list[FeedbackRecord],
    summary="View user feedback",
)
def list_feedback(
    admin: AdminUser,
    feedback_repository: FeedbackStore,
    feedback_status: Annotated[
        FeedbackStatus | None,
        Query(alias="status"),
    ] = None,
    category: Annotated[
        FeedbackCategory | None,
        Query(),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,
) -> list[FeedbackRecord]:
    del admin

    try:
        return feedback_repository.list_feedback(
            status=feedback_status,
            category=category,
            limit=limit,
        )
    except Exception as error:
        raise _feedback_service_unavailable() from error


@router.get(
    "/feedback/{feedback_id}",
    response_model=FeedbackRecord,
    summary="View one feedback record",
)
def get_feedback(
    feedback_id: str,
    admin: AdminUser,
    feedback_repository: FeedbackStore,
) -> FeedbackRecord:
    del admin

    try:
        feedback = feedback_repository.get_feedback(
            feedback_id
        )
    except Exception as error:
        raise _feedback_service_unavailable() from error

    if feedback is None:
        raise _feedback_not_found()

    return feedback


@router.patch(
    "/feedback/{feedback_id}/review",
    response_model=FeedbackRecord,
    summary="Mark feedback as reviewed",
)
def review_feedback(
    feedback_id: str,
    request: FeedbackReviewRequest,
    admin: AdminUser,
    feedback_repository: FeedbackStore,
) -> FeedbackRecord:
    # FeedbackReviewRequest currently only permits
    # status="reviewed".
    del request

    try:
        feedback = feedback_repository.mark_reviewed(
            feedback_id,
            admin.uid,
        )
    except Exception as error:
        raise _feedback_service_unavailable() from error

    if feedback is None:
        raise _feedback_not_found()

    return feedback
