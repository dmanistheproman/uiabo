"""Protected profile endpoint tests using in-memory account storage."""

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


FIXED_TIME = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def account_context():
    repository = InMemoryAccountRepository(clock=lambda: FIXED_TIME)
    current = {
        "user": AuthenticatedUser(
            uid="user-123",
            email="person@example.com",
            email_verified=False,
        )
    }

    app.dependency_overrides[get_account_repository] = lambda: repository
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    with TestClient(app) as client:
        yield client, repository, current
    app.dependency_overrides.clear()


def test_registration_creates_pending_free_profile_and_allowance(
    account_context,
) -> None:
    client, repository, _ = account_context

    response = client.put("/account/me", json={"name": "  Test   User "})

    assert response.status_code == 200
    profile = response.json()
    assert profile["uid"] == "user-123"
    assert profile["name"] == "Test User"
    assert profile["role"] == "free"
    assert profile["account_status"] == "pending_verification"
    assert profile["allowance"]["submission_limit"] == 1
    assert profile["allowance"]["remaining_submissions"] == 1
    assert repository.profiles["user-123"]["email"] == (
        "person@example.com"
    )


def test_verified_login_activates_and_returns_own_profile(
    account_context,
) -> None:
    client, _, current = account_context
    client.put("/account/me", json={"name": "Test User"})
    current["user"] = AuthenticatedUser(
        uid="user-123",
        email="person@example.com",
        email_verified=True,
    )

    refreshed = client.put("/account/me", json={"name": "Test User"})
    viewed = client.get("/account/me")

    assert refreshed.status_code == 200
    assert refreshed.json()["account_status"] == "active"
    assert viewed.status_code == 200
    assert viewed.json()["uid"] == "user-123"
    assert viewed.json()["email_verified"] is True


def test_unverified_user_cannot_view_protected_profile(
    account_context,
) -> None:
    client, _, _ = account_context
    client.put("/account/me", json={"name": "Test User"})

    response = client.get("/account/me")

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == (
        "EMAIL_VERIFICATION_REQUIRED"
    )


def test_missing_profile_returns_404(account_context) -> None:
    client, _, current = account_context
    current["user"] = AuthenticatedUser(
        uid="user-123",
        email="person@example.com",
        email_verified=True,
    )

    response = client.get("/account/me")

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "PROFILE_NOT_FOUND"


def test_suspended_account_cannot_access_profile(account_context) -> None:
    client, repository, current = account_context
    current["user"] = AuthenticatedUser(
        uid="user-123",
        email="person@example.com",
        email_verified=True,
    )
    client.put("/account/me", json={"name": "Test User"})
    repository.profiles["user-123"]["account_status"] = "suspended"

    response = client.get("/account/me")

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "ACCOUNT_UNAVAILABLE"
