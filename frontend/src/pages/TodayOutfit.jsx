import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api.js';

export default function TodayOutfit() {
  const [travelMode, setTravelMode] = useState(false);
  const [notes, setNotes] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const generate = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.recommend({ travel_mode: travelMode, notes, n: 3 });
      setData(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [travelMode, notes]);

  // Auto-generate on first mount only. Re-runs are user-triggered (toggle / regenerate).
  useEffect(() => {
    generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
            {loading ? 'Thinking…' : 'Regenerate'}
          </button>
        </div>
      </div>

      {data?.weather && <WeatherStrip w={data.weather} />}

      <label className="field" style={{ marginTop: '1rem' }}>
        <span className="muted">
          Anything special about today? (optional — e.g. "client meeting", "long walk")
        </span>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => { if (notes) generate(); }}
          placeholder="Press Tab/click out to apply"
        />
      </label>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Picking outfits…</p>}

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

function WeatherStrip({ w }) {
  return (
    <div className="weather">
      <span><strong>{w.temp_high_c}°C</strong> high · <strong>{w.temp_low_c}°C</strong> low</span>
      <span>· {w.conditions}</span>
      <span>· {Math.round(w.precip_chance * 100)}% precip</span>
      <span>· {w.wind_kmh} km/h wind</span>
    </div>
  );
}

function Outfit({ index, outfit }) {
  return (
    <div className="outfit">
      <div className="outfit__header">
        <h3>Option {index + 1}</h3>
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
