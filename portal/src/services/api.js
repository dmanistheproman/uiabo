const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

async function request(path, user, options = {}) {
  const token = await user.getIdToken(true);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeout || 30000);
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
      throw new Error('The request timed out. Please retry.');
    }
    throw new Error('Cannot reach the UIABO backend. Is uvicorn running?');
  } finally {
    clearTimeout(timeout);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      (typeof detail === 'object' && detail?.message) ||
      (typeof detail === 'string' && detail) ||
      'The UIABO backend could not complete this request.';
    const error = new Error(message);
    error.status = response.status;
    error.code = detail?.error_code;
    throw error;
  }
  return data;
}

function qs(params) {
  const query = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value);
  });
  const text = query.toString();
  return text ? `?${text}` : '';
}

export function ensureProfile(user, name) {
  return request('/account/me', user, { body: JSON.stringify({ name }), method: 'PUT' });
}

export function getProfile(user) {
  return request('/account/me', user);
}

export const getReportSummary = (user, params) =>
  request(`/portal/reports/summary${qs(params)}`, user);

export const listReports = (user, params) =>
  request(`/portal/reports${qs(params)}`, user);

export const getReport = (user, reportId) =>
  request(`/portal/reports/${encodeURIComponent(reportId)}`, user);

export const updateReport = (user, reportId, body) =>
  request(`/portal/reports/${encodeURIComponent(reportId)}`, user, {
    method: 'PATCH', body: JSON.stringify(body),
  });

export const listRuns = (user, params) =>
  request(`/portal/runs${qs(params)}`, user);

export const getRunSummary = (user, params) =>
  request(`/portal/runs/summary${qs(params)}`, user);

export const getRun = (user, runId) =>
  request(`/portal/runs/${encodeURIComponent(runId)}`, user);

export const listIngestionRuns = (user, params) =>
  request(`/portal/ingestion-runs${qs(params)}`, user);

export const getIngestionRun = (user, runId) =>
  request(`/portal/ingestion-runs/${encodeURIComponent(runId)}`, user);

export const triggerIngestionJob = (user, job) =>
  request(`/portal/ingestion-jobs/${encodeURIComponent(job)}/run`, user, { method: 'POST' });

export const addFollowUp = (user, runId, note) =>
  request(`/portal/ingestion-runs/${encodeURIComponent(runId)}/follow-up`, user, {
    method: 'POST', body: JSON.stringify({ note }),
  });
