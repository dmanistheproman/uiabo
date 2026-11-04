"""Firestore and in-memory repositories for user profiles and allowances."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Protocol

from app.accounts.models import AccountStatus, UsageAllowance, UserProfile
from app.auth.models import AuthenticatedUser
from app.accounts.roles import require_account_type, stored_account_type
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

    def ensure_staff_profile(self, user: AuthenticatedUser, name: str) -> UserProfile:
        """Register/refresh a staff-only account without app allowance."""

    def search_profiles(
        self,
        query: str | None = None,
        limit: int = 50,
    ) -> list[UserProfile]:
        """Search account profiles."""

    def update_account_status(
        self,
        uid: str,
        account_status: AccountStatus,
        *, actor_uid: str | None = None, reason: str = "",
    ) -> UserProfile | None:
        """Update an account's status."""

    def change_portal_roles(self, identity, roles, *, actor_uid, reason,
                            additive=False, expected_roles=None, name=None, audit_id=None):
        """Provision or edit portal permissions with current administrator checks."""

    def convert_staff_to_app(self, identity, *, actor_uid, reason, audit_id):
        """Convert a staff account with no permissions into a Free app account."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_free_allowance(uid: str, now: datetime) -> dict[str, Any]:
    period_start = now.astimezone(timezone(timedelta(hours=8))).replace(
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
    now: datetime | None = None,
) -> UserProfile:
    role = profile_data.get("role")
    if stored_account_type(profile_data) == "staff":
        allowance_data = None
    if (
        now is not None
        and stored_account_type(profile_data) == "app"
        and role in {"free", "premium"}
        and (
            allowance_data is None
            or allowance_data["reset_at"] <= now
            or allowance_data.get("tier") != role
        )
    ):
        allowance_data = (
            _new_premium_allowance
            if role == "premium"
            else _new_free_allowance
        )(profile_data["uid"], now)

    allowance = None

    if allowance_data is not None:
        allowance = UsageAllowance.model_validate(allowance_data)

    return UserProfile.model_validate(
        {
            **profile_data,
            "allowance": allowance,
        }
    )


def _new_premium_allowance(
    uid: str,
    now: datetime,
) -> dict[str, Any]:
    """Calendar-month allowance for a server-granted premium role."""
    start = now.astimezone(
        timezone(timedelta(hours=8))
    ).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )

    return {
        "user_id": uid,
        "tier": "premium",
        "period_type": "monthly",
        "period_start": start,
        "period_end": end,
        "submission_limit": 60,
        "successful_submissions": 0,
        "remaining_submissions": 60,
        "reset_at": end,
        "updated_at": now,
    }


def _updated_profile_data(
    existing: dict[str, Any] | None,
    user: AuthenticatedUser,
    name: str,
    now: datetime,
) -> dict[str, Any]:
    if existing is None:
        role = "free"
        status = (
            "active"
            if user.email_verified
            else "pending_verification"
        )
        created_at = now
        profile = {}
        storage_used_bytes = 0
        storage_quota_bytes = 0
    else:
        role = existing.get("role", "free")
        status = existing.get(
            "account_status",
            "pending_verification",
        )

        if (
            status == "pending_verification"
            and user.email_verified
        ):
            status = "active"

        created_at = existing.get("created_at", now)
        profile = existing.get("profile", {})
        storage_used_bytes = existing.get(
            "storage_used_bytes",
            0,
        )
        storage_quota_bytes = existing.get(
            "storage_quota_bytes",
            0,
        )

    return {
        "uid": user.uid,
        "account_type": "app",
        **({"operational_roles": existing["operational_roles"]}
           if existing is not None and "operational_roles" in existing else {}),
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
            else (
                existing.get("last_login_at")
                if existing is not None
                else None
            )
        ),
        "created_at": created_at,
        "updated_at": now,
    }


def _updated_staff_profile_data(existing, user, name, now):
    require_account_type(existing, "staff")
    profile = _updated_profile_data(existing, user, name, now)
    profile.update(account_type="staff", role="staff")
    from app.accounts.roles import stored_operational_roles
    profile["operational_roles"] = stored_operational_roles(existing)
    return profile


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

    def get_profile(
        self,
        uid: str,
    ) -> UserProfile | None:
        profile_snapshot = (
            self._client
            .collection(USERS_COLLECTION)
            .document(uid)
            .get()
        )

        if not profile_snapshot.exists:
            return None

        allowance_snapshot = (
            self._client
            .collection(ALLOWANCES_COLLECTION)
            .document(uid)
            .get()
        )

        allowance_data = (
            allowance_snapshot.to_dict()
            if allowance_snapshot.exists
            else None
        )

        return _profile_view(
            profile_snapshot.to_dict(),
            allowance_data,
            self._clock(),
        )

    def ensure_free_profile(self, user, name):
        return self._ensure_profile(user, name, "app")

    def ensure_staff_profile(self, user, name):
        return self._ensure_profile(user, name, "staff")

    def _ensure_profile(self, user, name, account_type):
        from google.cloud import firestore
        from fastapi import HTTPException
        now = self._clock()
        user_reference = self._client.collection(USERS_COLLECTION).document(user.uid)
        allowance_reference = self._client.collection(ALLOWANCES_COLLECTION).document(user.uid)
        job_reference = self._client.collection("account_deletions").document(user.uid)
        from hashlib import sha256
        receipt_reference = self._client.collection("deleted_account_receipts").document(sha256(user.uid.encode()).hexdigest())

        @firestore.transactional
        def ensure(tx):
            existing = user_reference.get(transaction=tx).to_dict()
            allowance = allowance_reference.get(transaction=tx).to_dict()
            deletion = job_reference.get(transaction=tx).to_dict()
            receipt = receipt_reference.get(transaction=tx).to_dict()
            if deletion or receipt or (existing and existing.get("account_status") in {"deactivated", "suspended"}):
                raise HTTPException(403, detail={"error_code": "ACCOUNT_UNAVAILABLE", "message": "This account is currently unavailable."})
            require_account_type(existing, account_type)
            make_profile = _updated_staff_profile_data if account_type == "staff" else _updated_profile_data
            profile_data = make_profile(existing, user, name, now)
            if account_type == "app" and allowance is None and profile_data["role"] == "free":
                allowance = _new_free_allowance(user.uid, now)
                tx.set(allowance_reference, allowance)
            tx.set(user_reference, profile_data, merge=True)
            return _profile_view(profile_data, allowance, now)
        return ensure(self._client.transaction())

    def search_profiles(
        self,
        query: str | None = None,
        limit: int = 50,
    ) -> list[UserProfile]:
        normalised_query = (
            query or ""
        ).strip().lower()

        results: list[UserProfile] = []

        for snapshot in (
            self._client
            .collection(USERS_COLLECTION)
            .stream()
        ):
            profile_data = snapshot.to_dict()

            if not profile_data:
                continue

            if normalised_query:
                searchable_values = [
                    str(
                        profile_data.get(
                            "uid",
                            "",
                        )
                    ),
                    str(
                        profile_data.get(
                            "name",
                            "",
                        )
                    ),
                    str(
                        profile_data.get(
                            "email",
                            "",
                        )
                    ),
                ]

                if not any(
                    normalised_query
                    in value.lower()
                    for value in searchable_values
                ):
                    continue

            uid = profile_data.get("uid")

            allowance_data = None

            if isinstance(uid, str) and uid:
                allowance_snapshot = (
                    self._client
                    .collection(
                        ALLOWANCES_COLLECTION
                    )
                    .document(uid)
                    .get()
                )

                if allowance_snapshot.exists:
                    allowance_data = (
                        allowance_snapshot.to_dict()
                    )

            results.append(
                _profile_view(
                    profile_data,
                    allowance_data,
                    self._clock(),
                )
            )

            if len(results) >= limit:
                break

        return results

    def update_account_status(
        self,
        uid: str,
        account_status: AccountStatus,
        *, actor_uid: str | None = None, reason: str = "",
    ) -> UserProfile | None:
        from google.cloud import firestore
        from app.accounts.access import check_admin_change
        target_ref = self._client.collection(USERS_COLLECTION).document(uid)

        @firestore.transactional
        def change(tx):
            actor = self._client.collection(USERS_COLLECTION).document(actor_uid).get(transaction=tx).to_dict() if actor_uid else None
            target = target_ref.get(transaction=tx).to_dict()
            if actor_uid:
                check_admin_change(actor, target, actor_uid, uid)
            if not target:
                return False
            details = dict(target.get("profile", {}))
            details["access_change"] = {"reason": reason, "actor_uid": actor_uid,
                                        "status": account_status, "at": self._clock()}
            tx.update(target_ref, {"account_status": account_status, "updated_at": self._clock(), "profile": details})
            return True
        return self.get_profile(uid) if change(self._client.transaction()) else None

    def change_portal_roles(self, identity, roles, *, actor_uid, reason,
                            additive=False, expected_roles=None, name=None, audit_id=None):
        from google.cloud import firestore
        from hashlib import sha256
        from app.accounts.staff import role_change_data
        from app.accounts.roles import stored_operational_roles
        target_ref = self._client.collection(USERS_COLLECTION).document(identity.uid)
        actor_ref = self._client.collection(USERS_COLLECTION).document(actor_uid)
        now = self._clock()

        @firestore.transactional
        def change(tx):
            actor = actor_ref.get(transaction=tx).to_dict()
            target = target_ref.get(transaction=tx).to_dict()
            allowance = self._client.collection(ALLOWANCES_COLLECTION).document(identity.uid).get(transaction=tx).to_dict()
            job = self._client.collection("account_deletions").document(identity.uid).get(transaction=tx).to_dict()
            receipt = self._client.collection("deleted_account_receipts").document(sha256(identity.uid.encode()).hexdigest()).get(transaction=tx).to_dict()
            if not target and not additive:
                return None
            profile, before = role_change_data(actor, target, actor_uid=actor_uid, identity=identity,
                roles=roles, reason=reason, now=now, additive=additive,
                expected_roles=expected_roles, name=name, deleting=bool(job or receipt))
            # Validate the response before any write is queued.
            result = _profile_view(profile, allowance, now)
            tx.set(target_ref, profile, merge=True)
            if audit_id:
                tx.set(self._client.collection("operational_audit").document(audit_id), {
                    "change_applied": True, "committed_at": now,
                    "actor_mask": sha256(actor_uid.encode()).hexdigest()[:16],
                    "target_mask": sha256(identity.uid.encode()).hexdigest()[:16],
                    "actor_role": "system_admin", "action_details": {
                        "before": before, "after": stored_operational_roles(profile), "reason": reason}}, merge=True)
            return result
        return change(self._client.transaction())


    def convert_staff_to_app(self, identity, *, actor_uid, reason, audit_id):
        from google.cloud import firestore
        from hashlib import sha256
        from app.accounts.conversion import conversion_data, conversion_audit
        from app.accounts.staff import fail
        if not audit_id:
            fail("AUDIT_UNAVAILABLE", "The account change could not be recorded. Please retry.", 503)
        now = self._clock()
        target_ref = self._client.collection(USERS_COLLECTION).document(identity.uid)
        allowance_ref = self._client.collection(ALLOWANCES_COLLECTION).document(identity.uid)

        @firestore.transactional
        def convert(tx):
            actor = self._client.collection(USERS_COLLECTION).document(actor_uid).get(transaction=tx).to_dict()
            target = target_ref.get(transaction=tx).to_dict()
            job = self._client.collection("account_deletions").document(identity.uid).get(transaction=tx).to_dict()
            receipt = self._client.collection("deleted_account_receipts").document(sha256(identity.uid.encode()).hexdigest()).get(transaction=tx).to_dict()
            lock = self._client.collection("analysis_locks").document(identity.uid).get(transaction=tx).to_dict()
            profile = conversion_data(actor, target, actor_uid=actor_uid, identity=identity,
                                      now=now, deleting=bool(job or receipt))
            if lock and lock.get("expires_at", now) > now:
                fail("ANALYSIS_IN_PROGRESS", "Wait for the current check to finish before converting this account.")
            allowance = _new_free_allowance(identity.uid, now)
            result = _profile_view(profile, allowance, now)
            tx.set(target_ref, profile)
            tx.set(allowance_ref, allowance)
            tx.set(self._client.collection("operational_audit").document(audit_id), {
                "change_applied": True, "committed_at": now,
                "actor_mask": sha256(actor_uid.encode()).hexdigest()[:16],
                "target_mask": sha256(identity.uid.encode()).hexdigest()[:16],
                "actor_role": "system_admin", "action_details": conversion_audit(reason)}, merge=True)
            return result
        return convert(self._client.transaction())


class InMemoryAccountRepository:
    """Small deterministic repository used by API tests."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._clock = clock
        self.profiles: dict[
            str,
            dict[str, Any],
        ] = {}
        self.allowances: dict[
            str,
            dict[str, Any],
        ] = {}

    def get_profile(
        self,
        uid: str,
    ) -> UserProfile | None:
        profile = self.profiles.get(uid)

        if profile is None:
            return None

        return _profile_view(
            profile,
            self.allowances.get(uid),
            self._clock(),
        )

    def ensure_free_profile(self, user, name):
        return self._ensure_profile(user, name, "app")

    def ensure_staff_profile(self, user, name):
        return self._ensure_profile(user, name, "staff")

    def _ensure_profile(self, user, name, account_type):
        now = self._clock()

        require_account_type(self.profiles.get(user.uid), account_type)
        make_profile = _updated_staff_profile_data if account_type == "staff" else _updated_profile_data
        profile = make_profile(
            self.profiles.get(user.uid),
            user,
            name,
            now,
        )

        self.profiles[user.uid] = profile

        if (
            account_type == "app"
            and user.uid not in self.allowances
            and profile["role"] == "free"
        ):
            self.allowances[user.uid] = (
                _new_free_allowance(
                    user.uid,
                    now,
                )
            )

        return _profile_view(
            profile,
            self.allowances.get(user.uid),
            now,
        )

    def search_profiles(
        self,
        query: str | None = None,
        limit: int = 50,
    ) -> list[UserProfile]:
        normalised_query = (
            query or ""
        ).strip().lower()

        results: list[UserProfile] = []

        for uid, profile in self.profiles.items():
            if normalised_query:
                searchable_values = [
                    uid,
                    str(
                        profile.get(
                            "name",
                            "",
                        )
                    ),
                    str(
                        profile.get(
                            "email",
                            "",
                        )
                    ),
                ]

                if not any(
                    normalised_query
                    in value.lower()
                    for value in searchable_values
                ):
                    continue

            results.append(
                _profile_view(
                    profile,
                    self.allowances.get(uid),
                    self._clock(),
                )
            )

            if len(results) >= limit:
                break

        return results

    def update_account_status(
        self,
        uid: str,
        account_status: AccountStatus,
        *, actor_uid: str | None = None, reason: str = "",
    ) -> UserProfile | None:
        if actor_uid:
            from app.accounts.access import check_admin_change
            check_admin_change(self.profiles.get(actor_uid), self.profiles.get(uid), actor_uid, uid)
        profile = self.profiles.get(uid)

        if profile is None:
            return None

        profile["account_status"] = (
            account_status
        )

        profile.setdefault("profile", {})["access_change"] = {
            "reason": reason, "actor_uid": actor_uid,
            "status": account_status, "at": self._clock(),
        }

        profile["updated_at"] = (
            self._clock()
        )

        return _profile_view(
            profile,
            self.allowances.get(uid),
            self._clock(),
        )

    def change_portal_roles(self, identity, roles, *, actor_uid, reason,
                            additive=False, expected_roles=None, name=None, audit_id=None):
        from app.accounts.staff import role_change_data
        target = self.profiles.get(identity.uid)
        if not target and not additive:
            return None
        profile, _ = role_change_data(self.profiles.get(actor_uid), target,
            actor_uid=actor_uid, identity=identity, roles=roles, reason=reason,
            now=self._clock(), additive=additive, expected_roles=expected_roles, name=name)
        result = _profile_view(profile, self.allowances.get(identity.uid), self._clock())
        self.profiles[identity.uid] = profile
        return result


    def convert_staff_to_app(self, identity, *, actor_uid, reason, audit_id):
        from app.accounts.conversion import conversion_data
        from app.accounts.staff import fail
        if not audit_id:
            fail("AUDIT_UNAVAILABLE", "The account change could not be recorded. Please retry.", 503)
        now = self._clock()
        profile = conversion_data(self.profiles.get(actor_uid), self.profiles.get(identity.uid),
                                  actor_uid=actor_uid, identity=identity, now=now)
        allowance = _new_free_allowance(identity.uid, now)
        result = _profile_view(profile, allowance, now)
        self.profiles[identity.uid] = profile
        self.allowances[identity.uid] = allowance
        return result


@lru_cache
def get_account_repository() -> AccountRepository:
    return FirestoreAccountRepository()
