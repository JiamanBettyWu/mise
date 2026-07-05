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
          <button
            type="button"
            className={`chip ${!item.available ? 'chip--on-laundry' : ''}`}
            aria-pressed={!item.available}
            disabled={busy}
            onClick={(e) => patch({ available: !item.available }, e)}
          >
            <span className="chip__dot" />
            In laundry
          </button>
          <button
            type="button"
            className={`chip ${item.in_travel_bag ? 'chip--on-packed' : ''}`}
            aria-pressed={item.in_travel_bag}
            disabled={busy}
            onClick={(e) => patch({ in_travel_bag: !item.in_travel_bag }, e)}
          >
            <span className="chip__dot" />
            {item.in_travel_bag ? 'Packed' : 'Pack'}
          </button>
        </div>
      </div>
    </div>
  );
}
