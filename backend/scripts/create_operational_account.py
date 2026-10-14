"""Provision an operational portal account (data engineer or system admin).

Usage (from backend/ with the virtual environment active):

    python -m scripts.create_operational_account --email engineer@example.com --role data_engineer

The Firebase Auth account must already exist (register once in the app or
portal console). The script sets the operational role and active status on the
users/{uid} Firestore profile without touching allowances.
"""

import argparse
from datetime import datetime, timezone

from firebase_admin import auth as firebase_auth

from app.firebase import get_firebase_app, get_firestore_client

ROLES = ("data_engineer", "system_admin")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Registered Firebase Auth email.")
    parser.add_argument("--role", required=True, choices=ROLES)
    parser.add_argument("--name", help="Display name; defaults to the email local part.")
    args = parser.parse_args()

    get_firebase_app()
    db = get_firestore_client()

    try:
        user = firebase_auth.get_user_by_email(args.email)
    except firebase_auth.UserNotFoundError:
        print(
            f"No Firebase Auth account for {args.email}. Register once with that email, "
            "then rerun this script."
        )
        return 1

    now = datetime.now(timezone.utc)
    reference = db.collection("users").document(user.uid)
    snapshot = reference.get()
    profile = snapshot.to_dict() or {}
    profile.update(
        {
            "uid": user.uid,
            "name": args.name or args.email.split("@")[0],
            "email": user.email,
            "email_verified": user.email_verified,
            "role": args.role,
            "account_status": "active",
            "profile": profile.get("profile", {}),
            "storage_used_bytes": profile.get("storage_used_bytes", 0),
            "storage_quota_bytes": profile.get("storage_quota_bytes", 0),
            "last_login_at": profile.get("last_login_at"),
            "created_at": profile.get("created_at", now),
            "updated_at": now,
        }
    )
    reference.set(profile)
    print(f"users/{user.uid} now has role={args.role} account_status=active.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
