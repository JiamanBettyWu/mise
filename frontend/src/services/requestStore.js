// Shared pub-sub scaffold for module-scope stores, so an in-flight generation
// survives SPA navigation (react-router unmounts the page; component state
// and effects die with it, but the module — and the fetch it started — keep
// running). Pages subscribe via useSyncExternalStore. A full page reload
// still kills the request — the browser aborts the fetch itself.
// Both store flavors below build their `start`/`consume*` behavior on top of
// this; only the snapshot shape and event handling differ between them.
function createObservableStore(initialSnapshot) {
  let snapshot = initialSnapshot;
  const listeners = new Set();

  function emit(patch) {
    snapshot = { ...snapshot, ...patch };
    listeners.forEach((fn) => fn());
  }

  return {
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    getSnapshot() {
      return snapshot;
    },
    emit,
  };
}

// `run(args)` is the injected async step: it returns `{ result, ...extra }`,
// where extra fields (e.g. usingMyLocation) are merged into the snapshot
// alongside the result. Extracted from todayGeneration.js for #105.
export function createRequestStore(run) {
  const { subscribe, getSnapshot, emit } = createObservableStore({
    loading: false,
    error: '',
    result: null,
  });

  return {
    subscribe,
    getSnapshot,
    async start(args) {
      if (getSnapshot().loading) return;
      emit({ loading: true, error: '', result: null });
      try {
        const { result, ...extra } = await run(args);
        emit({ loading: false, result, ...extra });
      } catch (e) {
        emit({ loading: false, error: String(e) });
      }
    },
    // The page takes ownership of the result (into its own state +
    // localStorage); clearing it here keeps a later remount from
    // re-applying a stale result.
    consumeResult() {
      emit({ result: null });
    },
    clearError() {
      emit({ error: '' });
    },
  };
}

// Streaming variant (#124): snapshot shape is { loading, stage, plan,
// purchases, error } instead of { loading, error, result } — a generation
// arrives as a sequence of SSE events, not one resolved promise, so the page
// consumes the plan the moment it lands rather than waiting for `done`.
// `loading` stays true until `done` (or a thrown error), matching the old
// result-based store's contract for disabling the submit button mid-request.
//
// `runStream(args, onEvent)` is the injected async step: onEvent(event, payload)
// fires per SSE frame (`progress` | `plan` | `purchases` | `error` | `done`).
export function createStreamRequestStore(runStream) {
  const { subscribe, getSnapshot, emit } = createObservableStore({
    loading: false,
    error: '',
    stage: null,
    plan: null,
    purchases: null,
    done: false,
  });

  return {
    subscribe,
    getSnapshot,
    async start(args) {
      if (getSnapshot().loading) return;
      emit({ loading: true, error: '', stage: null, plan: null, purchases: null, done: false });
      try {
        await runStream(args, (event, payload) => {
          if (event === 'progress') emit({ stage: payload.stage });
          else if (event === 'plan') emit({ plan: payload });
          else if (event === 'purchases') emit({ purchases: payload.purchase_suggestions });
          else if (event === 'error') emit({ error: payload.detail || 'Trip planning failed' });
          else if (event === 'done') emit({ loading: false, done: true });
        });
      } catch (e) {
        emit({ loading: false, error: String(e) });
      }
    },
    // The page takes ownership of plan+purchases (into its own state +
    // localStorage) once `done` fires; clearing them here keeps a later
    // remount from re-applying a stale generation.
    consumePlan() {
      emit({ plan: null, purchases: null, done: false });
    },
    clearError() {
      emit({ error: '' });
    },
  };
}
