"""Feedback submission route tests for the account endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from app.accounts.repository import (
    InMemoryAccountRepository,
    get_account_repository,
)
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.feedback.repository import (
    InMemoryFeedbackRepository,
    get_feedback_repository,
)
from app.main import app


FIXED_TIME = datetime(
    2026,
    10,
    12,
    12,
    0,
    tzinfo=timezone.utc,
)


@pytest.fixture
def feedback_context():
    account_repository = InMemoryAccountRepository(
        clock=lambda: FIXED_TIME
    )

    feedback_repository = InMemoryFeedbackRepository(
        clock=lambda: FIXED_TIME
    )

    identity = AuthenticatedUser(
        uid="user-456",
        email="person@example.com",
        email_verified=True,
    )

    account_repository.ensure_free_profile(
        identity,
        "Test User",
    )

    current = {
        "user": identity
    }

    app.dependency_overrides[
        get_account_repository
    ] = lambda: account_repository

    app.dependency_overrides[
        get_feedback_repository
    ] = lambda: feedback_repository

    app.dependency_overrides[
        get_current_user
    ] = lambda: current["user"]

    with TestClient(app) as client:
        yield (
            client,
            account_repository,
            feedback_repository,
            current,
        )

    app.dependency_overrides.clear()


def test_user_can_submit_general_feedback(
    feedback_context,
) -> None:
    client, _, feedback_repository, _ = feedback_context

    response = client.post(
        "/account/feedback",
        json={
            "category": "general_feedback",
            "comments": "The app is easy to use.",
        },
    )

    assert response.status_code == 201

    record = response.json()

    assert record["user_id"] == "user-456"
    assert record["category"] == "general_feedback"
    assert record["rating"] is None
    assert record["comments"] == "The app is easy to use."
    assert record["status"] == "submitted"
    assert record["reviewed_at"] is None

    stored = feedback_repository.list_feedback()

    assert len(stored) == 1
    assert stored[0].feedback_id == record["feedback_id"]


def test_user_can_submit_rating_only_feedback(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.post(
        "/account/feedback",
        json={
            "category": "service_review",
            "rating": 4,
        },
    )

    assert response.status_code == 201

    record = response.json()

    assert record["rating"] == 4
    assert record["comments"] is None


def test_submission_rejects_empty_feedback(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.post(
        "/account/feedback",
        json={
            "category": "general_feedback",
        },
    )

    assert response.status_code == 422

    assert (
        response.json()["detail"]["error_code"]
        == "FEEDBACK_EMPTY"
    )

    response = client.post(
        "/account/feedback",
        json={
            "category": "general_feedback",
            "comments": "   ",
        },
    )

    assert response.status_code == 422


def test_submission_rejects_invalid_rating(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.post(
        "/account/feedback",
        json={
            "category": "general_feedback",
            "rating": 9,
        },
    )

    assert response.status_code == 422


def test_suspended_user_cannot_submit_feedback(
    feedback_context,
) -> None:
    client, account_repository, _, _ = feedback_context

    account_repository.profiles[
        "user-456"
    ]["account_status"] = "suspended"

    response = client.post(
        "/account/feedback",
        json={
            "category": "general_feedback",
            "comments": "Still wants to talk.",
        },
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "ACCOUNT_UNAVAILABLE"
    )


def test_unverified_user_cannot_submit_feedback(
    feedback_context,
) -> None:
    client, _, _, current = feedback_context

    current["user"] = AuthenticatedUser(
        uid="user-456",
        email="person@example.com",
        email_verified=False,
    )

    response = client.post(
        "/account/feedback",
        json={
            "category": "general_feedback",
            "comments": "Hello.",
        },
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "EMAIL_VERIFICATION_REQUIRED"
    )


def test_submitted_feedback_reaches_admin_review(
    feedback_context,
) -> None:
    client, account_repository, _, current = feedback_context

    response = client.post(
        "/account/feedback",
        json={
            "category": "service_review",
            "rating": 5,
            "comments": "Great checks.",
        },
    )

    assert response.status_code == 201

    feedback_id = response.json()["feedback_id"]

    admin_identity = AuthenticatedUser(
        uid="admin-123",
        email="admin@example.com",
        email_verified=True,
    )

    account_repository.ensure_free_profile(
        admin_identity,
        "System Admin",
    )

    account_repository.profiles[
        "admin-123"
    ]["role"] = "system_admin"

    account_repository.profiles[
        "admin-123"
    ]["account_status"] = "active"

    current["user"] = admin_identity

    listing = client.get(
        "/admin/feedback"
    )

    assert listing.status_code == 200

    records = listing.json()

    assert len(records) == 1

    assert records[0]["feedback_id"] == feedback_id

    assert records[0]["status"] == "submitted"


def test_non_admin_cannot_list_feedback(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.get(
        "/admin/feedback"
    )

    assert response.status_code == 403
