"""Operational permissions are separate from the app tier/legacy primary role."""
from collections.abc import Mapping
from typing import Literal

OperationalRole = Literal["data_engineer", "system_admin"]
OPERATIONAL_ROLES = ("data_engineer", "system_admin")


def stored_account_type(profile: Mapping | None) -> str:
    if not profile:
        return "app"
    if "account_type" in profile:
        return profile["account_type"]
    # Legacy operational accounts remain staff; Free/Premium profiles remain app
    # accounts even if an older release stored portal grants on them.
    return "staff" if profile.get("role") in (*OPERATIONAL_ROLES, "staff") else "app"


def require_account_type(profile: Mapping | None, expected: str):
    from fastapi import HTTPException
    if profile and stored_account_type(profile) != expected:
        code = "STAFF_ACCOUNT_ONLY" if expected == "app" else "APP_ACCOUNT_ONLY"
        message = ("This is a staff portal account. Use a separate UIABO app account."
                   if expected == "app" else
                   "This email belongs to a UIABO app account. Register a separate staff account with a different email in the portal.")
        if expected == "app" and not stored_operational_roles(profile):
            message = "This email is still a staff account. Ask a System Admin to convert it to an app account, then sign in with your existing email and password."
        raise HTTPException(403, detail={"error_code": code, "message": message})


def stored_operational_roles(profile: Mapping | None) -> list[str]:
    if not profile or stored_account_type(profile) != "staff":
        return []
    if "operational_roles" in profile:
        roles = profile["operational_roles"]
        # An explicit empty list revokes access, even on a legacy admin profile.
        return [role for role in OPERATIONAL_ROLES if isinstance(roles, list) and role in roles]
    legacy = profile.get("role")
    return [legacy] if legacy in OPERATIONAL_ROLES else []
