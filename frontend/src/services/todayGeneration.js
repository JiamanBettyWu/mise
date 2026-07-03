import { api } from './api.js';
import { getCurrentPosition } from './geo.js';

// Module-scope store for the Today generation request, so an in-flight
// generation survives SPA navigation (react-router unmounts TodayOutfit on
// nav; component state and effects die with it, but this module — and the
// fetch it started — keep running). The page subscribes via
// useSyncExternalStore and consumes `result` when it lands. A full page
// reload still kills the request — the browser aborts the fetch itself.

let snapshot = { loading: false, error: '', result: null, usingMyLocation: false };
const listeners = new Set();
let coords = null; // cached across generations (was coordsRef)

function emit(patch) {
  snapshot = { ...snapshot, ...patch };
  listeners.forEach((fn) => fn());
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getSnapshot() {
  return snapshot;
}

export async function startGeneration({ travelMode, notes }) {
  if (snapshot.loading) return;
  emit({ loading: true, error: '', result: null });
  try {
    coords = coords || (await getCurrentPosition());
    const result = await api.recommend({
      travel_mode: travelMode,
      notes,
      n: 3,
      lat: coords?.lat ?? null,
      lon: coords?.lon ?? null,
    });
    emit({ loading: false, result, usingMyLocation: !!coords });
  } catch (e) {
    emit({ loading: false, error: String(e) });
  }
}

// The page takes ownership of the result (into its own state + localStorage);
// clearing it here keeps a later remount from re-applying a stale outfit.
export function consumeResult() {
  emit({ result: null });
}

export function clearError() {
  emit({ error: '' });
}
