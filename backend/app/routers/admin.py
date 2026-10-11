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
