"""Firestore and in-memory repositories for user profiles and allowances."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Protocol

from app.accounts.models import UsageAllowance, UserProfile
from app.auth.models import AuthenticatedUser
from app.firebase import get_firestore_client


USERS_COLLECTION = "users"
ALLOWANCES_COLLECTION = "usage_allowances"


class AccountRepository(Protocol):
    def get_profile(self, uid: str) -> UserProfile | None:
        """Return one user's profile, or None when it does not exist."""

    def ensure_free_profile(
        self,
        user: AuthenticatedUser,
        name: str,
    ) -> UserProfile:
        """Create or refresh the authenticated user's own profile."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_free_allowance(uid: str, now: datetime) -> dict[str, Any]:
    period_start = now.astimezone(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    period_end = period_start + timedelta(days=1)
    return {
        "user_id": uid,
        "tier": "free",
        "period_type": "daily",
        "period_start": period_start,
        "period_end": period_end,
        "submission_limit": 1,
        "successful_submissions": 0,
        "remaining_submissions": 1,
        "reset_at": period_end,
        "updated_at": now,
    }


def _profile_view(
    profile_data: dict[str, Any],
    allowance_data: dict[str, Any] | None,
) -> UserProfile:
    allowance = None
    if allowance_data is not None:
        allowance = UsageAllowance.model_validate(allowance_data)
    return UserProfile.model_validate(
        {
            **profile_data,
            "allowance": allowance,
        }
    )


def _updated_profile_data(
    existing: dict[str, Any] | None,
    user: AuthenticatedUser,
    name: str,
    now: datetime,
) -> dict[str, Any]:
    if existing is None:
        role = "free"
        status = "active" if user.email_verified else "pending_verification"
        created_at = now
        profile = {}
        storage_used_bytes = 0
        storage_quota_bytes = 0
    else:
        role = existing.get("role", "free")
        status = existing.get("account_status", "pending_verification")
        if status == "pending_verification" and user.email_verified:
            status = "active"
        created_at = existing.get("created_at", now)
        profile = existing.get("profile", {})
        storage_used_bytes = existing.get("storage_used_bytes", 0)
        storage_quota_bytes = existing.get("storage_quota_bytes", 0)

    return {
        "uid": user.uid,
        "name": name,
        "email": user.email,
        "email_verified": user.email_verified,
        "role": role,
        "account_status": status,
        "profile": profile,
        "storage_used_bytes": storage_used_bytes,
        "storage_quota_bytes": storage_quota_bytes,
        "last_login_at": (
            now
            if user.email_verified
            else existing.get("last_login_at") if existing is not None else None
        ),
        "created_at": created_at,
        "updated_at": now,
    }


class FirestoreAccountRepository:
    """Store account data under the authenticated Firebase UID."""

    def __init__(
        self,
        client=None,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client or get_firestore_client()
        self._clock = clock

    def get_profile(self, uid: str) -> UserProfile | None:
        profile_snapshot = (
            self._client.collection(USERS_COLLECTION).document(uid).get()
        )
        if not profile_snapshot.exists:
            return None
        allowance_snapshot = (
            self._client.collection(ALLOWANCES_COLLECTION).document(uid).get()
        )
        allowance_data = (
            allowance_snapshot.to_dict() if allowance_snapshot.exists else None
        )
        return _profile_view(profile_snapshot.to_dict(), allowance_data)

    def ensure_free_profile(
        self,
        user: AuthenticatedUser,
        name: str,
    ) -> UserProfile:
        now = self._clock()
        user_reference = self._client.collection(USERS_COLLECTION).document(
            user.uid
        )
        allowance_reference = self._client.collection(
            ALLOWANCES_COLLECTION
        ).document(user.uid)
        existing_snapshot = user_reference.get()
        existing = (
            existing_snapshot.to_dict() if existing_snapshot.exists else None
        )
        allowance_snapshot = allowance_reference.get()
        allowance = (
            allowance_snapshot.to_dict() if allowance_snapshot.exists else None
        )

        profile_data = _updated_profile_data(existing, user, name, now)
        if allowance is None and profile_data["role"] == "free":
            allowance = _new_free_allowance(user.uid, now)

        batch = self._client.batch()
        batch.set(user_reference, profile_data, merge=True)
        if not allowance_snapshot.exists and allowance is not None:
            batch.set(allowance_reference, allowance)
        batch.commit()
        return _profile_view(profile_data, allowance)


class InMemoryAccountRepository:
    """Small deterministic repository used by API tests."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._clock = clock
        self.profiles: dict[str, dict[str, Any]] = {}
        self.allowances: dict[str, dict[str, Any]] = {}

    def get_profile(self, uid: str) -> UserProfile | None:
        profile = self.profiles.get(uid)
        if profile is None:
            return None
        return _profile_view(profile, self.allowances.get(uid))

    def ensure_free_profile(
        self,
        user: AuthenticatedUser,
        name: str,
    ) -> UserProfile:
        now = self._clock()
        profile = _updated_profile_data(
            self.profiles.get(user.uid),
            user,
            name,
            now,
        )
        self.profiles[user.uid] = profile
        if user.uid not in self.allowances and profile["role"] == "free":
            self.allowances[user.uid] = _new_free_allowance(user.uid, now)
        return _profile_view(profile, self.allowances.get(user.uid))


@lru_cache
def get_account_repository() -> AccountRepository:
    return FirestoreAccountRepository()
