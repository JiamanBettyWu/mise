import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api.js';
import { getCurrentPosition } from '../services/geo.js';

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [usingMyLocation, setUsingMyLocation] = useState(false);
  const coordsRef = useRef(null);

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

  const generate = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const coords = coordsRef.current || (await getCurrentPosition());
      coordsRef.current = coords;
      setUsingMyLocation(!!coords);
      const result = await api.recommend({
        travel_mode: travelMode,
        notes,
        n: 3,
        lat: coords?.lat ?? null,
        lon: coords?.lon ?? null,
      });
      setData(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [travelMode, notes]);

  return (
    <div>
      <div className="page-header">
        <h1>Today's outfit</h1>
        <div className="page-header__actions">
          <label>
            <input
              type="checkbox"
              checked={travelMode}
              onChange={(e) => setTravelMode(e.target.checked)}
            />
            Travel mode
          </label>
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

        <div>
          <button onClick={generate} disabled={loading}>
            {loading ? 'Thinking…' : data ? 'Regenerate' : 'Generate'}
          </button>
        </div>

        {error && <p className="error">{error}</p>}
      </div>

      {data?.weather && <WeatherStrip w={data.weather} usingMyLocation={usingMyLocation} />}

      {loading && <p className="muted">Picking outfits…</p>}

      {!data && !loading && !error && (
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
        <Outfit key={i} index={i} outfit={outfit} />
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

function Outfit({ index, outfit }) {
  const heading = outfit.label || `Option ${index + 1}`;
  const empty = !outfit.items?.length;
  return (
    <div className={`outfit ${empty ? 'outfit--empty' : ''}`}>
      <div className="outfit__header">
        <h3>{heading}</h3>
        <p className="outfit__reasoning muted">{outfit.reasoning}</p>
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
    </div>
  );
}
