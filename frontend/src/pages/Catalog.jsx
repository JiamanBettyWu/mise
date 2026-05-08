import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import ClothingCard from '../components/ClothingCard.jsx';
import { api } from '../services/api.js';

export default function Catalog() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [travelMode, setTravelMode] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.listClothing()
      .then(setItems)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  function handleChange(updated) {
    setItems((arr) => arr.map((i) => (i.id === updated.id ? updated : i)));
  }
  function handleDelete(id) {
    setItems((arr) => arr.filter((i) => i.id !== id));
  }

  const visible = travelMode ? items.filter((i) => i.in_travel_bag) : items;

  return (
    <div>
      <div className="page-header">
        <h1>Catalog</h1>
        <div className="page-header__actions">
          <label>
            <input
              type="checkbox"
              checked={travelMode}
              onChange={(e) => setTravelMode(e.target.checked)}
            />
            Travel mode
          </label>
          <Link to="/add"><button>Add item</button></Link>
        </div>
      </div>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && visible.length === 0 && (
        <p className="muted">
          {travelMode ? 'Nothing packed yet.' : 'No items yet — add your first.'}
        </p>
      )}

      <div className="grid">
        {visible.map((item) => (
          <ClothingCard
            key={item.id}
            item={item}
            onChange={handleChange}
            onDelete={handleDelete}
          />
        ))}
      </div>
    </div>
  );
}
