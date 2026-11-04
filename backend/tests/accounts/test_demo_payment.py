from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.accounts.demo_payment import complete_demo_payment
from app.accounts.repository import InMemoryAccountRepository
from app.main import app

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


@pytest.fixture
def checkout(signed_analysis, monkeypatch):
    monkeypatch.setenv('DEMO_PAYMENTS_ENABLED', '1')
    store, identity = signed_analysis
    store.clock = lambda: NOW
    user = identity['user']
    accounts = InMemoryAccountRepository(clock=lambda: NOW)
    accounts.ensure_free_profile(user, 'Test User')
    store.documents['users', user.uid] = deepcopy(accounts.profiles[user.uid])
    store.documents['usage_allowances', user.uid] = deepcopy(accounts.allowances[user.uid])
    return store, identity, TestClient(app)


def test_checkout_grants_premium_and_one_durable_zero_charge_receipt(checkout):
    store, identity, client = checkout
    uid = identity['user'].uid
    before = deepcopy(store.documents['users', uid])
    response = client.post('/account/demo-payment', json={'confirm_demo': True})
    assert response.status_code == 200
    body = response.json()
    assert body['profile']['uid'] == uid and body['profile']['role'] == 'premium'
    assert body['profile']['allowance']['remaining_submissions'] == 60
    assert body['amount_charged'] == 0 and body['mode'] == 'demo'
    assert store.documents['demo_payments', uid]['receipt_id'] == body['receipt_id']
    assert store.documents['users', uid]['created_at'] == before['created_at']
    assert store.documents['users', uid].get('operational_roles', []) == before.get('operational_roles', [])


def test_retries_and_parallel_requests_do_not_reset_allowance(checkout):
    store, identity, client = checkout
    uid = identity['user'].uid
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: complete_demo_payment(store, uid), range(4)))
    assert sum(item.status == 'upgraded' for item in responses) == 1
    assert len({item.receipt_id for item in responses}) == 1
    store.documents['usage_allowances', uid].update(successful_submissions=7, remaining_submissions=53)
    body = client.post('/account/demo-payment', json={'confirm_demo': True}).json()
    assert body['status'] == 'already_premium'
    assert body['profile']['allowance']['remaining_submissions'] == 53
    assert store.documents['usage_allowances', uid]['remaining_submissions'] == 53


@pytest.mark.parametrize('body', [{}, {'confirm_demo': False}, {'confirm_demo': True, 'uid': 'other'},
                                 {'confirm_demo': True, 'card_number': 'never-accept'}, {'confirm_demo': True, 'role': 'system_admin'}])
def test_checkout_rejects_missing_consent_or_extra_fields(checkout, body):
    store, identity, client = checkout
    assert client.post('/account/demo-payment', json=body).status_code == 422
    assert store.documents['users', identity['user'].uid]['role'] == 'free'


@pytest.mark.parametrize('case', ['staff', 'suspended', 'deactivated', 'unverified', 'deleting', 'checking'])
def test_ineligible_accounts_cannot_upgrade(checkout, case):
    store, identity, client = checkout
    uid = identity['user'].uid
    profile = store.documents['users', uid]
    if case == 'staff': profile.update(account_type='staff', role='premium')
    elif case in {'suspended', 'deactivated'}: profile['account_status'] = case
    elif case == 'unverified': identity['user'] = identity['user'].model_copy(update={'email_verified': False})
    elif case == 'deleting': store.documents['account_deletions', uid] = {'status': 'pending'}
    elif case == 'checking': store.documents['analysis_locks', uid] = {'expires_at': NOW + timedelta(minutes=1)}
    before = deepcopy(store.documents)
    assert client.post('/account/demo-payment', json={'confirm_demo': True}).status_code in {403, 409}
    assert store.documents == before


def test_disabled_checkout_and_cancel_do_not_change_account(checkout, monkeypatch):
    store, identity, client = checkout
    before = deepcopy(store.documents)
    # Reviewing/cancelling checkout is read-only.
    assert client.get('/account/demo-payment').json()['enabled'] is True
    assert store.documents == before
    monkeypatch.delenv('DEMO_PAYMENTS_ENABLED', raising=False)
    assert client.get('/account/demo-payment').json()['enabled'] is False
    assert client.post('/account/demo-payment', json={'confirm_demo': True}).status_code == 503
    assert store.documents == before


def test_transaction_failure_does_not_grant_partial_premium(checkout, monkeypatch):
    from app.analyses.store import MemorySession
    store, identity, client = checkout
    before = deepcopy(store.documents)
    real_set = MemorySession.set
    def fail_receipt(self, collection, key, value):
        if collection == 'demo_payments': raise RuntimeError('private storage details')
        real_set(self, collection, key, value)
    monkeypatch.setattr(MemorySession, 'set', fail_receipt)
    response = client.post('/account/demo-payment', json={'confirm_demo': True})
    assert response.status_code == 503 and 'private storage' not in response.text
    assert store.documents == before


def test_no_token_cannot_upgrade():
    response = TestClient(app).post('/account/demo-payment', json={'confirm_demo': True})
    assert response.status_code == 401
