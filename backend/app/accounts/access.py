"""Account suspension policy shared by persistent and in-memory repositories."""
from fastapi import HTTPException
from firebase_admin import auth
from app.firebase import get_firebase_app
from app.accounts.roles import stored_operational_roles


def check_admin_change(actor, target, actor_uid, target_uid):
    # Reading actor and target in the same transaction also protects against two
    # administrators suspending one another concurrently, leaving no active admin.
    if not actor or "system_admin" not in stored_operational_roles(actor) or actor.get("account_status") != "active":
        raise HTTPException(403, detail={"error_code": "ADMIN_ACCESS_DENIED", "message": "Administrator access is unavailable."})
    if actor_uid == target_uid:
        raise HTTPException(409, detail={"error_code": "SELF_STATUS_CHANGE", "message": "You cannot change your own account access."})


def revoke_sessions(uid):
    auth.revoke_refresh_tokens(uid, app=get_firebase_app())
