"""System Administrator route tests."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from app.accounts.repository import (
    InMemoryAccountRepository,
    get_account_repository,
)
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.main import app


FIXED_TIME = datetime(
    2026,
    10,
    12,
    4,
    0,
    tzinfo=timezone.utc,
)


def test_admin_cannot_suspend_self(admin_context):
    client, repository, _ = admin_context
    response = client.patch('/admin/users/admin-123/status', json={'account_status':'suspended','reason':'test'})
    assert response.status_code == 409
    assert repository.profiles['admin-123']['account_status'] == 'active'


def test_suspension_requires_reason_and_revokes_sessions(admin_context, monkeypatch):
    from unittest.mock import Mock
    from app.routers import admin
    client, repository, _ = admin_context
    revoke = Mock()
    monkeypatch.setattr(admin,'revoke_sessions',revoke)
    assert client.patch('/admin/users/user-456/status',json={'account_status':'suspended'}).status_code == 422
    response = client.patch('/admin/users/user-456/status',json={'account_status':'suspended','reason':'Abusive submissions'})
    assert response.status_code == 200
    revoke.assert_called_once_with('user-456')
    assert repository.profiles['user-456']['profile']['access_change']['reason'] == 'Abusive submissions'


def test_operational_requests_have_audit_and_fail_closed(admin_context):
    from app.portal.audit import get_audit_store
    client, _, _ = admin_context
    events = {}
    class Audit:
        def write(self,key,value): events[key] = dict(value)
    app.dependency_overrides[get_audit_store] = Audit
    assert client.get('/admin/users?query=private-email@example.org').status_code == 200
    event = next(iter(events.values()))
    assert event['outcome'] == 'succeeded' and event['status_code'] == 200
    assert 'private-email' not in str(event)
    class UnavailableAudit:
        def write(self,key,value): raise RuntimeError('offline')
    app.dependency_overrides[get_audit_store] = UnavailableAudit
    assert client.patch('/admin/users/user-456/status',json={'account_status':'suspended','reason':'test'}).status_code == 503


@pytest.fixture
def admin_context():
    repository = InMemoryAccountRepository(
        clock=lambda: FIXED_TIME
    )

    admin_identity = AuthenticatedUser(
        uid="admin-123",
        email="admin@example.com",
        email_verified=True,
    )

    target_identity = AuthenticatedUser(
        uid="user-456",
        email="person@example.com",
        email_verified=True,
    )

    # Create the admin profile.
    repository.ensure_staff_profile(
        admin_identity,
        "System Admin",
    )

    # Promote the account on the server side.
    repository.profiles["admin-123"]["operational_roles"] = ["system_admin"]
    repository.profiles["admin-123"]["account_status"] = "active"

    # Create an ordinary user for the admin to manage.
    repository.ensure_free_profile(
        target_identity,
        "Test User",
    )

    current = {
        "user": admin_identity
    }

    app.dependency_overrides[
        get_account_repository
    ] = lambda: repository

    app.dependency_overrides[
        get_current_user
    ] = lambda: current["user"]

    with TestClient(app) as client:
        yield client, repository, current

    app.dependency_overrides.clear()


def test_system_admin_can_search_users(
    admin_context,
) -> None:
    client, _, _ = admin_context

    response = client.get(
        "/admin/users?query=person@example.com"
    )

    assert response.status_code == 200

    users = response.json()

    assert len(users) == 1
    assert users[0]["uid"] == "user-456"
    assert users[0]["email"] == "person@example.com"


def test_system_admin_can_view_user(
    admin_context,
) -> None:
    client, _, _ = admin_context

    response = client.get(
        "/admin/users/user-456"
    )

    assert response.status_code == 200

    profile = response.json()

    assert profile["uid"] == "user-456"
    assert profile["name"] == "Test User"
    assert profile["account_status"] == "active"


def test_system_admin_can_suspend_user(
    admin_context,
) -> None:
    client, repository, _ = admin_context

    response = client.patch(
        "/admin/users/user-456/status",
        json={
            "account_status": "suspended", "reason": "Test suspension"
        },
    )

    assert response.status_code == 200

    assert (
        response.json()["account_status"]
        == "suspended"
    )

    assert (
        repository.profiles[
            "user-456"
        ]["account_status"]
        == "suspended"
    )


def test_system_admin_can_restore_user(
    admin_context,
) -> None:
    client, repository, _ = admin_context

    repository.profiles[
        "user-456"
    ]["account_status"] = "suspended"

    response = client.patch(
        "/admin/users/user-456/status",
        json={
            "account_status": "active"
        },
    )

    assert response.status_code == 200

    assert (
        response.json()["account_status"]
        == "active"
    )

    assert (
        repository.profiles[
            "user-456"
        ]["account_status"]
        == "active"
    )


def test_free_user_cannot_access_admin_routes(
    admin_context,
) -> None:
    client, repository, current = admin_context

    normal_user = AuthenticatedUser(
        uid="user-456",
        email="person@example.com",
        email_verified=True,
    )

    current["user"] = normal_user

    repository.profiles[
        "user-456"
    ]["role"] = "free"

    response = client.get(
        "/admin/users"
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "ADMIN_ACCESS_REQUIRED"
    )


def test_premium_user_cannot_access_admin_routes(
    admin_context,
) -> None:
    client, repository, current = admin_context

    premium_user = AuthenticatedUser(
        uid="user-456",
        email="person@example.com",
        email_verified=True,
    )

    current["user"] = premium_user

    repository.profiles[
        "user-456"
    ]["role"] = "premium"

    response = client.get(
        "/admin/users"
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "ADMIN_ACCESS_REQUIRED"
    )


def test_data_engineer_cannot_access_admin_routes(
    admin_context,
) -> None:
    client, repository, current = admin_context

    engineer = AuthenticatedUser(
        uid="engineer-789",
        email="engineer@example.com",
        email_verified=True,
    )

    repository.ensure_staff_profile(
        engineer,
        "Data Engineer",
    )

    repository.profiles[
        "engineer-789"
    ]["operational_roles"] = ["data_engineer"]

    repository.profiles[
        "engineer-789"
    ]["account_status"] = "active"

    current["user"] = engineer

    response = client.get(
        "/admin/users"
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "ADMIN_ACCESS_REQUIRED"
    )


def test_suspended_admin_cannot_access_admin_routes(
    admin_context,
) -> None:
    client, repository, _ = admin_context

    repository.profiles[
        "admin-123"
    ]["account_status"] = "suspended"

    response = client.get(
        "/admin/users"
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "ACCOUNT_UNAVAILABLE"
    )


def test_missing_user_returns_404(
    admin_context,
) -> None:
    client, _, _ = admin_context

    response = client.get(
        "/admin/users/does-not-exist"
    )

    assert response.status_code == 404

    assert (
        response.json()["detail"]["error_code"]
        == "USER_NOT_FOUND"
    )


def test_invalid_status_is_rejected(
    admin_context,
) -> None:
    client, _, _ = admin_context

    response = client.patch(
        "/admin/users/user-456/status",
        json={
            "account_status": "deactivated"
        },
    )

    assert response.status_code == 422
