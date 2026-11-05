// Empty-state copy for the Profile page's "Learned from your feedback" section
// (#149). The heartbeat (preferences_reviewed_at) says WHEN the weekly job last
// ran; the newest inference_runs row says WHAT it did. Before #149 an
// alive-and-wiped run — the job finished, kept nothing, and retired the
// existing inferred prefs — rendered as the same bare "No patterns learned
// yet" as a job that had simply found nothing, and the wipe went unnoticed
// until the panel looked surprisingly empty. Each branch below names the
// run's actual outcome so the sentence carries the diagnosis.
//
// Pure (no React, no fetch) so it can be unit-tested with node --test.

// "Jul 6" within the current year, "Jul 6, 2025" otherwise — a retired-on date
// is a point in time, not a staleness signal, so absolute beats relative here
// (contrast the heading's "Reviewed N days ago", which IS a staleness signal).
export function shortDate(iso, now = new Date()) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const opts = { month: 'short', day: 'numeric' };
  if (d.getFullYear() !== now.getFullYear()) opts.year = 'numeric';
  return d.toLocaleDateString('en-US', opts);
}

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

/**
 * @param {object} args
 * @param {string|null|undefined} args.reviewedAt  profile.preferences_reviewed_at
 * @param {object|null|undefined} args.lastRun     newest inference_runs row, or null
 * @param {Date} [args.now]                        injected for tests
 * @returns {string} one sentence for the empty state
 */
export function inferredEmptyCopy({ reviewedAt, lastRun, now = new Date() }) {
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
    if (removed > 0) {
      const when = shortDate(ranAt, now);
      return `No patterns this week (${removed} retired${when ? ` on ${when}` : ''}).`;
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
