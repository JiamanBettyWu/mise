import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import DestinationCombobox from '../components/DestinationCombobox.jsx';
import PastTrips from '../components/PastTrips.jsx';
import TripPlanResult from '../components/TripPlanResult.jsx';
import { api } from '../services/api.js';
import {
  clearError as clearPlanError,
  consumePlan,
  getSnapshot,
  startPlanning,
  subscribe,
} from '../services/tripGeneration.js';

const STORAGE_KEY = 'trip_state';

// #124: node-progress labels shown while the plan streams in, before
// `plan` lands. Falls back to a generic label for any stage not yet seen.
const STAGE_LABELS = {
  weather: 'Checking the weather…',
  catalog: 'Loading your wardrobe…',
  reasoning: 'Thinking through your packing list…',
  shopping: 'Looking for missing pieces…',
};

function todayPlus(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function mergePurchases(plan, purchases) {
  return { ...plan, purchase_suggestions: purchases ?? plan.purchase_suggestions ?? [] };
}

// Pull persisted state on mount. Silent expiry: trips whose end_date has
// passed are dropped (the empty form is signal enough). Anything unparseable
// also resets — let the user start over rather than crash on stale shapes.
function hydrate() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.plan?.end_date && parsed.plan.end_date < todayISO()) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export default function TripPlan() {
  // Lazy initializer: hydrate() reads + can mutate localStorage (clearing an
  // expired trip), so it must run once on mount, not on every render — the
  // streaming updates below re-render the page ~8-10 times per generation.
  const [persisted] = useState(() => hydrate());
  const [destination, setDestination] = useState(persisted?.form?.destination ?? '');
  const [selected, setSelected] = useState(persisted?.form?.selected ?? null);
  const [startDate, setStartDate] = useState(persisted?.form?.startDate ?? todayPlus(1));
  const [endDate, setEndDate] = useState(persisted?.form?.endDate ?? todayPlus(5));
  const [notes, setNotes] = useState(persisted?.form?.notes ?? '');
  const [plan, setPlan] = useState(persisted?.plan ?? null);
  const [error, setError] = useState(''); // local validation errors only

  // #128 explicit save: pruning is client-state only (never touches `plan`,
  // which regenerate-fallback and localStorage persistence still rely on
  // being the model's actual output). saveFlash bumps to retrigger the
  // "✓ Saved" confirmation; tripsRefresh bumps to make PastTrips refetch.
  const [removedItemIds, setRemovedItemIds] = useState(() => new Set());
  const [saving, setSaving] = useState(false);
  const [saveFlash, setSaveFlash] = useState(0);
  const [saveError, setSaveError] = useState('');
  const [tripsRefresh, setTripsRefresh] = useState(0);

  // Planning lives in a module-scope store so it survives navigating away
  // mid-request; we subscribe here and render its plan/purchases as they
  // stream in, then adopt the finished plan (the persistence effect below
  // writes it into localStorage) once `done` fires.
  const gen = useSyncExternalStore(subscribe, getSnapshot);
  const { loading } = gen;

  // The plan renders the moment `reason_and_select`/`generate_output` finish
  // — purchase suggestions fill in afterward via `gen.purchases`, so this
  // merges them onto the streamed plan rather than waiting for both.
  const streamingPlan = gen.plan ? mergePurchases(gen.plan, gen.purchases) : null;
  // Falls back to the last-good `plan` (not null) while loading with no
  // streamed plan yet, so a failure before `plan` lands (bad destination,
  // reasoning error) re-shows the previous result instead of losing it —
  // `plan`/localStorage are only ever replaced by a plan that actually landed.
  const displayPlan = streamingPlan ?? (loading ? null : plan);
  const purchasesPending =
    !!streamingPlan && !gen.done && (streamingPlan.gaps?.length ?? 0) > 0 && gen.purchases == null;

  // What Save actually persists — displayPlan with pre-save ✕ removals
  // applied. Kept separate from `plan`/localStorage (see above).
  const prunedPlan = useMemo(() => {
    if (!displayPlan) return null;
    if (removedItemIds.size === 0) return displayPlan;
    return {
      ...displayPlan,
      packing_list: displayPlan.packing_list.map((section) => ({
        ...section,
        items: section.items.filter((item) => !removedItemIds.has(item.id)),
      })),
    };
  }, [displayPlan, removedItemIds]);

  useEffect(() => {
    if (!gen.done) return;
    if (gen.plan) setPlan(mergePurchases(gen.plan, gen.purchases));
    // Deferred a tick: consumePlan's store notification and this setPlan
    // both trigger re-renders, and they don't always land in the same React
    // commit. Clearing gen.plan/purchases synchronously here can produce one
    // render where neither the (just-cleared) store nor `plan` (not yet
    // committed) is populated — displayPlan goes briefly null/stale, which
    // unmounts TripPlanResult and silently resets any state it owns (e.g.
    // #128's Save-flash timer). Letting setPlan's render commit first closes
    // that window.
    setTimeout(consumePlan, 0);
  }, [gen.done]);

  useEffect(() => {
    const isEmpty = !destination && !notes && !plan;
    if (isEmpty) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        form: { destination, selected, startDate, endDate, notes },
        plan,
      })
    );
  }, [destination, selected, startDate, endDate, notes, plan]);

  function planAnotherTrip() {
    setDestination('');
    setSelected(null);
    setStartDate(todayPlus(1));
    setEndDate(todayPlus(5));
    setNotes('');
    setPlan(null);
    setError('');
    clearPlanError();
    setRemovedItemIds(new Set());
    setSaveError('');
  }

  function generate(e) {
    e?.preventDefault();
    if (!destination.trim()) {
      setError('Destination is required.');
      return;
    }
    if (endDate < startDate) {
      setError('End date must be on or after start date.');
      return;
    }
    setError('');
    // Don't clear `plan` here — `displayPlan` already hides it behind the
    // progress message while loading, and leaving it intact (and persisted)
    // means a failed regenerate falls back to the last-good plan instead of
    // losing it.
    setRemovedItemIds(new Set());
    setSaveError('');
    startPlanning({
      destination: destination.trim(),
      start_date: startDate,
      end_date: endDate,
      additional_notes: notes.trim(),
      lat: selected?.lat ?? null,
      lon: selected?.lon ?? null,
    });
  }

  function handleRemoveItem(itemId) {
    setRemovedItemIds((prev) => new Set(prev).add(itemId));
  }

  async function handleSave() {
    if (!prunedPlan) return;
    setSaving(true);
    setSaveError('');
    try {
      await api.saveTrip({
        destination: prunedPlan.destination,
        start_date: prunedPlan.start_date,
        end_date: prunedPlan.end_date,
        notes: notes.trim(),
        plan: prunedPlan,
        edited: removedItemIds.size > 0,
      });
      setSaveFlash((f) => f + 1);
      setTripsRefresh((n) => n + 1);
    } catch (e) {
      setSaveError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="form-page">
        <h1>Trip planner</h1>

        <form className="trip-form" onSubmit={generate}>
        <label className="field">
          <span className="muted">Destination</span>
          <DestinationCombobox
            value={destination}
            onChange={setDestination}
            onSelect={setSelected}
          />
        </label>

        <div className="trip-form__dates">
          <label className="field">
            <span className="muted">Start date</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="muted">End date</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
        </div>

        <label className="field">
          <span className="muted">
            Activities & notes (optional — e.g. "ruins tour, mole class, cobblestones")
          </span>
          <textarea
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>

        <div className="trip-form__actions">
          <button type="submit" disabled={loading}>
            {loading ? 'Planning…' : displayPlan ? 'Regenerate' : 'Generate packing plan'}
          </button>
        </div>

        {/* Gated on streamingPlan (this generation's plan), not displayPlan
            (which can be the stale last-good plan reappearing on failure) —
            otherwise a failed regenerate with an old plan on screen would
            silently fall back to that old plan with no indication the new
            attempt failed. Only suppressed when THIS generation's plan
            actually rendered (e.g. a late purchase-search failure shouldn't
            read as "everything failed" over a plan that already succeeded). */}
        {(gen.error || error) && !streamingPlan && <p className="error">{gen.error || error}</p>}
        </form>
      </div>

      {loading && !displayPlan && (
        <p className="muted">{STAGE_LABELS[gen.stage] || 'Thinking through your trip…'}</p>
      )}

      {prunedPlan && (
        <>
          <TripPlanResult
            plan={prunedPlan}
            onPlanAnother={planAnotherTrip}
            purchasesPending={purchasesPending}
            onSave={handleSave}
            saving={saving}
            saveFlash={saveFlash}
            onRemoveItem={handleRemoveItem}
          />
          {saveError && <p className="error">{saveError}</p>}
        </>
      )}

      <PastTrips refreshSignal={tripsRefresh} />
    </div>
  );
}
