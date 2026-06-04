import { useEffect, useState } from 'react';
import TripPlanResult from '../components/TripPlanResult.jsx';
import { api } from '../services/api.js';

const STORAGE_KEY = 'trip_state';

function todayPlus(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
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
  const [startDate, setStartDate] = useState(persisted?.form?.startDate ?? todayPlus(1));
  const [endDate, setEndDate] = useState(persisted?.form?.endDate ?? todayPlus(5));
  const [notes, setNotes] = useState(persisted?.form?.notes ?? '');
  const [plan, setPlan] = useState(persisted?.plan ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const isEmpty = !destination && !notes && !plan;
    if (isEmpty) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        form: { destination, startDate, endDate, notes },
        plan,
      })
    );
  }, [destination, startDate, endDate, notes, plan]);

  function planAnotherTrip() {
    setDestination('');
    setStartDate(todayPlus(1));
    setEndDate(todayPlus(5));
    setNotes('');
    setPlan(null);
    setError('');
  }

  async function generate(e) {
    e?.preventDefault();
    if (!destination.trim()) {
      setError('Destination is required.');
      return;
    }
    if (endDate < startDate) {
      setError('End date must be on or after start date.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await api.planTrip({
        destination: destination.trim(),
        start_date: startDate,
        end_date: endDate,
        additional_notes: notes.trim(),
      });
      setPlan(result);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="form-page">
        <h1>Trip planner</h1>

        <form className="trip-form" onSubmit={generate}>
        <label className="field">
          <span className="muted">Destination</span>
          <input
            type="text"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="e.g. Oaxaca, Mexico"
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
            {loading ? 'Planning…' : plan ? 'Regenerate' : 'Generate packing plan'}
          </button>
        </div>

        {error && <p className="error">{error}</p>}
        </form>

        {plan && !loading && (
          <div className="trip-form__actions trip-form__actions--reset">
            <button type="button" onClick={planAnotherTrip}>
              Plan another trip
            </button>
          </div>
        )}
      </div>

      {loading && <p className="muted">Thinking through weather, catalog, and gaps…</p>}

      {plan && !loading && <TripPlanResult plan={plan} />}
    </div>
  );
}
