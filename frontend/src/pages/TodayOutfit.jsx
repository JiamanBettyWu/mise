import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import { api } from '../services/api.js';
import {
  clearError as clearGenError,
  consumeResult,
  getSnapshot,
  startGeneration,
  subscribe,
} from '../services/todayGeneration.js';

const STORAGE_KEY = 'today_state';

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

// Today's outfit is by definition for today — drop anything generated on a
// prior day. Unparseable payloads also reset rather than crash on stale shapes.
function hydrate() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.generatedOn && parsed.generatedOn !== todayISO()) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export default function TodayOutfit() {
  const persisted = hydrate();
  const [travelMode, setTravelMode] = useState(persisted?.form?.travelMode ?? false);
  const [notes, setNotes] = useState(persisted?.form?.notes ?? '');
  const [data, setData] = useState(persisted?.data ?? null);
  const [error, setError] = useState('');

  // Generation lives in a module-scope store so it survives navigating away
  // mid-request; we subscribe here and adopt the result when it lands.
  const gen = useSyncExternalStore(subscribe, getSnapshot);
  const { loading, usingMyLocation } = gen;

  useEffect(() => {
    if (gen.result) {
      setData(gen.result);
      consumeResult();
    }
  }, [gen.result]);

  useEffect(() => {
    const isEmpty = !notes && !data && !travelMode;
    if (isEmpty) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        form: { travelMode, notes },
        data,
        generatedOn: data ? todayISO() : null,
      })
    );
  }, [travelMode, notes, data]);

  // Discard notes + results and start over. Travel mode is preserved — it's a
  // standing preference (mirrors the page-header toggle), not part of one ask.
  function clear() {
    setNotes('');
    setData(null);
    setError('');
    clearGenError();
  }

  // Web twin of the email 👍/👎 (#41): same outfit_history row, authed POST
  // instead of a signed token. Optimistic — revert on failure. Tapping the
  // active thumb clears the verdict (verdict 0); the other thumb switches.
  // Every tap also drops any attribution (#60) — the backend wipes it too.
  const sendFeedback = useCallback(
    async (index, verdict) => {
      const outfit = data?.outfits?.[index];
      if (!outfit?.history_id) return;
      const next = outfit.feedback === verdict ? 0 : verdict;
      const apply = (fb, attribution) =>
        setData((d) => ({
          ...d,
          outfits: d.outfits.map((o, i) =>
            i === index ? { ...o, feedback: fb, attribution } : o
          ),
        }));
      apply(next || null, null);
      try {
        await api.outfitFeedback(outfit.history_id, next);
      } catch (e) {
        apply(outfit.feedback ?? null, outfit.attribution ?? null);
        setError(String(e));
      }
    },
    [data]
  );

  // Optional 👎 follow-up (#60). Not optimistic — the chips collapse into
  // "Noted" only once the attribution actually landed.
  const sendAttribution = useCallback(
    async (index, payload) => {
      const outfit = data?.outfits?.[index];
      if (!outfit?.history_id) return;
      await api.outfitAttribution(outfit.history_id, payload);
      setData((d) => ({
        ...d,
        outfits: d.outfits.map((o, i) =>
          i === index ? { ...o, attribution: payload } : o
        ),
      }));
    },
    [data]
  );

  // Local-only: she declined the follow-up, so stop offering it for this
  // verdict. A later verdict tap resets attribution and re-offers.
  const skipAttribution = useCallback((index) => {
    setData((d) => ({
      ...d,
      outfits: d.outfits.map((o, i) =>
        i === index ? { ...o, attribution: { skipped: true } } : o
      ),
    }));
  }, []);

  // Multi-turn refinement (#145): each turn revises the same outfit_history
  // row server-side (history_id doubles as the conversation thread id), so
  // the card swaps items in place and any verdict resets — it judged the
  // old items, and the backend already cleared it.
  const sendRefine = useCallback(
    async (index, message) => {
      const outfit = data?.outfits?.[index];
      if (!outfit?.history_id) return;
      const revised = await api.outfitRefine(outfit.history_id, message);
      setData((d) => ({
        ...d,
        outfits: d.outfits.map((o, i) =>
          i === index
            ? {
                ...o,
                items: revised.items,
                reasoning: revised.reasoning,
                feedback: null,
                attribution: null,
              }
            : o
        ),
      }));
    },
    [data]
  );

  const generate = useCallback(() => {
    setError('');
    startGeneration({ travelMode, notes });
  }, [travelMode, notes]);

  return (
    <div>
      <div className="page-header">
        <h1>Today's outfit</h1>
        <div className="page-header__actions">
          <button
            className="switch"
            role="switch"
            aria-checked={travelMode}
            onClick={() => setTravelMode(!travelMode)}
          >
            <span className="switch__track" aria-hidden="true" />
            Travel mode
          </button>
        </div>
      </div>

      <div className="form-page">
        <label className="field">
          <span className="muted">
            Anything special about today? (optional — e.g. "client meeting", "long walk")
          </span>
          <textarea
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Describe the occasion, then click Generate"
          />
        </label>

        <div className="form-page__actions">
          <button onClick={generate} disabled={loading}>
            {loading ? 'Thinking…' : data ? 'Regenerate' : 'Generate'}
          </button>
          {(data || notes) && (
            <button
              type="button"
              className="ghost"
              onClick={clear}
              disabled={loading}
            >
              Clear
            </button>
          )}
        </div>

        {(gen.error || error) && <p className="error">{gen.error || error}</p>}
      </div>

      {data?.weather && <WeatherStrip w={data.weather} usingMyLocation={usingMyLocation} />}

      {loading && <p className="muted">Picking outfits…</p>}

      {!data && !loading && !error && !gen.error && (
        <p className="muted" style={{ marginTop: '1rem' }}>
          Click <strong>Generate</strong> to get suggestions for today. For your
          regular daily picks, check your morning email.
        </p>
      )}

      {data?.outfits?.length === 0 && !loading && (
        <p className="muted">
          {travelMode
            ? 'Nothing packed — turn off travel mode or pack some items.'
            : 'No available items — add some clothes first.'}
        </p>
      )}

      {data?.outfits?.map((outfit, i) => (
        <Outfit
          key={i}
          index={i}
          outfit={outfit}
          onFeedback={sendFeedback}
          onAttribution={sendAttribution}
          onSkipAttribution={skipAttribution}
          onRefine={sendRefine}
        />
      ))}
    </div>
  );
}

function WeatherStrip({ w, usingMyLocation }) {
  return (
    <div className="weather">
      <span><strong>{w.temp_high_c}°C</strong> high · <strong>{w.temp_low_c}°C</strong> low</span>
      <span>· {w.conditions}</span>
      <span>· {Math.round(w.precip_chance * 100)}% precip</span>
      <span>· {w.wind_kmh} km/h wind</span>
      <span className="muted">· {usingMyLocation ? 'your location' : 'home'}</span>
    </div>
  );
}

function Outfit({ index, outfit, onFeedback, onAttribution, onSkipAttribution, onRefine }) {
  const heading = outfit.label || `Option ${index + 1}`;
  const empty = !outfit.items?.length;
  const offerAttribution = !empty && outfit.history_id && outfit.feedback === -1;
  return (
    <div className={`outfit ${empty ? 'outfit--empty' : ''}`}>
      <div className="outfit__header">
        <div className="outfit__header-row">
          <h3>{heading}</h3>
          {!empty && outfit.history_id && (
            <div className="outfit__feedback">
              <button
                type="button"
                className={`chip ${outfit.feedback === 1 ? 'chip--on-verdict' : ''}`}
                aria-pressed={outfit.feedback === 1}
                aria-label="Thumbs up"
                onClick={() => onFeedback(index, 1)}
              >
                👍
              </button>
              <button
                type="button"
                className={`chip ${outfit.feedback === -1 ? 'chip--on-verdict' : ''}`}
                aria-pressed={outfit.feedback === -1}
                aria-label="Thumbs down"
                onClick={() => onFeedback(index, -1)}
              >
                👎
              </button>
            </div>
          )}
        </div>
        <p className="outfit__reasoning muted">{outfit.reasoning}</p>
        {offerAttribution &&
          (outfit.attribution ? (
            !outfit.attribution.skipped && (
              <p className="muted" style={{ margin: '0.5rem 0 0.25rem' }}>
                Noted — thanks.
              </p>
            )
          ) : (
            <AttributionComposer
              outfit={outfit}
              onSubmit={(payload) => onAttribution(index, payload)}
              onSkip={() => onSkipAttribution(index)}
            />
          ))}
      </div>
      {!empty && (
        <div className="outfit__items">
          {outfit.items.map((item) => (
            <div key={item.id} className="outfit__item">
              <img src={item.photo_url} alt={item.name} />
              <div className="outfit__item-name">{item.name}</div>
            </div>
          ))}
        </div>
      )}
      {!empty && outfit.history_id && (
        <RefineComposer onRefine={(message) => onRefine(index, message)} />
      )}
    </div>
  );
}

// Multi-turn refinement (#145): a collapsed ghost chip that expands into an
// inline composer (the attribution-composer precedent — optional follow-ups
// never open modals). Stays open after a turn so the conversation continues;
// the card itself re-rendering with new items is the success signal.
function RefineComposer({ onRefine }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!open) {
    return (
      <div className="outfit__refine">
        <button type="button" className="chip" onClick={() => setOpen(true)}>
          Refine
        </button>
      </div>
    );
  }

  async function submit() {
    setSending(true);
    setFailed(false);
    try {
      await onRefine(message.trim());
      setMessage('');
    } catch {
      setFailed(true);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="outfit__refine">
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && message.trim() && !sending) submit();
        }}
        placeholder='e.g. "swap the shoes for something more comfortable"'
        autoFocus
      />
      <button type="button" onClick={submit} disabled={!message.trim() || sending}>
        {sending ? 'Refining…' : 'Refine'}
      </button>
      <button
        type="button"
        className="ghost"
        onClick={() => setOpen(false)}
        disabled={sending}
      >
        Close
      </button>
      {failed && <span className="error">Couldn't refine — try again.</span>}
    </div>
  );
}

// Optional 👎 follow-up (#60): turns a bare thumbs-down into an attributed
// one. Item chips imply "specific items" and are exclusive with the three
// outfit-level reason chips; at most one reason. Entirely skippable — the
// verdict was already recorded the moment the thumb was tapped.
function AttributionComposer({ outfit, onSubmit, onSkip }) {
  const [itemIds, setItemIds] = useState([]);
  const [reason, setReason] = useState(null);
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState(false);

  const toggleItem = (id) => {
    setReason(null);
    setItemIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  };
  const pickReason = (r) => {
    setItemIds([]);
    setReason((cur) => (cur === r ? null : r));
  };

  const effectiveReason = itemIds.length ? 'specific_items' : reason;
  const canSend = !!effectiveReason || !!note.trim();

  async function submit() {
    setSending(true);
    setFailed(false);
    try {
      await onSubmit({ reason: effectiveReason, item_ids: itemIds, note: note.trim() });
    } catch {
      setFailed(true);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="outfit__attribution">
      <span className="muted">What was off? (optional)</span>
      {outfit.items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`chip ${itemIds.includes(item.id) ? 'chip--on-attr' : ''}`}
          aria-pressed={itemIds.includes(item.id)}
          onClick={() => toggleItem(item.id)}
        >
          {item.name}
        </button>
      ))}
      {[
        ['combination', 'The combo'],
        ['weather', 'Weather call'],
        ['occasion', 'Occasion'],
      ].map(([r, label]) => (
        <button
          key={r}
          type="button"
          className={`chip ${reason === r ? 'chip--on-attr' : ''}`}
          aria-pressed={reason === r}
          onClick={() => pickReason(r)}
        >
          {label}
        </button>
      ))}
      <input
        type="text"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Anything else? (optional)"
      />
      <button type="button" onClick={submit} disabled={!canSend || sending}>
        {sending ? 'Sending…' : 'Send'}
      </button>
      <button type="button" className="ghost" onClick={onSkip} disabled={sending}>
        Skip
      </button>
      {failed && <span className="error">Couldn't save — try again.</span>}
    </div>
  );
}
