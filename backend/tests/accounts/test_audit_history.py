from datetime import datetime, timedelta, timezone
from hashlib import sha256
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.accounts.audit_history import AuditHistory, AuditPage, audit_window, decode_cursor, event_action, public_event, get_audit_history
from app.accounts.repository import InMemoryAccountRepository, get_account_repository
from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.main import app

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def record(index, path='/admin/users', **extra):
    return {'started_at': NOW - timedelta(seconds=index), 'method': 'GET', 'path': path,
            'outcome': 'succeeded', **extra}


def test_actions_and_private_fields_are_not_exposed():
    mask = sha256(b'admin').hexdigest()[:16]
    event = record(0, '/admin/users/{user_id}/roles', method='PATCH', actor_mask=mask,
        actor_uid='must-not-leak', token='secret', raw_body={'password': 'secret'},
        action_details={'reason': 'Team change', 'before': [], 'after': ['system_admin'], 'password': 'secret'})
    view = public_event('event', event, {mask: {'name': 'Administrator', 'email': 'admin@example.org'}})
    assert view.action == 'change_roles' and view.actor_name == 'Administrator'
    assert 'secret' not in view.model_dump_json() and 'must-not-leak' not in view.model_dump_json()
    assert public_event('event', event, {}).actor_name is None
    assert event_action(record(0, '/admin/provision', method='POST')) == 'provision_account'
    assert event_action(record(0, '/admin/audit')) == 'view_audit'


@pytest.mark.parametrize('start,end', [
    (NOW, NOW - timedelta(days=1)), (NOW - timedelta(days=32), NOW),
    (NOW.replace(tzinfo=None), NOW),
])
def test_invalid_date_windows_are_rejected(start, end):
    with pytest.raises(HTTPException): audit_window(start, end)


@pytest.mark.parametrize('cursor', ['bad', 'e30=', 'eyJpZCI6Ii4uL3VzZXJzL2FkbWluIiwiYXQiOiIyMDI2LTExLTAyIn0='])
def test_malformed_cursors_are_rejected(cursor):
    with pytest.raises(HTTPException): decode_cursor(cursor)


class Snapshot:
    def __init__(self, key, data): self.id, self.data = key, data
    def to_dict(self): return self.data


class Query:
    def __init__(self, snapshots):
        self.snapshots, self.bound, self.filters, self.cursor = snapshots, None, [], None
    def document(self, key): return SimpleNamespace(id=key)
    def select(self, fields): return self
    def where(self, *, filter): self.filters.append(filter); return self
    def order_by(self, *args, **kwargs): return self
    def limit(self, size): self.bound = size; return self
    def start_after(self, values): self.cursor = values; return self
    def stream(self):
        items = self.snapshots
        if self.filters:
            items = sorted(items, key=lambda item: (item.data['started_at'], item.id), reverse=True)
            for condition in self.filters:
                items = [item for item in items if (item.data['started_at'] >= condition.value
                    if condition.op_string == '>=' else item.data['started_at'] <= condition.value)]
        if self.cursor:
            items = [item for item in items if (item.data['started_at'], item.id) <
                     (self.cursor['started_at'], self.cursor['__name__'].id)]
        return iter(items[:self.bound] if self.bound else items)


def reader(events, users=None):
    return AuditHistory(SimpleNamespace(collection=lambda name: Query(
        [Snapshot(key, value) for key, value in (events if name == 'operational_audit' else users or {}).items()])))


def test_pagination_crosses_unmatched_rows_and_resolves_current_accounts():
    mask = sha256(b'admin').hexdigest()[:16]
    events = {f'event-{i:03}': record(i, '/admin/provision' if i >= 300 else '/admin/users',
        actor_mask=mask, method='POST' if i >= 300 else 'GET') for i in range(325)}
    history = reader(events, {'admin': {'name': 'Admin', 'email': 'admin@example.org'}})
    params = dict(from_time=NOW-timedelta(days=1), to_time=NOW, action='provision_account', limit=10)
    page = history.list_events(**params)
    assert page.items == [] and page.scanned == 300 and page.next_cursor
    ids = []
    while page.next_cursor:
        page = history.list_events(**params, cursor=page.next_cursor)
        ids.extend(item.event_id for item in page.items)
        assert all(item.actor_email == 'admin@example.org' for item in page.items)
    assert ids == [f'event-{i:03}' for i in range(300, 325)]
    assert len(ids) == len(set(ids))


def test_same_timestamp_page_boundaries_and_actor_or_target_filter():
    mask = sha256(b'target').hexdigest()[:16]
    events = {'a': record(0, target_mask=mask), 'b': record(0, actor_mask=mask), 'c': record(0, actor_mask='different')}
    history = reader(events)
    params = dict(from_time=NOW-timedelta(days=1), to_time=NOW, user_id='target', limit=1)
    first = history.list_events(**params)
    second = history.list_events(**params, cursor=first.next_cursor)
    assert [first.items[0].event_id, second.items[0].event_id] == ['b', 'a']
    assert second.next_cursor is None


def test_audit_endpoint_validates_filters_and_reports_service_failure():
    repo = InMemoryAccountRepository(clock=lambda: NOW)
    user = AuthenticatedUser(uid='admin', email='admin@example.org', email_verified=True)
    repo.ensure_staff_profile(user, 'Admin')
    repo.profiles[user.uid]['operational_roles'] = ['system_admin']
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_account_repository] = lambda: repo
    queries = []
    class History:
        def list_events(self, **params): queries.append(params); return AuditPage(items=[], scanned=0)
    app.dependency_overrides[get_audit_history] = History
    try:
        with TestClient(app) as client:
            assert client.get('/admin/audit?action=change_roles&user_id=target').status_code == 200
            assert queries[0]['action'] == 'change_roles'
            assert client.get('/admin/audit?outcome=unknown').status_code == 422
            assert client.get('/admin/audit?action=unknown').status_code == 422
            assert client.get('/admin/audit?limit=1000').status_code == 422
            assert client.get('/admin/audit?from_time=2026-01-01T00:00:00Z&to_time=2026-11-02T00:00:00Z').status_code == 422
            class Offline:
                def list_events(self, **params): raise RuntimeError('secret database details')
            app.dependency_overrides[get_audit_history] = Offline
            failed = client.get('/admin/audit')
            assert failed.status_code == 503 and 'secret' not in failed.text
    finally: app.dependency_overrides.clear()
