import { useState } from 'react';
import { api } from '../services/api.js';
import './ClothingCardEditorial.css';

// Editorial variant — OpenAI/Anthropic-inspired editorial minimalism.
// Try changing: serif font, tag/name order (tags act as a "kicker"),
// aspect ratio of the photo, divider weight.

export default function ClothingCardEditorial({ item, onChange, onOpen }) {
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
    <article
      className={`ed-card ${item.available ? '' : 'ed-card--unavailable'}`}
      onClick={() => onOpen?.(item)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen?.(item); }}
    >
      <div className="ed-card__photo-wrap">
        <img src={item.photo_url} alt={item.name} className="ed-card__photo" />
      </div>
      <div className="ed-card__body">
        <div className="ed-card__tags">{item.type} — {item.color}</div>
        <h3 className="ed-card__name">{item.name}</h3>
        <div className="ed-card__divider" />
        <div className="ed-card__actions" onClick={(e) => e.stopPropagation()}>
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
    </article>
  );
}
