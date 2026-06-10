import { useEffect, useState } from 'react';
import { api } from '../services/api.js';
import ClothingFields from './ClothingFields.jsx';
import './ItemDetailModal.css';

export default function ItemDetailModal({ item, onClose, onChange, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function save() {
    setBusy(true);
    setError('');
    try {
      const patch = {
        name: draft.name,
        type: draft.type,
        color: draft.color,
        formality: draft.formality,
        season: draft.season,
        fabric: draft.fabric,
        warmth: draft.warmth ?? null,
        description: draft.description || '',
        brand: draft.brand?.trim() || null,
        notes: draft.notes || null,
      };
      const updated = await api.patchClothing(item.id, patch);
      onChange?.(updated);
      setDraft(updated);
      setEditing(false);
    } catch (err) {
      setError(String(err));
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
      onClose();
    } catch (err) {
      setError(String(err));
      setBusy(false);
    }
  }

  return (
    <div className="gmodal-backdrop" onClick={onClose}>
      <div className="gmodal" onClick={(e) => e.stopPropagation()}>
        <button className="gmodal__close" onClick={onClose} aria-label="Close">×</button>
        <img src={item.photo_url} alt={item.name} className="gmodal__photo" />

        {!editing ? (
          <div className="gmodal__body">
            <h2 className="gmodal__name">{item.name}</h2>
            <div className="gmodal__meta">
              {item.type} · {item.color} · {item.formality} · {item.season} · {item.fabric}
              {item.warmth != null && <> · warmth {item.warmth}/5</>}
            </div>
            {item.brand && <div className="gmodal__meta">Brand: {item.brand}</div>}
            {item.description && <p>{item.description}</p>}
            {item.notes && <p className="gmodal__meta">Notes: {item.notes}</p>}
            <div className="gmodal__meta">
              {item.available ? 'Available' : 'In laundry'}
              {item.in_travel_bag ? ' · Packed' : ''}
            </div>
            <div className="gmodal__actions">
              <button onClick={() => { setDraft(item); setEditing(true); }}>Edit</button>
              <button onClick={remove} disabled={busy} className="danger">Delete</button>
            </div>
          </div>
        ) : (
          <div className="gmodal__body">
            <ClothingFields value={draft} onChange={setDraft} />
            <div className="gmodal__actions">
              <button onClick={save} disabled={busy}>
                {busy ? 'Saving…' : 'Save'}
              </button>
              <button onClick={() => { setEditing(false); setDraft(item); setError(''); }} disabled={busy}>
                Cancel
              </button>
            </div>
          </div>
        )}
        {error && <p className="gmodal__error">{error}</p>}
      </div>
    </div>
  );
}
