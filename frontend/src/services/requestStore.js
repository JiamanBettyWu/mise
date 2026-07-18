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

// `run(args, progress)` is the injected async step: it returns
// `{ result, ...extra }`, where extra fields (e.g. usingMyLocation) are
// merged into the snapshot alongside the result. Extracted from
// todayGeneration.js for #105. `progress(patch)` (#154) lets run publish
// interim snapshot fields (e.g. { stage }) while still in flight — start
// resets `stage` so a previous run's last stage never leaks into the next.
export function createRequestStore(run) {
  const { subscribe, getSnapshot, emit } = createObservableStore({
    loading: false,
    error: '',
    result: null,
    stage: null,
  });

  return {
    subscribe,
    getSnapshot,
    async start(args) {
      if (getSnapshot().loading) return;
      emit({ loading: true, error: '', result: null, stage: null });
      try {
        const { result, ...extra } = await run(args, emit);
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
      // LangGraph's `stream_mode="updates"` reports a node's completion, not
      // its start — so the real "reasoning" tick only fires once the Sonnet
      // call is already done, which for a multi-second call means the label
      // stalls on whichever of "weather"/"catalog" resolved last for the
      // entire wait. reason_and_select always starts the instant BOTH fan-out
      // branches have reported, so once we've seen both, infer it's running
      // and show that label early instead of waiting for its own tick.
      let sawWeather = false;
      let sawCatalog = false;
      let sawReasoning = false;
      try {
        await runStream(args, (event, payload) => {
          if (event === 'progress') {
            if (payload.stage === 'weather') sawWeather = true;
            else if (payload.stage === 'catalog') sawCatalog = true;
            else if (payload.stage === 'reasoning') sawReasoning = true;

            const stage =
              !sawReasoning && sawWeather && sawCatalog ? 'reasoning' : payload.stage;
            if (stage !== getSnapshot().stage) emit({ stage });
          } else if (event === 'plan') emit({ plan: payload });
          else if (event === 'purchases') emit({ purchases: payload.purchase_suggestions });
          else if (event === 'error') emit({ error: payload.detail || 'Trip planning failed' });
          else if (event === 'done') emit({ loading: false, done: true });
        });
      } catch (e) {
        emit({ loading: false, error: String(e) });
      }
      // The body can close cleanly without a trailing `done` frame (backend
      // worker killed mid-stream, proxy idle-timeout) — reader.read() then
      // just returns { done: true } with no exception, so runStream resolves
      // normally. Without this, `loading` would stay true forever and the
      // `if (getSnapshot().loading) return` guard above would block every
      // retry until a full page reload.
      if (getSnapshot().loading) {
        emit({ loading: false, error: getSnapshot().error || 'Connection lost' });
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
