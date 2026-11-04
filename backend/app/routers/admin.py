"""System Administrator endpoints."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.accounts.dependencies import get_system_admin
from app.accounts.access import revoke_sessions
from app.accounts.models import (
    AdminStatusUpdateRequest,
    UserProfile,
    PortalRoleUpdateRequest,
    ProvisionAccountRequest,
    StaffToAppRequest,
)
from app.accounts.staff import verified_staff_identity
from app.auth.models import AuthenticatedUser
from app.accounts.audit_history import ACTIONS, AuditPage, audit_window, get_audit_history
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


@router.post("/provision", response_model=UserProfile, summary="Grant staff access by verified email")
def provision_account(body: ProvisionAccountRequest, admin: AdminUser,
                      repository: Repository, http_request: Request):
    try:
        identity, name = verified_staff_identity(email=body.email)
        http_request.state.authenticated_uid = admin.uid
        http_request.state.audit_target_uid = identity.uid
        profile = repository.change_portal_roles(identity, body.operational_roles,
            actor_uid=admin.uid, reason=body.reason, additive=True, name=name,
            audit_id=getattr(http_request.state, "audit_id", None))
        http_request.state.audit_metadata = {key: profile.profile["permission_change"][key] for key in ("before", "after", "reason")}
        return profile
    except HTTPException:
        raise
    except Exception as error:
        raise _admin_service_unavailable() from error


@router.patch("/users/{uid}/roles", response_model=UserProfile, summary="Change staff portal permissions")
def update_portal_roles(uid: str, body: PortalRoleUpdateRequest, admin: AdminUser,
                        repository: Repository, http_request: Request):
    try:
        existing = repository.get_profile(uid)
        if existing is None:
            raise _user_not_found()
        # Revocation must remain possible even if Firebase Auth is disabled.
        if set(body.operational_roles) - set(existing.operational_roles):
            identity, name = verified_staff_identity(uid=uid)
        else:
            identity = AuthenticatedUser(uid=uid, email=existing.email, email_verified=existing.email_verified)
            name = existing.name
        http_request.state.authenticated_uid = admin.uid
        http_request.state.audit_target_uid = uid
        profile = repository.change_portal_roles(identity, body.operational_roles,
            actor_uid=admin.uid, reason=body.reason, expected_roles=body.expected_roles,
            name=name, audit_id=getattr(http_request.state, "audit_id", None))
        if profile is None:
            raise _user_not_found()
        http_request.state.audit_metadata = {key: profile.profile["permission_change"][key] for key in ("before", "after", "reason")}
        return profile
    except HTTPException:
        raise
    except Exception as error:
        raise _admin_service_unavailable() from error


@router.post("/users/{uid}/convert-to-app", response_model=UserProfile,
             summary="Convert a former staff login to a Free app account")
def convert_staff_to_app(uid: str, body: StaffToAppRequest, admin: AdminUser,
                         repository: Repository, http_request: Request):
    from app.accounts.conversion import conversion_audit
    try:
        http_request.state.audit_target_uid = uid
        identity, _ = verified_staff_identity(uid=uid)
        profile = repository.convert_staff_to_app(identity, actor_uid=admin.uid,
            reason=body.reason, audit_id=getattr(http_request.state, "audit_id", None))
        http_request.state.audit_metadata = conversion_audit(body.reason)
        return profile
    except HTTPException:
        raise
    except Exception as error:
        raise _admin_service_unavailable() from error


@router.get("/audit", response_model=AuditPage, summary="Read operational audit history")
def audit_history(admin: AdminUser, history: Annotated[object, Depends(get_audit_history)],
                  from_time: datetime | None = None, to_time: datetime | None = None,
                  action: str | None = None,
                  outcome: Literal["succeeded", "denied", "failed", "started"] | None = None,
                  user_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
                  cursor: Annotated[str | None, Query(max_length=1024)] = None,
                  limit: Annotated[int, Query(ge=1, le=100)] = 50):
    if action and action not in ACTIONS:
        raise HTTPException(422, detail={"error_code": "INVALID_AUDIT_ACTION", "message": "Choose a valid action filter."})
    start, end = audit_window(from_time, to_time)
    try:
        return history.list_events(from_time=start, to_time=end, action=action, outcome=outcome,
                                   user_id=user_id, cursor=cursor, limit=limit)
    except HTTPException:
        raise
    except Exception as error:
        raise _admin_service_unavailable() from error


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
    http_request: Request,
) -> UserProfile:
    http_request.state.authenticated_uid = admin.uid
    http_request.state.audit_metadata = {"account_status": request.account_status, "reason": request.reason.strip()}
    if request.account_status == "suspended" and not request.reason.strip():
        raise HTTPException(422, detail={"error_code": "REASON_REQUIRED", "message": "Provide a reason for suspending this account."})

    try:
        profile = repository.update_account_status(
            uid,
            request.account_status, actor_uid=admin.uid, reason=request.reason.strip(),
        )
        if profile is not None and request.account_status == "suspended":
            revoke_sessions(uid)
    except HTTPException:
        raise
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
