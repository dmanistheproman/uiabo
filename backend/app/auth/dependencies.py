"""FastAPI dependencies that verify Firebase Authentication ID tokens."""

from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth

from app.auth.models import AuthenticatedUser
from app.firebase import get_firebase_app


bearer_scheme = HTTPBearer(auto_error=False)


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error_code": "AUTHENTICATION_REQUIRED",
            "message": "Please log in again to continue.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authentication_service_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "AUTHENTICATION_SERVICE_UNAVAILABLE",
            "message": "Authentication is temporarily unavailable. Please retry.",
        },
    )


def verify_firebase_id_token(token: str) -> dict[str, Any]:
    """Verify a client ID token and return its trusted Firebase claims."""
    try:
        get_firebase_app()
        return firebase_auth.verify_id_token(token, check_revoked=True)
    except (
        ValueError,
        firebase_auth.ExpiredIdTokenError,
        firebase_auth.InvalidIdTokenError,
        firebase_auth.RevokedIdTokenError,
        firebase_auth.UserDisabledError,
    ) as error:
        raise _authentication_error() from error
    except Exception as error:
        raise _authentication_service_error() from error


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> AuthenticatedUser:
    """Return the user represented by the request's Bearer token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error()

    claims = verify_firebase_id_token(credentials.credentials)
    uid = claims.get("uid") or claims.get("sub")
    email = claims.get("email")
    if not isinstance(uid, str) or not uid:
        raise _authentication_error()
    if not isinstance(email, str) or not email:
        raise _authentication_error()

    return AuthenticatedUser(
        uid=uid,
        email=email,
        email_verified=bool(claims.get("email_verified", False)),
    )


def get_verified_user(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Require the Firebase account's email address to be verified."""
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "EMAIL_VERIFICATION_REQUIRED",
                "message": "Verify your email address before continuing.",
            },
        )
    return user
