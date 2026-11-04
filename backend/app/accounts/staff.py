"""Permission changes for existing, verified Firebase identities."""
from fastapi import HTTPException
from firebase_admin import auth
from app.accounts.roles import stored_operational_roles, require_account_type
from app.auth.models import AuthenticatedUser
from app.firebase import get_firebase_app


def fail(code, message, status=409):
    raise HTTPException(status, detail={"error_code": code, "message": message})


def verified_staff_identity(*, email=None, uid=None):
    try:
        app = get_firebase_app()
        account = auth.get_user_by_email(email, app=app) if email else auth.get_user(uid, app=app)
    except auth.UserNotFoundError:
        fail("STAFF_ACCOUNT_NOT_FOUND", "Ask this person to register a staff account through the portal and verify their email first.", 404)
    except Exception as error:
        raise HTTPException(503, detail={"error_code": "AUTHENTICATION_SERVICE_UNAVAILABLE",
            "message": "Account verification is temporarily unavailable. Please retry."}) from error
    if account.disabled or not account.email_verified:
        fail("STAFF_ACCOUNT_NOT_READY", "The account must be enabled and its email verified before this change.")
    return AuthenticatedUser(uid=account.uid, email=account.email, email_verified=True), account.display_name


def role_change_data(actor, target, *, actor_uid, identity, roles, reason, now,
                     additive=False, expected_roles=None, name=None, deleting=False):
    from app.accounts.repository import _updated_staff_profile_data
    if not actor or actor.get("account_status") != "active" or "system_admin" not in stored_operational_roles(actor):
        fail("ADMIN_ACCESS_DENIED", "Administrator access is unavailable.", 403)
    require_account_type(target, "staff")
    before = stored_operational_roles(target)
    after = sorted(set(before if additive else []) | set(roles))
    if expected_roles is not None and set(expected_roles) != set(before):
        fail("PERMISSIONS_CHANGED", "Another administrator changed these permissions. Reload the account and review them again.")
    # Every change reads the acting administrator and target in the same
    # transaction. Forbidding self-demotion means a successful change always
    # leaves its acting administrator active, even under concurrent revocations.
    if actor_uid == identity.uid and "system_admin" not in after:
        fail("SELF_ADMIN_REMOVAL", "You cannot remove your own System Admin access. Ask another active administrator to do this.")
    if deleting or (target and target.get("account_status") == "deactivated"):
        fail("ACCOUNT_UNAVAILABLE", "This account is unavailable.", 403)
    if set(after) - set(before) and target and target.get("account_status") == "suspended":
        fail("ACCOUNT_UNAVAILABLE", "Restore this account before granting additional permissions.", 403)
    if after and not identity.email_verified:
        fail("STAFF_ACCOUNT_NOT_READY", "Verify the account's email before granting access.")
    profile = _updated_staff_profile_data(target, identity,
        (target or {}).get("name") or name or identity.email.split("@")[0], now)
    profile["last_login_at"] = (target or {}).get("last_login_at")
    profile["operational_roles"] = after
    profile["profile"] = {**profile.get("profile", {}), "permission_change": {
        "before": before, "after": after, "actor_uid": actor_uid, "reason": reason, "at": now}}
    return profile, before
