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

function Badge({ label, color, bg }) {
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 4, fontSize: 11,
      fontWeight: 600, color, background: bg
    }}>
      {label}
    </span>
  );
}

const fmt = (n, d = 2) => Number(n || 0).toFixed(d);

export default function UOATab({ theme }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/api/uoa");
      setData(r.data || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (loading) return <Loader theme={theme} />;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>Unusual Options Activity</h2>
        <button onClick={load} style={{ padding: "6px 14px", borderRadius: 6, background: theme.accent, color: "#fff", border: "none", cursor: "pointer" }}>⟳ Refresh</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 12 }}>
        {data.length === 0 && <Card theme={theme} style={{ textAlign: "center", color: theme.muted }}>No unusual activity detected in recent scans.</Card>}
        {data.map((u, i) => (
          <Card key={i} theme={theme} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ fontWeight: 800, fontSize: 16 }}>{u.symbol}</div>
              <Badge label={`${u.strike} ${u.type}`} color={u.type === "CE" ? theme.green : theme.red} bg={u.type === "CE" ? "rgba(34,197,94,.15)" : "rgba(239,68,68,.15)"} />
            </div>
            <div style={{ display: "flex", gap: 24, textAlign: "right" }}>
              <div>
                <div style={{ fontSize: 10, color: theme.muted }}>V/OI RATIO</div>
                <div style={{ fontWeight: 700, color: theme.accent, fontSize: 15 }}>{fmt(u.ratio, 1)}x</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: theme.muted }}>VOLUME</div>
                <div style={{ fontWeight: 700 }}>{u.volume.toLocaleString()}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: theme.muted }}>OI</div>
                <div style={{ fontWeight: 700 }}>{u.oi.toLocaleString()}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
