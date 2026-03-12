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

export default function SectorTab({ theme }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/api/sector-heatmap");
      setData(r.data || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (loading) return <Loader theme={theme} />;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>Sector Performance</h2>
        <button onClick={load} style={{ padding: "6px 14px", borderRadius: 6, background: theme.accent, color: "#fff", border: "none", cursor: "pointer" }}>⟳ Refresh</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
        {data.map(s => (
          <Card key={s.sector} theme={theme} style={{ borderTop: `4px solid ${s.change_pct >= 0 ? theme.green : theme.red}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <div>
                <div style={{ fontWeight: 800, fontSize: 15 }}>{s.sector}</div>
                <div style={{ fontSize: 11, color: theme.muted }}>{s.stocks.length} stocks traced</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontWeight: 800, color: s.change_pct >= 0 ? theme.green : theme.red, fontSize: 16 }}>
                  {s.change_pct >= 0 ? "+" : ""}{fmt(s.change_pct)}%
                </div>
                <div style={{ fontSize: 10, color: theme.muted }}>Avg Sector Chg</div>
              </div>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {s.stocks.sort((a,b) => b.change_pct - a.change_pct).map(st => (
                <div key={st.symbol} title={`${st.symbol}: ${st.change_pct}%`}
                  style={{
                    padding: "3px 6px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                    background: st.change_pct >= 0.5 ? "rgba(34,197,94,.15)" : st.change_pct <= -0.5 ? "rgba(239,68,68,.15)" : theme.bg,
                    color: st.change_pct >= 0.5 ? theme.green : st.change_pct <= -0.5 ? theme.red : theme.muted,
                    border: `1px solid ${st.change_pct >= 0.5 ? "rgba(34,197,94,.2)" : st.change_pct <= -0.5 ? "rgba(239,68,68,.2)" : theme.border}`
                  }}>
                  {st.symbol}
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
