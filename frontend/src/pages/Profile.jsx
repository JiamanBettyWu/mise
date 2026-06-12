import { useEffect, useRef, useState } from 'react';
import DestinationCombobox from '../components/DestinationCombobox.jsx';
import { api, setStoredPassword } from '../services/api.js';

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
    if (!text || text === pref.text) {
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
    await api.deletePreference(pref.id);
    // User prefs are hard-deleted; inferred prefs are tombstoned (status=rejected).
    // Either way, remove from the visible list.
    setPrefs((ps) => ps.filter((p) => p.id !== pref.id));
  }

  const userPrefs = prefs.filter((p) => p.source === 'user');
  const inferredPrefs = prefs.filter((p) => p.source === 'inferred');

  const locationDirty =
    locationCoords &&
    (locationText !== (profile?.home_location_text || '') ||
      locationCoords.lat !== profile?.home_lat ||
      locationCoords.lon !== profile?.home_lon);

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
            {userPrefs.map((pref) =>
              editId === pref.id ? (
                <div key={pref.id} className="profile__pref-tile profile__pref-tile--editing">
                  <input
                    ref={editRef}
                    className="profile__pref-input"
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit(pref);
                      if (e.key === 'Escape') cancelEdit();
                    }}
                  />
                  <div className="profile__pref-actions">
                    <button onClick={() => saveEdit(pref)}>Save</button>
                    <button className="ghost" onClick={cancelEdit}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div key={pref.id} className="profile__pref-tile">
                  <span className="profile__pref-text">{pref.text}</span>
                  <div className="profile__pref-actions">
                    <button className="ghost" onClick={() => startEdit(pref)}>Edit</button>
                    <button className="ghost danger" onClick={() => deletePref(pref)}>
                      Remove
                    </button>
                  </div>
                </div>
              )
            )}
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
              {inferredPrefs.map((pref) =>
                editId === pref.id ? (
                  <div key={pref.id} className="profile__pref-tile profile__pref-tile--editing">
                    <input
                      ref={editRef}
                      className="profile__pref-input"
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveEdit(pref);
                        if (e.key === 'Escape') cancelEdit();
                      }}
                    />
                    <div className="profile__pref-actions">
                      <button onClick={() => saveEdit(pref)}>Save</button>
                      <button className="ghost" onClick={cancelEdit}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div key={pref.id} className="profile__pref-tile">
                    <span className="profile__pref-text">{pref.text}</span>
                    <span className="chip chip--on-attr profile__pref-badge">
                      inferred{pref.evidence_ids?.length > 0 ? ` · from ${pref.evidence_ids.length} outfits` : ''}
                    </span>
                    <div className="profile__pref-actions">
                      <button className="ghost" onClick={() => startEdit(pref)}>
                        Edit &amp; own
                      </button>
                      <button className="ghost danger" onClick={() => deletePref(pref)}>
                        Dismiss
                      </button>
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
