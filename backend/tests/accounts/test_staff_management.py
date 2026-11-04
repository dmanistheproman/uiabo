from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.accounts.repository import InMemoryAccountRepository, FirestoreAccountRepository, get_account_repository
from app.accounts import staff
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.routers import admin
from app.portal.audit import get_audit_store

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


@pytest.fixture
def setup(monkeypatch):
    repo = InMemoryAccountRepository(clock=lambda: NOW)
    identities = {uid: AuthenticatedUser(uid=uid, email=f'{uid}@example.org', email_verified=True)
                  for uid in ('admin', 'staff', 'other')}
    for uid, identity in identities.items(): repo.ensure_staff_profile(identity, uid.title())
    repo.profiles['admin']['operational_roles'] = ['system_admin']
    state = {'user': identities['admin']}
    events = {}
    class Audit:
        def write(self, key, value): events[key] = {**events.get(key, {}), **deepcopy(value)}
    def lookup(*, email=None, uid=None):
        identity = identities.get(uid or (email or '').split('@')[0])
        if not identity: staff.fail('STAFF_ACCOUNT_NOT_FOUND', 'Register first.', 404)
        if not identity.email_verified: staff.fail('STAFF_ACCOUNT_NOT_READY', 'Verify first.')
        return identity, 'Firebase name'
    monkeypatch.setattr(admin, 'verified_staff_identity', lookup)
    app.dependency_overrides[get_account_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: state['user']
    app.dependency_overrides[get_audit_store] = Audit
    with TestClient(app) as client: yield client, repo, identities, state, events
    app.dependency_overrides.clear()


def provision(client, email='staff@example.org', roles=None):
    return client.post('/admin/provision', json={'email': email,
        'operational_roles': roles or ['data_engineer', 'system_admin'], 'reason': 'Team assignment'})


def edit(client, uid, roles, expected):
    return client.patch(f'/admin/users/{uid}/roles', json={
        'operational_roles': roles, 'expected_roles': expected, 'reason': 'Responsibilities changed'})


def convert(client, uid='staff', **extra):
    return client.post(f'/admin/users/{uid}/convert-to-app', json={
        'confirm_conversion': True, 'reason': 'No longer a staff member', **extra})


def test_retired_staff_can_reuse_login_in_app_only_after_admin_conversion(setup):
    client, repo, identities, state, events = setup
    assert provision(client).status_code == 200
    assert convert(client).json()['detail']['error_code'] == 'STAFF_ACCESS_REMAINS'
    assert edit(client, 'staff', [], ['data_engineer', 'system_admin']).status_code == 200
    previous = deepcopy(repo.profiles['staff'])
    response = convert(client)
    assert response.status_code == 200
    body = response.json()
    assert body['uid'] == 'staff' and body['email'] == 'staff@example.org'
    assert body['account_type'] == 'app' and body['role'] == 'free' and body['operational_roles'] == []
    assert body['allowance']['remaining_submissions'] == 1
    assert repo.profiles['staff']['created_at'] == previous['created_at']
    assert body['profile'] == {}  # No internal staff administrative notes in app profile.
    assert list(events.values())[-1]['action_details']['account_type_to'] == 'app'
    state['user'] = identities['staff']
    assert client.get('/account/me').status_code == 200
    assert client.put('/account/me', json={'name': 'Former staff'}).status_code == 200
    assert client.get('/portal/session?portal_role=data_engineer').status_code == 403
    assert client.put('/portal/me', json={'name': 'Try portal again'}).status_code == 403
    assert convert(client, 'other').status_code == 403


@pytest.mark.parametrize('status', ['suspended', 'deactivated'])
def test_conversion_does_not_restore_blocked_accounts(setup, status):
    client, repo, _, _, _ = setup
    repo.profiles['staff']['account_status'] = status
    before = deepcopy(repo.profiles)
    assert convert(client).status_code == 403
    assert repo.profiles == before and 'staff' not in repo.allowances


def test_conversion_rechecks_permissions_and_prevents_self_conversion(setup):
    client, repo, identities, _, _ = setup
    assert convert(client, 'admin').status_code == 409
    repo.profiles['staff']['operational_roles'] = ['data_engineer']
    with pytest.raises(HTTPException) as rejected:
        repo.convert_staff_to_app(identities['staff'], actor_uid='admin', reason='stale UI', audit_id='test')
    assert rejected.value.detail['error_code'] == 'STAFF_ACCESS_REMAINS'
    repo.profiles['staff']['operational_roles'] = []
    repo.profiles['admin']['operational_roles'] = []
    with pytest.raises(HTTPException) as rejected:
        repo.convert_staff_to_app(identities['staff'], actor_uid='admin', reason='stale request', audit_id='test')
    assert rejected.value.status_code == 403
    assert repo.profiles['staff']['account_type'] == 'staff'


def test_repeated_conversion_never_resets_app_membership_or_allowance(setup):
    client, repo, _, _, _ = setup
    assert convert(client).status_code == 200
    repo.profiles['staff']['role'] = 'premium'
    repo.allowances['staff'].update(successful_submissions=1, remaining_submissions=0)
    before = deepcopy(repo.allowances)
    response = convert(client)
    assert response.status_code == 409 and response.json()['detail']['error_code'] == 'ALREADY_APP_ACCOUNT'
    assert repo.profiles['staff']['role'] == 'premium' and repo.allowances == before


@pytest.mark.parametrize('extra', [{'confirm_conversion': False}, {'reason': '  '}, {'role': 'premium'}, {'account_type': 'app'}])
def test_conversion_requires_explicit_confirmation_reason_and_fixed_free_tier(setup, extra):
    client, repo, _, _, _ = setup
    assert convert(client, **extra).status_code == 422
    assert repo.profiles['staff']['account_type'] == 'staff'


def test_unverified_identity_and_missing_profile_are_not_converted(setup):
    client, repo, identities, _, _ = setup
    identities['staff'] = identities['staff'].model_copy(update={'email_verified': False})
    assert convert(client).status_code == 409
    identities['staff'] = identities['staff'].model_copy(update={'email_verified': True})
    del repo.profiles['staff']
    assert convert(client).status_code == 404


def test_firestore_conversion_commits_profile_allowance_and_audit_atomically(monkeypatch):
    from google.cloud import firestore
    memory = InMemoryAccountRepository(clock=lambda: NOW)
    actor = AuthenticatedUser(uid='admin', email='admin@example.org', email_verified=True)
    target = AuthenticatedUser(uid='staff', email='staff@example.org', email_verified=True)
    memory.ensure_staff_profile(actor, 'Admin'); memory.ensure_staff_profile(target, 'Staff')
    memory.profiles['admin']['operational_roles'] = ['system_admin']
    docs = {('users', key): deepcopy(value) for key, value in memory.profiles.items()}
    reads, writes = [], []
    class Ref:
        def __init__(self, key): self.key = key
        def get(self, transaction=None):
            assert transaction is db and not writes, 'All reads must precede writes'
            reads.append(self.key)
            return SimpleNamespace(to_dict=lambda: deepcopy(docs.get(self.key)))
    class DB:
        fail_audit = False
        def collection(self, name): return SimpleNamespace(document=lambda key: Ref((name, key)))
        def transaction(self): return self
        def set(self, ref, value, **kwargs):
            if self.fail_audit and ref.key[0] == 'operational_audit': raise RuntimeError('audit failure')
            writes.append(ref.key)
            self.pending[ref.key] = deepcopy(value)
    db = DB()
    def transactional(fn):
        def execute(tx):
            db.pending = {}; reads.clear(); writes.clear()
            result = fn(tx)
            docs.update(db.pending)
            return result
        return execute
    monkeypatch.setattr(firestore, 'transactional', transactional)
    repo = FirestoreAccountRepository(db, clock=lambda: NOW)
    def run(): return repo.convert_staff_to_app(target, actor_uid='admin', reason='Retired staff', audit_id='event')
    db.fail_audit = True
    with pytest.raises(RuntimeError): run()
    assert docs['users', 'staff']['account_type'] == 'staff'
    assert ('usage_allowances', 'staff') not in docs
    db.fail_audit = False
    docs['account_deletions', 'staff'] = {'status': 'pending'}
    with pytest.raises(HTTPException): run()
    assert not writes
    del docs['account_deletions', 'staff']
    result = run()
    assert result.account_type == 'app' and result.role == 'free'
    assert writes == [('users', 'staff'), ('usage_allowances', 'staff'), ('operational_audit', 'event')]
    assert ('users', 'admin') in reads and ('analysis_locks', 'staff') in reads
    assert docs['operational_audit', 'event']['change_applied'] is True
    assert docs['operational_audit', 'event']['action_details']['account_type_from'] == 'staff'


def test_provision_is_additive_and_preserves_staff_name_without_app_allowance(setup):
    client, repo, _, _, events = setup
    original = deepcopy(repo.allowances)
    assert provision(client, roles=['data_engineer']).status_code == 200
    response = provision(client, roles=['system_admin'])
    assert response.status_code == 200
    assert response.json()['operational_roles'] == ['data_engineer', 'system_admin']
    assert response.json()['name'] == 'Staff' and response.json()['role'] == 'staff'
    assert response.json()['allowance'] is None
    assert repo.allowances == original == {}
    event = list(events.values())[-1]
    assert event['actor_role'] == 'system_admin'
    assert event['target_mask'] == sha256(b'staff').hexdigest()[:16]
    assert event['action_details'] == {'before': ['data_engineer'], 'after': ['data_engineer', 'system_admin'], 'reason': 'Team assignment'}
    assert 'staff@example.org' not in str(event)
    assert 'actor_uid' not in str(event)
    assert provision(client).status_code == 200  # Safe to retry.


def test_provision_creates_missing_profile_for_verified_identity(setup):
    client, repo, _, _, _ = setup
    del repo.profiles['staff']
    response = provision(client)
    assert response.status_code == 200
    assert response.json()['role'] == 'staff'
    assert response.json()['name'] == 'Firebase name'


def test_invalid_unregistered_and_unverified_accounts_cannot_be_provisioned(setup):
    client, repo, identities, _, _ = setup
    before = deepcopy(repo.profiles)
    assert provision(client, 'absent@example.org').status_code == 404
    identities['staff'] = identities['staff'].model_copy(update={'email_verified': False})
    assert provision(client).status_code == 409
    for body in [
        {'email': 'bad', 'operational_roles': ['system_admin'], 'reason': 'test'},
        {'email': 'staff@example.org', 'operational_roles': [], 'reason': 'test'},
        {'email': 'staff@example.org', 'operational_roles': ['owner'], 'reason': 'test'},
        {'email': 'staff@example.org', 'operational_roles': ['system_admin'], 'reason': '   '},
        {'email': 'staff@example.org', 'operational_roles': ['system_admin'], 'reason': 'test', 'password': 'not-accepted'},
    ]: assert client.post('/admin/provision', json=body).status_code == 422
    assert repo.profiles == before


def test_exact_role_edit_and_stale_update_protection(setup):
    client, repo, _, _, _ = setup
    assert provision(client).status_code == 200
    assert edit(client, 'staff', ['data_engineer'], ['data_engineer', 'system_admin']).status_code == 200
    stale = edit(client, 'staff', [], ['data_engineer', 'system_admin'])
    assert stale.status_code == 409 and stale.json()['detail']['error_code'] == 'PERMISSIONS_CHANGED'
    assert repo.profiles['staff']['operational_roles'] == ['data_engineer']
    assert edit(client, 'staff', [], ['data_engineer']).status_code == 200
    assert repo.profiles['staff']['operational_roles'] == []


def test_last_admin_protection_and_mutual_revocation(setup):
    client, repo, identities, state, _ = setup
    assert edit(client, 'admin', [], ['system_admin']).status_code == 409
    assert edit(client, 'admin', ['data_engineer', 'system_admin'], ['system_admin']).status_code == 200
    assert provision(client, 'other@example.org', ['system_admin']).status_code == 200
    assert edit(client, 'other', [], ['system_admin']).status_code == 200
    # A stale authorised request must fail the repository's transactional recheck.
    with pytest.raises(HTTPException) as denied:
        repo.change_portal_roles(identities['admin'], [], actor_uid='other', reason='stale request',
                                 expected_roles=['data_engineer', 'system_admin'])
    assert denied.value.status_code == 403
    state['user'] = identities['other']
    assert edit(client, 'admin', [], ['data_engineer', 'system_admin']).status_code == 403
    assert 'system_admin' in repo.profiles['admin']['operational_roles']


def test_suspended_staff_can_lose_roles_but_cannot_gain_roles(setup):
    client, repo, _, _, _ = setup
    provision(client, roles=['data_engineer'])
    repo.profiles['staff']['account_status'] = 'suspended'
    assert provision(client).status_code == 403
    assert edit(client, 'staff', [], ['data_engineer']).status_code == 200
    assert repo.profiles['staff']['account_status'] == 'suspended'


@pytest.mark.parametrize('role', ['free', 'premium', 'data_engineer'])
def test_only_admins_can_provision_or_edit_roles(setup, role):
    client, repo, identities, state, _ = setup
    repo.profiles['staff']['role'] = role
    state['user'] = identities['staff']
    assert provision(client).status_code == 403
    assert edit(client, 'other', ['system_admin'], []).status_code == 403
    assert client.get('/admin/audit').status_code == 403


def test_grant_revocation_enforced_without_a_new_login(setup):
    client, repo, identities, state, _ = setup
    provision(client)
    state['user'] = identities['staff']
    assert client.get('/portal/session?portal_role=system_admin').status_code == 200
    state['user'] = identities['admin']
    edit(client, 'staff', [], ['data_engineer', 'system_admin'])
    state['user'] = identities['staff']
    assert client.get('/portal/session?portal_role=system_admin').status_code == 403


@pytest.mark.parametrize('disabled,verified', [(True, True), (False, False)])
def test_firebase_identity_lookup_refuses_unready_accounts(monkeypatch, disabled, verified):
    monkeypatch.setattr(staff, 'get_firebase_app', lambda: object())
    monkeypatch.setattr(staff.auth, 'get_user_by_email', lambda *args, **kwargs: SimpleNamespace(disabled=disabled, email_verified=verified))
    with pytest.raises(HTTPException) as error: staff.verified_staff_identity(email='user@example.org')
    assert error.value.detail['error_code'] == 'STAFF_ACCOUNT_NOT_READY'


def test_firestore_mutation_reads_current_actor_and_commits_role_audit_together(monkeypatch):
    from google.cloud import firestore
    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)
    memory = InMemoryAccountRepository(clock=lambda: NOW)
    actor = AuthenticatedUser(uid='admin', email='admin@example.org', email_verified=True)
    target = AuthenticatedUser(uid='staff', email='staff@example.org', email_verified=True)
    memory.ensure_staff_profile(actor, 'Admin'); memory.ensure_staff_profile(target, 'Staff')
    memory.profiles['admin']['operational_roles'] = ['system_admin']
    docs = {('users', uid): value for uid, value in memory.profiles.items()}
    reads, writes = [], []
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
    repo.change_portal_roles(target, ['data_engineer'], actor_uid='admin', reason='test', expected_roles=[], audit_id='event')
    assert ('users', 'admin') in reads and ('users', 'staff') in reads
    assert writes == [('users', 'staff'), ('operational_audit', 'event')]
    assert docs['operational_audit', 'event']['change_applied'] is True
    assert docs['operational_audit', 'event']['action_details']['before'] == []
    writes.clear()
    docs['users', 'admin']['operational_roles'] = []
    with pytest.raises(HTTPException):
        repo.change_portal_roles(target, [], actor_uid='admin', reason='stale', expected_roles=['data_engineer'])
    assert writes == []
    docs['users', 'admin']['operational_roles'] = ['system_admin']
    docs['account_deletions', 'staff'] = {'status': 'pending'}
    with pytest.raises(HTTPException):
        repo.change_portal_roles(target, ['system_admin'], actor_uid='admin', reason='test', additive=True)
    assert writes == []
