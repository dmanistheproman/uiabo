import assert from 'node:assert/strict';
import test from 'node:test';
import { imageInputError,
  confirmedImageFailure, deleteAfterVerification } from '../src/utils/inputFlows.js';

test('image checks reject unsupported or oversized selections before uploading', () => {
  const valid = { uri: 'file:///photo.jpg', mimeType: 'image/jpeg', fileSize: 1024, width: 1000, height: 1000 };
  assert.equal(imageInputError(valid), '');
  assert.equal(imageInputError({ uri: 'file:///photo.PNG' }), '');
  assert.match(imageInputError(null), /Choose an image/);
  assert.match(imageInputError({ ...valid, mimeType: 'image/heic' }), /PNG or JPEG/);
  assert.match(imageInputError({ ...valid, fileSize: 10485761 }), /10 MB/);
  assert.match(imageInputError({ ...valid, width: 6000, height: 6000 }), /25 megapixels/);
});

test('retry key is reset for confirmed image failures but retained for ambiguous saves', () => {
  for (const code of ['IMAGE_ANALYSIS_FAILED', 'IMAGE_CONTEXT_ANALYSIS_FAILED', 'IMAGE_ANALYSIS_TIMEOUT', 'IMAGE_ANALYSIS_BUSY']) assert.ok(confirmedImageFailure(code));
  for (const code of [undefined, 'RESULT_STORAGE_UNAVAILABLE', 'ANALYSIS_IN_PROGRESS']) assert.equal(confirmedImageFailure(code), false);
});

function deletionFlow(overrides = {}) {
  const calls = [];
  return { calls, options: {
    password: 'test-password',
    verify: async password => { calls.push(['verify', password]); },
    requestDeletion: async () => { calls.push('request'); return { status: 'pending' }; },
    onAccepted: () => calls.push('accepted'),
    logout: async () => { calls.push('logout'); }, ...overrides,
  } };
}

test('deletion verifies identity, requests deletion, locks the session then signs out', async () => {
  const { calls, options } = deletionFlow();
  assert.deepEqual(await deleteAfterVerification(options), { status: 'pending' });
  assert.deepEqual(calls, [['verify', 'test-password'], 'request', 'accepted', 'logout']);
});

test('missing or incorrect password cannot request deletion or sign out', async () => {
  const missing = deletionFlow({ password: '' });
  await assert.rejects(deleteAfterVerification(missing.options), /current password/);
  assert.deepEqual(missing.calls, []);
  const incorrect = deletionFlow({ verify: async () => { throw new Error('Incorrect password'); } });
  await assert.rejects(deleteAfterVerification(incorrect.options), /Incorrect password/);
  assert.deepEqual(incorrect.calls, []);
});

test('rejected, interrupted or unconfirmed deletion never claims acceptance or signs out', async () => {
  for (const requestDeletion of [async () => { throw new Error('network interrupted'); }, async () => null, async () => ({ status: 'unknown' })]) {
    const { calls, options } = deletionFlow({ requestDeletion });
    await assert.rejects(deleteAfterVerification(options));
    assert.deepEqual(calls, [['verify', 'test-password']]);
  }
});

test('a sign-out failure after acceptance still reports deletion as accepted', async () => {
  const { calls, options } = deletionFlow({ logout: async () => { throw new Error('offline'); } });
  assert.equal((await deleteAfterVerification(options)).status, 'pending');
  assert.deepEqual(calls, [['verify', 'test-password'], 'request', 'accepted']);
});
