import { useState } from "react";

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

export default function BacktestTab({ theme }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [params, setParams] = useState({
    start: "2023-01-01", end: "2024-12-31", score: 20, confidence: 0,
    tp: 40, sl: 25, signal: "ALL", regime: "ALL", symbols: ""
  });

  const run = async () => {
    setLoading(true); setResult(null);
    try {
      const res = await apiFetch("/api/historical-backtest", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      setResult(res);
    } catch (e) { console.error(e); alert("Backtest failed."); }
    setLoading(false);
  };

  const inp = (extra = {}) => ({
    style: {
      background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 6,
      color: theme.text, padding: "7px 10px", fontSize: 13, width: "100%", boxSizing: "border-box", ...extra
    }
  });

  return (
    <div>
      <Card theme={theme} style={{ marginBottom: 20 }}>
        <h2>Strategy Backtester</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
          <div><label style={{ fontSize: 10, color: theme.muted }}>START DATE</label><input type="date" {...inp()} value={params.start} onChange={e => setParams({ ...params, start: e.target.value })} /></div>
          <div><label style={{ fontSize: 10, color: theme.muted }}>END DATE</label><input type="date" {...inp()} value={params.end} onChange={e => setParams({ ...params, end: e.target.value })} /></div>
          <div><label style={{ fontSize: 10, color: theme.muted }}>SCORE &gt;=</label><input type="number" {...inp()} value={params.score} onChange={e => setParams({ ...params, score: +e.target.value })} /></div>
          <div><label style={{ fontSize: 10, color: theme.muted }}>TAKE PROFIT %</label><input type="number" {...inp()} value={params.tp} onChange={e => setParams({ ...params, tp: +e.target.value })} /></div>
          <div><label style={{ fontSize: 10, color: theme.muted }}>STOP LOSS %</label><input type="number" {...inp()} value={params.sl} onChange={e => setParams({ ...params, sl: +e.target.value })} /></div>
        </div>
        <button onClick={run} disabled={loading} style={{ marginTop: 16, background: theme.accent, color: "#fff", border: "none", borderRadius: 6, padding: "10px 24px", fontWeight: 700, cursor: "pointer" }}>
          {loading ? "Running Simulation..." : "▶ Run Backtest"}
        </button>
      </Card>

      {result && (
        <div style={{ animation: "fadeIn 0.3s" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12, marginBottom: 20 }}>
            <Card theme={theme}><label style={{ fontSize: 10, color: theme.muted }}>Win Rate</label><div style={{ fontSize: 20, fontWeight: 800, color: result.win_rate >= 50 ? theme.green : theme.red }}>{result.win_rate}%</div></Card>
            <Card theme={theme}><label style={{ fontSize: 10, color: theme.muted }}>Total Trades</label><div style={{ fontSize: 20, fontWeight: 800 }}>{result.total_trades}</div></Card>
            <Card theme={theme}><label style={{ fontSize: 10, color: theme.muted }}>Avg P&amp;L</label><div style={{ fontSize: 20, fontWeight: 800, color: result.avg_pnl >= 0 ? theme.green : theme.red }}>{fmt(result.avg_pnl)}%</div></Card>
          </div>
        </div>
      )}
    </div>
  );
}
