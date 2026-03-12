import { useState, useEffect } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ReferenceLine } from "recharts";

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

export default function HeatmapTab({ theme }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/api/scan?limit=51");
      const rows = r.data || [];
      setData(rows.sort((a, b) => b.change_pct - a.change_pct));
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (loading) return <Loader theme={theme} />;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>OI & Price Heatmap</h2>
        <button onClick={load} style={{ padding: "6px 14px", borderRadius: 6, background: theme.accent, color: "#fff", border: "none", cursor: "pointer" }}>⟳ Refresh</button>
      </div>

      <Card theme={theme} style={{ padding: "24px 16px" }}>
        <ResponsiveContainer width="100%" height={500}>
          <BarChart data={data} layout="vertical" margin={{ left: 20, right: 20 }}>
            <XAxis type="number" hide />
            <YAxis dataKey="symbol" type="category" width={80} tick={{ fontSize: 10, fill: theme.text }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 8 }}
              formatter={(v, name, props) => [
                <span style={{ color: v >= 0 ? theme.green : theme.red }}>{v >= 0 ? "+" : ""}{v}%</span>,
                "Price Change"
              ]}
            />
            <ReferenceLine x={0} stroke={theme.border} />
            <Bar dataKey="change_pct" radius={[0, 4, 4, 0]}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.change_pct >= 0 ? theme.green : theme.red} fillOpacity={0.8} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <div style={{ marginTop: 24, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8 }}>
        {data.map(r => (
          <div key={r.symbol} style={{
            padding: "10px", borderRadius: 8, background: theme.card, 
            border: `1px solid ${theme.border}`, textAlign: "center",
            borderTop: `3px solid ${r.change_pct >= 0 ? theme.green : theme.red}`
          }}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{r.symbol}</div>
            <div style={{ fontSize: 11, color: r.change_pct >= 0 ? theme.green : theme.red, fontWeight: 700, marginTop: 4 }}>
              {r.change_pct >= 0 ? "+" : ""}{fmt(r.change_pct)}%
            </div>
            <div style={{ fontSize: 9, color: theme.muted, marginTop: 2 }}>OI: {fmt(r.pcr, 2)} PCR</div>
          </div>
        ))}
      </div>
    </div>
  );
}
