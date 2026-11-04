export function imageInputError(asset) {
  if (!asset?.uri) return 'Choose an image first.';
  const mime = (asset.mimeType || '').toLowerCase();
  const name = (asset.fileName || asset.uri).split('?')[0];
  if (mime ? !['image/jpeg', 'image/jpg', 'image/png'].includes(mime) : !/\.(png|jpe?g)$/i.test(name)) {
    return 'Choose a PNG or JPEG image.';
  }
  if (asset.fileSize > 10 * 1024 * 1024) return 'Choose an image smaller than 10 MB.';
  if (asset.width * asset.height > 25000000) return 'Choose an image of at most 25 megapixels.';
  return '';
}

export function confirmedImageFailure(code) {
  return ['IMAGE_CONTEXT_ANALYSIS_FAILED', 'IMAGE_ANALYSIS_FAILED', 'IMAGE_ANALYSIS_TIMEOUT',
    'IMAGE_ANALYSIS_BUSY', 'PREVIOUS_ANALYSIS_FAILED', 'ANALYSIS_EXPIRED', 'REQUEST_KEY_REUSED'].includes(code);
}

export async function deleteAfterVerification({ password, verify, requestDeletion, onAccepted, logout }) {
  if (!password) throw new Error('Enter your current password to confirm it is you.');
  await verify(password);
  const result = await requestDeletion();
  if (result?.status !== 'pending') throw new Error('The deletion request could not be confirmed. Please retry.');
  // Show acceptance before signing out; a sign-out failure must never suggest
  // that an already accepted deletion failed or that it should be cancelled.
  onAccepted();
  try { await logout(); } catch { /* The accepted screen remains locked with a sign-out retry. */ }
  return result;
}
