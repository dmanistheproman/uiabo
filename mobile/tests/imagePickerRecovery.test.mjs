import assert from 'node:assert/strict';
import test from 'node:test';
import { registerHooks } from 'node:module';

let saved = null;
let selection = { canceled: false, assets: [{ uri: 'file:///photo.png' }] };
globalThis.pickerTest = {
  storage: { getItem: async () => saved, setItem: async (_, value) => { saved = value; }, removeItem: async () => { saved = null; } },
  launch: async () => selection,
  pending: async () => selection,
};
const modules = {
  '@react-native-async-storage/async-storage': 'export default globalThis.pickerTest.storage;',
  'expo-image-picker': 'export const launchImageLibraryAsync = (...args) => globalThis.pickerTest.launch(...args); export const getPendingResultAsync = (...args) => globalThis.pickerTest.pending(...args);',
  'react-native': 'export const Platform = { OS: "android" };',
};
registerHooks({ resolve(specifier, context, next) {
  if (modules[specifier]) return { shortCircuit: true, url: 'data:text/javascript,' + encodeURIComponent(modules[specifier]) };
  return next(specifier, context);
} });
const { chooseImageFor, recoverImageSelection } = await import('../src/services/imagePicker.js');

test('each picker records its destination and clears it after a normal return', async () => {
  for (const page of ['ocr', 'imageContext', 'deepfakeAI']) {
    globalThis.pickerTest.launch = async () => { assert.equal(JSON.parse(saved).page, page); return selection; };
    assert.equal(await chooseImageFor('test-user', page, {}), selection);
    assert.equal(saved, null);
  }
});

test('recovered selections return to the originating feature, not always OCR', async () => {
  for (const page of ['ocr', 'imageContext', 'deepfakeAI']) {
    saved = JSON.stringify({ userId: 'test-user', page, at: Date.now() });
    assert.deepEqual(await recoverImageSelection('test-user'), { page, selection });
    assert.equal(saved, null);
  }
});

test('recovery ignores another account, stale, invalid and cancelled selections', async () => {
  for (const intent of [
    { userId: 'different-user', page: 'imageContext', at: Date.now() },
    { userId: 'test-user', page: 'imageContext', at: Date.now() - 600001 },
    { userId: 'test-user', page: 'unknown', at: Date.now() },
    { userId: 'test-user', page: 'imageContext' },
  ]) {
    saved = JSON.stringify(intent);
    assert.equal(await recoverImageSelection('test-user'), null);
  }
  selection = { canceled: true };
  saved = JSON.stringify({ userId: 'test-user', page: 'deepfakeAI', at: Date.now() });
  assert.equal(await recoverImageSelection('test-user'), null);
});
