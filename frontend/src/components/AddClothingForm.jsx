import { useState } from 'react';
import { api } from '../services/api.js';

const TYPES = [
  'jacket', 'coat', 'shirt', 't-shirt', 'sweater', 'blouse', 'dress', 'skirt',
  'trousers', 'jeans', 'shorts', 'shoes', 'boots', 'sneakers', 'sandals',
  'bag', 'scarf', 'hat', 'belt', 'accessory', 'other',
];
const FORMALITIES = ['casual', 'smart-casual', 'formal'];
const SEASONS = ['spring', 'summer', 'fall', 'winter', 'all-season'];

export default function AddClothingForm({ onSaved }) {
  const [stage, setStage] = useState('pick'); // pick | tagging | review | saving
  const [error, setError] = useState('');
  const [draft, setDraft] = useState(null);

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError('');
    setStage('tagging');
    try {
      const tags = await api.uploadAndTag(file);
      setDraft({ ...tags, available: true, in_travel_bag: false, notes: '' });
      setStage('review');
    } catch (err) {
      setError(String(err));
      setStage('pick');
    }
  }

  function setField(k, v) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  async function save() {
    setStage('saving');
    setError('');
    try {
      const saved = await api.createClothing(draft);
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
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  return (
    <div className="form">
      <img src={draft.photo_url} alt="" className="form__preview" />
      <Field label="Name">
        <input value={draft.name} onChange={(e) => setField('name', e.target.value)} />
      </Field>
      <Field label="Type">
        <select value={draft.type} onChange={(e) => setField('type', e.target.value)}>
          {TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
      </Field>
      <Field label="Color">
        <input value={draft.color} onChange={(e) => setField('color', e.target.value)} />
      </Field>
      <Field label="Formality">
        <select value={draft.formality} onChange={(e) => setField('formality', e.target.value)}>
          {FORMALITIES.map((f) => <option key={f}>{f}</option>)}
        </select>
      </Field>
      <Field label="Season">
        <select value={draft.season} onChange={(e) => setField('season', e.target.value)}>
          {SEASONS.map((s) => <option key={s}>{s}</option>)}
        </select>
      </Field>
      <Field label="Fabric">
        <input value={draft.fabric} onChange={(e) => setField('fabric', e.target.value)} />
      </Field>
      <Field label="Notes (optional)">
        <input value={draft.notes || ''} onChange={(e) => setField('notes', e.target.value)} />
      </Field>
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

function Field({ label, children }) {
  return (
    <label className="field">
      <span className="muted">{label}</span>
      {children}
    </label>
  );
}
