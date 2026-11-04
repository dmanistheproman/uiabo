"""Selected portals never grant permissions; current server roles do."""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.accounts.repository import InMemoryAccountRepository, get_account_repository
from app.portal.repository import InMemoryReportRepository, get_report_repository

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


@pytest.fixture
def operator():
    accounts = InMemoryAccountRepository(clock=lambda: NOW)
    identity = {'user': AuthenticatedUser(uid='operator', email='operator@example.org', email_verified=True)}
    accounts.ensure_staff_profile(identity['user'], 'Operator')
    accounts.profiles['operator']['operational_roles'] = ['data_engineer', 'system_admin']
    reports = InMemoryReportRepository()
    app.dependency_overrides[get_current_user] = lambda: identity['user']
    app.dependency_overrides[get_account_repository] = lambda: accounts
    app.dependency_overrides[get_report_repository] = lambda: reports
    with TestClient(app) as client:
        yield client, accounts, identity
    app.dependency_overrides.clear()


@pytest.mark.parametrize('roles', [[], ['data_engineer'], ['system_admin'], ['data_engineer', 'system_admin']])
def test_portal_choice_and_actual_routes_enforce_each_grant(operator, roles):
    client, accounts, _ = operator
    accounts.profiles['operator']['operational_roles'] = roles
    for role, path in [('data_engineer', '/portal/reports'), ('system_admin', '/admin/users')]:
        expected = 200 if role in roles else 403
        response = client.get('/portal/session', params={'portal_role': role})
        assert response.status_code == expected
        assert client.get(path).status_code == expected
        if expected == 200:
            assert response.json()['portal_role'] == role
            assert response.json()['profile']['role'] == 'staff'
            assert response.json()['profile']['operational_roles'] == sorted(roles)


def test_legacy_single_role_accounts_work_without_migration(operator):
    client, accounts, _ = operator
    accounts.profiles['operator'].pop('operational_roles')
    accounts.profiles['operator'].pop('account_type')
    accounts.profiles['operator']['role'] = 'system_admin'
    assert client.get('/portal/session?portal_role=system_admin').status_code == 200
    assert client.get('/admin/users').status_code == 200
    assert client.get('/portal/reports').status_code == 403


def test_explicit_empty_roles_revoke_even_a_legacy_primary_admin_role(operator):
    client, accounts, _ = operator
    accounts.profiles['operator'].update(role='system_admin', operational_roles=[])
    assert client.get('/portal/session?portal_role=system_admin').status_code == 403
    assert client.get('/admin/users').status_code == 403


def test_permission_removal_takes_effect_without_changing_token(operator):
    client, accounts, _ = operator
    assert client.get('/portal/session?portal_role=system_admin').status_code == 200
    accounts.profiles['operator']['operational_roles'] = ['data_engineer']
    assert client.get('/admin/users').status_code == 403
    assert client.get('/portal/session?portal_role=system_admin').status_code == 403
    assert client.get('/portal/reports').status_code == 200


@pytest.mark.parametrize('status', ['suspended', 'deactivated', 'pending_verification'])
def test_inactive_dual_role_account_is_denied_everywhere(operator, status):
    client, accounts, _ = operator
    accounts.profiles['operator']['account_status'] = status
    for path in ['/portal/session?portal_role=system_admin', '/portal/session?portal_role=data_engineer',
                 '/admin/users', '/portal/reports']:
        assert client.get(path).status_code == 403


def test_email_verification_and_valid_selection_still_required(operator):
    client, _, identity = operator
    assert client.get('/portal/session?portal_role=premium').status_code == 422
    identity['user'] = identity['user'].model_copy(update={'email_verified': False})
    response = client.get('/portal/session?portal_role=system_admin')
    assert response.status_code == 403
    assert response.json()['detail']['error_code'] == 'EMAIL_VERIFICATION_REQUIRED'


def test_profile_edit_preserves_roles_and_cannot_self_grant(operator):
    client, accounts, _ = operator
    response = client.put('/portal/me', json={'name': 'New operator name'})
    assert response.status_code == 200
    assert response.json()['operational_roles'] == ['data_engineer', 'system_admin']
    assert accounts.profiles['operator']['operational_roles'] == ['data_engineer', 'system_admin']
    assert response.json()['role'] == 'staff'
    assert response.json()['allowance'] is None
    assert client.put('/portal/me', json={'name': 'Name', 'operational_roles': ['system_admin']}).status_code == 422


def test_dual_role_admin_passes_transaction_authorization_and_still_cannot_suspend_self(operator):
    client, accounts, _ = operator
    target = AuthenticatedUser(uid='target', email='target@example.org', email_verified=True)
    accounts.ensure_free_profile(target, 'Target')
    response = client.patch('/admin/users/target/status', json={'account_status': 'suspended', 'reason': 'Test suspension'})
    assert response.status_code == 200
    assert accounts.profiles['target']['account_status'] == 'suspended'
    assert client.patch('/admin/users/operator/status', json={'account_status': 'suspended', 'reason': 'Self'}).status_code == 409


def test_audit_records_selected_permission_instead_of_primary_tier(operator):
    from app.portal.audit import get_audit_store
    client, _, _ = operator
    events = {}
    class Audit:
        def write(self, key, value): events[key] = dict(value)
    app.dependency_overrides[get_audit_store] = Audit
    assert client.get('/portal/session?portal_role=data_engineer').status_code == 200
    assert client.get('/admin/users').status_code == 200
    assert {event.get('actor_role') for event in events.values()} == {'data_engineer', 'system_admin'}
