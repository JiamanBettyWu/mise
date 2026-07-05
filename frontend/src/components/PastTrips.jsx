import { useEffect, useState } from 'react';
import { api } from '../services/api.js';
import TripPlanResult from './TripPlanResult.jsx';
import './PastTrips.css';

// #128: saved trip plans are frozen snapshots (destination/dates/notes +
// the full plan blob). This list only ever fetches the scalar summary rows
// (GET /trips) — the full blob + a fresh catalog cross-ref are fetched lazily
// when a tile is opened, since packed status must read LIVE catalog state,
// never what's embedded in the snapshot.

export default function PastTrips({ refreshSignal = 0 }) {
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openingId, setOpeningId] = useState(null);
  const [viewing, setViewing] = useState(null); // { trip, catalogById }

  // refreshSignal bumps after a successful Save on the planning form above,
  // so a freshly-saved trip shows up here without a full page reload.
  useEffect(() => {
    api.listTrips()
      .then(setTrips)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [refreshSignal]);

  useEffect(() => {
    if (!viewing) return;
    function onKey(e) { if (e.key === 'Escape') setViewing(null); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [viewing]);

  async function open(summary) {
    setOpeningId(summary.id);
    setError('');
    try {
      const [trip, catalog] = await Promise.all([
        api.getTrip(summary.id),
        api.listClothing(),
      ]);
      setViewing({ trip, catalogById: new Map(catalog.map((c) => [c.id, c])) });
    } catch (e) {
      setError(String(e));
    } finally {
      setOpeningId(null);
    }
  }

  async function remove(summary, e) {
    e.stopPropagation();
    if (!confirm(`Delete the saved trip to ${summary.destination}?`)) return;
    try {
      await api.deleteTrip(summary.id);
      setTrips((arr) => arr.filter((t) => t.id !== summary.id));
    } catch (e) {
      setError(String(e));
    }
  }

  function togglePacked(item) {
    api.patchClothing(item.id, { in_travel_bag: !item.in_travel_bag })
      .then((updated) => {
        setViewing((v) => {
          if (!v) return v;
          const catalogById = new Map(v.catalogById);
          catalogById.set(updated.id, updated);
          return { ...v, catalogById };
        });
      })
      .catch((e) => setError(String(e)));
  }

  async function markAllPacked(liveItems) {
    if (liveItems.length === 0) return;
    try {
      const updated = await Promise.all(
        liveItems.map((item) => api.patchClothing(item.id, { in_travel_bag: true }))
      );
      setViewing((v) => {
        if (!v) return v;
        const catalogById = new Map(v.catalogById);
        for (const u of updated) catalogById.set(u.id, u);
        return { ...v, catalogById };
      });
    } catch (e) {
      setError(String(e));
    }
  }

  if (loading) return null;
  if (trips.length === 0) return null;

  return (
    <div className="past-trips">
      <h3>Past trips</h3>
      {error && <p className="error">{error}</p>}
      <div className="past-trips__list">
        {trips.map((t) => (
          <div
            key={t.id}
            className="trip-tile"
            role="button"
            tabIndex={0}
            onClick={() => open(t)}
            onKeyDown={(e) => { if (e.key === 'Enter') open(t); }}
          >
            <div className="trip-tile__body">
              <div className="trip-tile__destination">{t.destination}</div>
              <div className="muted">{t.start_date} → {t.end_date}</div>
            </div>
            <div className="trip-tile__actions" onClick={(e) => e.stopPropagation()}>
              {openingId === t.id && <span className="muted">Opening…</span>}
              <button type="button" className="danger" onClick={(e) => remove(t, e)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {viewing && (
        <div className="gmodal-backdrop" onClick={() => setViewing(null)}>
          <div
            className="gmodal gmodal--wide"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="gmodal__close"
              onClick={() => setViewing(null)}
              aria-label="Close"
            >
              ×
            </button>
            <div className="gmodal__body">
              <TripPlanResult
                plan={viewing.trip.plan}
                catalogById={viewing.catalogById}
                onTogglePacked={togglePacked}
                onMarkAllPacked={markAllPacked}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
