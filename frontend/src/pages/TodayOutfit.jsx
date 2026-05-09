import { useCallback, useRef, useState } from 'react';
import { api } from '../services/api.js';
import { getCurrentPosition } from '../services/geo.js';

export default function TodayOutfit() {
  const [travelMode, setTravelMode] = useState(false);
  const [notes, setNotes] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [usingMyLocation, setUsingMyLocation] = useState(false);
  const coordsRef = useRef(null);

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
          <button onClick={generate} disabled={loading}>
            {loading ? 'Thinking…' : data ? 'Regenerate' : 'Generate'}
          </button>
        </div>
      </div>

      <label className="field" style={{ marginTop: '1rem' }}>
        <span className="muted">
          Anything special about today? (optional — e.g. "client meeting", "long walk")
        </span>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Describe the occasion, then click Generate"
        />
      </label>

      {data?.weather && <WeatherStrip w={data.weather} usingMyLocation={usingMyLocation} />}

      {error && <p className="error">{error}</p>}
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
  return (
    <div className="outfit">
      <div className="outfit__header">
        <h3>{heading}</h3>
        <p className="outfit__reasoning muted">{outfit.reasoning}</p>
      </div>
      <div className="outfit__items">
        {outfit.items.map((item) => (
          <div key={item.id} className="outfit__item">
            <img src={item.photo_url} alt={item.name} />
            <div className="outfit__item-name">{item.name}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
