"""Administrator-controlled reuse of a retired staff login as an app account."""
from app.accounts.access import check_admin_change
from app.accounts.roles import stored_account_type, stored_operational_roles
from app.accounts.staff import fail


def conversion_data(actor, target, *, actor_uid, identity, now, deleting=False):
    check_admin_change(actor, target, actor_uid, identity.uid)
    if not target:
        fail("USER_NOT_FOUND", "The requested account could not be found.", 404)
    if deleting or target.get("account_status") != "active":
        fail("ACCOUNT_UNAVAILABLE", "Only active accounts can be converted. Restore access first if appropriate.", 403)
    if stored_account_type(target) != "staff":
        fail("ALREADY_APP_ACCOUNT", "This is already an app account. Refresh its details and ask the user to sign in, rather than register again.")
    if stored_operational_roles(target):
        fail("STAFF_ACCESS_REMAINS", "Remove all Data Engineer and System Admin permissions before converting this account.")
    if not identity.email_verified:
        fail("ACCOUNT_NOT_VERIFIED", "Verify this account's email before converting it.")
    # Keep the Firebase UID, email, name and owned history. Staff administration
    # notes stay in operational_audit, not in the new app-facing profile.
    return {**target, "account_type": "app", "role": "free", "operational_roles": [],
            "email": identity.email, "email_verified": True, "profile": {}, "updated_at": now}


def conversion_audit(reason):
    return {"account_type_from": "staff", "account_type_to": "app",
            "membership": "free", "reason": reason}
