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
            className="switch"
            role="switch"
            aria-checked={multi}
            onClick={() => setMulti(!multi)}
          >
            <span className="switch__track" aria-hidden="true" />
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
