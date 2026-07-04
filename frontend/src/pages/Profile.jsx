import { useEffect, useRef, useState } from 'react';
import DestinationCombobox from '../components/DestinationCombobox.jsx';
import { api, setStoredPassword } from '../services/api.js';

// Relative "time ago" for the inference job's last-success heartbeat (#62).
// Days is the largest unit on purpose: a weekly job reads clearest in days
// ("9 days ago" = a run was missed), and "last week"/"last month" are too
// vague for a staleness signal. Returns null for missing/unparseable input.
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

const STAT_RANGES = [
  ['7d', '7 days'],
  ['30d', '30 days'],
  ['90d', '90 days'],
  ['all', 'All time'],
];

// Human-readable labels for llm_usage call_type keys (#115). Unknown keys
// fall back to the raw key so new call types render without a code change.
const CALL_TYPE_LABELS = {
  daily_outfit: 'Daily outfits',
  tag_photo: 'Photo tagging',
  tag_photo_multi: 'Photo tagging (multi)',
  trip_plan: 'Trip plans',
  trip_climate_infer: 'Trip climate',
  purchase_query_plan: 'Shopping queries',
  mode_classify: 'Calendar modes',
  pref_inference: 'Preference review',
  repair: 'Outfit repair',
};

// "since June 2026" label for the All-time asymmetry: token data only exists
// from #114's deploy onward, so all-time cost undercounts earlier history.
function monthOf(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}

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
        <span className="profile__pref-badge">
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

  // Shopping department (#82) auto-saves on change — see saveDepartment.
  const [deptSaving, setDeptSaving] = useState(false);

  const [prefs, setPrefs] = useState([]);
  const [newText, setNewText] = useState('');
  const [adding, setAdding] = useState(false);

  // Flash counters: bumping remounts the <Flash> (key) and restarts its fade.
  const [locationFlash, setLocationFlash] = useState(0);
  const [deptFlash, setDeptFlash] = useState(0);
  const [prefsFlash, setPrefsFlash] = useState({ n: 0, msg: '' });

  // Failed requests must be visible — a dead backend otherwise reads as
  // "my preferences vanished" (or never listed at all).
  const [loadError, setLoadError] = useState('');
  const [locationError, setLocationError] = useState('');
  const [deptError, setDeptError] = useState('');
  const [prefsError, setPrefsError] = useState('');

  // Stats (#115)
  const [statsRange, setStatsRange] = useState('30d');
  const [stats, setStats] = useState(null);
  const [statsError, setStatsError] = useState('');

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

  // Refetch stats whenever the range changes; guard against a slow older
  // response landing after a newer one (rapid range clicking).
  useEffect(() => {
    let stale = false;
    setStatsError('');
    api.getStats(statsRange)
      .then((s) => { if (!stale) setStats(s); })
      .catch((err) => {
        if (!stale) setStatsError(`Couldn’t load stats: ${err?.message ?? 'unknown error'}`);
      });
    return () => { stale = true; };
  }, [statsRange]);

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

  // ---- Shopping department (#82) -------------------------------------------

  // Auto-saves on change (a 4-option select doesn't warrant a Save button).
  // Optimistic with rollback: flip the control immediately, then revert + show
  // an error if the PUT fails, so the control never silently disagrees with the
  // backend. "No preference" is the string 'no_preference', never null — a null
  // shopping_department is dropped by PUT /profile and would leave the value
  // unchanged. (See DESIGN.md 2026-06-26 for the auto-save rule.)
  async function saveDepartment(next) {
    const prev = profile?.shopping_department ?? 'womens';
    if (next === prev) return;
    setProfile((p) => ({ ...p, shopping_department: next })); // optimistic
    setDeptSaving(true);
    setDeptError('');
    try {
      const updated = await api.updateProfile({ shopping_department: next });
      setProfile(updated);
      setDeptFlash((n) => n + 1);
    } catch (err) {
      setProfile((p) => ({ ...p, shopping_department: prev })); // roll back
      setDeptError(`Save failed: ${err?.message ?? 'unknown error'}`);
    } finally {
      setDeptSaving(false);
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
    const action = pref.source === 'inferred' ? 'Dismiss' : 'Remove';
    if (!confirm(`${action} "${pref.text}"?`)) return;
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
  const reviewedAgo = timeAgo(profile?.preferences_reviewed_at);

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

          <div className="profile__subfield">
            <label className="profile__label" htmlFor="shopping-dept">
              Shopping department
            </label>
            <p className="profile__hint muted">
              Which retail section the trip planner searches when it suggests
              items to buy. About shopping results, not identity.
            </p>
            <div className="profile__dept-row">
              <select
                id="shopping-dept"
                className="profile__dept-select"
                value={profile?.shopping_department ?? 'womens'}
                onChange={(e) => saveDepartment(e.target.value)}
                disabled={deptSaving}
              >
                <option value="womens">Women’s</option>
                <option value="mens">Men’s</option>
                <option value="unisex">Unisex</option>
                <option value="no_preference">No preference</option>
              </select>
              {deptFlash > 0 && <Flash key={deptFlash}>Saved</Flash>}
            </div>
            {deptError && <div className="error">{deptError}</div>}
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
            {prefsFlash.n > 0 && <Flash key={prefsFlash.n}>{prefsFlash.msg}</Flash>}
          </form>
          {prefsError && <div className="error">{prefsError}</div>}
        </section>

        {/* ---- Learned from your feedback ---- */}
        <section className="profile__section">
          <div className="profile__section-head">
            <h2 className="profile__section-heading">Learned from your feedback</h2>
            {reviewedAgo && (
              <span
                className="profile__reviewed muted"
                title={profile.preferences_reviewed_at}
              >
                Reviewed {reviewedAgo}
              </span>
            )}
          </div>
          <p className="profile__hint muted">
            Distilled from your feedback each week, once ~10 outfits are rated. Soft
            nudges, not rules.
          </p>
          {inferredPrefs.length === 0 ? (
            <p className="profile__empty muted">
              {profile?.preferences_reviewed_at
                ? 'No patterns learned from your feedback yet.'
                : 'These appear after the weekly review job first runs.'}
            </p>
          ) : (
            <div className="profile__pref-list">
              {inferredPrefs.map((pref) => (
                <PrefTile key={pref.id} pref={pref} editing={editId === pref.id} {...tileHandlers} />
              ))}
            </div>
          )}
        </section>

        {/* ---- Your stats (#115) ---- */}
        <section className="profile__section">
          <div className="profile__section-head">
            <h2 className="profile__section-heading">Your stats</h2>
            <div className="profile__range" role="group" aria-label="Time range">
              {STAT_RANGES.map(([key, label]) => (
                <button
                  key={key}
                  className={`chip${statsRange === key ? ' chip--on-range' : ''}`}
                  aria-pressed={statsRange === key}
                  onClick={() => setStatsRange(key)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {statsError && <div className="error">{statsError}</div>}

          {stats && (
            <>
              <div className="profile__stat-tiles">
                <div className="profile__stat-tile">
                  <span className="profile__stat-value">{stats.outfits}</span>
                  <span className="profile__stat-label">outfits recommended</span>
                </div>
                <div className="profile__stat-tile">
                  <span className="profile__stat-value">
                    {stats.feedback_count}
                    {stats.thumbs_up_rate != null && (
                      <span className="profile__stat-sub">
                        {' '}· {Math.round(stats.thumbs_up_rate * 100)}% 👍
                      </span>
                    )}
                  </span>
                  <span className="profile__stat-label">verdicts given</span>
                </div>
                <div className="profile__stat-tile">
                  <span className="profile__stat-value">{stats.trips}</span>
                  <span className="profile__stat-label">trips planned</span>
                </div>
              </div>

              <div className="profile__usage">
                <p className="profile__usage-total">
                  {stats.usage.total_tokens.toLocaleString()} tokens ·{' '}
                  ~${stats.usage.estimated_cost.toFixed(2)}{' '}
                  <span className="muted">
                    estimated
                    {statsRange === 'all' && stats.usage_since
                      ? ` · since ${monthOf(stats.usage_since)}`
                      : ''}
                  </span>
                </p>
                {(() => {
                  const entries = Object.entries(stats.usage.by_call_type)
                    .sort((a, b) => b[1].tokens - a[1].tokens);
                  const max = entries[0]?.[1].tokens || 1;
                  return entries.map(([key, v]) => (
                    <div key={key} className="profile__usage-row">
                      <span className="profile__usage-name">
                        {CALL_TYPE_LABELS[key] || key}
                      </span>
                      <div className="profile__usage-bar">
                        <div
                          className="profile__usage-fill"
                          style={{ width: `${Math.max(2, (v.tokens / max) * 100)}%` }}
                        />
                      </div>
                      <span className="profile__usage-cost muted">
                        ${v.cost.toFixed(2)}
                      </span>
                    </div>
                  ));
                })()}
              </div>

              {stats.top_items.length > 0 && (
                <div className="profile__top-items">
                  <p className="profile__label">Most-recommended items</p>
                  <div className="profile__top-row">
                    {stats.top_items.map((item) => (
                      <div key={item.id} className="profile__top-item" title={item.name}>
                        <img src={item.photo_url} alt={item.name} />
                        <span className="profile__top-count">×{item.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
