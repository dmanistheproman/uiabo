"""Explicit authenticated context for analysis-route tests."""
import os

# Set before importing app.main: optional image providers load dotenv on import.
# Offline tests must not inherit credentials or pipeline flags from a developer's file.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

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


@pytest.fixture(autouse=True)
def offline_operational_services(monkeypatch):
    monkeypatch.setenv("TEXT_ANALYSIS_MODE", "pipeline")
    monkeypatch.setenv("EVIDENCE_PIPELINE_V3", "0")
    monkeypatch.setenv("EVIDENCE_RETRIEVAL_MODE", "catalogue")
    monkeypatch.setenv("EVIDENCE_ASSESSMENT_MODE", "lexical")
    from app.portal.audit import AuditStore
    from app.accounts.deletion import DeletionService
    from app.routers import admin
    monkeypatch.setattr(AuditStore, "write", lambda self, key, value: None)
    monkeypatch.setattr(DeletionService, "run_pending", lambda self: None)
    monkeypatch.setattr(admin, "revoke_sessions", lambda uid: None)
