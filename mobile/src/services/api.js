const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8000').replace(/\/$/, '');

async function accountRequest(path, user, options = {}) {
  const token = await user.getIdToken(true);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeout || 20000);
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('The request is taking longer than expected. Open Results before retrying; your check may have finished.');
    }
    throw new Error(
      'Cannot reach UIABO. Check your connection and try again.',
    );
  } finally {
    clearTimeout(timeout);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      (typeof detail === 'object' && detail?.message) ||
      (typeof detail === 'string' && detail) ||
      'The UIABO server could not complete this request.';
    const error = new Error(message);
    error.status = response.status;
    error.code = detail?.error_code;
    throw error;
  }
  return data;
}

export function ensureProfile(user, name) {
  return accountRequest('/account/me', user, {
    body: JSON.stringify({ name }),
    method: 'PUT',
  });
}

export function getProfile(user) {
  return accountRequest('/account/me', user);
}

export function checkText(user, text, requestKey) {
  return accountRequest('/analysis/text', user, {
    // Claim (90s), retrieval (65s), assessment (65s), plus transport/storage.
    method: 'POST', body: JSON.stringify({ text }), timeout: 240000,
    headers: { 'Idempotency-Key': requestKey },
  });
}

export function getResults(user, cursor) {
  return accountRequest(`/analysis/results${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`, user);
}

export function getResult(user, resultId) {
  return accountRequest(`/analysis/results/${encodeURIComponent(resultId)}`, user);
}

export { API_URL };
