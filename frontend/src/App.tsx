import React from 'react';
import { RefreshCw } from 'lucide-react';
import { Dashboard } from './pages/Dashboard';
import './styles.css';

export const App: React.FC = () => {
  const [key, setKey] = React.useState(0);

  return (
    <div className="app-shell">
      {/* ── Top Bar ─────────────────────────────────────── */}
      <header className="topbar" role="banner">
        <div className="topbar-left">
          <img
            src="/logo.svg"
            alt="NeerUrja logo"
            className="topbar-logo"
            width={28}
            height={28}
          />
          <span className="topbar-wordmark">NeerUrja</span>
          <div className="topbar-divider" aria-hidden="true" />
          <span className="topbar-subtitle">Solar Pump Optimiser</span>
        </div>

        <div className="topbar-right">
          <span
            className="demo-badge demo-badge--simulated"
            role="status"
            title="Data is from a simulated scenario, not a live sensor feed"
          >
            <span className="demo-badge-dot" />
            Simulated
          </span>

          <button
            className="btn btn-secondary"
            onClick={() => setKey((k) => k + 1)}
            title="Reload scenario"
            aria-label="Reload scenario"
          >
            <RefreshCw size={13} />
            Reload
          </button>
        </div>
      </header>

      {/* ── Main Content ──────────────────────────────── */}
      <main role="main">
        <Dashboard key={key} />
      </main>

      {/* ── Footer ───────────────────────────────────── */}
      <footer className="footer" role="contentinfo">
        <span>NeerUrja · Solar-aligned water pump scheduling</span>
        <span>
          Data:{' '}
          <span style={{ fontFamily: 'IBM Plex Mono, monospace' }}>
            {import.meta.env.VITE_API_BASE_URL || 'no backend configured'}
          </span>
        </span>
      </footer>
    </div>
  );
};

export default App;
