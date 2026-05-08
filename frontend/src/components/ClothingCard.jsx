import { useState } from 'react';
import { api } from '../services/api.js';

export default function ClothingCard({ item, onChange, onOpen }) {
  const [busy, setBusy] = useState(false);

  async function patch(fields, e) {
    e?.stopPropagation();
    setBusy(true);
    try {
      const updated = await api.patchClothing(item.id, fields);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={`card ${item.available ? '' : 'card--unavailable'}`}
      onClick={() => onOpen?.(item)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen?.(item); }}
    >
      <img src={item.photo_url} alt={item.name} className="card__photo" />
      <div className="card__body">
        <div className="card__name">{item.name}</div>
        <div className="card__tags muted">
          {item.type} · {item.color}
        </div>
        <div className="card__actions" onClick={(e) => e.stopPropagation()}>
          <label>
            <input
              type="checkbox"
              checked={!item.available}
              onChange={(e) => patch({ available: !e.target.checked }, e)}
              disabled={busy}
            />
            In laundry
          </label>
          <label>
            <input
              type="checkbox"
              checked={item.in_travel_bag}
              onChange={(e) => patch({ in_travel_bag: e.target.checked }, e)}
              disabled={busy}
            />
            Packed
          </label>
        </div>
      </div>
    </div>
  );
}
