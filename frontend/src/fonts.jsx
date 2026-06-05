// fonts.jsx
// ─────────────────────────────────────────────────────────
// Font-combo playground. Wrap the app in <FontProvider> (see main.jsx)
// and drop <FontPicker /> anywhere to switch combos live — no rebuild.
//
// The CSS consumes three variables that FontProvider sets on :root:
//   var(--font-heading)  var(--font-body)  var(--font-mono)
// Picked combo persists in localStorage so it survives reloads.
//
// Once you settle on a combo: set ACTIVE_COMBO below to that key,
// delete the other combos + <FontPicker />, and update DESIGN.md.
// ─────────────────────────────────────────────────────────

import { createContext, useContext, useEffect, useState } from "react";

// ── 1. FONT COMBOS ───────────────────────────────────────
//   heading → titles, section headers, card/outfit names
//   body    → everything else (labels, buttons, descriptions)
//   mono    → optional, for tags/sizes/codes
export const FONT_COMBOS = {
  // The app's current pairing — keep as an A/B baseline.
  ebgaramond: {
    label: "EB Garamond (current)",
    heading: "'EB Garamond', Georgia, 'Times New Roman', serif",
    body: "system-ui, -apple-system, sans-serif",
    mono: "ui-monospace, 'SF Mono', monospace",
    googleFontsUrl:
      "https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400..700;1,400..700&display=swap",
  },

  // Editorial, fashion-forward
  cormorant: {
    label: "Cormorant + DM Sans",
    heading: "'Cormorant Garamond', Georgia, serif",
    body: "'DM Sans', system-ui, sans-serif",
    mono: "'DM Mono', monospace",
    googleFontsUrl:
      "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400&display=swap",
  },

  // Elegant + timeless
  playfair: {
    label: "Playfair Display + Inter",
    heading: "'Playfair Display', Georgia, serif",
    body: "'Inter', system-ui, sans-serif",
    mono: "'JetBrains Mono', monospace",
    googleFontsUrl:
      "https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,700;1,400&family=Inter:wght@300;400;500&family=JetBrains+Mono:wght@400&display=swap",
  },

  // Softer, more approachable
  fraunces: {
    label: "Fraunces + Nunito",
    heading: "'Fraunces', Georgia, serif",
    body: "'Nunito', system-ui, sans-serif",
    mono: "'Courier New', monospace",
    googleFontsUrl:
      "https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,300;0,400;0,600;1,300;1,400&family=Nunito:wght@300;400;500&display=swap",
  },

  // Modern, minimal
  libre: {
    label: "Libre Baskerville + Jost",
    heading: "'Libre Baskerville', Georgia, serif",
    body: "'Jost', system-ui, sans-serif",
    mono: "'Courier New', monospace",
    googleFontsUrl:
      "https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Jost:wght@300;400;500&display=swap",
  },
};

// ── 2. ACTIVE COMBO ──────────────────────────────────────
// The shipped default — change this one line to re-theme the whole app.
export const ACTIVE_COMBO = "cormorant";

const STORAGE_KEY = "wardrobe-font-combo";

// ── 3. PROVIDER + CONTEXT ────────────────────────────────
const FontContext = createContext(null);
export const useFont = () => useContext(FontContext);

export function FontProvider({ children, combo = ACTIVE_COMBO }) {
  const [active, setActive] = useState(() => {
    const saved =
      typeof localStorage !== "undefined" && localStorage.getItem(STORAGE_KEY);
    return saved && FONT_COMBOS[saved] ? saved : combo;
  });
  const selected = FONT_COMBOS[active] ?? FONT_COMBOS[ACTIVE_COMBO];

  useEffect(() => {
    // Inject (or update) the Google Fonts <link> for the active combo.
    const id = "app-google-fonts";
    let link = document.getElementById(id);
    if (!link) {
      link = document.createElement("link");
      link.id = id;
      link.rel = "stylesheet";
      document.head.appendChild(link);
    }
    link.href = selected.googleFontsUrl;

    // Set the CSS variables the stylesheet reads.
    const root = document.documentElement;
    root.style.setProperty("--font-heading", selected.heading);
    root.style.setProperty("--font-body", selected.body);
    root.style.setProperty("--font-mono", selected.mono);

    localStorage.setItem(STORAGE_KEY, active);
  }, [active, selected]);

  return (
    <FontContext.Provider value={{ active, setActive, combos: FONT_COMBOS }}>
      {children}
    </FontContext.Provider>
  );
}

// ── 4. LIVE PICKER (dev/exploration only) ────────────────
// Floating dropdown to swap combos without editing code. Remove once
// you've chosen — see the cleanup note at the top of this file.
export function FontPicker() {
  const ctx = useFont();
  if (!ctx) return null;
  const { active, setActive, combos } = ctx;

  return (
    <div className="font-picker">
      <span className="font-picker__label">Font</span>
      <select
        className="font-picker__select"
        value={active}
        onChange={(e) => setActive(e.target.value)}
        aria-label="Preview font combo"
      >
        {Object.entries(combos).map(([key, c]) => (
          <option key={key} value={key}>
            {c.label}
          </option>
        ))}
      </select>
    </div>
  );
}
