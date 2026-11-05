// Empty-state copy for the Profile page's "Learned from your feedback" section
// (#149). The heartbeat (preferences_reviewed_at) says WHEN the weekly job last
// ran; the inference_runs rows that ride GET /profile say WHAT it did. Before
// #149 an alive-and-wiped run — the job finished, kept nothing, and retired the
// existing inferred prefs — rendered as the same bare "No patterns learned
// yet" as a job that had simply found nothing, and the wipe went unnoticed
// until the panel looked surprisingly empty. Each branch below names the
// run's actual outcome so the sentence carries the diagnosis.
//
// Pure (no React, no fetch) so it can be unit-tested with node --test.

// "Jul 6" within the current year, "Jul 6, 2025" otherwise — a retired-on date
// is a point in time, not a staleness signal, so absolute beats relative here
// (contrast the heading's "Reviewed N days ago", which IS a staleness signal).
// Always formatted in UTC: the run timestamp is the Monday 01:20 UTC cron, so
// the local-zone day would differ for anyone west of Greenwich (an EST viewer
// would read "Jul 5" for the Jul 6 run), and the date must match the Actions
// log and the DB row the user might go look at.
export function shortDate(iso, now = new Date()) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const opts = { month: 'short', day: 'numeric', timeZone: 'UTC' };
  if (d.getUTCFullYear() !== now.getUTCFullYear()) opts.year = 'numeric';
  return d.toLocaleDateString('en-US', opts);
}

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const onDate = (iso, now) => {
  const when = shortDate(iso, now);
  return when ? ` on ${when}` : '';
};

/**
 * @param {object} args
 * @param {string|null|undefined} args.reviewedAt  profile.preferences_reviewed_at
 * @param {object|null|undefined} args.lastRun     profile.last_inference_run (newest row)
 * @param {object|null|undefined} args.lastWipe    profile.last_inference_wipe (newest row
 *                                                 with outcome 'empty' and removed > 0)
 * @param {Date} [args.now]                        injected for tests
 * @returns {string} one sentence for the empty state
 */
export function inferredEmptyCopy({ reviewedAt, lastRun, lastWipe, now = new Date() }) {
  // Never run (or never logged a run): the pre-first-run copy from #61.
  if (!reviewedAt && !lastRun) return 'These appear after the weekly review job first runs.';

  // Ran before the run log existed, or the log is unreadable: fall back to
  // the pre-#149 wording rather than invent a diagnosis.
  if (!lastRun) return 'No patterns learned from your feedback yet.';

  const { outcome, verdicts = 0, written = 0, removed = 0, ran_at: ranAt } = lastRun;

  if (outcome === 'insufficient') {
    return `Not enough rated outfits yet (${verdicts} so far) — keep rating and the weekly review will start finding patterns.`;
  }

  if (outcome === 'empty') {
    // The wipe itself. "Latest review", not "this week": if the cron stops,
    // this sentence must not contradict a "Reviewed 90 days ago" heading.
    if (removed > 0) return `No patterns in the latest review (${removed} retired${onDate(ranAt, now)}).`;
    // A routine empty week AFTER a wipe: with only the newest row, "never had
    // any" and "retired a month ago" look identical — the earlier wipe is
    // what explains why the panel is empty, so keep naming it.
    if (lastWipe?.removed > 0) {
      return `No patterns since ${lastWipe.removed} ${lastWipe.removed === 1 ? 'was' : 'were'} retired${onDate(lastWipe.ran_at, now)}.`;
    }
    return 'No patterns learned from your feedback yet.';
  }

  // outcome === 'inferred' but the list is empty: the user has since edited
  // (promoted) or dismissed every statement the last run produced.
  if (written > 0) {
    return `The ${plural(written, 'pattern')} from the last review ${written === 1 ? 'was' : 'were'} since edited or dismissed.`;
  }
  return 'No patterns learned from your feedback yet.';
}
