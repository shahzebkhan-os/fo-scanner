import { useState, useEffect } from "react";

async function apiFetch(path, options = {}) {
  const API = "";
  const r = await fetch(API + path, options);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function Loader({ theme }) {
  return (
    <div style={{ textAlign: "center", padding: 40, color: theme.muted }}>
      <div style={{
        fontSize: 24, animation: "spin 1s linear infinite",
        display: "inline-block"
      }}>⟳</div>
      <div style={{ marginTop: 8, fontSize: 12 }}>Loading...</div>
    </div>
  );
}

function Card({ children, theme, style = {} }) {
  return (
    <div style={{
      background: theme.card, border: `1px solid ${theme.border}`,
      borderRadius: 8, padding: 16, ...style
    }}>
      {children}
    </div>
  );
}

export default function SettingsTab({ theme }) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/api/settings");
      setSettings(r);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings)
      });
      alert("Settings saved!");
    } catch (e) { console.error(e); alert("Failed to save settings."); }
    setSaving(false);
  };

  const inp = (extra = {}) => ({
    style: {
      background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 6,
      color: theme.text, padding: "7px 10px", fontSize: 13, width: "100%", boxSizing: "border-box", ...extra
    }
  });

  if (loading) return <Loader theme={theme} />;
  if (!settings) return null;

  return (
    <div>
      <h2 style={{ fontSize: 18, marginBottom: 20 }}>System Settings</h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <Card theme={theme}>
          <h3 style={{ fontSize: 14, marginTop: 0 }}>Scanning Engine</h3>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, color: theme.muted }}>Refresh Interval (seconds)</label>
            <input type="number" {...inp()} value={settings.refresh_interval || 60} onChange={e => setSettings({ ...settings, refresh_interval: +e.target.value })} />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, color: theme.muted }}>Min Score for Auto-Select</label>
            <input type="number" {...inp()} value={settings.min_score || 85} onChange={e => setSettings({ ...settings, min_score: +e.target.value })} />
          </div>
        </Card>
        <Card theme={theme}>
          <h3 style={{ fontSize: 14, marginTop: 0 }}>Risk Management</h3>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, color: theme.muted }}>Max Positions</label>
            <input type="number" {...inp()} value={settings.max_positions || 5} onChange={e => setSettings({ ...settings, max_positions: +e.target.value })} />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 11, color: theme.muted }}>Stop Loss %</label>
            <input type="number" {...inp()} value={settings.stop_loss || 25} onChange={e => setSettings({ ...settings, stop_loss: +e.target.value })} />
          </div>
        </Card>
      </div>
      <button onClick={save} disabled={saving} style={{ marginTop: 20, background: theme.accent, color: "#fff", border: "none", borderRadius: 6, padding: "10px 24px", fontWeight: 700, cursor: "pointer" }}>
        {saving ? "Saving..." : "Save Configuration"}
      </button>
    </div>
  );
}
