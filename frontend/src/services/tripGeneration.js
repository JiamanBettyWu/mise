import { api } from './api.js';
import { createStreamRequestStore } from './requestStore.js';

// Trip packing-plan store (see requestStore.js for the nav-survival
// rationale, and the streaming-variant comment for the snapshot shape).
// Matters more here than on Today: the trip LangGraph pipeline (weather →
// catalog → reasoning → gap queries → SerpAPI) runs long enough that tabbing
// away mid-plan is tempting, and #124 streams node progress so the plan
// renders as soon as reasoning finishes instead of staring at one spinner
// for the whole pipeline. Snapshot: { loading, stage, plan, purchases, error }.

const store = createStreamRequestStore((payload, onEvent) => api.planTripStream(payload, onEvent));

export const { subscribe, getSnapshot, consumePlan, clearError } = store;
export const startPlanning = store.start;
