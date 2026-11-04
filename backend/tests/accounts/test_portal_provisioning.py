from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from scripts import create_operational_account as script

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


class Database:
    def __init__(self): self.docs = {}
    def collection(self, name):
        return SimpleNamespace(document=lambda uid: Reference(self, (name, uid)))
    def transaction(self): return self
    def set(self, ref, value, merge=False):
        self.docs[ref.key] = {**(self.docs.get(ref.key, {}) if merge else {}), **deepcopy(value)}


class Reference:
    def __init__(self, db, key): self.db, self.key = db, key
    def get(self, **kwargs):
        return SimpleNamespace(to_dict=lambda: deepcopy(self.db.docs.get(self.key)))


@pytest.fixture
def grant_env(monkeypatch):
    monkeypatch.setattr(script.firestore, 'transactional', lambda function: function)
    user = SimpleNamespace(uid='operator', email='operator@example.org', email_verified=True, disabled=False, display_name='Operator')
    db = Database()
    db.docs['users', user.uid] = {'role': 'staff', 'account_status': 'active', 'name': 'Existing name'}
    return db, user


def test_additive_staff_grants_preserve_name_without_creating_allowance(grant_env):
    db, user = grant_env
    assert script.grant_portal_access(db, user, ['data_engineer'], now=NOW) == ['data_engineer']
    assert script.grant_portal_access(db, user, ['system_admin'], now=NOW) == ['data_engineer', 'system_admin']
    assert script.grant_portal_access(db, user, ['system_admin'], now=NOW) == ['data_engineer', 'system_admin']
    assert db.docs['users', user.uid]['role'] == 'staff'
    assert db.docs['users', user.uid]['name'] == 'Existing name'
    assert ('usage_allowances', user.uid) not in db.docs


@pytest.mark.parametrize('role', ['free', 'premium'])
def test_bootstrap_script_cannot_convert_an_app_account(grant_env, role):
    db, user = grant_env
    db.docs['users', user.uid]['role'] = role
    before = deepcopy(db.docs)
    with pytest.raises(ValueError, match='separate staff account'):
        script.grant_portal_access(db, user, ['system_admin'])
    assert db.docs == before


def test_grant_both_and_migrate_legacy_role(grant_env):
    db, user = grant_env
    db.docs['users', user.uid]['role'] = 'data_engineer'
    assert script.grant_portal_access(db, user, ['system_admin'], now=NOW) == ['data_engineer', 'system_admin']
    db.docs['users', user.uid].pop('operational_roles')
    assert script.grant_portal_access(db, user, ['data_engineer', 'system_admin'], now=NOW) == ['data_engineer', 'system_admin']


@pytest.mark.parametrize('status', ['suspended', 'deactivated'])
def test_role_grant_does_not_reactivate_account(grant_env, status):
    db, user = grant_env
    db.docs['users', user.uid]['account_status'] = status
    before = deepcopy(db.docs)
    with pytest.raises(ValueError): script.grant_portal_access(db, user, ['system_admin'])
    assert db.docs == before


def test_invalid_unverified_disabled_or_deleting_account_is_unchanged(grant_env):
    db, user = grant_env
    before = deepcopy(db.docs)
    with pytest.raises(ValueError): script.grant_portal_access(db, user, ['super_admin'])
    user.email_verified = False
    with pytest.raises(ValueError): script.grant_portal_access(db, user, ['system_admin'])
    user.email_verified = True
    user.disabled = True
    with pytest.raises(ValueError): script.grant_portal_access(db, user, ['system_admin'])
    assert db.docs == before
    user.disabled = False
    db.docs['account_deletions', user.uid] = {'status': 'pending'}
    with pytest.raises(ValueError): script.grant_portal_access(db, user, ['system_admin'])
    assert db.docs['users', user.uid] == before['users', user.uid]


@pytest.mark.parametrize('flags', [
    ['--roles', 'data_engineer', 'system_admin'],
    ['--role', 'data_engineer', '--role', 'system_admin'],
])
def test_cli_accepts_both_role_options(grant_env, monkeypatch, flags):
    db, user = grant_env
    monkeypatch.setattr(script, 'get_firebase_app', lambda: None)
    monkeypatch.setattr(script, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(script.firebase_auth, 'get_user_by_email', lambda email: user)
    monkeypatch.setattr('sys.argv', ['create_operational_account', '--email', user.email, *flags])
    assert script.main() == 0
    assert db.docs['users', user.uid]['operational_roles'] == ['data_engineer', 'system_admin']
