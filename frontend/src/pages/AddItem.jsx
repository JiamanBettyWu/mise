import { useNavigate } from 'react-router-dom';
import AddClothingForm from '../components/AddClothingForm.jsx';

export default function AddItem() {
  const navigate = useNavigate();
  return (
    <div>
      <h1>Add item</h1>
      <AddClothingForm onSaved={() => navigate('/')} />
    </div>
  );
}
