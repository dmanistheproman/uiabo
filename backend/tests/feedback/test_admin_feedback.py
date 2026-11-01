"""System Administrator feedback-review route tests."""

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

    admin_identity = AuthenticatedUser(
        uid="admin-123",
        email="admin@example.com",
        email_verified=True,
    )

    normal_identity = AuthenticatedUser(
        uid="user-456",
        email="person@example.com",
        email_verified=True,
    )

    # Create System Administrator account.
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

    # Create an ordinary user.
    account_repository.ensure_free_profile(
        normal_identity,
        "Test User",
    )

    # Add sample feedback.
    feedback_repository.feedback[
        "feedback-123"
    ] = {
        "feedback_id": "feedback-123",
        "user_id": "user-456",
        "category": "service_review",
        "rating": 4,
        "comments": (
            "The explanation was easy to understand."
        ),
        "status": "submitted",
        "created_at": FIXED_TIME,
        "reviewed_at": None,
        "reviewed_by": None,
    }

    feedback_repository.feedback[
        "feedback-456"
    ] = {
        "feedback_id": "feedback-456",
        "user_id": "user-456",
        "category": "general_feedback",
        "rating": None,
        "comments": (
            "I would like the text to be slightly larger."
        ),
        "status": "reviewed",
        "created_at": FIXED_TIME - timedelta(hours=1),
        "reviewed_at": FIXED_TIME - timedelta(minutes=30),
        "reviewed_by": "admin-old",
    }

    current = {
        "user": admin_identity
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


def test_system_admin_can_list_feedback(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.get(
        "/admin/feedback"
    )

    assert response.status_code == 200

    feedback = response.json()

    assert len(feedback) == 2

    assert (
        feedback[0]["feedback_id"]
        == "feedback-123"
    )


def test_system_admin_can_filter_feedback_by_status(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.get(
        "/admin/feedback?status=submitted"
    )

    assert response.status_code == 200

    feedback = response.json()

    assert len(feedback) == 1

    assert (
        feedback[0]["feedback_id"]
        == "feedback-123"
    )

    assert (
        feedback[0]["status"]
        == "submitted"
    )


def test_system_admin_can_filter_feedback_by_category(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.get(
        "/admin/feedback"
        "?category=general_feedback"
    )

    assert response.status_code == 200

    feedback = response.json()

    assert len(feedback) == 1

    assert (
        feedback[0]["feedback_id"]
        == "feedback-456"
    )

    assert (
        feedback[0]["category"]
        == "general_feedback"
    )


def test_system_admin_can_view_feedback_details(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.get(
        "/admin/feedback/feedback-123"
    )

    assert response.status_code == 200

    feedback = response.json()

    assert (
        feedback["feedback_id"]
        == "feedback-123"
    )

    assert (
        feedback["user_id"]
        == "user-456"
    )

    assert (
        feedback["category"]
        == "service_review"
    )

    assert feedback["rating"] == 4

    assert (
        feedback["status"]
        == "submitted"
    )


def test_system_admin_can_mark_feedback_reviewed(
    feedback_context,
) -> None:
    (
        client,
        _,
        feedback_repository,
        _,
    ) = feedback_context

    response = client.patch(
        "/admin/feedback/feedback-123/review",
        json={
            "status": "reviewed"
        },
    )

    assert response.status_code == 200

    feedback = response.json()

    assert (
        feedback["status"]
        == "reviewed"
    )

    assert (
        feedback["reviewed_by"]
        == "admin-123"
    )

    assert feedback["reviewed_at"] is not None

    stored = feedback_repository.feedback[
        "feedback-123"
    ]

    assert (
        stored["status"]
        == "reviewed"
    )

    assert (
        stored["reviewed_by"]
        == "admin-123"
    )

    assert (
        stored["reviewed_at"]
        == FIXED_TIME
    )


def test_missing_feedback_returns_404(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.get(
        "/admin/feedback/does-not-exist"
    )

    assert response.status_code == 404

    assert (
        response.json()["detail"]["error_code"]
        == "FEEDBACK_NOT_FOUND"
    )


def test_free_user_cannot_access_feedback(
    feedback_context,
) -> None:
    (
        client,
        account_repository,
        _,
        current,
    ) = feedback_context

    normal_user = AuthenticatedUser(
        uid="user-456",
        email="person@example.com",
        email_verified=True,
    )

    current["user"] = normal_user

    account_repository.profiles[
        "user-456"
    ]["role"] = "free"

    response = client.get(
        "/admin/feedback"
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "ADMIN_ACCESS_REQUIRED"
    )


def test_data_engineer_cannot_access_admin_feedback(
    feedback_context,
) -> None:
    (
        client,
        account_repository,
        _,
        current,
    ) = feedback_context

    engineer = AuthenticatedUser(
        uid="engineer-789",
        email="engineer@example.com",
        email_verified=True,
    )

    account_repository.ensure_free_profile(
        engineer,
        "Data Engineer",
    )

    account_repository.profiles[
        "engineer-789"
    ]["role"] = "data_engineer"

    account_repository.profiles[
        "engineer-789"
    ]["account_status"] = "active"

    current["user"] = engineer

    response = client.get(
        "/admin/feedback"
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "ADMIN_ACCESS_REQUIRED"
    )


def test_suspended_admin_cannot_access_feedback(
    feedback_context,
) -> None:
    (
        client,
        account_repository,
        _,
        _,
    ) = feedback_context

    account_repository.profiles[
        "admin-123"
    ]["account_status"] = "suspended"

    response = client.get(
        "/admin/feedback"
    )

    assert response.status_code == 403

    assert (
        response.json()["detail"]["error_code"]
        == "ACCOUNT_UNAVAILABLE"
    )


def test_invalid_feedback_status_filter_is_rejected(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.get(
        "/admin/feedback?status=random_status"
    )

    assert response.status_code == 422


def test_invalid_feedback_category_is_rejected(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.get(
        "/admin/feedback?category=random_category"
    )

    assert response.status_code == 422


def test_invalid_review_status_is_rejected(
    feedback_context,
) -> None:
    client, _, _, _ = feedback_context

    response = client.patch(
        "/admin/feedback/feedback-123/review",
        json={
            "status": "submitted"
        },
    )

    assert response.status_code == 422
