import { useEffect, useState } from 'react';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import Catalog from './pages/Catalog.jsx';
import AddItem from './pages/AddItem.jsx';
import TodayOutfit from './pages/TodayOutfit.jsx';
import TripPlan from './pages/TripPlan.jsx';
import { api, getStoredPassword, setStoredPassword } from './services/api.js';

export default function App() {
  const [unlocked, setUnlocked] = useState(false);
  const [pw, setPw] = useState('');
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!getStoredPassword()) { setChecking(false); return; }
    api.healthAuth()
      .then(() => setUnlocked(true))
      .catch(() => setStoredPassword(''))
      .finally(() => setChecking(false));
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    setStoredPassword(pw);
    try {
      await api.healthAuth();
      setUnlocked(true);
      setError('');
    } catch (err) {
      setStoredPassword('');
      const msg = err?.message ?? '';
      if (msg.startsWith('401')) {
        setError('Wrong password.');
      } else if (msg.startsWith('500')) {
        setError('Server misconfigured — APP_PASSWORD not set.');
      } else {
        setError('Could not reach the server. Is the backend running?');
      }
    }
  }

  if (checking) return <p className="muted">Loading…</p>;

  if (!unlocked) {
    return (
      <form className="gate" onSubmit={onSubmit}>
        <h1>Wardrobe AI</h1>
        <label>Password</label>
        <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
        <button type="submit">Unlock</button>
        {error && <div className="error">{error}</div>}
      </form>
    );
  }

  return (
    <BrowserRouter>
      <nav className="nav">
        <Link to="/">Catalog</Link>
        <Link to="/today">Today</Link>
        <Link to="/trip">Trip</Link>
        <Link to="/add">Add</Link>
        <button
          className="link-btn nav__lock"
          onClick={() => { setStoredPassword(''); location.reload(); }}
        >
          Lock
        </button>
      </nav>
      <Routes>
        <Route path="/" element={<Catalog />} />
        <Route path="/today" element={<TodayOutfit />} />
        <Route path="/trip" element={<TripPlan />} />
        <Route path="/add" element={<AddItem />} />
      </Routes>
    </BrowserRouter>
  );
}
