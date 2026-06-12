import { useEffect, useRef, useState } from 'react';
import DestinationCombobox from '../components/DestinationCombobox.jsx';
import { api, setStoredPassword } from '../services/api.js';

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
  const [locationSaved, setLocationSaved] = useState(false);

  const [prefs, setPrefs] = useState([]);
  const [newText, setNewText] = useState('');
  const [adding, setAdding] = useState(false);

  // editingId → current draft text
  const [editId, setEditId] = useState(null);
  const [editText, setEditText] = useState('');
  const editRef = useRef(null);

  useEffect(() => {
    api.getProfile().then((p) => {
      setProfile(p);
      setLocationText(p?.home_location_text || '');
      if (p?.home_lat != null && p?.home_lon != null) {
        setLocationCoords({ lat: p.home_lat, lon: p.home_lon });
      }
    });
    api.listPreferences().then(setPrefs);
  }, []);

  useEffect(() => {
    if (editRef.current) editRef.current.focus();
  }, [editId]);

  // ---- Location save -------------------------------------------------------

  async function saveLocation() {
    if (!locationCoords) return;
    setLocationSaving(true);
    try {
      const updated = await api.updateProfile({
        home_location_text: locationText,
        home_lat: locationCoords.lat,
        home_lon: locationCoords.lon,
      });
      setProfile(updated);
      setLocationSaved(true);
      setTimeout(() => setLocationSaved(false), 2000);
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
    try {
      const created = await api.createPreference(text);
      setPrefs((p) => [...p, created]);
      setNewText('');
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
    const updated = await api.updatePreference(pref.id, { text });
    setPrefs((ps) => ps.map((p) => (p.id === updated.id ? updated : p)));
    setEditId(null);
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
    await api.deletePreference(pref.id);
    setPrefs((ps) => ps.filter((p) => p.id !== pref.id));
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
              {locationSaving ? 'Saving…' : locationSaved ? 'Saved' : 'Save'}
            </button>
          </div>
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
          </form>
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
