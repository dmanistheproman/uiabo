import assert from 'node:assert/strict';
import test from 'node:test';
import { storedPortalChoice, portalRoles, validatePortalSession } from '../src/utils/portalAccess.js';

test('both permissions are available only on staff accounts', () => {
  assert.deepEqual(portalRoles({ role: 'staff', account_type: 'staff', operational_roles: ['data_engineer', 'system_admin'] }), ['data_engineer', 'system_admin']);
  assert.deepEqual(portalRoles({ role: 'premium', operational_roles: ['system_admin'] }), []);
  assert.deepEqual(portalRoles({ role: 'system_admin', account_type: 'app' }), []);
  assert.deepEqual(portalRoles({ role: 'system_admin' }), ['system_admin']);
  assert.deepEqual(portalRoles({ role: 'system_admin', operational_roles: [] }), []);
  assert.deepEqual(portalRoles({ role: 'free', operational_roles: 'system_admin' }), []);
});

test('portal choice is a per-tab preference and invalid storage does not become a role', () => {
  assert.equal(storedPortalChoice({ getItem: () => 'system_admin' }), 'system_admin');
  assert.equal(storedPortalChoice({ getItem: () => 'super_admin' }), 'data_engineer');
  assert.equal(storedPortalChoice({ getItem: () => { throw Error('blocked'); } }), 'data_engineer');
});

test('a verified server response must match the account and chosen portal', () => {
  const session = { portal_role: 'system_admin', profile: { uid: 'a', account_status: 'active', role: 'staff', account_type: 'staff', operational_roles: ['data_engineer', 'system_admin'] } };
  assert.equal(validatePortalSession(session, 'a', 'system_admin'), session);
  assert.throws(() => validatePortalSession(session, 'b', 'system_admin'));
  assert.throws(() => validatePortalSession(session, 'a', 'data_engineer'));
  assert.throws(() => validatePortalSession(null, 'a', 'system_admin'));
  assert.throws(() => validatePortalSession({ ...session, profile: { ...session.profile, account_status: 'suspended' } }, 'a', 'system_admin'));
  assert.throws(() => validatePortalSession({ ...session, profile: { ...session.profile, operational_roles: ['data_engineer'] } }, 'a', 'system_admin'));
});
