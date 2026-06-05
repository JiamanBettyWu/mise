import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import { FontProvider, FontPicker } from './fonts.jsx';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <FontProvider>
      <App />
      {/* Live combo switcher — dev only; stripped from production builds. */}
      {import.meta.env.DEV && <FontPicker />}
    </FontProvider>
  </React.StrictMode>
);
