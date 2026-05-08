import { useEffect, useState } from 'react';
import { api } from '../services/api.js';
import ClothingFields from './ClothingFields.jsx';

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
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose} aria-label="Close">×</button>
        <img src={item.photo_url} alt={item.name} className="modal__photo" />

        {!editing ? (
          <div className="modal__body">
            <h2>{item.name}</h2>
            <div className="muted">
              {item.type} · {item.color} · {item.formality} · {item.season} · {item.fabric}
            </div>
            {item.brand && <div className="muted">Brand: {item.brand}</div>}
            {item.description && <p>{item.description}</p>}
            {item.notes && <p className="muted">Notes: {item.notes}</p>}
            <div className="muted">
              {item.available ? 'Available' : 'In laundry'}
              {item.in_travel_bag ? ' · Packed' : ''}
            </div>
            <div className="modal__actions">
              <button onClick={() => { setDraft(item); setEditing(true); }}>Edit</button>
              <button onClick={remove} disabled={busy} className="danger">Delete</button>
            </div>
          </div>
        ) : (
          <div className="modal__body">
            <ClothingFields value={draft} onChange={setDraft} />
            <div className="modal__actions">
              <button onClick={save} disabled={busy}>
                {busy ? 'Saving…' : 'Save'}
              </button>
              <button onClick={() => { setEditing(false); setDraft(item); setError(''); }} disabled={busy}>
                Cancel
              </button>
            </div>
          </div>
        )}
        {error && <div className="error">{error}</div>}
      </div>
    </div>
  );
}
