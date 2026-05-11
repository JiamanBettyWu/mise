import { useState } from 'react';
import TripPlanResult from '../components/TripPlanResult.jsx';
import { api } from '../services/api.js';

function todayPlus(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function TripPlan() {
  const [destination, setDestination] = useState('');
  const [startDate, setStartDate] = useState(todayPlus(1));
  const [endDate, setEndDate] = useState(todayPlus(5));
  const [notes, setNotes] = useState('');
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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

      {loading && <p className="muted">Thinking through weather, catalog, and gaps…</p>}

      {plan && !loading && <TripPlanResult plan={plan} />}
    </div>
  );
}
