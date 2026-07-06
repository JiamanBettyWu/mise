import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api.js';
import TripPlanResult from './TripPlanResult.jsx';
import './PastTrips.css';

// #128: saved trip plans are frozen snapshots (destination/dates/notes +
// the full plan blob). This list only ever fetches the scalar summary rows
// (GET /trips) — the full blob + a fresh catalog cross-ref are fetched lazily
// when a tile is opened, since packed status must read LIVE catalog state,
// never what's embedded in the snapshot.

// #134: relative "saved X ago" for the tile timestamp — same shape as
// Profile.jsx's inference-heartbeat helper, but this one's read at a glance
// on a list rather than as a staleness signal, so seconds count too.
function timeAgo(iso) {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const sec = Math.round((then.getTime() - Date.now()) / 1000); // < 0 = past
  const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
  for (const [unit, secs] of [['day', 86400], ['hour', 3600], ['minute', 60]]) {
    if (Math.abs(sec) >= secs) return rtf.format(Math.round(sec / secs), unit);
  }
  return 'just now';
}

export default function PastTrips({ refreshSignal = 0 }) {
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openingId, setOpeningId] = useState(null);
  const [viewing, setViewing] = useState(null); // { trip, catalogById }

  // #134 inline rename — editingId → current draft text, same click-to-edit
  // shape as Profile.jsx's preference tiles.
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const editRef = useRef(null);

  // refreshSignal bumps after a successful Save on the planning form above,
  // so a freshly-saved trip shows up here without a full page reload.
  useEffect(() => {
    setError('');
    api.listTrips()
      .then(setTrips)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [refreshSignal]);

  useEffect(() => {
    if (editRef.current) editRef.current.focus();
  }, [editingId]);

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

  function startEdit(t, e) {
    e.stopPropagation();
    setEditingId(t.id);
    setEditText(t.name || '');
  }

  function cancelEdit() {
    setEditingId(null);
    setEditText('');
  }

  async function saveEdit(t) {
    const name = editText.trim();
    if (name === (t.name || '')) {
      setEditingId(null);
      return;
    }
    setEditSaving(true);
    setError('');
    try {
      const updated = await api.updateTrip(t.id, { name });
      setTrips((arr) => arr.map((x) => (x.id === updated.id ? updated : x)));
      setEditingId(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setEditSaving(false);
    }
  }

  function togglePacked(item) {
    // Optimistic flip (applied before the PATCH fires) so a second rapid
    // click reads the just-toggled value instead of closing over the same
    // stale `item` — otherwise pack-then-unpack in quick succession both
    // compute from the pre-click state and the second click gets swallowed.
    const next = !item.in_travel_bag;
    setViewing((v) => {
      if (!v) return v;
      const catalogById = new Map(v.catalogById);
      catalogById.set(item.id, { ...item, in_travel_bag: next });
      return { ...v, catalogById };
    });
    api.patchClothing(item.id, { in_travel_bag: next })
      .then((updated) => {
        setViewing((v) => {
          if (!v) return v;
          const catalogById = new Map(v.catalogById);
          catalogById.set(updated.id, updated);
          return { ...v, catalogById };
        });
      })
      .catch((e) => {
        setError(String(e));
        setViewing((v) => {
          if (!v) return v;
          const catalogById = new Map(v.catalogById);
          catalogById.set(item.id, item);
          return { ...v, catalogById };
        });
      });
  }

  async function markAllPacked(liveItems) {
    if (liveItems.length === 0) return;
    // allSettled (not all): one failing PATCH out of N shouldn't discard the
    // N-1 that already succeeded server-side — those still land in
    // catalogById, and only the failures get reported/re-clickable.
    const results = await Promise.allSettled(
      liveItems.map((item) => api.patchClothing(item.id, { in_travel_bag: true }))
    );
    const failures = results.filter((r) => r.status === 'rejected');
    setViewing((v) => {
      if (!v) return v;
      const catalogById = new Map(v.catalogById);
      for (const r of results) {
        if (r.status === 'fulfilled') catalogById.set(r.value.id, r.value);
      }
      return { ...v, catalogById };
    });
    if (failures.length > 0) {
      setError(`${failures.length} item(s) failed to update: ${failures[0].reason}`);
    }
  }

  if (loading) return null;
  if (trips.length === 0 && !error) return null;

  return (
    <div className="past-trips">
      <h3>Past trips</h3>
      {error && <p className="error">{error}</p>}
      <div className="past-trips__list">
        {trips.map((t) => {
          const editing = editingId === t.id;
          return (
            <div
              key={t.id}
              className="trip-tile"
              role="button"
              tabIndex={0}
              onClick={() => { if (!editing) open(t); }}
              onKeyDown={(e) => { if (!editing && e.key === 'Enter') open(t); }}
            >
              {editing ? (
                <div className="trip-tile__edit" onClick={(e) => e.stopPropagation()}>
                  <input
                    ref={editRef}
                    className="trip-tile__edit-input"
                    placeholder={t.destination}
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit(t);
                      if (e.key === 'Escape') cancelEdit();
                    }}
                  />
                  <div className="trip-tile__actions">
                    <button type="button" onClick={() => saveEdit(t)} disabled={editSaving}>
                      {editSaving ? 'Saving…' : 'Save'}
                    </button>
                    <button type="button" className="ghost" onClick={cancelEdit} disabled={editSaving}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="trip-tile__body">
                    <div className="trip-tile__destination">{t.name || t.destination}</div>
                    {t.name && <div className="muted trip-tile__subtitle">{t.destination}</div>}
                    <div className="muted">{t.start_date} → {t.end_date}</div>
                    <div className="muted trip-tile__saved-at" title={t.created_at}>
                      Saved {timeAgo(t.created_at)}
                    </div>
                  </div>
                  <div className="trip-tile__actions" onClick={(e) => e.stopPropagation()}>
                    {openingId === t.id && <span className="muted">Opening…</span>}
                    <button type="button" className="ghost" onClick={(e) => startEdit(t, e)}>
                      Rename
                    </button>
                    <button type="button" className="danger" onClick={(e) => remove(t, e)}>
                      Delete
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
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
