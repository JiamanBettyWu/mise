export const TYPES = [
  'jacket', 'coat', 'vest', 'shirt', 't-shirt', 'sweater', 'blouse', 'dress',
  'skirt', 'trousers', 'jeans', 'shorts', 'shoes', 'boots', 'sneakers',
  'sandals', 'bag', 'scarf', 'hat', 'belt', 'accessory', 'other',
];
export const FORMALITIES = ['casual', 'smart-casual', 'formal'];
export const SEASONS = ['spring', 'summer', 'fall', 'winter', 'all-season'];
export const WARMTH_LEVELS = [
  [1, '1 — minimal'],
  [2, '2 — light'],
  [3, '3 — moderate'],
  [4, '4 — warm'],
  [5, '5 — maximum'],
];

export default function ClothingFields({ value, onChange }) {
  const set = (k, v) => onChange({ ...value, [k]: v });

  return (
    <>
      <Field label="Name (3–7 words)">
        <input value={value.name || ''} maxLength={80} onChange={(e) => set('name', e.target.value)} />
      </Field>
      <Field label="Type">
        <select value={value.type || ''} onChange={(e) => set('type', e.target.value)}>
          {TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
      </Field>
      <Field label="Color">
        <input value={value.color || ''} onChange={(e) => set('color', e.target.value)} />
      </Field>
      <Field label="Formality">
        <select value={value.formality || ''} onChange={(e) => set('formality', e.target.value)}>
          {FORMALITIES.map((f) => <option key={f}>{f}</option>)}
        </select>
      </Field>
      <Field label="Season">
        <select value={value.season || ''} onChange={(e) => set('season', e.target.value)}>
          {SEASONS.map((s) => <option key={s}>{s}</option>)}
        </select>
      </Field>
      <Field label="Fabric">
        <input value={value.fabric || ''} onChange={(e) => set('fabric', e.target.value)} />
      </Field>
      <Field label="Warmth">
        <select
          value={value.warmth ?? ''}
          onChange={(e) => set('warmth', e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">— not rated</option>
          {WARMTH_LEVELS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </select>
      </Field>
      <Field label="Brand (optional)">
        <input value={value.brand || ''} onChange={(e) => set('brand', e.target.value || null)} />
      </Field>
      <Field label="Description">
        <textarea
          rows={3}
          value={value.description || ''}
          onChange={(e) => set('description', e.target.value)}
        />
      </Field>
      <Field label="Notes (optional)">
        <input value={value.notes || ''} onChange={(e) => set('notes', e.target.value)} />
      </Field>
    </>
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
