import test from 'node:test';
import assert from 'node:assert/strict';
import { inferredEmptyCopy, shortDate } from './inferenceCopy.js';

const NOW = new Date('2026-07-10T12:00:00Z');
const REVIEWED = '2026-07-06T01:24:00Z';
const run = (over) => ({
  id: 'r1',
  ran_at: '2026-07-06T01:24:00+00:00', // just after the Monday 01:20 UTC cron
  outcome: 'inferred',
  verdicts: 26,
  written: 1,
  removed: 1,
  ...over,
});
const WIPE = run({ outcome: 'empty', written: 0, removed: 2 });

test('never run: pre-first-run copy', () => {
  assert.equal(
    inferredEmptyCopy({ reviewedAt: null, lastRun: null, lastWipe: null, now: NOW }),
    'These appear after the weekly review job first runs.',
  );
});

test('heartbeat present but no run log (pre-#149 history): old wording, no invented diagnosis', () => {
  assert.equal(
    inferredEmptyCopy({ reviewedAt: REVIEWED, lastRun: null, now: NOW }),
    'No patterns learned from your feedback yet.',
  );
});

test('the 2026-07-06 wipe names the count and the date', () => {
  const copy = inferredEmptyCopy({ reviewedAt: REVIEWED, lastRun: WIPE, lastWipe: WIPE, now: NOW });
  assert.equal(copy, 'No patterns in the latest review (2 retired on Jul 6).');
});

test('wipe in a previous year carries the year', () => {
  const old = run({ outcome: 'empty', written: 0, removed: 1, ran_at: '2025-12-29T01:24:00Z' });
  const copy = inferredEmptyCopy({ reviewedAt: '2025-12-29T01:24:00Z', lastRun: old, lastWipe: old, now: NOW });
  assert.equal(copy, 'No patterns in the latest review (1 retired on Dec 29, 2025).');
});

test('dates are formatted in UTC regardless of the viewer\'s zone', () => {
  // The cron fires at 01:20 UTC, so any zone west of Greenwich would otherwise
  // show the previous calendar day. Node re-reads TZ at runtime.
  const prev = process.env.TZ;
  try {
    for (const tz of ['America/New_York', 'America/Los_Angeles', 'Pacific/Auckland', 'UTC']) {
      process.env.TZ = tz;
      assert.equal(shortDate('2026-07-06T01:24:00Z', NOW), 'Jul 6', tz);
      assert.equal(shortDate('2025-12-29T01:24:00Z', NOW), 'Dec 29, 2025', tz);
    }
  } finally {
    if (prev === undefined) delete process.env.TZ;
    else process.env.TZ = prev;
  }
});

test('a routine empty week after a wipe still names the wipe', () => {
  // Jul 13: wrote 0, removed 0 (nothing left to remove). Without lastWipe this
  // would fall back to the generic copy — the silent state #149 set out to fix.
  const later = run({ outcome: 'empty', written: 0, removed: 0, ran_at: '2026-07-13T01:24:00Z' });
  const copy = inferredEmptyCopy({
    reviewedAt: '2026-07-13T01:24:00Z', lastRun: later, lastWipe: WIPE, now: new Date('2026-07-15T12:00:00Z'),
  });
  assert.equal(copy, 'No patterns since 2 were retired on Jul 6.');
  const one = inferredEmptyCopy({
    reviewedAt: '2026-07-13T01:24:00Z', lastRun: later, lastWipe: run({ outcome: 'empty', written: 0, removed: 1 }), now: NOW,
  });
  assert.equal(one, 'No patterns since 1 was retired on Jul 6.');
});

test('empty with nothing to retire and no prior wipe is routine', () => {
  const copy = inferredEmptyCopy({
    reviewedAt: REVIEWED,
    lastRun: run({ outcome: 'empty', written: 0, removed: 0 }),
    lastWipe: null,
    now: NOW,
  });
  assert.equal(copy, 'No patterns learned from your feedback yet.');
});

test('a stale wipe never claims "this week"', () => {
  // Cron disabled in August; viewed in November next to "Reviewed 90 days ago".
  const aug = run({ outcome: 'empty', written: 0, removed: 2, ran_at: '2026-08-03T01:24:00Z' });
  const copy = inferredEmptyCopy({ reviewedAt: '2026-08-03T01:24:00Z', lastRun: aug, lastWipe: aug, now: new Date('2026-11-05T12:00:00Z') });
  assert.equal(copy, 'No patterns in the latest review (2 retired on Aug 3).');
  assert.doesNotMatch(copy, /this week/);
});

test('insufficient evidence reports the verdict count', () => {
  const copy = inferredEmptyCopy({
    reviewedAt: REVIEWED,
    lastRun: run({ outcome: 'insufficient', verdicts: 6, written: 0, removed: 0 }),
    now: NOW,
  });
  assert.match(copy, /^Not enough rated outfits yet \(6 so far\)/);
});

test('inferred but list empty: the user edited or dismissed them', () => {
  const one = inferredEmptyCopy({ reviewedAt: REVIEWED, lastRun: run({ outcome: 'inferred', written: 1 }), now: NOW });
  assert.equal(one, 'The 1 pattern from the last review was since edited or dismissed.');
  const three = inferredEmptyCopy({ reviewedAt: REVIEWED, lastRun: run({ outcome: 'inferred', written: 3 }), now: NOW });
  assert.equal(three, 'The 3 patterns from the last review were since edited or dismissed.');
});

test('shortDate tolerates garbage', () => {
  assert.equal(shortDate('not a date', NOW), null);
  const bad = run({ outcome: 'empty', written: 0, removed: 2, ran_at: 'garbage' });
  assert.equal(
    inferredEmptyCopy({ reviewedAt: 'x', lastRun: bad, lastWipe: bad, now: NOW }),
    'No patterns in the latest review (2 retired).',
  );
});
