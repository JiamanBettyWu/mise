import test from 'node:test';
import assert from 'node:assert/strict';
import { createStreamRequestStore } from './requestStore.js';

const plan = { destination: 'Boston', packing_list: [], gaps: ['Rain jacket'] };
const purchases = [{ gap: 'Rain jacket', results: [] }];

for (const hasPlan of [false, true]) {
  for (const ending of ['error → done', 'throw', 'close', 'error → close']) {
    test(`${hasPlan ? 'plan → ' : ''}${ending}: classifies and finalizes the run`, async () => {
      const store = createStreamRequestStore(async (_, event) => {
        if (hasPlan) {
          event('plan', plan);
          event('purchases', { purchase_suggestions: purchases });
        }
        if (ending.startsWith('error')) event('error', { detail: 'Service failed' });
        if (ending === 'error → done') event('done', {});
        if (ending === 'throw') throw new Error('Transport failed');
      });
      await store.start({});
      const snapshot = store.getSnapshot();
      assert.equal(snapshot.loading, false);
      assert.equal(snapshot.done, true);
      assert.equal(snapshot.plan, hasPlan ? plan : null);
      assert.equal(Boolean(snapshot.error), !hasPlan);
      assert.equal(Boolean(snapshot.warning), hasPlan);
      if (!hasPlan && ending.startsWith('error')) assert.equal(snapshot.error, 'Service failed');
      store.consumePlan();
      assert.deepEqual(store.getSnapshot(), {
        ...snapshot, plan: null, purchases: null, done: false,
      });
      store.clearError();
      assert.equal(store.getSnapshot().error, '');
      assert.equal(store.getSnapshot().warning, '');
    });
  }

  test(`retry clears a prior ${hasPlan ? 'warning' : 'error'} and succeeds`, async () => {
    let runs = 0;
    let finishRetry;
    const store = createStreamRequestStore(async (_, event) => {
      if (runs++ === 0) {
        if (hasPlan) event('plan', plan);
        event('error', { detail: 'Service failed' });
      } else {
        await new Promise((resolve) => { finishRetry = resolve; });
        event('plan', plan);
        event('purchases', { purchase_suggestions: purchases });
      }
      event('done', {});
    });
    await store.start({});
    store.consumePlan();
    const retry = store.start({});
    assert.equal(store.getSnapshot().loading, true);
    assert.equal(store.getSnapshot().error, '');
    assert.equal(store.getSnapshot().warning, '');
    finishRetry();
    await retry;
    assert.equal(store.getSnapshot().plan, plan);
    assert.equal(store.getSnapshot().purchases, purchases);
    assert.equal(store.getSnapshot().done, true);
    assert.equal(store.getSnapshot().error, '');
    assert.equal(store.getSnapshot().warning, '');
  });
}

test('consuming a delivered plan cannot turn a late transport error into a fatal error', async () => {
  const store = createStreamRequestStore(async (_, event) => {
    event('plan', plan);
    store.consumePlan();
    throw new Error('Connection reset');
  });
  await store.start({});
  assert.equal(store.getSnapshot().error, '');
  assert.ok(store.getSnapshot().warning);
  assert.equal(store.getSnapshot().loading, false);
});

test('a completed and consumed run is not mistaken for a premature close', async () => {
  const store = createStreamRequestStore(async (_, event) => {
    event('plan', plan);
    event('done', {});
    store.consumePlan();
  });
  await store.start({});
  assert.equal(store.getSnapshot().error, '');
  assert.equal(store.getSnapshot().warning, '');
  assert.equal(store.getSnapshot().done, false);
});
