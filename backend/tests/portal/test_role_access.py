"""Role-gated access for the operational portal."""

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.accounts.repository import InMemoryAccountRepository, get_account_repository
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.portal.dependencies import require_role

FIXED_TIME = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)

portal_app = FastAPI()


@portal_app.get("/engineer-only")
def engineer_only(context: Any = Depends(require_role("data_engineer"))):
    return {"ok": True, "role": context.profile.role}


@portal_app.get("/any-operational")
def any_operational(context: Any = Depends(require_role())):
    return {"ok": True, "role": context.profile.role}


def _profile(uid, role, status="active", email_verified=True):
    return {
        "uid": uid,
        "name": f"User {uid}",
        "email": f"{uid}@example.com",
        "email_verified": email_verified,
        "role": role,
        "account_status": status,
        "profile": {},
        "storage_used_bytes": 0,
        "storage_quota_bytes": 0,
        "created_at": FIXED_TIME,
        "updated_at": FIXED_TIME,
    }


@pytest.fixture
def portal_context():
    repository = InMemoryAccountRepository(clock=lambda: FIXED_TIME)
    identity = {"user": AuthenticatedUser(uid="op-1", email="op-1@example.com", email_verified=True)}
    portal_app.dependency_overrides[get_current_user] = lambda: identity["user"]
    portal_app.dependency_overrides[get_account_repository] = lambda: repository
    with TestClient(portal_app) as client:
        yield client, repository, identity
    portal_app.dependency_overrides.clear()


def test_data_engineer_reaches_engineer_route(portal_context):
    client, repository, identity = portal_context
    repository.profiles["op-1"] = _profile("op-1", "data_engineer")
    response = client.get("/engineer-only")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "role": "data_engineer"}


def test_system_admin_reaches_engineer_route(portal_context):
    client, repository, identity = portal_context
    repository.profiles["op-1"] = _profile("op-1", "system_admin")
    response = client.get("/engineer-only")
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "PORTAL_ACCESS_DENIED"


def test_free_role_is_denied(portal_context):
    client, repository, identity = portal_context
    repository.profiles["op-1"] = _profile("op-1", "free")
    response = client.get("/engineer-only")
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "PORTAL_ACCESS_DENIED"


def test_missing_profile_is_denied_without_revealing_state(portal_context):
    client, repository, identity = portal_context
    response = client.get("/engineer-only")
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "PORTAL_ACCESS_DENIED"


def test_suspended_engineer_is_denied(portal_context):
    client, repository, identity = portal_context
    repository.profiles["op-1"] = _profile("op-1", "data_engineer", status="suspended")
    response = client.get("/engineer-only")
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "ACCOUNT_UNAVAILABLE"


def test_unverified_email_is_rejected_first(portal_context):
    client, repository, identity = portal_context
    identity["user"] = AuthenticatedUser(uid="op-1", email="op-1@example.com", email_verified=False)
    repository.profiles["op-1"] = _profile("op-1", "data_engineer")
    response = client.get("/engineer-only")
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "EMAIL_VERIFICATION_REQUIRED"


def test_engineer_cannot_reach_admin_only_route(portal_context):
    client, repository, identity = portal_context

    @portal_app.get("/admin-only", dependencies=[Depends(require_role("system_admin"))])
    def admin_only():
        return {"ok": True}

    repository.profiles["op-1"] = _profile("op-1", "data_engineer")
    response = client.get("/admin-only")
    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "PORTAL_ACCESS_DENIED"


def test_repository_failure_maps_to_service_unavailable(portal_context):
    client, repository, identity = portal_context

    def broken(uid):
        raise RuntimeError("firestore down")

    portal_app.dependency_overrides[get_account_repository] = lambda: broken
    response = client.get("/engineer-only")
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "PORTAL_SERVICE_UNAVAILABLE"
