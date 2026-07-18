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

// Reads a response body as SSE frames (`event: <name>\ndata: <json>\n\n`),
// firing onEvent(name, payload) per frame. fetch + reader instead of
// EventSource — EventSource can't send the X-App-Password header. Shared by
// the trip (#124), generate, and refine (#154) streams.
async function readSSE(res, onEvent) {
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
}

async function streamRequest(path, body, onEvent, { signal } = {}) {
  const res = await rawRequest(path, { method: 'POST', body, signal });
  await readSSE(res, onEvent);
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

  // SSE (#154): `progress` {stage} frames, then `result` with the full
  // payload, then `done`. The blocking /outfits/recommend endpoint still
  // exists server-side (cron/eval/tests) but has no frontend caller now.
  recommendStream: (
    { travel_mode = false, notes = '', n = 3, lat = null, lon = null } = {},
    onEvent
  ) => streamRequest('/outfits/recommend/stream', { travel_mode, notes, n, lat, lon }, onEvent),
  // verdict: 1 = thumbs up, -1 = thumbs down, 0 = clear
  outfitFeedback: (historyId, verdict) =>
    request(`/outfits/${historyId}/feedback`, { method: 'POST', body: { verdict } }),
  // optional 👎 follow-up (#60); payload = { reason, item_ids, note }
  outfitAttribution: (historyId, payload) =>
    request(`/outfits/${historyId}/attribution`, { method: 'POST', body: payload }),
  // Multi-turn refinement (#145), streamed (#154): `progress` {stage} frames
  // per graph node, then `outfit` with the revised outfit, then `done`.
  // Repeat calls continue the same conversation (thread = history_id).
  outfitRefineStream: (historyId, message, onEvent) =>
    streamRequest(`/outfits/${historyId}/refine/stream`, { message }, onEvent),

  // Node-progress streaming (#124): the non-streaming /trips/plan JSON
  // endpoint still exists server-side (used by tests/eval) but has no
  // frontend caller now that this replaced it.
  planTripStream: (
    { destination, start_date, end_date, additional_notes = '', lat = null, lon = null },
    onEvent,
    { signal } = {}
  ) =>
    streamRequest(
      '/trips/plan/stream',
      { destination, start_date, end_date, additional_notes, lat, lon },
      onEvent,
      { signal }
    ),

  searchGeo: (q, limit = 5) =>
    request(`/geo/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  // Saved trip plans (#128): explicit save only, frozen snapshot.
  saveTrip: (payload) => request('/trips', { method: 'POST', body: payload }),
  listTrips: () => request('/trips'),
  getTrip: (id) => request(`/trips/${id}`),
  // #134: currently just the custom name; "" clears back to the destination fallback.
  updateTrip: (id, patch) => request(`/trips/${id}`, { method: 'PATCH', body: patch }),
  deleteTrip: (id) => request(`/trips/${id}`, { method: 'DELETE' }),

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
