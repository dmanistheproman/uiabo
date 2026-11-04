"""Grant one or both portal roles to a separate staff account.

From backend/:
  python -m scripts.create_operational_account --email operator@example.com --roles data_engineer system_admin

The verified Firebase Auth account must already exist. Grants are additive;
existing staff permissions and suspension state are preserved. App accounts
cannot be converted to staff accounts; register a separate email in the portal.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
from firebase_admin import auth as firebase_auth
from google.cloud import firestore

from app.accounts.repository import _updated_staff_profile_data
from app.accounts.roles import OPERATIONAL_ROLES, stored_operational_roles, stored_account_type
from app.auth.models import AuthenticatedUser
from app.firebase import get_firebase_app, get_firestore_client


def grant_portal_access(db, user, roles, name=None, now=None):
    requested = set(roles)
    if not requested or requested - set(OPERATIONAL_ROLES):
        raise ValueError("Choose data_engineer, system_admin, or both.")
    if user.disabled or not user.email_verified:
        raise ValueError("The account must be enabled and its email verified before granting portal access.")
    now = now or datetime.now(timezone.utc)
    reference = db.collection("users").document(user.uid)
    deletion = db.collection("account_deletions").document(user.uid)
    receipt = db.collection("deleted_account_receipts").document(sha256(user.uid.encode()).hexdigest())

    @firestore.transactional
    def grant(tx):
        existing = reference.get(transaction=tx).to_dict()
        if existing and stored_account_type(existing) != "staff":
            raise ValueError("This is a UIABO app account. Register a separate staff account with a different email in the portal.")
        deletion_job = deletion.get(transaction=tx).to_dict()
        deleted = receipt.get(transaction=tx).to_dict()
        if deletion_job or deleted or (existing and existing.get("account_status") in {"suspended", "deactivated"}):
            raise ValueError("This account is unavailable. A role grant cannot restore suspended or deleted accounts.")
        identity = AuthenticatedUser(uid=user.uid, email=user.email, email_verified=user.email_verified)
        profile = _updated_staff_profile_data(existing, identity,
            name or (existing or {}).get("name") or user.display_name or user.email.split("@")[0], now)
        profile["last_login_at"] = (existing or {}).get("last_login_at")
        profile["operational_roles"] = sorted(set(stored_operational_roles(existing)) | requested)
        tx.set(reference, profile, merge=True)
        return profile["operational_roles"]
    return grant(db.transaction())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Registered, verified Firebase Auth email.")
    parser.add_argument("--role", "--roles", dest="roles", required=True,
                        choices=OPERATIONAL_ROLES, nargs="+", action="extend",
                        help="Portal permissions to add. Existing permissions are retained.")
    parser.add_argument("--name", help="Display name; preserves the existing name when omitted.")
    args = parser.parse_args()
    get_firebase_app()
    try:
        user = firebase_auth.get_user_by_email(args.email.strip())
    except firebase_auth.UserNotFoundError:
        print("No Firebase Auth account found. Register and verify that email, then rerun this command.")
        return 1
    try:
        roles = grant_portal_access(get_firestore_client(), user, args.roles, args.name)
    except ValueError as error:
        print(str(error))
        return 1
    print(f"Staff account users/{user.uid} now has portal access: {', '.join(roles)}. No app membership or allowance was created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
