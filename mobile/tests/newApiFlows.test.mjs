import assert from 'node:assert/strict';
import test from 'node:test';
import { registerHooks } from 'node:module';

// Exercise the actual API adapter; only the native file binding and transport
// are replaced. No Firebase account, provider call or deletion is performed.
registerHooks({ resolve(specifier, context, next) {
  if (specifier === 'expo-file-system') return { shortCircuit: true, url: 'data:text/javascript,' + encodeURIComponent(
    'export class File extends Blob { constructor(uri) { super(["test-image"], {type:"image/png"}); this.name="photo.png"; } }') };
  return next(specifier, context);
} });
const api = await import('../src/services/api.js');
const originalFileReader = globalThis.FileReader;
// Stand in only for the native blob-to-data-URL binding; exercise the real
// authenticated fetch, response validation and error handling below.
globalThis.FileReader = class {
  readAsDataURL(blob) {
    blob.arrayBuffer().then(bytes => {
      this.result = `data:${blob.type};base64,${Buffer.from(bytes).toString('base64')}`;
      this.onload();
    }).catch(() => this.onerror());
  }
};
test.after(() => { globalThis.FileReader = originalFileReader; });
let requests = [];
let tokens = [];
const user = { getIdToken: async force => { tokens.push(force); return 'fake-test-token'; } };
test.beforeEach(() => {
  requests = []; tokens = [];
  globalThis.fetch = async (url, options) => { requests.push({ url, ...options }); return { ok: true, json: async () => ({ status: 'pending' }) }; };
});

test('text checks retain the normal text and OCR provenance', async () => {
  await api.checkText(user, 'Copied claim', 'check-1');
  await api.checkText(user, 'Reviewed image text', 'check-2', 'ocr');
  assert.ok(requests[0].url.endsWith('/analysis/text'));
  assert.deepEqual(JSON.parse(requests[0].body), { text: 'Copied claim', input_source: 'text' });
  assert.deepEqual(JSON.parse(requests[1].body), { text: 'Reviewed image text', input_source: 'ocr' });
  assert.equal(requests[0].headers['Idempotency-Key'], 'check-1');
  assert.equal(requests[0].timeout, undefined, 'internal timeout options are not passed to fetch');
});

test('image-context multipart sends an explicit caption or omits it for OCR extraction', async () => {
  await api.checkImageContext(user, { uri: 'file:///photo.png', fileName: 'photo.png' }, 'image-1', '  A caption  ');
  await api.checkImageContext(user, { uri: 'file:///photo.png' }, 'image-2', '  ');
  assert.equal(requests[0].body.get('caption'), 'A caption');
  assert.equal(requests[0].body.get('filename'), 'photo.png');
  assert.ok(requests[0].body.get('image') instanceof Blob);
  assert.equal(requests[0].headers['Content-Type'], undefined, 'fetch must create the multipart boundary');
  assert.equal(requests[0].headers['Idempotency-Key'], 'image-1');
  assert.equal(requests[1].body.has('caption'), false);
});

test('account deletion sends only a refreshed token, without password or client user ID', async () => {
  await api.requestAccountDeletion(user);
  assert.ok(requests[0].url.endsWith('/account/me'));
  assert.equal(requests[0].method, 'DELETE');
  assert.equal(requests[0].body, undefined);
  assert.deepEqual(tokens, [true]);
});

test('demo checkout sends explicit consent with no card details, user ID or client-selected plan', async () => {
  await api.getDemoPaymentOffer(user);
  await api.completeDemoPayment(user);
  assert.ok(requests[0].url.endsWith('/account/demo-payment'));
  assert.equal(requests[0].body, undefined);
  assert.equal(requests[1].method, 'POST');
  assert.deepEqual(JSON.parse(requests[1].body), { confirm_demo: true });
  assert.deepEqual(tokens, [true, true]);
});

test('reports use the owned result ID and preserve duplicate-report errors for recovery', async () => {
  await api.reportResult(user, 'abc', 'wrong_label', 'The image looks authentic.');
  assert.ok(requests[0].url.endsWith('/analysis/results/abc/report'));
  assert.deepEqual(JSON.parse(requests[0].body), { reason: 'wrong_label', detail: 'The image looks authentic.' });
  globalThis.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: { error_code: 'ALREADY_REPORTED', message: 'Already under review' } }) });
  await assert.rejects(api.reportResult(user, 'abc', 'wrong_label', 'Retry'), error => error.code === 'ALREADY_REPORTED');
});

test('saved images fetch private bytes with a refreshed token, then display without a second network request', async () => {
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
  const blob = new Blob([png], { type: 'image/png' });
  let closed = false;
  blob.close = () => { closed = true; };
  globalThis.fetch = async (url, options) => {
    requests.push({ url, ...options });
    return { ok: true, blob: async () => blob, json: async () => { throw new Error('Images are not JSON'); } };
  };
  const source = await api.savedImageSource(user, 'saved-result');
  assert.equal(requests.length, 1);
  assert.ok(requests[0].url.endsWith('/analysis/results/saved-result/image'));
  assert.equal(requests[0].headers.Authorization, 'Bearer fake-test-token');
  assert.equal(requests[0].responseType, undefined);
  assert.equal(source.uri, `data:image/png;base64,${png.toString('base64')}`);
  assert.deepEqual(Object.keys(source), ['uri']);
  assert.equal(JSON.stringify(source).includes('fake-test-token'), false);
  assert.deepEqual(tokens, [true]);
  assert.equal(closed, true, 'release native blob memory after conversion');
});

test('saved image authentication and missing-image errors remain recoverable API errors', async () => {
  for (const [status, code, message] of [[401, 'AUTHENTICATION_REQUIRED', 'Please log in again.'], [404, undefined, 'The saved image is no longer available.']]) {
    globalThis.fetch = async () => ({ ok: false, status, json: async () => ({ detail: code ? { error_code: code, message } : message }), blob: async () => { throw new Error('Do not display error responses'); } });
    await assert.rejects(api.savedImageSource(user, 'saved-result'), error => error.status === status && error.code === code && error.message === message);
  }
});

test('saved image rejects unexpected content and oversized or empty downloads', async () => {
  for (const blob of [new Blob(['error'], { type: 'text/html' }), new Blob([], { type: 'image/png' }), { type: 'image/jpeg', size: 10 * 1024 * 1024 + 1 }]) {
    let closed = false;
    blob.close = () => { closed = true; };
    globalThis.fetch = async () => ({ ok: true, blob: async () => blob });
    await assert.rejects(api.savedImageSource(user, 'saved-result'), /supported saved image/);
    assert.equal(closed, true);
  }
});

test('saved image reports an interrupted download and releases failed blob reads', async () => {
  globalThis.fetch = async () => ({ ok: true, blob: async () => { throw new DOMException('aborted', 'AbortError'); } });
  await assert.rejects(api.savedImageSource(user, 'saved-result'), /Loading the saved image took too long/);
  let closed = false;
  const blob = { type: 'image/png', size: 5, arrayBuffer: async () => { throw new Error('Cannot read'); }, close: () => { closed = true; } };
  globalThis.fetch = async () => ({ ok: true, blob: async () => blob });
  await assert.rejects(api.savedImageSource(user, 'saved-result'), /could not be read/);
  assert.equal(closed, true);
});

test('API errors retain status and error code for recovery and meaningful messages', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: { error_code: 'ANALYSIS_IN_PROGRESS', message: 'Wait for your check to finish.' } }) });
  await assert.rejects(api.requestAccountDeletion(user), error => error.status === 409 && error.code === 'ANALYSIS_IN_PROGRESS' && /Wait/.test(error.message));
});

test('deletion timeout does not falsely report that the request was rejected', async () => {
  globalThis.fetch = async () => { throw new DOMException('aborted', 'AbortError'); };
  await assert.rejects(api.requestAccountDeletion(user), /could not confirm whether deletion was requested/);
});
