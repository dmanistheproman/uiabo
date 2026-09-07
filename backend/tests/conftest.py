"""Explicit authenticated context for analysis-route tests."""
import pytest
from app.analyses.store import InMemoryAnalysisStore, get_analysis_store
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.main import app


@pytest.fixture
def signed_analysis():
    store = InMemoryAnalysisStore()
    identity = {"user": AuthenticatedUser(uid="analysis-user", email="test@example.com", email_verified=True)}
    store.documents["users", "analysis-user"] = {"uid": "analysis-user", "role": "free", "account_status": "active"}
    app.dependency_overrides[get_current_user] = lambda: identity["user"]
    app.dependency_overrides[get_analysis_store] = lambda: store
    yield store, identity
    app.dependency_overrides.clear()
