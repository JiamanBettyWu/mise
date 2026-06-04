import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import ClothingCard from '../components/ClothingCard.jsx';
import ClothingCardGlass from '../components/ClothingCardGlass.jsx';
import ClothingCardEditorial from '../components/ClothingCardEditorial.jsx';
import ItemDetailModal from '../components/ItemDetailModal.jsx';
import { api } from '../services/api.js';

// Design experiment: swap between three card variants to compare styles.
// Remove the picker + extra imports once a winner is picked.
const CARD_VARIANTS = {
  original: ClothingCard,
  glass: ClothingCardGlass,
  editorial: ClothingCardEditorial,
};

export default function Catalog() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [travelMode, setTravelMode] = useState(false);
  const [openItem, setOpenItem] = useState(null);
  const [query, setQuery] = useState('');
  const [variant, setVariant] = useState(
    () => localStorage.getItem('card-variant') || 'original'
  );
  useEffect(() => { localStorage.setItem('card-variant', variant); }, [variant]);
  const CardComponent = CARD_VARIANTS[variant] ?? ClothingCard;

  useEffect(() => {
    setLoading(true);
    api.listClothing()
      .then(setItems)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  function handleChange(updated) {
    setItems((arr) => arr.map((i) => (i.id === updated.id ? updated : i)));
    if (openItem?.id === updated.id) setOpenItem(updated);
  }
  function handleDelete(id) {
    setItems((arr) => arr.filter((i) => i.id !== id));
  }

  const visible = useMemo(() => {
    let list = travelMode ? items.filter((i) => i.in_travel_bag) : items;
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter((i) =>
        [i.name, i.type, i.color, i.brand, i.fabric, i.description, i.notes]
          .some((f) => (f || '').toLowerCase().includes(q))
      );
    }
    return list;
  }, [items, travelMode, query]);

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

      <input
        className="search-bar"
        type="search"
        placeholder="Search name, type, color, brand…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      <div className="variant-picker">
        <span className="variant-picker__label">Card style:</span>
        {Object.keys(CARD_VARIANTS).map((key) => (
          <button
            key={key}
            type="button"
            className={`variant-picker__btn ${variant === key ? 'is-active' : ''}`}
            onClick={() => setVariant(key)}
          >
            {key}
          </button>
        ))}
      </div>

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && visible.length === 0 && (
        <p className="muted">
          {query
            ? `No matches for "${query}".`
            : travelMode
              ? 'Nothing packed yet.'
              : 'No items yet — add your first.'}
        </p>
      )}

      <div className="grid">
        {visible.map((item) => (
          <CardComponent
            key={item.id}
            item={item}
            onChange={handleChange}
            onOpen={setOpenItem}
          />
        ))}
      </div>

      {openItem && (
        <ItemDetailModal
          item={openItem}
          onClose={() => setOpenItem(null)}
          onChange={handleChange}
          onDelete={handleDelete}
        />
      )}
    </div>
  );
}
