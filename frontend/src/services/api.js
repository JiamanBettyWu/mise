const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const PASSWORD_KEY = 'wardrobe_app_password';

export function getStoredPassword() {
  return localStorage.getItem(PASSWORD_KEY) || '';
}

export function setStoredPassword(pw) {
  if (pw) localStorage.setItem(PASSWORD_KEY, pw);
  else localStorage.removeItem(PASSWORD_KEY);
}

// Builds the auth/JSON headers, fetches, and throws on a non-ok response —
// shared by request() (which parses JSON) and planTripStream (which reads
// the body as an SSE stream instead), so the auth/error contract has one
// implementation.
async function rawRequest(path, { method = 'GET', body, headers = {}, auth = true, signal } = {}) {
  const finalHeaders = { ...headers };
  if (auth) finalHeaders['X-App-Password'] = getStoredPassword();
  if (body && !(body instanceof FormData)) {
    finalHeaders['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE_URL}${path}`, { method, headers: finalHeaders, body, signal });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res;
}

async function request(path, opts = {}) {
  const res = await rawRequest(path, opts);
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  health: () => request('/health', { auth: false }),
  healthAuth: () => request('/health/auth'),

  uploadAndTag: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return request('/clothes/upload', { method: 'POST', body: fd });
  },
  // Multi-item tagging (#24): one photo, N tag suggestions sharing its URL.
  uploadAndTagMulti: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return request('/clothes/upload-multi', { method: 'POST', body: fd });
  },
  createClothing: (item) => request('/clothes', { method: 'POST', body: item }),
  listClothing: (params = {}) => {
    const q = new URLSearchParams();
    if (params.available !== undefined) q.set('available', params.available);
    if (params.in_travel_bag !== undefined) q.set('in_travel_bag', params.in_travel_bag);
    const qs = q.toString();
    return request(`/clothes${qs ? `?${qs}` : ''}`);
  },
  patchClothing: (id, patch) => request(`/clothes/${id}`, { method: 'PATCH', body: patch }),
  deleteClothing: (id) => request(`/clothes/${id}`, { method: 'DELETE' }),

  recommend: ({ travel_mode = false, notes = '', n = 3, lat = null, lon = null } = {}) =>
    request('/outfits/recommend', {
      method: 'POST',
      body: { travel_mode, notes, n, lat, lon },
    }),
  // verdict: 1 = thumbs up, -1 = thumbs down, 0 = clear
  outfitFeedback: (historyId, verdict) =>
    request(`/outfits/${historyId}/feedback`, { method: 'POST', body: { verdict } }),
  // optional 👎 follow-up (#60); payload = { reason, item_ids, note }
  outfitAttribution: (historyId, payload) =>
    request(`/outfits/${historyId}/attribution`, { method: 'POST', body: payload }),

  // Node-progress streaming (#124): SSE frames of `event: <name>\ndata: <json>\n\n`.
  // The non-streaming /trips/plan JSON endpoint still exists server-side (used
  // by tests/eval) but has no frontend caller now that this replaced it.
  // fetch + reader instead of EventSource — EventSource can't send the
  // X-App-Password header. onEvent(name, payload) fires per frame.
  planTripStream: async (
    { destination, start_date, end_date, additional_notes = '', lat = null, lon = null },
    onEvent,
    { signal } = {}
  ) => {
    const res = await rawRequest('/trips/plan/stream', {
      method: 'POST',
      body: { destination, start_date, end_date, additional_notes, lat, lon },
      signal,
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const lines = frame.split('\n');
        const eventLine = lines.find((l) => l.startsWith('event: '));
        const dataLine = lines.find((l) => l.startsWith('data: '));
        if (eventLine && dataLine) {
          onEvent(eventLine.slice('event: '.length), JSON.parse(dataLine.slice('data: '.length)));
        }
      }
    }
  },

  searchGeo: (q, limit = 5) =>
    request(`/geo/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  // Profile
  getProfile: () => request('/profile'),
  updateProfile: (data) => request('/profile', { method: 'PUT', body: data }),

  // Stats (#115); range = '7d' | '30d' | '90d' | 'all'
  getStats: (range = '30d') => request(`/profile/stats?range=${range}`),

  // Preferences
  listPreferences: () => request('/profile/preferences'),
  createPreference: (text) =>
    request('/profile/preferences', { method: 'POST', body: { text } }),
  updatePreference: (id, data) =>
    request(`/profile/preferences/${id}`, { method: 'PATCH', body: data }),
  deletePreference: (id) =>
    request(`/profile/preferences/${id}`, { method: 'DELETE' }),
};
