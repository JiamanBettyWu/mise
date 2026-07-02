import { useState } from 'react';
import { api } from '../services/api.js';
import { compressImage } from '../services/image.js';
import ClothingFields from './ClothingFields.jsx';

// Multi-item review flow (#24): one photo, N independent review cards.
// Unlike AddClothingForm's single linear state machine, each card carries its
// own status — card 3 can fail to save while card 4 succeeds.
export default function AddClothingMultiForm({ onDone }) {
  const [stage, setStage] = useState('pick'); // pick | tagging | review
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [photoUrl, setPhotoUrl] = useState('');
  // Each card: { key, draft, status: 'review' | 'saving' | 'saved', error }
  const [cards, setCards] = useState([]);

  async function handleFile(e) {
    const picked = e.target.files?.[0];
    if (!picked) return;
    setError('');
    setNotice('');
    setStage('tagging');
    try {
      const file = await compressImage(picked);
      const suggestions = await api.uploadAndTagMulti(file);
      if (!suggestions.length) {
        setNotice('No items detected — try another photo.');
        setStage('pick');
        return;
      }
      setPhotoUrl(suggestions[0].photo_url);
      setCards(
        suggestions.map((tags, i) => ({
          key: i,
          status: 'review',
          error: '',
          draft: {
            ...tags,
            brand: tags.brand || '',
            description: tags.description || '',
            available: true,
            in_travel_bag: false,
            notes: '',
          },
        })),
      );
      setStage('review');
    } catch (err) {
      setError(String(err));
      setStage('pick');
    }
  }

  const patchCard = (key, patch) =>
    setCards((cs) => cs.map((c) => (c.key === key ? { ...c, ...patch } : c)));

  async function saveCard(card) {
    patchCard(card.key, { status: 'saving', error: '' });
    try {
      const payload = { ...card.draft, brand: card.draft.brand?.trim() || null };
      await api.createClothing(payload);
      patchCard(card.key, { status: 'saved' });
    } catch (err) {
      patchCard(card.key, { status: 'review', error: String(err) });
    }
  }

  function discardCard(key) {
    setCards((cs) => cs.filter((c) => c.key !== key));
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
        <div className="muted">
          Every item in the photo gets its own entry — best for accessories.
          All entries share the one photo.
        </div>
        {notice && <div className="muted">{notice}</div>}
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  const allDone = cards.every((c) => c.status === 'saved');

  return (
    <div className="form multi-form">
      <img src={photoUrl} alt="" className="form__preview" />
      <div className="muted">
        {cards.length} item{cards.length === 1 ? '' : 's'} found — all will share
        this photo in your catalog.
      </div>
      {cards.map((card) => (
        <div key={card.key} className="multi-form__card">
          {card.status === 'saved' ? (
            <div className="muted">✓ Saved — {card.draft.name}</div>
          ) : (
            <>
              <ClothingFields
                value={card.draft}
                onChange={(draft) => patchCard(card.key, { draft })}
              />
              <div className="form__actions">
                <button
                  onClick={() => saveCard(card)}
                  disabled={card.status === 'saving'}
                >
                  {card.status === 'saving' ? 'Saving…' : 'Save'}
                </button>
                <button
                  className="ghost"
                  onClick={() => discardCard(card.key)}
                  disabled={card.status === 'saving'}
                >
                  Discard
                </button>
              </div>
              {card.error && <div className="error">{card.error}</div>}
            </>
          )}
        </div>
      ))}
      <div className="form__actions">
        <button className={allDone ? '' : 'ghost'} onClick={() => onDone?.()}>
          Done
        </button>
      </div>
    </div>
  );
}
