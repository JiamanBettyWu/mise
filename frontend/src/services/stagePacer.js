// Paces SSE stage-label updates (#154 follow-up): real node completions can
// arrive milliseconds apart (weather + wardrobe resolve fast; the model call
// is the long pole), which made early labels flicker past unreadably. Each
// stage now stays visible at least `minMs` before the next queued one shows.
// The pacing only delays *labels* — the caller emits the result the moment
// it lands and calls stop(), which drops any still-queued labels: a rendered
// result must never wait on cosmetic dwell time.
export function paceStages(apply, minMs = 1500) {
  let queue = [];
  let shownAt = 0;
  let lastStage = null; // dedupes repeat ticks (e.g. the trip graph's double "weather")
  let timer = null;
  let stopped = false;

  function show(stage) {
    shownAt = Date.now();
    apply(stage);
  }

  function schedule() {
    if (timer || stopped || !queue.length) return;
    const wait = Math.max(0, shownAt + minMs - Date.now());
    timer = setTimeout(() => {
      timer = null;
      if (stopped || !queue.length) return;
      show(queue.shift());
      schedule();
    }, wait);
  }

  return {
    push(stage) {
      if (stopped || stage === lastStage) return;
      lastStage = stage;
      if (!shownAt) show(stage); // first stage renders immediately
      else {
        queue.push(stage);
        schedule();
      }
    },
    stop() {
      stopped = true;
      queue = [];
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    },
  };
}
