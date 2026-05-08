import { useState } from 'react';
import { api } from '../services/api.js';

export default function ClothingCard({ item, onChange, onDelete }) {
  const [busy, setBusy] = useState(false);

  async function patch(fields) {
    setBusy(true);
    try {
      const updated = await api.patchClothing(item.id, fields);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(`Delete "${item.name}"?`)) return;
    setBusy(true);
    try {
      await api.deleteClothing(item.id);
      onDelete?.(item.id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`card ${item.available ? '' : 'card--unavailable'}`}>
      <img src={item.photo_url} alt={item.name} className="card__photo" />
      <div className="card__body">
        <div className="card__name">{item.name}</div>
        <div className="card__tags muted">
          {item.type} · {item.color} · {item.formality} · {item.season}
        </div>
        <div className="card__actions">
          <label>
            <input
              type="checkbox"
              checked={!item.available}
              onChange={(e) => patch({ available: !e.target.checked })}
              disabled={busy}
            />
            In laundry
          </label>
          <label>
            <input
              type="checkbox"
              checked={item.in_travel_bag}
              onChange={(e) => patch({ in_travel_bag: e.target.checked })}
              disabled={busy}
            />
            Packed
          </label>
          <button onClick={remove} disabled={busy} className="link-btn">
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
