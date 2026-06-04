import { useState } from 'react';
import { api } from '../services/api.js';
import './ClothingCardGlass.css';

// Glass variant — Wispr-inspired glassmorphism + soft minimalism.
// Try changing: blur intensity, border-radius, shadow softness, hover lift.

export default function ClothingCardGlass({ item, onChange, onOpen }) {
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
      className={`glass-card ${item.available ? '' : 'glass-card--unavailable'}`}
      onClick={() => onOpen?.(item)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen?.(item); }}
    >
      <div className="glass-card__photo-wrap">
        <img src={item.photo_url} alt={item.name} className="glass-card__photo" />
      </div>
      <div className="glass-card__body">
        <div className="glass-card__name">{item.name}</div>
        <div className="glass-card__tags">
          {item.type} · {item.color}
        </div>
        <div className="glass-card__actions" onClick={(e) => e.stopPropagation()}>
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
