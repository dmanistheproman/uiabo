from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.accounts.repository import InMemoryAccountRepository, FirestoreAccountRepository, get_account_repository
from app.accounts.roles import stored_account_type, stored_operational_roles
from app.analyses.store import InMemoryAnalysisStore, get_analysis_store, active_profile
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.main import app
from app.routers import admin
from app.feedback.repository import InMemoryFeedbackRepository, get_feedback_repository

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


@pytest.fixture
def separated(monkeypatch):
    repo = InMemoryAccountRepository(clock=lambda: NOW)
    store = InMemoryAnalysisStore(clock=lambda: NOW)
    identity = {name: AuthenticatedUser(uid=name, email=f'{name}@example.org', email_verified=True)
                for name in ('admin', 'staff', 'app', 'new')}
    repo.ensure_staff_profile(identity['admin'], 'Admin')
    repo.profiles['admin']['operational_roles'] = ['system_admin']
    repo.ensure_staff_profile(identity['staff'], 'Staff')
    repo.profiles['staff']['operational_roles'] = ['data_engineer', 'system_admin']
    repo.ensure_free_profile(identity['app'], 'App user')
    repo.profiles['app']['role'] = 'premium'
    for uid, profile in repo.profiles.items(): store.documents['users', uid] = deepcopy(profile)
    current = {'user': identity['new']}
    monkeypatch.setattr(admin, 'verified_staff_identity', lambda **kwargs:
        (identity[kwargs.get('uid') or kwargs['email'].split('@')[0]], 'Name'))
    app.dependency_overrides[get_current_user] = lambda: current['user']
    app.dependency_overrides[get_account_repository] = lambda: repo
    app.dependency_overrides[get_analysis_store] = lambda: store
    app.dependency_overrides[get_feedback_repository] = InMemoryFeedbackRepository
    with TestClient(app) as client: yield client, repo, store, identity, current
    app.dependency_overrides.clear()


def test_portal_registration_creates_staff_with_no_allowance_or_permissions(separated):
    client, repo, _, identities, current = separated
    current['user'] = identities['new'].model_copy(update={'email_verified': False})
    response = client.put('/portal/me', json={'name': 'New staff'})
    assert response.status_code == 200
    assert response.json()['account_type'] == 'staff'
    assert response.json()['role'] == 'staff'
    assert response.json()['account_status'] == 'pending_verification'
    assert response.json()['operational_roles'] == []
    assert response.json()['allowance'] is None
    assert 'new' not in repo.allowances
    assert client.put('/account/me', json={'name': 'Try app'}).status_code == 403
    current['user'] = identities['new']
    assert client.put('/portal/me', json={'name': 'New staff'}).json()['account_status'] == 'active'
    assert client.get('/portal/session?portal_role=system_admin').status_code == 403


def test_staff_accounts_cannot_use_app_profiles_feedback_history_or_checks(separated):
    client, repo, store, identities, current = separated
    current['user'] = identities['staff']
    before = deepcopy(repo.profiles['staff'])
    for response in (
        client.get('/account/me'), client.put('/account/me', json={'name': 'App conversion'}),
        client.post('/account/feedback', json={'category': 'general_feedback', 'comments': 'test'}),
        client.get('/analysis/results'), client.get('/analysis/results/' + 'a'*32),
    ):
        assert response.status_code == 403
        assert response.json()['detail']['error_code'] == 'STAFF_ACCOUNT_ONLY'
    for input_type in ('text', 'link_safety', 'ocr_text', 'deepfake_ai', 'image_context'):
        with pytest.raises(HTTPException) as rejected: store.reserve('staff', 'request', 'input', input_type)
        assert rejected.value.detail['error_code'] == 'STAFF_ACCOUNT_ONLY'
    assert repo.profiles['staff'] == before and 'staff' not in repo.allowances
    assert not any(collection == 'usage_allowances' for collection, _ in store.documents)
    assert client.get('/portal/me').status_code == 200
    assert client.get('/portal/session?portal_role=data_engineer').status_code == 200


def test_app_account_cannot_become_staff_or_keep_historical_portal_grants(separated):
    client, repo, _, identities, current = separated
    repo.profiles['app']['operational_roles'] = ['data_engineer', 'system_admin']
    before = deepcopy(repo.profiles['app'])
    current['user'] = identities['app']
    assert client.get('/account/me').status_code == 200
    assert client.get('/account/me').json()['operational_roles'] == []
    for response in (client.get('/portal/me'), client.put('/portal/me', json={'name': 'Convert'}),
                     client.get('/portal/session?portal_role=system_admin'), client.get('/admin/users')):
        assert response.status_code == 403
    current['user'] = identities['admin']
    for response in (
        client.post('/admin/provision', json={'email': 'app@example.org', 'operational_roles': ['data_engineer'], 'reason': 'test'}),
        client.patch('/admin/users/app/roles', json={'operational_roles': ['system_admin'], 'expected_roles': [], 'reason': 'test'}),
    ):
        assert response.status_code == 403 and response.json()['detail']['error_code'] == 'APP_ACCOUNT_ONLY'
    assert repo.profiles['app'] == before


def test_registration_cannot_choose_account_type_or_grant_own_roles(separated):
    client, repo, _, _, _ = separated
    for path in ('/account/me', '/portal/me'):
        for field, value in [('account_type', 'staff'), ('role', 'system_admin'), ('operational_roles', ['system_admin'])]:
            assert client.put(path, json={'name': 'New', field: value}).status_code == 422
    assert 'new' not in repo.profiles


def test_legacy_account_classification_and_explicit_types():
    assert stored_account_type({'role': 'system_admin'}) == 'staff'
    assert stored_account_type({'role': 'premium', 'operational_roles': ['system_admin']}) == 'app'
    assert stored_operational_roles({'role': 'premium', 'operational_roles': ['system_admin']}) == []
    assert stored_operational_roles({'account_type': 'staff', 'role': 'system_admin', 'operational_roles': []}) == []
    with pytest.raises(HTTPException): active_profile({'account_type': 'staff', 'role': 'premium', 'account_status': 'active'})


def test_firestore_staff_registration_cannot_overwrite_app_or_create_allowance(monkeypatch):
    from google.cloud import firestore
    monkeypatch.setattr(firestore, 'transactional', lambda function: function)
    identity = AuthenticatedUser(uid='new', email='new@example.org', email_verified=True)
    docs, writes, reads = {}, [], []
    class Ref:
        def __init__(self, key): self.key = key
        def get(self, transaction=None):
            assert transaction is db
            reads.append(self.key)
            return SimpleNamespace(to_dict=lambda: deepcopy(docs.get(self.key)))
    class DB:
        def collection(self, name): return SimpleNamespace(document=lambda uid: Ref((name, uid)))
        def transaction(self): return self
        def set(self, ref, value, **kwargs):
            writes.append(ref.key); docs[ref.key] = {**docs.get(ref.key, {}), **deepcopy(value)}
    db = DB()
    repo = FirestoreAccountRepository(db, clock=lambda: NOW)
    result = repo.ensure_staff_profile(identity, 'Staff')
    assert result.account_type == 'staff' and result.allowance is None
    assert writes == [('users', 'new')] and ('users', 'new') in reads
    writes.clear()
    with pytest.raises(HTTPException): repo.ensure_free_profile(identity, 'App')
    assert writes == []
    docs['users', 'new'] = {'account_type': 'app', 'role': 'premium', 'account_status': 'active'}
    with pytest.raises(HTTPException): repo.ensure_staff_profile(identity, 'Staff')
    assert writes == [] and docs['users', 'new']['role'] == 'premium'
