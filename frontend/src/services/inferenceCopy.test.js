import test from 'node:test';
import assert from 'node:assert/strict';
import { inferredEmptyCopy, shortDate } from './inferenceCopy.js';

const NOW = new Date('2026-07-10T12:00:00Z');
const run = (over) => ({
  id: 'r1',
  ran_at: '2026-07-06T01:24:00+00:00',
  outcome: 'inferred',
  verdicts: 26,
  written: 1,
  removed: 1,
  ...over,
});

test('never run: pre-first-run copy', () => {
  assert.equal(
    inferredEmptyCopy({ reviewedAt: null, lastRun: null, now: NOW }),
    'These appear after the weekly review job first runs.',
  );
});

test('heartbeat present but no run log (pre-#149 history): old wording, no invented diagnosis', () => {
  assert.equal(
    inferredEmptyCopy({ reviewedAt: '2026-07-06T01:24:00Z', lastRun: null, now: NOW }),
    'No patterns learned from your feedback yet.',
  );
});

test('the 2026-07-06 wipe names the count and the date', () => {
  const copy = inferredEmptyCopy({
    reviewedAt: '2026-07-06T01:24:00Z',
    lastRun: run({ outcome: 'empty', written: 0, removed: 2 }),
    now: NOW,
  });
  assert.equal(copy, 'No patterns this week (2 retired on Jul 6).');
});

test('wipe in a previous year carries the year', () => {
  const copy = inferredEmptyCopy({
    reviewedAt: '2025-12-29T01:24:00Z',
    lastRun: run({ outcome: 'empty', written: 0, removed: 1, ran_at: '2025-12-29T01:24:00Z' }),
    now: NOW,
  });
  assert.equal(copy, 'No patterns this week (1 retired on Dec 29, 2025).');
});

test('empty with nothing to retire is routine, not a wipe', () => {
  const copy = inferredEmptyCopy({
    reviewedAt: '2026-07-06T01:24:00Z',
    lastRun: run({ outcome: 'empty', written: 0, removed: 0 }),
    now: NOW,
  });
  assert.equal(copy, 'No patterns learned from your feedback yet.');
});

test('insufficient evidence reports the verdict count', () => {
  const copy = inferredEmptyCopy({
    reviewedAt: '2026-07-06T01:24:00Z',
    lastRun: run({ outcome: 'insufficient', verdicts: 6, written: 0, removed: 0 }),
    now: NOW,
  });
  assert.match(copy, /^Not enough rated outfits yet \(6 so far\)/);
});

test('inferred but list empty: the user edited or dismissed them', () => {
  const one = inferredEmptyCopy({
    reviewedAt: '2026-07-06T01:24:00Z',
    lastRun: run({ outcome: 'inferred', written: 1 }),
    now: NOW,
  });
  assert.equal(one, 'The 1 pattern from the last review was since edited or dismissed.');
  const three = inferredEmptyCopy({
    reviewedAt: '2026-07-06T01:24:00Z',
    lastRun: run({ outcome: 'inferred', written: 3 }),
    now: NOW,
  });
  assert.equal(three, 'The 3 patterns from the last review were since edited or dismissed.');
});

test('shortDate tolerates garbage', () => {
  assert.equal(shortDate('not a date', NOW), null);
  const copy = inferredEmptyCopy({
    reviewedAt: 'x',
    lastRun: run({ outcome: 'empty', written: 0, removed: 2, ran_at: 'garbage' }),
    now: NOW,
  });
  assert.equal(copy, 'No patterns this week (2 retired).');
});
