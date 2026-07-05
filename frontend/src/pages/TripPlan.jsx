import { useEffect, useState, useSyncExternalStore } from 'react';
import DestinationCombobox from '../components/DestinationCombobox.jsx';
import TripPlanResult from '../components/TripPlanResult.jsx';
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
  const persisted = hydrate();
  const [destination, setDestination] = useState(persisted?.form?.destination ?? '');
  const [selected, setSelected] = useState(persisted?.form?.selected ?? null);
  const [startDate, setStartDate] = useState(persisted?.form?.startDate ?? todayPlus(1));
  const [endDate, setEndDate] = useState(persisted?.form?.endDate ?? todayPlus(5));
  const [notes, setNotes] = useState(persisted?.form?.notes ?? '');
  const [plan, setPlan] = useState(persisted?.plan ?? null);
  const [error, setError] = useState(''); // local validation errors only

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

  useEffect(() => {
    if (!gen.done) return;
    if (gen.plan) setPlan(mergePurchases(gen.plan, gen.purchases));
    consumePlan();
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
    startPlanning({
      destination: destination.trim(),
      start_date: startDate,
      end_date: endDate,
      additional_notes: notes.trim(),
      lat: selected?.lat ?? null,
      lon: selected?.lon ?? null,
    });
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

        {/* Suppressed once a plan is on screen: a same-generation failure after
            the plan already rendered (e.g. the purchase-search leg) shouldn't
            read as "everything failed" over a plan that actually succeeded. */}
        {(gen.error || error) && !displayPlan && <p className="error">{gen.error || error}</p>}
        </form>
      </div>

      {loading && !displayPlan && (
        <p className="muted">{STAGE_LABELS[gen.stage] || 'Thinking through your trip…'}</p>
      )}

      {displayPlan && (
        <TripPlanResult
          plan={displayPlan}
          onPlanAnother={planAnotherTrip}
          purchasesPending={purchasesPending}
        />
      )}
    </div>
  );
}
