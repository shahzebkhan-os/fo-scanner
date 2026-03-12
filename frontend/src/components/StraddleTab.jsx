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

const fmt = (n, d = 2) => Number(n || 0).toFixed(d);

export default function StraddleTab({ theme }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/api/straddle-screen");
      setData(r.data || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (loading) return <Loader theme={theme} />;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>Straddle Opportunities</h2>
        <button onClick={load} style={{ padding: "6px 14px", borderRadius: 6, background: theme.accent, color: "#fff", border: "none", cursor: "pointer" }}>⟳ Refresh</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
        {data.map((s, i) => (
          <Card key={i} theme={theme}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div style={{ fontWeight: 800, fontSize: 16 }}>{s.symbol}</div>
              <div style={{ textAlign: "right", color: theme.muted, fontSize: 11 }}>ATM @ ₹{s.strike}</div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
              <div style={{ background: theme.bg, padding: "8px", borderRadius: 6, textAlign: "center" }}>
                <div style={{ fontSize: 10, color: theme.muted }}>IV</div>
                <div style={{ fontWeight: 700 }}>{fmt(s.iv)}%</div>
              </div>
              <div style={{ background: theme.bg, padding: "8px", borderRadius: 6, textAlign: "center" }}>
                <div style={{ fontSize: 10, color: theme.muted }}>DECAY (θ)</div>
                <div style={{ fontWeight: 700, color: theme.red }}>₹{fmt(s.theta)}/d</div>
              </div>
            </div>

            <div style={{ fontSize: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span>Straddle Cost</span>
                <strong style={{ color: theme.text }}>₹{fmt(s.cost)}</strong>
              </div>
              {s.strangle && (
                <div style={{ borderTop: `1px solid ${theme.border}`, paddingTop: 4, marginTop: 4 }}>
                  <div style={{ color: theme.muted, fontSize: 10, marginBottom: 4 }}>CHEAPER ALTERNATIVE: STRANGLE</div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>{s.strangle.ce_strike}CE / {s.strangle.pe_strike}PE</span>
                    <div>
                      <strong style={{ color: theme.text }}> ₹{fmt(s.strangle.cost)} </strong>
                      <span style={{ color: theme.green }}>(saves ₹{fmt(s.strangle.cheaper_by)})</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
