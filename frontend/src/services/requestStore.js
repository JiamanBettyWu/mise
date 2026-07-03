// Factory for module-scope request stores, so an in-flight generation
// survives SPA navigation (react-router unmounts the page; component state
// and effects die with it, but the module — and the fetch it started — keep
// running). Pages subscribe via useSyncExternalStore and consume `result`
// when it lands. A full page reload still kills the request — the browser
// aborts the fetch itself. Extracted from todayGeneration.js for #105.
//
// `run(args)` is the injected async step: it returns `{ result, ...extra }`,
// where extra fields (e.g. usingMyLocation) are merged into the snapshot
// alongside the result.
export function createRequestStore(run) {
  let snapshot = { loading: false, error: '', result: null };
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
    async start(args) {
      if (snapshot.loading) return;
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
