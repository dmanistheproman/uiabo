"""Account-level authorization dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.accounts.models import UserProfile
from app.accounts.repository import (
    AccountRepository,
    get_account_repository,
)
from app.auth.dependencies import get_verified_user
from app.auth.models import AuthenticatedUser


def _admin_access_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error_code": "ADMIN_ACCESS_REQUIRED",
            "message": "System administrator access is required.",
        },
    )


def _account_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error_code": "ACCOUNT_UNAVAILABLE",
            "message": "This account is currently unavailable.",
        },
    )


def get_system_admin(
    user: Annotated[
        AuthenticatedUser,
        Depends(get_verified_user),
    ],
    repository: Annotated[
        AccountRepository,
        Depends(get_account_repository),
    ],
) -> UserProfile:
    """Require an active System Administrator account."""

    try:
        profile = repository.get_profile(user.uid)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "ACCOUNT_SERVICE_UNAVAILABLE",
                "message": "Account information is temporarily unavailable.",
            },
        ) from error

    if profile is None:
        raise _admin_access_required()

    if profile.account_status != "active":
        raise _account_unavailable()

    if profile.role != "system_admin":
        raise _admin_access_required()

    return profile
