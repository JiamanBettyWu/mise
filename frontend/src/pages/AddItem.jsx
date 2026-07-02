import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AddClothingForm from '../components/AddClothingForm.jsx';
import AddClothingMultiForm from '../components/AddClothingMultiForm.jsx';

export default function AddItem() {
  const navigate = useNavigate();
  const [multi, setMulti] = useState(false);
  return (
    <div>
      <div className="page-header">
        <h1>Add item</h1>
        <div className="page-header__actions">
          <button
            className={`chip${multi ? ' chip--on-mode' : ''}`}
            aria-pressed={multi}
            onClick={() => setMulti(!multi)}
          >
            Multi-item photo
          </button>
        </div>
      </div>
      {multi ? (
        <AddClothingMultiForm onDone={() => navigate('/')} />
      ) : (
        <AddClothingForm onSaved={() => navigate('/')} />
      )}
    </div>
  );
}
