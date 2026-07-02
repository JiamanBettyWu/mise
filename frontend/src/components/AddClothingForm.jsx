import { useState } from 'react';
import { api } from '../services/api.js';
import { compressImage } from '../services/image.js';
import ClothingFields from './ClothingFields.jsx';

export default function AddClothingForm({ onSaved }) {
  const [stage, setStage] = useState('pick'); // pick | tagging | review | saving
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [draft, setDraft] = useState(null);

  async function handleFile(e) {
    const picked = e.target.files?.[0];
    if (!picked) return;
    setError('');
    setNotice('');
    setStage('tagging');
    try {
      const file = await compressImage(picked);
      let tags = await api.uploadAndTag(file);
      if (Array.isArray(tags)) {
        if (!tags.length) {
          setNotice('No items detected — try another photo.');
          setStage('pick');
          return;
        }
        tags = tags[0];
      }
      setDraft({
        ...tags,
        brand: tags.brand || '',
        description: tags.description || '',
        available: true,
        in_travel_bag: false,
        notes: '',
      });
      setStage('review');
    } catch (err) {
      setError(String(err));
      setStage('pick');
    }
  }

  async function save() {
    setStage('saving');
    setError('');
    try {
      const payload = { ...draft, brand: draft.brand?.trim() || null };
      const saved = await api.createClothing(payload);
      onSaved?.(saved);
      setDraft(null);
      setStage('pick');
    } catch (err) {
      setError(String(err));
      setStage('review');
    }
  }

  if (stage === 'pick' || stage === 'tagging') {
    return (
      <div className="form">
        <label className="file-input">
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/heic"
            onChange={handleFile}
            disabled={stage === 'tagging'}
          />
          <span>{stage === 'tagging' ? 'AI is tagging…' : 'Choose a photo'}</span>
        </label>
        {notice && <div className="muted">{notice}</div>}
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  return (
    <div className="form">
      <img src={draft.photo_url} alt="" className="form__preview" />
      <ClothingFields value={draft} onChange={setDraft} />
      <div className="form__actions">
        <button onClick={save} disabled={stage === 'saving'}>
          {stage === 'saving' ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={() => { setDraft(null); setStage('pick'); }}
          disabled={stage === 'saving'}
        >
          Discard
        </button>
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  );
}
