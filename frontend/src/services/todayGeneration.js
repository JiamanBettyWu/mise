import { api } from './api.js';
import { getCurrentPosition } from './geo.js';
import { createRequestStore } from './requestStore.js';

// Today generation store (see requestStore.js for the nav-survival rationale).
// Snapshot: { loading, error, result, usingMyLocation }.

let coords = null; // cached across generations (was coordsRef)

const store = createRequestStore(async ({ travelMode, notes }) => {
  coords = coords || (await getCurrentPosition());
  const result = await api.recommend({
    travel_mode: travelMode,
    notes,
    n: 3,
    lat: coords?.lat ?? null,
    lon: coords?.lon ?? null,
  });
  return { result, usingMyLocation: !!coords };
});

export const { subscribe, getSnapshot, consumeResult, clearError } = store;
export const startGeneration = store.start;
