"""Role-gated access dependencies for the operational portal."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.accounts.models import UserProfile
from app.accounts.repository import AccountRepository, get_account_repository
from app.auth.dependencies import get_verified_user
from app.auth.models import AuthenticatedUser


OPERATIONAL_ROLES = frozenset({"system_admin", "data_engineer"})


@dataclass(frozen=True)
class OperationalContext:
    """The verified token holder together with their Firestore profile."""

    user: AuthenticatedUser
    profile: UserProfile


def _access_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error_code": "PORTAL_ACCESS_DENIED",
            "message": "This area is only available to authorised operational accounts.",
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


def require_role(*roles: str):
    """Build a dependency that only admits the given active profile roles.

    With no arguments, any operational role is accepted. Access is denied
    without revealing whether the profile exists or which role it holds.
    """
    allowed = frozenset(roles) or OPERATIONAL_ROLES
    unknown = allowed - OPERATIONAL_ROLES
    if unknown:
        raise ValueError(f"Unknown operational roles: {sorted(unknown)}")

    def dependency(
        user: Annotated[AuthenticatedUser, Depends(get_verified_user)],
        repository: Annotated[AccountRepository, Depends(get_account_repository)],
    ) -> OperationalContext:
        try:
            profile = repository.get_profile(user.uid)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error_code": "PORTAL_SERVICE_UNAVAILABLE",
                    "message": "The portal is temporarily unavailable. Please retry.",
                },
            ) from error
        if profile is None or profile.role not in allowed:
            raise _access_denied()
        if profile.account_status != "active":
            raise _account_unavailable()
        return OperationalContext(user=user, profile=profile)

    return dependency
