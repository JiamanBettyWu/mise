import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api.js';

const DEBOUNCE_MS = 250;
const MIN_CHARS = 2;

export function formatLocation({ name, state, country }) {
  return [name, state, country].filter(Boolean).join(', ');
}

export default function DestinationCombobox({ value, onChange, onSelect }) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  // Ignore the next debounced fetch — fires after a programmatic value set
  // (a selection), where we already have the chosen location and don't want
  // the dropdown to re-open.
  const skipNextFetchRef = useRef(false);
  // Only open the menu while the input is focused: parents may set `value`
  // programmatically (e.g. Profile loading a saved location), and the
  // resulting fetch must not pop the menu under nobody's cursor. A ref, not
  // state — the debounced closure below would capture a stale state value.
  const focusedRef = useRef(false);

  useEffect(() => {
    if (skipNextFetchRef.current) {
      skipNextFetchRef.current = false;
      return;
    }
    const q = value.trim();
    if (q.length < MIN_CHARS) {
      setResults([]);
      setOpen(false);
      setHighlight(-1);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const rows = await api.searchGeo(q);
        if (cancelled) return;
        setResults(rows);
        setOpen(rows.length > 0 && focusedRef.current);
        setHighlight(-1);
      } catch {
        if (!cancelled) {
          setResults([]);
          setOpen(false);
          setHighlight(-1);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [value]);

  function handleSelect(row) {
    skipNextFetchRef.current = true;
    const label = formatLocation(row);
    onChange(label);
    onSelect({ label, lat: row.lat, lon: row.lon, country: row.country, state: row.state });
    setOpen(false);
    setHighlight(-1);
  }

  function handleKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open && results.length > 0) {
        setOpen(true);
        setHighlight(0);
        return;
      }
      setHighlight((h) => (results.length ? (h + 1) % results.length : -1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) =>
        results.length ? (h <= 0 ? results.length - 1 : h - 1) : -1
      );
    } else if (e.key === 'Enter') {
      if (open && highlight >= 0 && results[highlight]) {
        e.preventDefault();
        handleSelect(results[highlight]);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
      setHighlight(-1);
    }
  }

  return (
    <div className="combobox">
      <input
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          // Free-text typing invalidates any previously-selected coords.
          onSelect(null);
        }}
        onFocus={() => {
          focusedRef.current = true;
          if (results.length > 0) setOpen(true);
        }}
        onBlur={() => {
          focusedRef.current = false;
          setTimeout(() => setOpen(false), 150);
        }}
        onKeyDown={handleKeyDown}
        placeholder="e.g. Oaxaca, Mexico"
        autoComplete="off"
      />
      {open && (
        <ul className="combobox__menu">
          {results.map((row, i) => (
            <li
              key={`${row.lat},${row.lon},${i}`}
              className={`combobox__option${i === highlight ? ' combobox__option--active' : ''}`}
              onMouseEnter={() => setHighlight(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelect(row);
              }}
            >
              {formatLocation(row)}
            </li>
          ))}
        </ul>
      )}
      {loading && <span className="combobox__loading muted">Searching…</span>}
    </div>
  );
}
