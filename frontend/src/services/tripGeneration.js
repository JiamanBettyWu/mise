import { api } from './api.js';
import { createRequestStore } from './requestStore.js';

// Trip packing-plan store (see requestStore.js for the nav-survival
// rationale). Matters more here than on Today: the trip LangGraph pipeline
// (weather → catalog → reasoning → gap queries → SerpAPI) runs long enough
// that tabbing away mid-plan is tempting. Snapshot: { loading, error, result }.

const store = createRequestStore(async (payload) => {
  const result = await api.planTrip(payload);
  return { result };
});

export const { subscribe, getSnapshot, consumeResult, clearError } = store;
export const startPlanning = store.start;
