const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8000').replace(/\/$/, '');

async function accountRequest(path, user, options = {}) {
  const token = await user.getIdToken(true);
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
  } catch {
    throw new Error(
      'Cannot reach the UIABO server. Check that the backend is running and EXPO_PUBLIC_API_URL is correct.',
    );
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

export { API_URL };
