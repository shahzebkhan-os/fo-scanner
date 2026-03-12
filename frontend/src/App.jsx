import { useState, useEffect } from "react";

import ScannerTab from "./components/ScannerTab";
import ChainTab from "./components/ChainTab";
import GreeksTab from "./components/GreeksTab";
import HeatmapTab from "./components/HeatmapTab";
import SectorTab from "./components/SectorTab";
import UOATab from "./components/UOATab";
import StraddleTab from "./components/StraddleTab";
import AccuracyTab from "./components/AccuracyTab";
import BacktestTab from "./components/BacktestTab";
import SettingsTab from "./components/SettingsTab";

// ── Constants ─────────────────────────────────────────────────────────────────
const API = "";

const TABS = [
  { id: "scanner", label: "Scanner", icon: "⚡" },
  { id: "chain", label: "Chain", icon: "🔗" },
  { id: "greeks", label: "Greeks", icon: "Δ" },
  { id: "heatmap", label: "OI Map", icon: "🌡" },
  { id: "sector", label: "Sectors", icon: "🗺" },
  { id: "uoa", label: "UOA", icon: "🎯" },
  { id: "straddle", label: "Straddle", icon: "⚖" },
  { id: "accuracy", label: "Accuracy", icon: "📈" },
  { id: "backtest", label: "Backtest", icon: "🕰" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

async function apiFetch(path, options = {}) {
  const r = await fetch(API + path, options);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ── Root App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState("scanner");
  const [dark, setDark] = useState(() => localStorage.getItem("theme") !== "light");
  const [chainSymbol, setChainSymbol] = useState("NIFTY");
  const [marketStatus, setMarketStatus] = useState(null);
  const [scanData, setScanData] = useState([]);
  const [lotSizes, setLotSizes] = useState({});

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  // Keyboard shortcuts
  useEffect(() => {
    const handle = (e) => {
      if (e.target.tagName === "INPUT") return;
      const keys = {
        r: "scanner", c: "chain", g: "greeks", h: "heatmap",
        s: "sector", u: "uoa", ",": "settings"
      };
      if (keys[e.key]) setTab(keys[e.key]);
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, []);

  useEffect(() => {
    apiFetch("/health").then(d => setMarketStatus(d)).catch(() => { });
    apiFetch("/api/lot-sizes").then(setLotSizes).catch(() => {});
    const id = setInterval(() => apiFetch("/health").then(setMarketStatus).catch(() => { }), 30000);
    return () => clearInterval(id);
  }, []);

  const goChain  = (sym) => { setChainSymbol(sym); setTab("chain"); };
  const [greeksSymbol, setGreeksSymbol] = useState("NIFTY");
  const goGreeks = (sym) => { setGreeksSymbol(sym); setTab("greeks"); };

  const theme = {
    bg: dark ? "#0a0e1a" : "#f1f5f9",
    card: dark ? "#111827" : "#ffffff",
    border: dark ? "#1e293b" : "#e2e8f0",
    text: dark ? "#e2e8f0" : "#0f172a",
    muted: dark ? "#64748b" : "#94a3b8",
    accent: "#6366f1",
    green: "#22c55e",
    red: "#ef4444",
  };

  const signalBg = (s) => s === "BULLISH" ? "rgba(34,197,94,.15)" : "rgba(239,68,68,.15)";

  return (
    <div style={{
      minHeight: "100vh", background: theme.bg, color: theme.text,
      fontFamily: "'IBM Plex Mono', 'Fira Code', monospace",
      fontSize: 13
    }}>
      <style>{`
        @keyframes spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:translateY(0)} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }
        .tab-btn { transition: all 0.2s ease !important; }
        .tab-btn:hover { background: rgba(99,102,241,.08) !important; }
        .scan-card { transition: all 0.2s ease; }
        .scan-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.15); }
        .clickable-btn { transition: all 0.15s ease; }
        .clickable-btn:hover { opacity: 0.85; transform: scale(1.02); }
        .clickable-btn:active { transform: scale(0.98); }
      `}</style>

      {/* Header */}
      <header style={{
        background: theme.card, borderBottom: `1px solid ${theme.border}`,
        padding: "0 16px", display: "flex", alignItems: "center",
        justifyContent: "space-between", height: 52, position: "sticky",
        top: 0, zIndex: 100,
        backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
        background: dark ? "rgba(17,24,39,.92)" : "rgba(255,255,255,.92)"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: theme.accent, letterSpacing: -0.5 }}>F&O</span>
          <span style={{ color: theme.muted, fontSize: 12 }}>Scanner v5</span>
          {marketStatus && (
            <span style={{
              padding: "2px 8px", borderRadius: 4, fontSize: 11,
              background: signalBg(marketStatus.open ? "BULLISH" : "BEARISH"),
              color: marketStatus.open ? theme.green : theme.red,
              animation: marketStatus.open ? "pulse 2s infinite" : "none"
            }}>
              {marketStatus.open ? "● LIVE" : "○ CLOSED"}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => {
            if (!scanData.length) return;
            const baseCols = ["symbol", "signal", "score", "ltp", "change_pct", "volume", "pcr", "iv", "oi_change", "vol_spike"];
            const cols = [...baseCols, "suggested_trade", "trade_score", "lot_value"];
            const csvRows = scanData.map(r => {
              const pick = r.top_picks?.[0];
              const suggested_trade = pick ? `${pick.strike} ${pick.type}` : "";
              const trade_score = pick ? pick.score : "";
              const ls = lotSizes[r.symbol] || 0;
              const lot_value = (pick && ls) ? (pick.ltp * ls).toFixed(2) : "";
              const rowData = baseCols.map(c => r[c] ?? "");
              return [...rowData, suggested_trade, trade_score, lot_value].join(",");
            });
            const csv = [cols.join(","), ...csvRows].join("\n");
            const a = document.createElement("a");
            a.href = "data:text/csv;charset=utf-8," + encodeURIComponent(csv);
            a.download = `fo_scanner_${new Date().toISOString().slice(0, 10)}.csv`;
            a.click();
          }} style={{
            color: theme.muted, background: "none", cursor: "pointer",
            padding: "4px 10px", border: `1px solid ${theme.border}`, borderRadius: 4, fontSize: 11
          }}>
            ↓ CSV
          </button>
          <button onClick={() => setDark(d => !d)}
            style={{
              background: "none", border: `1px solid ${theme.border}`,
              color: theme.muted, padding: "4px 10px", borderRadius: 4,
              cursor: "pointer", fontSize: 13
            }}>
            {dark ? "☀" : "◑"}
          </button>
        </div>
      </header>

      {/* Tab Bar */}
      <nav style={{
        background: theme.card, borderBottom: `1px solid ${theme.border}`,
        display: "flex", gap: 0, overflowX: "auto",
        WebkitOverflowScrolling: "touch"
      }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className="tab-btn"
            style={{
              padding: "10px 16px", border: "none", cursor: "pointer",
              background: tab === t.id ? "rgba(99,102,241,.08)" : "none",
              color: tab === t.id ? theme.accent : theme.muted,
              borderBottom: tab === t.id ? `2px solid ${theme.accent}` : "2px solid transparent",
              whiteSpace: "nowrap", fontFamily: "inherit", fontSize: 12,
              fontWeight: tab === t.id ? 600 : 400
            }}>
            {t.icon} {t.label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <main style={{ padding: 16, maxWidth: 1400, margin: "0 auto" }}>
        <div style={{ display: tab === "scanner"   ? "block" : "none" }}><ScannerTab theme={theme} onChain={goChain} onGreeks={goGreeks} onData={setScanData} /></div>
        <div style={{ display: tab === "chain"     ? "block" : "none" }}><ChainTab theme={theme} symbol={chainSymbol} setSymbol={setChainSymbol} /></div>
        <div style={{ display: tab === "greeks"    ? "block" : "none" }}><GreeksTab theme={theme} symbol={greeksSymbol} /></div>
        <div style={{ display: tab === "heatmap"   ? "block" : "none" }}><HeatmapTab theme={theme} /></div>
        <div style={{ display: tab === "sector"    ? "block" : "none" }}><SectorTab theme={theme} onChain={goChain} /></div>
        <div style={{ display: tab === "uoa"       ? "block" : "none" }}><UOATab theme={theme} onChain={goChain} /></div>
        <div style={{ display: tab === "straddle"  ? "block" : "none" }}><StraddleTab theme={theme} /></div>
        <div style={{ display: tab === "accuracy"  ? "block" : "none" }}><AccuracyTab theme={theme} /></div>
        <div style={{ display: tab === "backtest"  ? "block" : "none" }}><BacktestTab theme={theme} /></div>
        <div style={{ display: tab === "settings"  ? "block" : "none" }}><SettingsTab theme={theme} /></div>
      </main>
    </div>
  );
}