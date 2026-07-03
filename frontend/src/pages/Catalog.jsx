import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import ClothingCardGlass from '../components/ClothingCardGlass.jsx';
import ItemDetailModal from '../components/ItemDetailModal.jsx';
import { api } from '../services/api.js';

export default function Catalog() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // Single mutually-exclusive view: 'all' | 'packed' | 'laundry'.
  // 'packed' is the old Travel-mode filter; 'laundry' is its mirror. One state
  // means picking one view clears the other for free (no coordinating booleans).
  const [view, setView] = useState('all');
  const [resetting, setResetting] = useState(false);
  const [openItem, setOpenItem] = useState(null);
  const [query, setQuery] = useState('');

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
    let list = items;
    if (view === 'packed') list = list.filter((i) => i.in_travel_bag);
    else if (view === 'laundry') list = list.filter((i) => !i.available);
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter((i) =>
        [i.name, i.type, i.color, i.brand, i.fabric, i.description, i.notes]
          .some((f) => (f || '').toLowerCase().includes(q))
      );
    }
    return list;
  }, [items, view, query]);

  // How many items the bulk reset would touch — counts the whole view set,
  // ignoring the search box (the button says "all", not "all matching").
  const resettableCount = useMemo(() => {
    if (view === 'packed') return items.filter((i) => i.in_travel_bag).length;
    if (view === 'laundry') return items.filter((i) => !i.available).length;
    return 0;
  }, [items, view]);

  async function bulkReset() {
    const isPacked = view === 'packed';
    const targets = items.filter((i) => (isPacked ? i.in_travel_bag : !i.available));
    if (targets.length === 0) return;
    const noun = isPacked ? 'packed' : 'laundry';
    const verb = isPacked ? 'Unpack' : 'Clear';
    const plural = targets.length === 1 ? '' : 's';
    if (!confirm(`${verb} all ${targets.length} ${noun} item${plural}?`)) return;

    const patch = isPacked ? { in_travel_bag: false } : { available: true };
    setResetting(true);
    try {
      const updated = await Promise.all(targets.map((i) => api.patchClothing(i.id, patch)));
      const byId = new Map(updated.map((u) => [u.id, u]));
      setItems((arr) => arr.map((i) => byId.get(i.id) || i));
    } catch (e) {
      setError(String(e));
    } finally {
      setResetting(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Catalog</h1>
        <div className="page-header__actions">
          <button
            className="switch"
            role="switch"
            aria-checked={view === 'packed'}
            onClick={() => setView(view === 'packed' ? 'all' : 'packed')}
          >
            <span className="switch__track" aria-hidden="true" />
            Travel mode
          </button>
          <button
            className="switch"
            role="switch"
            aria-checked={view === 'laundry'}
            onClick={() => setView(view === 'laundry' ? 'all' : 'laundry')}
          >
            <span className="switch__track" aria-hidden="true" />
            In laundry
          </button>
          {resettableCount > 0 && (
            <button className="ghost" onClick={bulkReset} disabled={resetting}>
              {view === 'packed' ? 'Unpack all' : 'Clear laundry'}
            </button>
          )}
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

      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && visible.length === 0 && (
        <p className="muted">
          {query
            ? `No matches for "${query}".`
            : view === 'packed'
              ? 'Nothing packed yet.'
              : view === 'laundry'
                ? 'Nothing in the laundry.'
                : 'No items yet — add your first.'}
        </p>
      )}

      <div className="grid">
        {visible.map((item) => (
          <ClothingCardGlass
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
