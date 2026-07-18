import { api } from './api.js';
import { getCurrentPosition } from './geo.js';
import { createRequestStore } from './requestStore.js';

// Today generation store (see requestStore.js for the nav-survival rationale).
// Snapshot: { loading, error, result, stage, usingMyLocation }.

let coords = null; // cached across generations (was coordsRef)

const store = createRequestStore(async ({ travelMode, notes }, progress) => {
  coords = coords || (await getCurrentPosition());
  // One outfit, not three (#145): with the Refine composer, iterating on a
  // single pick beats scanning alternatives — and it's a third the latency.
  // Streamed (#154): progress frames update the stage line; the result
  // arrives in its own frame, so the resolved shape is unchanged.
  let result = null;
  let errDetail = null;
  await api.recommendStream(
    {
      travel_mode: travelMode,
      notes,
      n: 1,
      lat: coords?.lat ?? null,
      lon: coords?.lon ?? null,
    },
    (event, payload) => {
      if (event === 'progress') progress({ stage: payload.stage });
      else if (event === 'result') result = payload;
      else if (event === 'error') errDetail = payload.detail;
    }
  );
  if (!result) throw new Error(errDetail || 'Recommendation failed');
  return { result, usingMyLocation: !!coords };
});

export const { subscribe, getSnapshot, consumeResult, clearError } = store;
export const startGeneration = store.start;
