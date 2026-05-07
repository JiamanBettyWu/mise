import { useEffect, useState } from 'react';
import { api, getStoredPassword, setStoredPassword } from './services/api.js';

export default function App() {
  const [unlocked, setUnlocked] = useState(false);
  const [pw, setPw] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (getStoredPassword()) verify(getStoredPassword());
  }, []);

  async function verify(candidate) {
    setStoredPassword(candidate);
    try {
      await api.healthAuth();
      setUnlocked(true);
      setError('');
    } catch (e) {
      setStoredPassword('');
      setUnlocked(false);
      setError('Wrong password.');
    }
  }

  function onSubmit(e) {
    e.preventDefault();
    verify(pw);
  }

  if (!unlocked) {
    return (
      <form className="gate" onSubmit={onSubmit}>
        <h1>Wardrobe AI</h1>
        <label>Password</label>
        <input
          type="password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          autoFocus
        />
        <button type="submit">Unlock</button>
        {error && <div className="error">{error}</div>}
      </form>
    );
  }

  return <Connected />;
}

function Connected() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.health().then(setStatus).catch((e) => setStatus({ error: String(e) }));
  }, []);

  return (
    <div>
      <h1>Wardrobe AI</h1>
      <p>Connected ✅</p>
      <pre className="muted">{JSON.stringify(status, null, 2)}</pre>
      <button
        onClick={() => {
          setStoredPassword('');
          location.reload();
        }}
      >
        Lock
      </button>
    </div>
  );
}
