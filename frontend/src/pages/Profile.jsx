import { useEffect, useRef, useState } from 'react';
import DestinationCombobox from '../components/DestinationCombobox.jsx';
import { api, setStoredPassword } from '../services/api.js';

// Lingering "✓ Saved" confirmation. Remounts on every trigger (the counter is
// the key at the call site) so consecutive saves restart the fade animation.
function Flash({ children }) {
  return <span className="profile__flash">✓ {children}</span>;
}

// One preference row — display or inline-edit. Shared by both sections; the
// inferred variant adds the evidence badge and relabels the actions.
function PrefTile({ pref, editing, editText, setEditText, editRef, onStartEdit, onSaveEdit, onCancelEdit, onDelete }) {
  if (editing) {
    return (
      <div className="profile__pref-tile profile__pref-tile--editing">
        <input
          ref={editRef}
          className="profile__pref-input"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSaveEdit(pref);
            if (e.key === 'Escape') onCancelEdit();
          }}
        />
        <div className="profile__pref-actions">
          <button onClick={() => onSaveEdit(pref)}>Save</button>
          <button className="ghost" onClick={onCancelEdit}>Cancel</button>
        </div>
      </div>
    );
  }

  const inferred = pref.source === 'inferred';
  const n = pref.evidence_ids?.length || 0;
  return (
    <div className="profile__pref-tile">
      <span className="profile__pref-text">{pref.text}</span>
      {inferred && (
        <span className="chip chip--on-attr profile__pref-badge">
          inferred{n > 0 ? ` · from ${n} outfit${n === 1 ? '' : 's'}` : ''}
        </span>
      )}
      <div className="profile__pref-actions">
        <button className="ghost" onClick={() => onStartEdit(pref)}>
          {inferred ? 'Edit & own' : 'Edit'}
        </button>
        <button className="ghost danger" onClick={() => onDelete(pref)}>
          {inferred ? 'Dismiss' : 'Remove'}
        </button>
      </div>
    </div>
  );
}

export default function Profile() {
  const [profile, setProfile] = useState(null);
  const [locationText, setLocationText] = useState('');
  const [locationCoords, setLocationCoords] = useState(null);
  const [locationSaving, setLocationSaving] = useState(false);

  const [prefs, setPrefs] = useState([]);
  const [newText, setNewText] = useState('');
  const [adding, setAdding] = useState(false);

  // Flash counters: bumping remounts the <Flash> (key) and restarts its fade.
  const [locationFlash, setLocationFlash] = useState(0);
  const [prefsFlash, setPrefsFlash] = useState({ n: 0, msg: '' });

  // Failed requests must be visible — a dead backend otherwise reads as
  // "my preferences vanished" (or never listed at all).
  const [loadError, setLoadError] = useState('');
  const [locationError, setLocationError] = useState('');
  const [prefsError, setPrefsError] = useState('');

  // editingId → current draft text
  const [editId, setEditId] = useState(null);
  const [editText, setEditText] = useState('');
  const editRef = useRef(null);

  useEffect(() => {
    api.getProfile()
      .then((p) => {
        setProfile(p);
        setLocationText(p?.home_location_text || '');
        if (p?.home_lat != null && p?.home_lon != null) {
          setLocationCoords({ lat: p.home_lat, lon: p.home_lon });
        }
      })
      .catch((err) => setLoadError(loadErrorMessage(err)));
    api.listPreferences()
      .then(setPrefs)
      .catch((err) => setLoadError(loadErrorMessage(err)));
  }, []);

  useEffect(() => {
    if (editRef.current) editRef.current.focus();
  }, [editId]);

  function loadErrorMessage(err) {
    const msg = err?.message ?? '';
    if (msg.startsWith('404')) {
      return 'The backend doesn’t have the /profile endpoints yet — it’s probably running main; deploy this branch (and run the SQL migration) first.';
    }
    return `Couldn’t load profile data: ${msg || 'is the backend running?'}`;
  }

  // ---- Location save -------------------------------------------------------

  async function saveLocation() {
    if (!locationCoords) return;
    setLocationSaving(true);
    setLocationError('');
    try {
      const updated = await api.updateProfile({
        home_location_text: locationText,
        home_lat: locationCoords.lat,
        home_lon: locationCoords.lon,
      });
      setProfile(updated);
      setLocationFlash((n) => n + 1);
    } catch (err) {
      setLocationError(`Save failed: ${err?.message ?? 'unknown error'}`);
    } finally {
      setLocationSaving(false);
    }
  }

  // ---- Add preference ------------------------------------------------------

  async function addPreference(e) {
    e.preventDefault();
    const text = newText.trim();
    if (!text) return;
    setAdding(true);
    setPrefsError('');
    try {
      const created = await api.createPreference(text);
      setPrefs((p) => [...p, created]);
      setNewText('');
      setPrefsFlash((f) => ({ n: f.n + 1, msg: 'Added' }));
    } catch (err) {
      setPrefsError(`Couldn’t add: ${err?.message ?? 'unknown error'}`);
    } finally {
      setAdding(false);
    }
  }

  // ---- Inline edit ---------------------------------------------------------

  function startEdit(pref) {
    setEditId(pref.id);
    setEditText(pref.text);
  }

  async function saveEdit(pref) {
    const text = editText.trim();
    if (!text) {
      setEditId(null);
      return;
    }
    // Saving unchanged text still PATCHes for inferred prefs: "Edit & own"
    // promises ownership, and the backend promotes on any text write.
    if (text === pref.text && pref.source !== 'inferred') {
      setEditId(null);
      return;
    }
    setPrefsError('');
    try {
      const updated = await api.updatePreference(pref.id, { text });
      setPrefs((ps) => ps.map((p) => (p.id === updated.id ? updated : p)));
      setEditId(null);
      setPrefsFlash((f) => ({ n: f.n + 1, msg: 'Saved' }));
    } catch (err) {
      setPrefsError(`Couldn’t save: ${err?.message ?? 'unknown error'}`);
    }
  }

  function cancelEdit() {
    setEditId(null);
    setEditText('');
  }

  // ---- Delete --------------------------------------------------------------

  async function deletePref(pref) {
    // A user pref is hand-written and gone for good — confirm. An inferred
    // pref is machine-made; dismissing it tombstones (status=rejected) so
    // #62's weekly job won't resurrect it. Either way it leaves the list.
    if (pref.source === 'user' && !confirm(`Remove "${pref.text}"?`)) return;
    setPrefsError('');
    try {
      await api.deletePreference(pref.id);
      setPrefs((ps) => ps.filter((p) => p.id !== pref.id));
    } catch (err) {
      setPrefsError(`Couldn’t remove: ${err?.message ?? 'unknown error'}`);
    }
  }

  const userPrefs = prefs.filter((p) => p.source === 'user');
  const inferredPrefs = prefs.filter((p) => p.source === 'inferred');

  const locationDirty =
    locationCoords &&
    (locationText !== (profile?.home_location_text || '') ||
      locationCoords.lat !== profile?.home_lat ||
      locationCoords.lon !== profile?.home_lon);

  const tileHandlers = {
    editText,
    setEditText,
    editRef,
    onStartEdit: startEdit,
    onSaveEdit: saveEdit,
    onCancelEdit: cancelEdit,
    onDelete: deletePref,
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-header__title">Profile</h1>
        <div className="page-header__actions">
          <button
            className="ghost"
            onClick={() => {
              setStoredPassword('');
              location.reload();
            }}
          >
            Lock
          </button>
        </div>
      </div>

      <div className="form-page">
        {loadError && <div className="error">{loadError}</div>}

        {/* ---- Basics ---- */}
        <section className="profile__section">
          <h2 className="profile__section-heading">Basics</h2>
          <label className="profile__label">Home location</label>
          <p className="profile__hint muted">
            Used for daily weather. Edit here instead of touching environment variables.
          </p>
          <div className="profile__location-row">
            <DestinationCombobox
              value={locationText}
              onChange={setLocationText}
              onSelect={(sel) => {
                if (sel) setLocationCoords({ lat: sel.lat, lon: sel.lon });
                else setLocationCoords(null);
              }}
            />
            <button
              onClick={saveLocation}
              disabled={!locationDirty || locationSaving}
            >
              {locationSaving ? 'Saving…' : 'Save'}
            </button>
            {locationFlash > 0 && <Flash key={locationFlash}>Saved</Flash>}
          </div>
          {locationError && <div className="error">{locationError}</div>}
        </section>

        {/* ---- Your aesthetic ---- */}
        <section className="profile__section">
          <h2 className="profile__section-heading">Your aesthetic</h2>
          <p className="profile__hint muted">
            Short, specific style statements. The outfit generator treats these as hard constraints.
          </p>

          <div className="profile__pref-list">
            {userPrefs.map((pref) => (
              <PrefTile key={pref.id} pref={pref} editing={editId === pref.id} {...tileHandlers} />
            ))}
          </div>

          <form className="profile__add-row" onSubmit={addPreference}>
            <input
              type="text"
              placeholder="e.g. I never like sporty footwear with elevated outfits"
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
            />
            <button type="submit" disabled={!newText.trim() || adding}>
              {adding ? 'Adding…' : 'Add'}
            </button>
            {prefsFlash.n > 0 && <Flash key={prefsFlash.n}>{prefsFlash.msg}</Flash>}
          </form>
          {prefsError && <div className="error">{prefsError}</div>}
        </section>

        {/* ---- Learned from your feedback ---- */}
        <section className="profile__section">
          <h2 className="profile__section-heading">Learned from your feedback</h2>
          {inferredPrefs.length === 0 ? (
            <p className="profile__empty muted">
              These appear once the weekly review job ships.
            </p>
          ) : (
            <div className="profile__pref-list">
              {inferredPrefs.map((pref) => (
                <PrefTile key={pref.id} pref={pref} editing={editId === pref.id} {...tileHandlers} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
