"""Tests for Firebase Bearer-token verification."""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from app.auth import dependencies
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser


auth_test_app = FastAPI()


@auth_test_app.get("/protected")
def protected(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    return user.model_dump()


client = TestClient(auth_test_app)


def test_missing_bearer_token_is_rejected() -> None:
    response = client.get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == (
        "AUTHENTICATION_REQUIRED"
    )


def test_valid_token_returns_trusted_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        dependencies,
        "verify_firebase_id_token",
        lambda token: {
            "uid": "user-123",
            "email": "person@example.com",
            "email_verified": True,
        },
    )

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer valid-test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "uid": "user-123",
        "email": "person@example.com",
        "email_verified": True,
    }


def test_invalid_token_is_a_neutral_401(monkeypatch) -> None:
    def reject(token: str) -> dict:
        del token
        raise dependencies._authentication_error()

    monkeypatch.setattr(dependencies, "verify_firebase_id_token", reject)

    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer invalid-test-token"},
    )

    assert response.status_code == 401
    assert "token" not in response.text.lower()


def test_verifier_maps_firebase_outage_to_503(monkeypatch) -> None:
    monkeypatch.setattr(dependencies, "get_firebase_app", lambda: object())

    def unavailable(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("certificate service unavailable")

    monkeypatch.setattr(
        dependencies.firebase_auth,
        "verify_id_token",
        unavailable,
    )

    with pytest.raises(HTTPException) as raised:
        dependencies.verify_firebase_id_token("test-token")

    assert raised.value.status_code == 503
    assert raised.value.detail["error_code"] == (
        "AUTHENTICATION_SERVICE_UNAVAILABLE"
    )
