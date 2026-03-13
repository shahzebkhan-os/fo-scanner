// App.jsx — NSE F&O Scanner v5 Frontend
// Features: Scanner, Chain, Greeks, OI Heatmap, Sector Map, UOA,
//           Straddle Screen, Portfolio Dashboard, Settings, Dark Mode
// v5: QoL improvements — auto-refresh, hover effects, TP/SL indicators

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, ReferenceLine, AreaChart, Area
} from "recharts";
import StrategyBuilder from "./components/StrategyBuilder";

// ── Constants ─────────────────────────────────────────────────────────────────
const API = "http://localhost:8000";   // same-origin; set to http://localhost:8000 for dev

const TABS = [
  { id: "scanner", label: "Scanner", icon: "⚡" },
  { id: "chain", label: "Chain", icon: "🔗" },
  { id: "greeks", label: "Greeks", icon: "Δ" },
  { id: "heatmap", label: "OI Map", icon: "🌡" },
  { id: "sector", label: "Sectors", icon: "🗺" },
  { id: "uoa", label: "UOA", icon: "🎯" },
  { id: "straddle", label: "Straddle", icon: "⚖" },
  { id: "portfolio", label: "P&L", icon: "💰" },
  { id: "manual", label: "Trade", icon: "🚀" },
  { id: "accuracy", label: "Accuracy", icon: "📈" },
  { id: "backtest", label: "Backtest", icon: "🕰" },
  { id: "strategy", label: "Strategy", icon: "🧪" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n, d = 2) => Number(n || 0).toFixed(d);
const pct = (n) => `${n >= 0 ? "+" : ""}${fmt(n, 1)}%`;
const signalColor = (s) =>
  s === "BULLISH" ? "#22c55e" : s === "BEARISH" ? "#ef4444" : "#94a3b8";
const signalBg = (s) =>
  s === "BULLISH" ? "rgba(34,197,94,.15)" : s === "BEARISH" ? "rgba(239,68,68,.15)" : "rgba(148,163,184,.1)";

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
  const [scanData, setScanData] = useState([]);  // lifted for CSV export
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
        s: "sector", u: "uoa", p: "portfolio", m: "manual", ",": "settings"
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

  return (
    <div style={{
      minHeight: "100vh", background: theme.bg, color: theme.text,
      fontFamily: "'IBM Plex Mono', 'Fira Code', monospace",
      fontSize: 13
    }}>
      {/* Global QoL styles */}
      <style>{`
        @keyframes spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:translateY(0)} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }
        .tab-btn { transition: all 0.2s ease !important; }
        .tab-btn:hover { background: rgba(99,102,241,.08) !important; }
        .scan-card { transition: all 0.2s ease; }
        .scan-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,.15); }
        .trade-row { transition: background 0.15s ease; }
        .trade-row:hover { background: rgba(99,102,241,.04) !important; }
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
            const cols = ["Symbol", "Signal", "Score", "ML Score", "Price", "Suggested Trade", "Trade LTP", "Trade Score", "Trade ML Score", "Lot Value"];
            const rowsHtml = scanData.map(r => {
              const pick = r.top_picks?.[0];
              const sig = r.signal || "NEUTRAL";
              const bgColor = sig === "BULLISH" ? "#d4edda" : sig === "BEARISH" ? "#f8d7da" : "transparent";
              const suggested_trade = pick ? `${pick.strike} ${pick.type}` : "";
              const trade_ltp = pick ? pick.ltp : "";
              const trade_score = pick ? pick.score : "";
              const trade_ml_score = pick ? (r.ml_score || 0) : "";
              const ls = lotSizes[r.symbol] || 0;
              const lot_value = (pick && ls) ? (pick.ltp * ls).toFixed(2) : "";
              
              const vals = [r.symbol, sig, r.score, r.ml_score, r.ltp, suggested_trade, trade_ltp, trade_score, trade_ml_score, lot_value];
              return `<tr style="background-color: ${bgColor};">${vals.map(v => `<td style="border: 1px solid #ccc; padding: 4px;">${v ?? ""}</td>`).join("")}</tr>`;
            }).join("");

            const tableHtml = `
              <table style="border-collapse: collapse; font-family: sans-serif; font-size: 12px;">
                <thead>
                  <tr style="background: #eee;">${cols.map(c => `<th style="border: 1px solid #ccc; padding: 6px; text-align: left;">${c}</th>`).join("")}</tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
              </table>
            `;
            
            const blob = new Blob([tableHtml], { type: "application/vnd.ms-excel" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `fo_scanner_${new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false }).replace(/[/, :]/g, '-')}.xls`;
            a.click();
            URL.revokeObjectURL(url);
          }} style={{
            color: theme.muted, background: "none", cursor: "pointer",
            padding: "4px 10px", border: `1px solid ${theme.border}`, borderRadius: 4, fontSize: 11
          }}>
            ↓ EXCEL
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
        <div style={{ display: tab === "portfolio" ? "block" : "none" }}><PortfolioTab theme={theme} /></div>
        <div style={{ display: tab === "manual"    ? "block" : "none" }}><ManualTradeTab theme={theme} /></div>
        <div style={{ display: tab === "accuracy"  ? "block" : "none" }}><AccuracyTab theme={theme} /></div>
        <div style={{ display: tab === "backtest"  ? "block" : "none" }}><BacktestTab theme={theme} /></div>
        <div style={{ display: tab === "strategy"  ? "block" : "none" }}><StrategyBuilder /></div>
        <div style={{ display: tab === "settings"  ? "block" : "none" }}><SettingsTab theme={theme} /></div>
      </main>
    </div>
  );
}

// ── Shared Components ─────────────────────────────────────────────────────────

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

function SymbolInput({ value, onChange, onSubmit, theme }) {
  return (
    <form onSubmit={e => { e.preventDefault(); onSubmit(); }}
      style={{ display: "flex", gap: 8 }}>
      <input value={value} onChange={e => onChange(e.target.value.toUpperCase())}
        placeholder="NIFTY / RELIANCE..."
        style={{
          padding: "6px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
          background: theme.bg, color: theme.text, fontFamily: "inherit",
          fontSize: 13, width: 180
        }} />
      <button type="submit"
        style={{
          padding: "6px 14px", borderRadius: 6, background: theme.accent,
          color: "#fff", border: "none", cursor: "pointer", fontFamily: "inherit"
        }}>
        Load
      </button>
    </form>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Scanner Tab
// ══════════════════════════════════════════════════════════════════════════════

function ScannerTab({ theme, onChain, onGreeks, onData }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [watchlist, setWatchlist] = useState([]);
  const [showWL, setShowWL] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [countdown, setCountdown] = useState(60);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [scanMeta, setScanMeta] = useState({ stale: false, stale_count: 0 });
  const [mlStatus, setMlStatus] = useState({ trained: false });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/api/scan?limit=51");
      const rows = r.data || [];
      setData(rows);
      setScanMeta({ stale: r.stale, stale_count: r.stale_count || 0, _fetched_at: r._fetched_at });
      if (onData) onData(rows);
      setLastUpdated(new Date());
      setCountdown(60);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  // Check ML model status
  useEffect(() => {
    apiFetch("/api/ml/status").then(setMlStatus).catch(() => {});
  }, []);

  // Train ML model
  const trainMLModel = async () => {
    try {
      const result = await apiFetch("/api/ml/train", { method: "POST" });
      if (result.error) {
        alert(result.error);
      } else {
        alert(`Model trained! CV Log Loss: ${result.cv_log_loss_mean}`);
        setMlStatus({ trained: true });
        load(); // Reload to get ML predictions
      }
    } catch (e) {
      alert("Training failed: " + e.message);
    }
  };

  // Auto-refresh countdown
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { load(); return 60; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [autoRefresh, load]);

  useEffect(() => { load(); apiFetch("/api/settings/watchlist").then(r => setWatchlist(r.watchlist || [])); }, []);

  const filtered = data
    .filter(r => filter === "ALL" || r.signal === filter)
    .filter(r => !search || r.symbol.includes(search.toUpperCase()))
    .sort((a, b) =>
      showWL
        ? (watchlist.includes(b.symbol) ? 1 : 0) - (watchlist.includes(a.symbol) ? 1 : 0) || b.score - a.score
        : b.score - a.score
    );

  const toggleWL = async (sym) => {
    const next = watchlist.includes(sym)
      ? watchlist.filter(s => s !== sym)
      : [...watchlist, sym];
    setWatchlist(next);
    await fetch(`${API}/api/settings/watchlist`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    });
  };

  // Count signals for badges
  const signalCounts = { ALL: data.length, BULLISH: 0, BEARISH: 0, NEUTRAL: 0 };
  data.forEach(r => { if (signalCounts[r.signal] !== undefined) signalCounts[r.signal]++; });

  return (
    <div>
      {/* Stale Data Warning Banner */}
      {scanMeta.stale && (
        <div style={{
          background: "rgba(251, 146, 60, 0.15)",
          border: "1px solid #fb923c",
          borderRadius: 8,
          padding: "12px 16px",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12
        }}>
          <span style={{ fontSize: 20 }}>⚠️</span>
          <div>
            <div style={{ fontWeight: 600, color: "#fb923c" }}>
              Stale Data Detected ({scanMeta.stale_count} symbols)
            </div>
            <div style={{ fontSize: 11, color: theme.muted }}>
              Some NSE responses may be outdated. Session refresh recommended.
            </div>
          </div>
          <button 
            onClick={load}
            style={{
              marginLeft: "auto", padding: "6px 12px", borderRadius: 6,
              background: "#fb923c", color: "#000", border: "none",
              cursor: "pointer", fontWeight: 600
            }}>
            Retry
          </button>
        </div>
      )}

      {/* ML Model Status */}
      {!mlStatus.trained && (
        <div style={{
          background: "rgba(99, 102, 241, 0.1)",
          border: "1px solid #6366f1",
          borderRadius: 8,
          padding: "10px 16px",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 12
        }}>
          <span style={{ fontSize: 16 }}>🤖</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, color: "#6366f1", fontSize: 12 }}>
              ML Model Not Trained
            </div>
            <div style={{ fontSize: 11, color: theme.muted }}>
              Train the LightGBM model to get AI-powered signal refinement.
            </div>
          </div>
          <button 
            onClick={trainMLModel}
            style={{
              padding: "6px 12px", borderRadius: 6,
              background: "#6366f1", color: "#fff", border: "none",
              cursor: "pointer", fontWeight: 600, fontSize: 11
            }}>
            Train Model
          </button>
        </div>
      )}

      {/* Controls */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={() => { load(); setCountdown(60); }} disabled={loading}
          className="clickable-btn"
          style={{
            padding: "6px 14px", borderRadius: 6, background: theme.accent,
          }}>
          {loading ? "⟳ Scanning..." : "⟳ Refresh"}
        </button>
        <button 
          onClick={async () => {
            if (data.length === 0) return alert("No trades to save");
            if (!window.confirm("Save these suggested trades to Accuracy Tracker?")) return;
            setSavingSnapshot(true);
            try {
              const res = await apiFetch("/api/tracker/snapshot/manual", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ results: data }),
              });
              if (res.status === "success") {
                alert(`Snapshot saved successfully! Added ${res.trades_saved} trades.`);
              } else {
                alert(res.message || "No trades met criteria.");
              }
            } catch (e) {
              console.error(e);
              alert("Failed to save snapshot.");
            }
            setSavingSnapshot(false);
          }} 
          disabled={loading || savingSnapshot || data.length === 0}
          className="clickable-btn"
          style={{
            padding: "6px 14px", borderRadius: 6, border: `1px solid ${theme.border}`,
            background: "transparent", color: theme.text, cursor: "pointer", fontWeight: 600,
            opacity: (loading || savingSnapshot || data.length === 0) ? 0.5 : 1
          }}>
          {savingSnapshot ? "Saving..." : "💾 Save Snapshot"}
        </button>
        {["ALL", "BULLISH", "BEARISH", "NEUTRAL"].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className="clickable-btn"
            style={{
              padding: "4px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
              background: filter === f ? signalBg(f) : "none",
              color: filter === f ? signalColor(f) : theme.muted,
              cursor: "pointer", fontFamily: "inherit", fontSize: 12,
              display: "flex", alignItems: "center", gap: 4
            }}>
            {f}
            <span style={{
              background: filter === f ? signalColor(f) : theme.border,
              color: filter === f ? "#fff" : theme.muted,
              borderRadius: 10, padding: "1px 6px", fontSize: 10, fontWeight: 700,
              minWidth: 18, textAlign: "center"
            }}>{signalCounts[f]}</span>
          </button>
        ))}
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="🔍 Search..."
          style={{
            padding: "5px 10px", borderRadius: 6, border: `1px solid ${theme.border}`,
            background: theme.bg, color: theme.text, fontFamily: "inherit", fontSize: 12
          }} />
        <button onClick={() => setShowWL(w => !w)}
          className="clickable-btn"
          style={{
            padding: "4px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
            background: showWL ? "rgba(99,102,241,.15)" : "none",
            color: showWL ? theme.accent : theme.muted, cursor: "pointer"
          }}>
          ★ Watchlist
        </button>
        <span style={{ color: theme.muted, fontSize: 11 }}>{filtered.length} symbols</span>
        {/* Auto-refresh controls */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <button onClick={() => setAutoRefresh(a => !a)}
            style={{
              padding: "3px 8px", borderRadius: 4, border: `1px solid ${theme.border}`,
              background: autoRefresh ? "rgba(34,197,94,.12)" : "none",
              color: autoRefresh ? theme.green : theme.muted, cursor: "pointer",
              fontSize: 11, fontFamily: "inherit"
            }}>
            {autoRefresh ? "⏱ Auto" : "⏸ Paused"}
          </button>
          {autoRefresh && (
            <span style={{ fontSize: 11, color: theme.muted, fontVariantNumeric: "tabular-nums" }}>
              {countdown}s
            </span>
          )}
          {lastUpdated && (
            <span style={{ fontSize: 10, color: theme.muted }}>
              {lastUpdated.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
          )}
        </div>
      </div>

      {loading && <Loader theme={theme} />}

      {/* Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
        {filtered.map((r, idx) => (
          <div key={r.symbol} className="scan-card" style={{ animation: `fadeIn 0.3s ease ${idx * 0.02}s both` }}>
            <ScanCard r={r} theme={theme} onChain={onChain} onGreeks={onGreeks}
              isWatched={watchlist.includes(r.symbol)} onToggleWL={toggleWL} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ScanCard({ r, theme, onChain, onGreeks, isWatched, onToggleWL }) {
  const [expanded, setExpanded] = useState(false);
  const sig = r.signal || "NEUTRAL";

  return (
    <div style={{
      background: theme.card, border: `1px solid ${theme.border}`,
      borderRadius: 8, overflow: "hidden",
      borderLeft: `3px solid ${signalColor(sig)}`
    }}>
      <div style={{ padding: "12px 14px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <button onClick={() => onToggleWL(r.symbol)}
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: isWatched ? "#f59e0b" : theme.muted, fontSize: 14
                }}>★</button>
              <span style={{ fontWeight: 700, fontSize: 15 }}>{r.symbol}</span>
              <Badge label={sig} color={signalColor(sig)} bg={signalBg(sig)} />
            </div>
            <div style={{ color: theme.muted, fontSize: 11, marginTop: 3 }}>
              ₹{fmt(r.ltp)} · {pct(r.change_pct)}
              {r.iv_rank > 0 && <span style={{ marginLeft: 8 }}>IVR {fmt(r.iv_rank, 0)}</span>}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <ScoreDial score={r.score} theme={theme} subLabel="QUANT" />
            <ScoreDial score={r.ml_score || 0} theme={theme} subLabel="ML SCORE" />
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 12 }}>
          {[["PCR", fmt(r.pcr, 3)], ["IV", `${fmt(r.iv)}%`], ["V/OI", fmt(r.vol_spike, 3)]].map(([k, v]) => (
            <div key={k} style={{ background: theme.bg, borderRadius: 6, padding: "6px 10px", textAlign: "center" }}>
              <div style={{ color: theme.muted, fontSize: 10 }}>{k}</div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{v}</div>
            </div>
          ))}
        </div>

        {/* Top Picks */}
        {r.top_picks?.length > 0 && (
          <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
            {r.top_picks.map((p, i) => (
              <div key={i} style={{
                flex: 1, background: signalBg(p.type === "CE" ? "BULLISH" : "BEARISH"),
                borderRadius: 6, padding: "6px 8px", fontSize: 11
              }}>
                <div style={{ fontWeight: 600, color: p.type === "CE" ? theme.green : theme.red }}>
                  {p.strike} {p.type}
                </div>
                <div style={{ color: theme.muted }}>₹{p.ltp} · {p.score}pts</div>
              </div>
            ))}
          </div>
        )}

        {/* Max Pain */}
        {r.max_pain && (
          <div style={{ marginTop: 8, fontSize: 11, color: theme.muted }}>
            Max Pain: <span style={{ color: theme.text }}>₹{r.max_pain}</span>
            {r.days_to_expiry && <span style={{ marginLeft: 8 }}>DTE: {r.days_to_expiry}d</span>}
          </div>
        )}

        {/* Stale Data Warning */}
        {r.stale && (
          <div style={{
            marginTop: 8, padding: "6px 10px", background: "rgba(251, 146, 60, 0.1)",
            borderRadius: 6, border: "1px solid #fb923c", fontSize: 10, color: "#fb923c"
          }}>
            ⚠️ Data may be stale — NSE session refresh recommended
          </div>
        )}

        {/* Reasons toggle */}
        {r.signal_reasons?.length > 0 && (
          <button onClick={() => setExpanded(e => !e)}
            style={{
              background: "none", border: "none", color: theme.muted, cursor: "pointer",
              fontSize: 11, padding: "6px 0 0", fontFamily: "inherit"
            }}>
            {expanded ? "▲ hide reasons" : `▼ ${r.signal_reasons.length} signal reasons`}
          </button>
        )}
        {expanded && (
          <ul style={{ margin: "6px 0 0", padding: "0 0 0 14px", fontSize: 11, color: theme.muted }}>
            {r.signal_reasons.map((reason, i) => <li key={i}>{reason}</li>)}
          </ul>
        )}
      </div>

      <div style={{ borderTop: `1px solid ${theme.border}`, display: "flex" }}>
        <button onClick={() => onChain(r.symbol)}
          style={{
            flex: 1, padding: "8px", background: "none", border: "none",
            cursor: "pointer", color: theme.accent, fontFamily: "inherit",
            fontSize: 11, fontWeight: 600, borderRight: `1px solid ${theme.border}`
          }}>
          📈 Track
        </button>
        <button onClick={() => onGreeks && onGreeks(r.symbol)}
          style={{
            flex: 1, padding: "8px", background: "none", border: "none",
            cursor: "pointer", color: theme.muted, fontFamily: "inherit",
            fontSize: 11
          }}>
          🔢 Greeks
        </button>
      </div>
    </div>
  );
}

function ScoreDial({ score, theme, subLabel = null }) {
  // v5 thresholds: 85+ is high conviction (trade-worthy), 70+ is moderate
  const color = score >= 85 ? "#22c55e" : score >= 70 ? "#f59e0b" : score >= 50 ? "#fb923c" : "#ef4444";
  const label = score >= 85 ? "HIGH" : score >= 70 ? "MED" : "LOW";
  const pctValue = Math.min(100, score);
  return (
    <div style={{ textAlign: "center", minWidth: 52 }}>
      {subLabel && <div style={{ fontSize: 9, color: theme.muted, fontWeight: 700, marginBottom: 4, whiteSpace: "nowrap" }}>{subLabel}</div>}
      <div style={{ position: "relative", width: 44, height: 44, margin: "0 auto" }}>
        <svg width="44" height="44" viewBox="0 0 48 48">
          <circle cx="24" cy="24" r="20" fill="none" stroke={theme.border} strokeWidth="3" />
          <circle cx="24" cy="24" r="20" fill="none" stroke={color} strokeWidth="3"
            strokeDasharray={`${pctValue * 1.26} 126`} strokeLinecap="round"
            transform="rotate(-90 24 24)" style={{ transition: "stroke-dasharray 0.5s ease" }} />
        </svg>
        <div style={{
          position: "absolute", top: "50%", left: "50%",
          transform: "translate(-50%, -50%)", fontSize: 13, fontWeight: 700, color
        }}>{score}</div>
      </div>
      <div style={{ fontSize: 8, color, fontWeight: 700, marginTop: 2 }}>{label}</div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Chain Tab
// ══════════════════════════════════════════════════════════════════════════════

function ChainTab({ theme, symbol, setSymbol }) {
  const [data, setData] = useState(null);
  const [expiry, setExpiry] = useState("");
  const [loading, setLoading] = useState(false);
  const [input, setInput] = useState(symbol);

  const load = useCallback(async (sym, exp) => {
    setLoading(true);
    try {
      const url = `/api/chain/${sym}` + (exp ? `?expiry=${encodeURIComponent(exp)}` : "");
      const r = await apiFetch(url);
      setData(r);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => {
    setInput(symbol);
    load(symbol, expiry);
  }, [symbol]);

  const handleSubmit = () => { setSymbol(input); load(input, expiry); };

  if (loading) return <Loader theme={theme} />;

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <SymbolInput value={input} onChange={setInput} onSubmit={handleSubmit} theme={theme} />
        {data?.expiries?.map(e => (
          <button key={e} onClick={() => { setExpiry(e); load(symbol, e); }}
            style={{
              padding: "4px 10px", borderRadius: 4, border: `1px solid ${theme.border}`,
              background: expiry === e ? theme.accent : "none",
              color: expiry === e ? "#fff" : theme.muted,
              cursor: "pointer", fontSize: 11, fontFamily: "inherit"
            }}>
            {e}
          </button>
        ))}
      </div>

      {data && (
        <>
          <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
            {[["Spot", `₹${fmt(data.spot)}`],
            ["Max Pain", data.max_pain ? `₹${data.max_pain}` : "—"],
            ["DTE", data.dte ? `${data.dte}d` : "—"]].map(([k, v]) => (
              <Card theme={theme} style={{ padding: "10px 16px" }} key={k}>
                <div style={{ color: theme.muted, fontSize: 10 }}>{k}</div>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{v}</div>
              </Card>
            ))}
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: theme.muted, borderBottom: `1px solid ${theme.border}` }}>
                  {["CE OI", "CE Vol", "CE LTP", "CE IV", "Strike", "PE IV", "PE LTP", "PE Vol", "PE OI"].map(h => (
                    <th key={h} style={{ padding: "6px 10px", textAlign: "center", fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.strikes?.map(row => (
                  <tr key={row.strike}
                    style={{
                      background: row.isATM ? "rgba(99,102,241,.08)" : "none",
                      borderBottom: `1px solid ${theme.border}`
                    }}>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: theme.green }}>
                      {(row.CE.oi / 1000).toFixed(0)}K
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: theme.muted }}>
                      {(row.CE.volume / 1000).toFixed(0)}K
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "right" }}>{fmt(row.CE.ltp)}</td>
                    <td style={{ padding: "5px 10px", textAlign: "right", color: theme.muted }}>{fmt(row.CE.iv)}</td>
                    <td style={{
                      padding: "5px 10px", textAlign: "center", fontWeight: row.isATM ? 700 : 400,
                      color: row.isATM ? theme.accent : theme.text
                    }}>
                      {row.strike}{row.isATM ? " ◀" : ""}
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "left", color: theme.muted }}>{fmt(row.PE.iv)}</td>
                    <td style={{ padding: "5px 10px", textAlign: "left" }}>{fmt(row.PE.ltp)}</td>
                    <td style={{ padding: "5px 10px", textAlign: "left", color: theme.muted }}>
                      {(row.PE.volume / 1000).toFixed(0)}K
                    </td>
                    <td style={{ padding: "5px 10px", textAlign: "left", color: theme.red }}>
                      {(row.PE.oi / 1000).toFixed(0)}K
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Greeks Tab
// ══════════════════════════════════════════════════════════════════════════════

function GreeksTab({ theme, symbol = "NIFTY" }) {
  const [input, setInput] = useState(symbol);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async (sym) => {
    setLoading(true);
    try { setData(await apiFetch(`/api/greeks/${sym}`)); }
    catch (e) { console.error(e); }
    setLoading(false);
  };

  // Sync input box and reload whenever parent changes the symbol (e.g. via Scanner Track)
  useEffect(() => {
    setInput(symbol);
    load(symbol);
  }, [symbol]);

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <SymbolInput value={input} onChange={setInput}
          onSubmit={() => load(input)} theme={theme} />
      </div>

      {loading && <Loader theme={theme} />}
      {data && (
        <>
          <div style={{ marginBottom: 8, color: theme.muted, fontSize: 12 }}>
            {data.symbol} · Spot ₹{fmt(data.spot)} · DTE {data.dte}d
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: theme.muted, borderBottom: `1px solid ${theme.border}` }}>
                  {["Strike", "CE Δ", "CE Γ", "CE θ/day", "CE Vega", "Moneyness", "PE Δ", "PE Γ", "PE θ/day", "PE Vega"].map(h => (
                    <th key={h} style={{ padding: "6px 10px", textAlign: "center", fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.strikes?.map(row => {
                  const cg = row.CE.greeks || {}; const pg = row.PE.greeks || {};
                  const isATM = cg.moneyness === "ATM" || pg.moneyness === "ATM";
                  return (
                    <tr key={row.strike}
                      style={{
                        background: isATM ? "rgba(99,102,241,.08)" : "none",
                        borderBottom: `1px solid ${theme.border}`
                      }}>
                      <td style={{
                        padding: "5px 10px", textAlign: "center", fontWeight: isATM ? 700 : 400,
                        color: isATM ? theme.accent : theme.text
                      }}>{row.strike}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.green }}>{fmt(cg.delta, 3)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.muted }}>{fmt(cg.gamma, 5)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.red }}>{fmt(cg.theta, 2)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center" }}>{fmt(cg.vega, 3)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center" }}>
                        <Badge label={cg.moneyness || "—"} color={theme.muted} bg={theme.bg} />
                      </td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.red }}>{fmt(pg.delta, 3)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.muted }}>{fmt(pg.gamma, 5)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center", color: theme.red }}>{fmt(pg.theta, 2)}</td>
                      <td style={{ padding: "5px 10px", textAlign: "center" }}>{fmt(pg.vega, 3)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// OI Heatmap Tab
// ══════════════════════════════════════════════════════════════════════════════

function HeatmapTab({ theme }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [input, setInput] = useState("NIFTY");
  const [heatmap, setHeatmap] = useState([]);
  const [pcr, setPcr] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async (sym) => {
    setLoading(true);
    try {
      const [h, p] = await Promise.all([
        apiFetch(`/api/oi-heatmap/${sym}`),
        apiFetch(`/api/pcr-history/${sym}`),
      ]);
      setHeatmap(h.data || []);
      setPcr(p.timeline || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(symbol); }, []);

  // Group heatmap by strike for bar chart
  const byStrike = {};
  heatmap.forEach(row => {
    if (!byStrike[row.strike]) byStrike[row.strike] = { ce_oi: 0, pe_oi: 0 };
    if (row.opt_type === "CE") byStrike[row.strike].ce_oi = Math.max(byStrike[row.strike].ce_oi, row.oi);
    else byStrike[row.strike].pe_oi = Math.max(byStrike[row.strike].pe_oi, row.oi);
  });
  const chartData = Object.entries(byStrike)
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(([strike, d]) => ({ strike: Number(strike), ...d }));

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <SymbolInput value={input} onChange={setInput}
          onSubmit={() => { setSymbol(input); load(input); }} theme={theme} />
      </div>
      {loading && <Loader theme={theme} />}

      {!loading && chartData.length > 0 && (
        <>
          <Card theme={theme} style={{ marginBottom: 16 }}>
            <div style={{ color: theme.muted, fontSize: 11, marginBottom: 8 }}>
              OI DISTRIBUTION BY STRIKE — {symbol}
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                <XAxis dataKey="strike" tick={{ fontSize: 10, fill: theme.muted }} />
                <YAxis tickFormatter={v => `${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 10, fill: theme.muted }} />
                <Tooltip formatter={(v, name) => [`${(v / 1000).toFixed(0)}K`, name]} />
                <Bar dataKey="pe_oi" name="PE OI" fill="#ef4444" opacity={0.8} />
                <Bar dataKey="ce_oi" name="CE OI" fill="#22c55e" opacity={0.8} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {pcr.length > 0 && (
            <Card theme={theme}>
              <div style={{ color: theme.muted, fontSize: 11, marginBottom: 8 }}>
                INTRADAY PCR — {symbol}
              </div>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={pcr} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: theme.muted }} />
                  <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: theme.muted }} />
                  <Tooltip />
                  <ReferenceLine y={1.0} stroke={theme.muted} strokeDasharray="4 4" label={{ value: "1.0", fill: theme.muted, fontSize: 10 }} />
                  <ReferenceLine y={1.3} stroke={theme.green} strokeDasharray="4 4" />
                  <ReferenceLine y={0.8} stroke={theme.red} strokeDasharray="4 4" />
                  <Line dataKey="pcr" dot={false} stroke={theme.accent} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}
        </>
      )}

      {!loading && chartData.length === 0 && (
        <Card theme={theme}>
          <div style={{ textAlign: "center", color: theme.muted, padding: 32 }}>
            No OI history yet. OI snapshots are taken every 15 minutes during market hours.
            <br /><br />
            Keep the scanner running for one full trading session to see data here.
          </div>
        </Card>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Sector Heatmap Tab
// ══════════════════════════════════════════════════════════════════════════════

function SectorTab({ theme, onChain }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setData(await apiFetch("/api/sector-heatmap")); }
    catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (loading) return <Loader theme={theme} />;
  if (!data) return null;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <span style={{ color: theme.muted, fontSize: 12 }}>Sector-level signal aggregation</span>
        <button onClick={load} style={{
          padding: "4px 12px", borderRadius: 6, background: theme.accent,
          color: "#fff", border: "none", cursor: "pointer"
        }}>⟳</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
        {Object.entries(data.sectors || {}).map(([sector, sd]) => (
          <Card key={sector} theme={theme} style={{ borderLeft: `3px solid ${signalColor(sd.signal)}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontWeight: 700 }}>{sector}</span>
              <Badge label={sd.signal} color={signalColor(sd.signal)} bg={signalBg(sd.signal)} />
            </div>
            <div style={{ display: "flex", gap: 12, marginBottom: 10, fontSize: 11, color: theme.muted }}>
              <span>Avg Score: <strong style={{ color: theme.text }}>{sd.avg_score}</strong></span>
              <span style={{ color: theme.green }}>▲ {sd.bullish}</span>
              <span style={{ color: theme.red }}>▼ {sd.bearish}</span>
              <span>— {sd.neutral}</span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {sd.symbols?.slice(0, 6).map(s => (
                <button key={s.symbol} onClick={() => onChain(s.symbol)}
                  style={{
                    padding: "2px 8px", borderRadius: 4, fontSize: 11,
                    background: signalBg(s.signal), color: signalColor(s.signal),
                    border: "none", cursor: "pointer", fontFamily: "inherit"
                  }}>
                  {s.symbol}
                  {s.bulk_deals > 0 && <span style={{ marginLeft: 3 }}>📦</span>}
                </button>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// UOA Tab
// ══════════════════════════════════════════════════════════════════════════════

function UOATab({ theme, onChain }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [threshold, setThreshold] = useState(5);

  const load = async () => {
    setLoading(true);
    try { const r = await apiFetch(`/api/uoa?threshold=${threshold}`); setData(r.data || []); }
    catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
        <span style={{ color: theme.muted, fontSize: 12 }}>Min volume ratio:</span>
        <input type="number" value={threshold} min={2} max={20}
          onChange={e => setThreshold(Number(e.target.value))}
          style={{
            width: 64, padding: "4px 8px", borderRadius: 6,
            border: `1px solid ${theme.border}`, background: theme.bg,
            color: theme.text, fontFamily: "inherit"
          }} />
        <button onClick={load} style={{
          padding: "5px 14px", borderRadius: 6, background: theme.accent,
          color: "#fff", border: "none", cursor: "pointer"
        }}>Scan</button>
        {loading && <span style={{ color: theme.muted }}>⟳</span>}
      </div>

      {!loading && data.length === 0 && (
        <Card theme={theme}>
          <div style={{ textAlign: "center", color: theme.muted, padding: 32 }}>
            No unusual activity detected (threshold: {threshold}×).
            <br />Reduce the threshold or check back when the market is active.
            <br /><br />
            <em style={{ fontSize: 11 }}>UOA requires at least 5 days of OI history to establish baselines.</em>
          </div>
        </Card>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
        {data.map((u, i) => (
          <Card key={i} theme={theme}
            style={{ borderLeft: `3px solid ${u.type === "CE" ? theme.green : theme.red}` }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <div>
                <span style={{ fontWeight: 700 }}>{u.symbol}</span>
                <span style={{ margin: "0 6px", color: theme.muted }}>·</span>
                <Badge label={`${u.strike} ${u.type}`}
                  color={u.type === "CE" ? theme.green : theme.red}
                  bg={signalBg(u.type === "CE" ? "BULLISH" : "BEARISH")} />
              </div>
              <span style={{ color: "#f59e0b", fontWeight: 700, fontSize: 16 }}>
                {u.ratio > 0 ? `${u.ratio}×` : "🔥"}
              </span>
            </div>
            <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, fontSize: 11 }}>
              {[["Volume", `${(u.volume / 1000).toFixed(0)}K`],
              ["5d Avg", u.avg_volume > 0 ? `${(u.avg_volume / 1000).toFixed(0)}K` : "—"],
              ["LTP", `₹${u.ltp}`],
              ["OI", `${(u.oi / 1000).toFixed(0)}K`],
              ["Dist", `${u.dist_pct > 0 ? "+" : ""}${u.dist_pct}%`],
              ["Spot", `₹${u.spot?.toFixed(0)}`]].map(([k, v]) => (
                <div key={k} style={{ background: theme.bg, borderRadius: 4, padding: "5px 8px" }}>
                  <div style={{ color: theme.muted, fontSize: 10 }}>{k}</div>
                  <div style={{ fontWeight: 600 }}>{v}</div>
                </div>
              ))}
            </div>
            <button onClick={() => onChain(u.symbol)}
              style={{
                marginTop: 10, width: "100%", padding: "6px", borderRadius: 6,
                background: "none", border: `1px solid ${theme.border}`,
                color: theme.accent, cursor: "pointer", fontFamily: "inherit", fontSize: 11
              }}>
              View Chain →
            </button>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Straddle Screener Tab
// ══════════════════════════════════════════════════════════════════════════════

function StraddleTab({ theme }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const r = await apiFetch("/api/straddle-screen"); setData(r.candidates || []); }
    catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <span style={{ color: theme.muted, fontSize: 12 }}>
          Symbols where PCR ≈ 1.0 and IV suggests volatility play
        </span>
        <button onClick={load} style={{
          padding: "4px 12px", borderRadius: 6, background: theme.accent,
          color: "#fff", border: "none", cursor: "pointer"
        }}>
          {loading ? "⟳" : "⟳ Scan"}
        </button>
      </div>

      {loading && <Loader theme={theme} />}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
        {data.map((s, i) => (
          <Card key={i} theme={theme} style={{ borderLeft: `3px solid #a78bfa` }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
              <span style={{ fontWeight: 700, fontSize: 15 }}>{s.symbol}</span>
              <span style={{ color: "#a78bfa", fontWeight: 600 }}>⚖ STRADDLE</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12 }}>
              <div style={{ background: theme.bg, borderRadius: 6, padding: "8px 12px" }}>
                <div style={{ color: theme.muted, fontSize: 10 }}>ATM Strike</div>
                <div style={{ fontWeight: 700 }}>{s.atm_strike}</div>
              </div>
              <div style={{ background: theme.bg, borderRadius: 6, padding: "8px 12px" }}>
                <div style={{ color: theme.muted, fontSize: 10 }}>Straddle Cost</div>
                <div style={{ fontWeight: 700 }}>₹{fmt(s.straddle_cost)}</div>
              </div>
              <div style={{ background: theme.bg, borderRadius: 6, padding: "8px 12px" }}>
                <div style={{ color: theme.muted, fontSize: 10 }}>Move Needed</div>
                <div style={{ fontWeight: 700, color: "#f59e0b" }}>{fmt(s.move_needed_pct)}%</div>
              </div>
              <div style={{ background: theme.bg, borderRadius: 6, padding: "8px 12px" }}>
                <div style={{ color: theme.muted, fontSize: 10 }}>ATM IV</div>
                <div style={{ fontWeight: 700 }}>{fmt(s.iv)}%</div>
              </div>
              <div style={{ background: theme.bg, borderRadius: 6, padding: "8px 12px" }}>
                <div style={{ color: theme.muted, fontSize: 10 }}>Breakeven ↑</div>
                <div style={{ fontWeight: 600, color: theme.green }}>₹{fmt(s.breakeven_upper, 0)}</div>
              </div>
              <div style={{ background: theme.bg, borderRadius: 6, padding: "8px 12px" }}>
                <div style={{ color: theme.muted, fontSize: 10 }}>Breakeven ↓</div>
                <div style={{ fontWeight: 600, color: theme.red }}>₹{fmt(s.breakeven_lower, 0)}</div>
              </div>
            </div>
            {s.strangle && (
              <div style={{
                marginTop: 10, padding: 10, background: "rgba(167,139,250,.08)",
                borderRadius: 6, fontSize: 11
              }}>
                <div style={{ color: "#a78bfa", fontWeight: 600, marginBottom: 4 }}>Strangle Alternative</div>
                <div style={{ color: theme.muted }}>
                  CE {s.strangle.ce_strike} @ ₹{s.strangle.ce_ltp} +
                  PE {s.strangle.pe_strike} @ ₹{s.strangle.pe_ltp} =
                  <strong style={{ color: theme.text }}> ₹{fmt(s.strangle.cost)} </strong>
                  <span style={{ color: theme.green }}>(saves ₹{fmt(s.strangle.cheaper_by)})</span>
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Manual Trade Tab (Top Signals)
// ══════════════════════════════════════════════════════════════════════════════

function ManualTradeTab({ theme }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lotSizes, setLotSizes] = useState({});
  const [submitting, setSubmitting] = useState(null); // stores active symbol submitting
  const [formFeedback, setFormFeedback] = useState({}); // { symbol: { success: "", error: "" } }

  // We maintain a state of "entry forms" keyed by symbol
  const [forms, setForms] = useState({});
  const [sortConfig, setSortConfig] = useState({ key: "score", direction: "desc" });

  const sortedData = [...data].sort((a, b) => {
    let valA, valB;
    if (sortConfig.key === "score") {
      valA = a.score || 0;
      valB = b.score || 0;
    } else if (sortConfig.key === "pick_score") {
      valA = (a.top_picks && a.top_picks[0]) ? a.top_picks[0].score : 0;
      valB = (b.top_picks && b.top_picks[0]) ? b.top_picks[0].score : 0;
    } else if (sortConfig.key === "symbol") {
      valA = a.symbol || "";
      valB = b.symbol || "";
    }
    
    if (valA < valB) return sortConfig.direction === "asc" ? -1 : 1;
    if (valA > valB) return sortConfig.direction === "asc" ? 1 : -1;
    return 0;
  });

  const requestSort = (key) => {
    let direction = "desc";
    if (sortConfig.key === key && sortConfig.direction === "desc") { direction = "asc"; }
    setSortConfig({ key, direction });
  };
  
  const SortIcon = ({ col }) => {
    if (sortConfig.key !== col) return " ↕";
    return sortConfig.direction === "asc" ? " ↑" : " ↓";
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, ls] = await Promise.all([
        apiFetch("/api/scan?limit=51"),
        apiFetch("/api/lot-sizes")
      ]);
      const rows = (r.candidates || r.data || []).filter(row => row.score >= 70); // High confidence only
      setData(rows);
      setLotSizes(ls);

      // Initialize form states
      const initialForms = {};
      rows.forEach(row => {
        const pick = (row.top_picks && row.top_picks.length > 0) ? row.top_picks[0] : null;
        initialForms[row.symbol] = {
          symbol: row.symbol,
          type: pick ? pick.type : (row.signal === "BULLISH" ? "CE" : "PE"),
          strike: pick ? pick.strike : "",
          entry_price: pick ? pick.ltp : "",
          lots: 1,
          reason: pick ? `Manual: Top Pick (Score: ${pick.score})` : `Manual: Top Signal (Score: ${fmt(row.score, 0)})`
        };
      });
      setForms(initialForms);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, []);

  const updateForm = (sym, field, val) => {
    setForms(prev => ({
      ...prev,
      [sym]: { ...prev[sym], [field]: val }
    }));
  };

  const submitTrade = async (e, row) => {
    e.preventDefault();
    const sym = row.symbol;
    const form = forms[sym];
    const ls = lotSizes[sym] || 1;

    setFormFeedback(prev => ({ ...prev, [sym]: null }));
    if (!form.strike || !form.entry_price) {
      setFormFeedback(prev => ({ ...prev, [sym]: { error: "Strike and entry price required" } }));
      return;
    }

    setSubmitting(sym);
    try {
      const res = await fetch(`${API}/api/paper-trades`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, strike: +form.strike, entry_price: +form.entry_price, lots: +form.lots }),
      });
      const json = await res.json();
      if (!res.ok) {
        setFormFeedback(prev => ({ ...prev, [sym]: { error: json.detail || "Error" } }));
      } else {
        setFormFeedback(prev => ({ ...prev, [sym]: { success: `✅ ${form.lots} lots × ${ls} = ${form.lots * ls} qty` } }));
        updateForm(sym, "strike", "");
        updateForm(sym, "entry_price", "");
      }
    } catch (ex) {
      setFormFeedback(prev => ({ ...prev, [sym]: { error: String(ex) } }));
    }
    setSubmitting(null);
  };

  const inp = (extra = {}) => ({
    style: {
      background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 6,
      color: theme.text, padding: "7px 10px", fontSize: 13, width: "100%", boxSizing: "border-box",
      ...extra
    }
  });

  if (loading) return <Loader theme={theme} />;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h2>High Confidence Signals</h2>
        <button onClick={load} style={{ padding: "6px 14px", borderRadius: 6, background: theme.accent, color: "#fff", border: "none", cursor: "pointer" }}>⟳ Refresh</button>
      </div>

      <Card theme={theme} style={{ padding: 0, overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
          <thead>
            <tr style={{ background: theme.border, color: theme.muted, textTransform: "uppercase", fontSize: 11 }}>
              <th onClick={() => requestSort("symbol")} style={{ padding: "12px 16px", cursor: "pointer", userSelect: "none" }}>Symbol <SortIcon col="symbol"/></th>
              <th style={{ padding: "12px 16px" }}>Signal</th>
              <th onClick={() => requestSort("score")} style={{ padding: "12px 16px", cursor: "pointer", userSelect: "none" }}>Scores <SortIcon col="score"/></th>
              <th onClick={() => requestSort("pick_score")} style={{ padding: "12px 16px", cursor: "pointer", userSelect: "none" }}>Option Contract <SortIcon col="pick_score"/></th>
              <th style={{ padding: "12px 16px" }}>Entry Limit</th>
              <th style={{ padding: "12px 16px" }}>Qty Target</th>
              <th style={{ padding: "12px 16px", textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 && (
              <tr><td colSpan="7" style={{ padding: 16, textAlign: "center", color: theme.muted }}>No high-confidence signals found.</td></tr>
            )}
            {sortedData.map(row => {
              const form = forms[row.symbol] || {};
              const ls = lotSizes[row.symbol] || 1;
              const pick = (row.top_picks && row.top_picks.length > 0) ? row.top_picks[0] : null;
              
              const qty = (form.lots || 1) * ls;
              const perLot = form.entry_price ? (+form.entry_price) * ls : 0;
              const capital = form.entry_price ? ((+form.entry_price) * qty).toLocaleString("en-IN") : "—";
              const feedback = formFeedback[row.symbol] || {};
              const isSubmitting = submitting === row.symbol;

              return (
                <tr key={row.symbol} style={{ borderBottom: `1px solid ${theme.border}` }}>
                  <td style={{ padding: "12px 16px", fontWeight: 700, verticalAlign: "middle" }}>
                    {row.symbol}
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "middle" }}>
                    <div style={{
                      display: "inline-block", background: signalBg(row.signal), color: signalColor(row.signal),
                      padding: "4px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700
                    }}>
                      {row.signal}
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "middle", fontSize: 12 }}>
                    <div>Stock: <b>{fmt(row.score,0)}</b></div>
                    <div style={{ color: theme.muted }}>Opt: <b>{pick ? pick.score : "—"}</b></div>
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "middle" }}>
                    {pick ? (
                      <Badge bg={form.type === "CE" ? "rgba(34,197,94,.15)" : "rgba(239,68,68,.15)"} 
                             color={form.type === "CE" ? theme.green : theme.red} 
                             label={`${form.strike} ${form.type}`} />
                    ) : (
                      <span style={{ color: theme.muted }}>N/A</span>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "middle" }}>
                    {pick ? (
                       <div>
                         <b>₹{fmt(form.entry_price)}</b>
                         <div style={{ fontSize: 11, color: theme.muted }}>LTP: ₹{fmt(row.ltp)}</div>
                         {perLot > 0 && (
                           <div style={{ fontSize: 11, color: theme.accent, fontWeight: 600 }}>Lot: ₹{perLot.toLocaleString("en-IN")}</div>
                         )}
                       </div>
                    ) : "—"}
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "middle" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <input 
                        {...inp({ padding: "4px 8px", width: 60 })} 
                        type="number" min="1" step="1"
                        value={form.lots || 1} 
                        onChange={e => updateForm(row.symbol, "lots", e.target.value)} 
                        disabled={!pick}
                      />
                      <span style={{ fontSize: 11, color: theme.muted }}>lots ({qty})</span>
                    </div>
                    <div style={{ fontSize: 11, marginTop: 4, color: theme.muted }}>Cap: ₹{capital}</div>
                  </td>
                  <td style={{ padding: "12px 16px", verticalAlign: "middle", textAlign: "right" }}>
                    {feedback.error ? (
                      <div style={{ color: theme.red, fontSize: 11, marginBottom: 6 }}>{feedback.error}</div>
                    ) : feedback.success ? (
                       <div style={{ color: theme.green, fontSize: 11, marginBottom: 6 }}>{feedback.success}</div>
                    ) : null}
                    <button 
                      onClick={(e) => pick && submitTrade(e, row)} 
                      disabled={isSubmitting || !pick} 
                      style={{
                        padding: "6px 12px", background: isSubmitting || !pick ? theme.border : theme.accent, 
                        color: isSubmitting || !pick ? theme.muted : "#fff", border: "none",
                        borderRadius: 6, fontWeight: 700, fontSize: 12, cursor: isSubmitting || !pick ? "not-allowed" : "pointer",
                      }}>
                      {isSubmitting ? "Wait..." : "⚡ One-Click Trade"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Portfolio Tab
// ══════════════════════════════════════════════════════════════════════════════

function PortfolioTab({ theme }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [openTrades, setOpenTrades] = useState([]);
  const [closedTrades, setClosedTrades] = useState([]);
  const [noteInput, setNoteInput] = useState({});
  const [exitInputs, setExitInputs] = useState({}); // { tradeId: exitPrice }
  const [exitingId, setExitingId]   = useState(null);
  const [viewType, setViewType] = useState("ALL"); // ALL, AUTO, MANUAL

  // ── Manual Trade Form ──
  const [showForm, setShowForm] = useState(false);
  const [lotSizes, setLotSizes] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");
  const [form, setForm] = useState({
    symbol: "NIFTY", type: "CE", strike: "", entry_price: "", lots: 1, reason: "Manual"
  });

  const load = async () => {
    setLoading(true);
    try {
      const [p, o, ls, hist] = await Promise.all([
        apiFetch("/api/portfolio"),
        apiFetch("/api/paper-trades/active"),
        apiFetch("/api/lot-sizes"),
        apiFetch("/api/paper-trades/history"),
      ]);
      setData(p);
      setOpenTrades(Array.isArray(o) ? o : []);
      setClosedTrades(Array.isArray(hist) ? hist.slice(0, 20) : []);
      setLotSizes(ls);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const addNote = async (tradeId) => {
    const note = noteInput[tradeId];
    if (!note) return;
    await fetch(`${API}/api/paper-trades/${tradeId}/note?note=${encodeURIComponent(note)}`, { method: "POST" });
    setNoteInput(prev => ({ ...prev, [tradeId]: "" }));
  };

  const exitTrade = async (tradeId) => {
    const exitPrice = exitInputs[tradeId];
    setExitingId(tradeId);
    // Optimistically remove from open list immediately
    const exitedTrade = openTrades.find(t => t.id === tradeId);
    setOpenTrades(prev => prev.filter(t => t.id !== tradeId));
    try {
      const url = exitPrice
        ? `${API}/api/paper-trades/${tradeId}/exit?exit_price=${exitPrice}`
        : `${API}/api/paper-trades/${tradeId}/exit`;
      const res = await fetch(url, { method: "POST" });
      if (res.ok) {
        // Add to closed trades list immediately
        if (exitedTrade) {
          const price = exitPrice ? +exitPrice : (exitedTrade.current_price || exitedTrade.entry_price);
          const pnl = (price - exitedTrade.entry_price) * (exitedTrade.lot_size || 1);
          setClosedTrades(prev => [{ ...exitedTrade, exit_price: price, pnl, pnl_pct: ((price - exitedTrade.entry_price) / exitedTrade.entry_price * 100), status: "CLOSED" }, ...prev]);
        }
        // Reload full portfolio stats in background
        load();
      } else {
        // Rollback on failure
        setOpenTrades(prev => exitedTrade ? [exitedTrade, ...prev] : prev);
      }
    } catch (ex) { console.error(ex); setOpenTrades(prev => exitedTrade ? [exitedTrade, ...prev] : prev); }
    setExitingId(null);
  };

  const submitTrade = async (e) => {
    e.preventDefault();
    setFormError(""); setFormSuccess("");
    if (!form.strike || !form.entry_price) { setFormError("Strike and entry price are required"); return; }
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/paper-trades`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, strike: +form.strike, entry_price: +form.entry_price, lots: +form.lots }),
      });
      const json = await res.json();
      if (!res.ok) { setFormError(json.detail || "Error"); }
      else {
        const ls = lotSizes[form.symbol] || 1;
        setFormSuccess(`✅ Trade added! ${form.lots} lot(s) × ${ls} = ${form.lots * ls} qty · ₹${json.capital?.toLocaleString("en-IN")} capital`);
        setForm(f => ({ ...f, strike: "", entry_price: "", reason: "Manual" }));
        load(); // refresh positions
      }
    } catch (ex) { setFormError(String(ex)); }
    setSubmitting(false);
  };

  const lotSize = lotSizes[form.symbol] || 1;
  const qty = (form.lots || 1) * lotSize;
  const capital = form.entry_price ? ((+form.entry_price) * qty).toLocaleString("en-IN") : "—";

  const inp = (extra = {}) => ({
    style: {
      background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 6,
      color: theme.text, padding: "7px 10px", fontSize: 13, width: "100%", boxSizing: "border-box",
      ...extra
    }
  });

  const symbols = Object.keys(lotSizes).length ? Object.keys(lotSizes) : ["NIFTY", "BANKNIFTY", "FINNIFTY"];


  if (loading) return <Loader theme={theme} />;
  if (!data) return null;

  const stats = (viewType === "AUTO" ? data.auto_stats : viewType === "MANUAL" ? data.manual_stats : data.closed_trades) || {};
  const equity = stats?.equity_curve || [];

  return (
    <div>
      {/* ── Manual Paper Trade Form ── */}
      <Card theme={theme} style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontWeight: 600, fontSize: 13 }}>📝 Manual Paper Trade</div>
          <button onClick={() => { setShowForm(f => !f); setFormError(""); setFormSuccess(""); }}
            style={{
              background: theme.accent, color: "#fff", border: "none", borderRadius: 5,
              padding: "5px 14px", fontSize: 12, cursor: "pointer", fontWeight: 600
            }}>
            {showForm ? "✕ Close" : "+ New Trade"}
          </button>
        </div>

        {showForm && (
          <form onSubmit={submitTrade} style={{ marginTop: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
              {/* Symbol */}
              <div>
                <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 3 }}>SYMBOL</label>
                <select {...inp()} value={form.symbol}
                  onChange={e => setForm(f => ({ ...f, symbol: e.target.value }))}>
                  {symbols.sort().map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

              {/* Type CE/PE */}
              <div>
                <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 3 }}>TYPE</label>
                <div style={{ display: "flex", gap: 6 }}>
                  {["CE", "PE"].map(t => (
                    <button key={t} type="button" onClick={() => setForm(f => ({ ...f, type: t }))}
                      style={{
                        flex: 1, padding: "7px 0", borderRadius: 6, fontWeight: 700, fontSize: 13,
                        cursor: "pointer", border: "none",
                        background: form.type === t ? (t === "CE" ? theme.green : theme.red) : theme.border,
                        color: form.type === t ? "#fff" : theme.muted,
                      }}>{t}</button>
                  ))}
                </div>
              </div>

              {/* Strike */}
              <div>
                <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 3 }}>STRIKE</label>
                <input {...inp()} type="number" step="50" placeholder="e.g. 24500"
                  value={form.strike} onChange={e => setForm(f => ({ ...f, strike: e.target.value }))} />
              </div>

              {/* Entry Price */}
              <div>
                <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 3 }}>ENTRY PRICE (₹)</label>
                <input {...inp()} type="number" step="0.05" placeholder="e.g. 120.50"
                  value={form.entry_price} onChange={e => setForm(f => ({ ...f, entry_price: e.target.value }))} />
              </div>

              {/* Lots */}
              <div>
                <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 3 }}>
                  LOTS <span style={{ color: theme.accent }}>× {lotSize} = {qty} qty</span>
                </label>
                <input {...inp()} type="number" min="1" step="1"
                  value={form.lots} onChange={e => setForm(f => ({ ...f, lots: e.target.value }))} />
              </div>

              {/* Reason */}
              <div>
                <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 3 }}>REASON</label>
                <input {...inp()} type="text" placeholder="Optional note"
                  value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))} />
              </div>
            </div>

            {/* Live preview */}
            <div style={{ marginTop: 10, fontSize: 12, color: theme.muted, display: "flex", gap: 20 }}>
              <span>Lot size: <b style={{ color: theme.text }}>{lotSize}</b></span>
              <span>Qty: <b style={{ color: theme.text }}>{qty}</b></span>
              <span>Est. capital: <b style={{ color: theme.accent }}>₹{capital}</b></span>
            </div>

            {formError && <div style={{ marginTop: 8, color: theme.red, fontSize: 12 }}>⚠ {formError}</div>}
            {formSuccess && <div style={{ marginTop: 8, color: theme.green, fontSize: 12 }}>{formSuccess}</div>}

            <button type="submit" disabled={submitting}
              style={{
                marginTop: 14, background: theme.accent, color: "#fff", border: "none",
                borderRadius: 6, padding: "9px 24px", fontWeight: 700, fontSize: 13,
                cursor: submitting ? "not-allowed" : "pointer", opacity: submitting ? 0.6 : 1
              }}>
              {submitting ? "Adding…" : "Add Trade"}
            </button>
          </form>
        )}
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
        {[
          ["Total P&L", `₹${(stats.total_pnl ?? 0).toLocaleString("en-IN")}`, (stats.total_pnl ?? 0) >= 0 ? theme.green : theme.red],
          ["Unrealised", `₹${(data.unrealised_pnl ?? 0).toLocaleString("en-IN")}`, (data.unrealised_pnl ?? 0) >= 0 ? theme.green : theme.red],
          ["Win Rate", `${stats.win_rate ?? 0}%`, (stats.win_rate ?? 0) >= 50 ? theme.green : theme.red],
          ["Trades", `${stats.wins ?? 0}W / ${stats.losses ?? 0}L`, theme.text],
          ["Avg P&L%", `${pct(stats.avg_pnl_pct ?? 0)}`, (stats.avg_pnl_pct ?? 0) >= 0 ? theme.green : theme.red],
          ["Max Drawdown", `₹${(stats.max_drawdown || 0).toLocaleString("en-IN")}`, theme.red],
          ["Capital", `₹${(data.capital ?? 0).toLocaleString("en-IN")}`, theme.muted],
          ["Open", `${data.open_positions ?? 0} pos`, theme.accent],
        ].map(([label, value, color], i) => (
          <Card key={i} theme={theme}>
            <div style={{ color: theme.muted, fontSize: 10, marginBottom: 4 }}>{label}</div>
            <div style={{ fontWeight: 700, fontSize: 16, color }}>{value}</div>
          </Card>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>Performance Snapshot</h3>
        <select {...inp({ width: "auto", padding: "6px 12px", background: theme.bg })} 
          value={viewType} onChange={e => setViewType(e.target.value)}>
          <option value="ALL">All Trades</option>
          <option value="AUTO">🤖 Auto System</option>
          <option value="MANUAL">👨‍💻 Manual Trades</option>
        </select>
      </div>

      {/* Equity Curve - responds to viewType */}
      <Card theme={theme} style={{ marginBottom: 20 }}>
        <div style={{ color: theme.muted, fontSize: 11, marginBottom: 8 }}>
          {viewType === "AUTO" ? "🤖 AUTO SYSTEM" : viewType === "MANUAL" ? "👨‍💻 MANUAL" : "ALL"} — EQUITY CURVE
        </div>
        {equity.length > 1 ? (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={equity} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: theme.muted }} />
              <YAxis tickFormatter={v => `₹${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 10, fill: theme.muted }} />
              <Tooltip formatter={v => [`₹${v.toLocaleString("en-IN")}`, "Cumulative P&L"]} />
              <ReferenceLine y={0} stroke={theme.muted} strokeDasharray="4 4" />
              <Line dataKey="cumulative" dot={false}
                stroke={viewType === "MANUAL" ? theme.accent : viewType === "AUTO" ? theme.green : theme.accent}
                strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ color: theme.muted, textAlign: "center", padding: 24, fontSize: 13 }}>
            No closed trades yet for this view.
          </div>
        )}
      </Card>

      {/* By Symbol Breakdown */}
      {Object.keys(stats.by_symbol || {}).length > 0 && (
        <Card theme={theme} style={{ marginBottom: 20 }}>
          <div style={{ color: theme.muted, fontSize: 11, marginBottom: 10 }}>BY SYMBOL</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
            {Object.entries(stats.by_symbol)
              .sort((a, b) => b[1].pnl - a[1].pnl)
              .map(([sym, sd]) => (
                <div key={sym} style={{ background: theme.bg, borderRadius: 6, padding: "8px 12px" }}>
                  <div style={{ fontWeight: 600 }}>{sym}</div>
                  <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>
                    {sd.trades} trades · {sd.win_rate}% WR
                  </div>
                  <div style={{ fontWeight: 600, color: sd.pnl >= 0 ? theme.green : theme.red }}>
                    ₹{sd.pnl.toLocaleString("en-IN")}
                  </div>
                </div>
              ))}
          </div>
        </Card>
      )}

      {/* Open Positions with Journal & Exit */}
      {openTrades.length > 0 && (
        <Card theme={theme}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ color: theme.muted, fontSize: 11 }}>OPEN POSITIONS ({openTrades.length})</div>
            <button onClick={load} style={{
              padding: "3px 10px", borderRadius: 4, background: "none",
              border: `1px solid ${theme.border}`, color: theme.muted,
              cursor: "pointer", fontSize: 10, fontFamily: "inherit"
            }}>⟳ Refresh</button>
          </div>
          {openTrades.map(t => {
            const pnlPct = t.pnl_pct || 0;
            const isExiting = exitingId === t.id;
            // TP/SL progress bar (TP = +25%, SL = -15%)
            const tpPct = 25, slPct = 15;
            const barPct = pnlPct >= 0 ? Math.min(100, (pnlPct / tpPct) * 100) : Math.min(100, (Math.abs(pnlPct) / slPct) * 100);
            const barColor = pnlPct >= 0 ? theme.green : theme.red;
            // Time in trade
            const entryTime = t.entry_time ? new Date(t.entry_time) : null;
            const elapsed = entryTime ? Math.floor((Date.now() - entryTime.getTime()) / 60000) : 0;
            const elapsedStr = elapsed > 60 ? `${Math.floor(elapsed/60)}h ${elapsed%60}m` : `${elapsed}m`;
            return (
              <div key={t.id} className="trade-row" style={{ borderBottom: `1px solid ${theme.border}`, padding: "10px 0" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <span style={{ fontWeight: 600 }}>{t.symbol}</span>
                    <span style={{ margin: "0 6px", color: theme.muted }}>·</span>
                    <Badge label={`${t.strike} ${t.type}`}
                      color={t.type === "CE" ? theme.green : theme.red}
                      bg={signalBg(t.type === "CE" ? "BULLISH" : "BEARISH")} />
                    {entryTime && <span style={{ marginLeft: 8, fontSize: 10, color: theme.muted }}>⏱ {elapsedStr}</span>}
                    <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>Entry ₹{t.entry_price} → Current ₹{t.current_price || "—"}</div>
                    {/* TP/SL progress bar */}
                    <div style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: 9, color: theme.red, fontWeight: 600 }}>SL -{slPct}%</span>
                      <div style={{ flex: 1, height: 4, borderRadius: 2, background: theme.border, maxWidth: 120, position: "relative" }}>
                        <div style={{
                          height: "100%", borderRadius: 2, background: barColor,
                          width: `${barPct}%`, transition: "width 0.3s ease",
                          position: "absolute", [pnlPct >= 0 ? "left" : "right"]: "50%"
                        }} />
                      </div>
                      <span style={{ fontSize: 9, color: theme.green, fontWeight: 600 }}>TP +{tpPct}%</span>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 700, fontSize: 15, color: pnlPct >= 0 ? theme.green : theme.red }}>
                      {pct(pnlPct)}
                    </div>
                    <div style={{ fontSize: 11, color: pnlPct >= 0 ? theme.green : theme.red }}>
                      ₹{(t.pnl || 0).toLocaleString("en-IN")}
                    </div>
                  </div>
                </div>

                {/* Exit row */}
                <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <input
                    type="number" step="0.05" placeholder={`Exit price (default: ${t.current_price || t.entry_price})`}
                    value={exitInputs[t.id] || ""}
                    onChange={e => setExitInputs(prev => ({ ...prev, [t.id]: e.target.value }))}
                    style={{
                      flex: 1, minWidth: 160, padding: "4px 8px", borderRadius: 4,
                      border: `1px solid ${theme.border}`, background: theme.bg,
                      color: theme.text, fontFamily: "inherit", fontSize: 11
                    }}
                  />
                  <button onClick={() => exitTrade(t.id)} disabled={isExiting}
                    style={{
                      padding: "4px 12px", borderRadius: 4, background: isExiting ? theme.border : theme.red,
                      color: isExiting ? theme.muted : "#fff", border: "none", cursor: isExiting ? "not-allowed" : "pointer",
                      fontSize: 11, fontWeight: 700
                    }}>
                    {isExiting ? "Exiting..." : "⬛ Exit Trade"}
                  </button>
                  <input value={noteInput[t.id] || ""}
                    onChange={e => setNoteInput(prev => ({ ...prev, [t.id]: e.target.value }))}
                    placeholder="Add journal note..."
                    style={{
                      flex: 1, minWidth: 120, padding: "4px 8px", borderRadius: 4,
                      border: `1px solid ${theme.border}`, background: theme.bg,
                      color: theme.text, fontFamily: "inherit", fontSize: 11
                    }} />
                  <button onClick={() => addNote(t.id)}
                    style={{
                      padding: "4px 10px", borderRadius: 4, background: theme.accent,
                      color: "#fff", border: "none", cursor: "pointer", fontSize: 11
                    }}>
                    + Note
                  </button>
                </div>
              </div>
            );
          })}
        </Card>
      )}

      {/* Closed Trades History */}
      {closedTrades.length > 0 && (
        <Card theme={theme} style={{ marginTop: 20 }}>
          <div style={{ color: theme.muted, fontSize: 11, marginBottom: 10 }}>RECENTLY CLOSED TRADES</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ color: theme.muted, textAlign: "left", fontSize: 11, textTransform: "uppercase" }}>
                <th style={{ padding: "6px 10px" }}>Symbol</th>
                <th style={{ padding: "6px 10px" }}>Contract</th>
                <th style={{ padding: "6px 10px" }}>Entry</th>
                <th style={{ padding: "6px 10px" }}>Exit</th>
                <th style={{ padding: "6px 10px", textAlign: "right" }}>P&amp;L</th>
                <th style={{ padding: "6px 10px", textAlign: "right" }}>P&amp;L %</th>
                <th style={{ padding: "6px 10px" }}>Exit Reason</th>
              </tr>
            </thead>
            <tbody>
              {closedTrades.map((t, i) => {
                const pnl = t.pnl || 0;
                const pnlPct = t.pnl_pct || 0;
                const color = pnl >= 0 ? theme.green : theme.red;
                const reason = t.reason || "";
                const isTP = reason.includes("TP");
                const isSL = reason.includes("SL");
                const isEOD = reason.includes("EOD");
                return (
                  <tr key={t.id ?? i} className="trade-row" style={{ borderTop: `1px solid ${theme.border}` }}>
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>{t.symbol}</td>
                    <td style={{ padding: "8px 10px" }}>
                      <Badge label={`${t.strike} ${t.type}`}
                        color={t.type === "CE" ? theme.green : theme.red}
                        bg={signalBg(t.type === "CE" ? "BULLISH" : "BEARISH")} />
                    </td>
                    <td style={{ padding: "8px 10px" }}>₹{fmt(t.entry_price)}</td>
                    <td style={{ padding: "8px 10px" }}>₹{fmt(t.exit_price)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color, fontWeight: 700 }}>
                      {pnl >= 0 ? "+" : ""}₹{pnl.toLocaleString("en-IN")}
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color }}>
                      {pnlPct >= 0 ? "+" : ""}{fmt(pnlPct, 1)}%
                    </td>
                    <td style={{ padding: "8px 10px" }}>
                      <span style={{
                        fontSize: 10, padding: "2px 6px", borderRadius: 4,
                        background: isTP ? "rgba(34,197,94,.12)" : isSL ? "rgba(239,68,68,.12)" : isEOD ? "rgba(148,163,184,.12)" : "none",
                        color: isTP ? theme.green : isSL ? theme.red : theme.muted,
                        fontWeight: 600
                      }}>
                        {isTP ? "✅ TP" : isSL ? "❌ SL" : isEOD ? "🔲 EOD" : reason.slice(0, 20) || "—"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Settings Tab
// ══════════════════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════════════════
// Accuracy Tracker Tab
// ══════════════════════════════════════════════════════════════════════════════

function AccuracyTab({ theme }) {
  const [snapshots, setSnapshots] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState(null); // for graph modal
  const [history, setHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);

  const sortedTrades = useMemo(() => {
    if (!data?.trades) return [];
    let sortableTrades = [...data.trades];
    if (sortConfig.key !== null) {
      sortableTrades.sort((a, b) => {
        let aVal = a[sortConfig.key];
        let bVal = b[sortConfig.key];
        
        // Custom logic for derived columns
        if (sortConfig.key === 'pnl') {
          aVal = a.current_price && a.entry_price ? ((a.current_price - a.entry_price) / a.entry_price) * 100 : 0;
          bVal = b.current_price && b.entry_price ? ((b.current_price - b.entry_price) / b.entry_price) * 100 : 0;
        } else if (sortConfig.key === 'lotPrice') {
          aVal = (a.current_price || a.entry_price) * (a.lot_size || 1);
          bVal = (b.current_price || b.entry_price) * (b.lot_size || 1);
        }

        if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return sortableTrades;
  }, [data, sortConfig]);

  const requestSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
    setSortConfig({ key, direction });
  };

  useEffect(() => {
    const fetchSnaps = () => apiFetch("/api/tracker/snapshots").then(setSnapshots).catch(console.error);
    fetchSnaps();
    const interval = setInterval(fetchSnaps, 60000); // Check for new snapshots every minute
    return () => clearInterval(interval);
  }, []);

  const loadSnapshot = async (id) => {
    if (!id) {
      setData(null);
      setSelectedId("");
      return;
    }
    setLoading(true);
    try {
      const res = await apiFetch(`/api/tracker/snapshot/${id}`);
      setData(res);
      setSelectedId(id);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const loadHistory = async (trade) => {
    setSelectedTrade(trade);
    setLoadingHistory(true);
    try {
      const res = await apiFetch(`/api/tracker/trade/${trade.id}/history`);
      const hist = (res.history || []).map(h => ({ ...h, timestamp: h.timestamp + (h.timestamp.endsWith("Z") ? "" : "Z") }));
      if (hist.length === 1) {
        // Duplicate the first point to the current time so the graph draws a flat line instead of failing to render
        hist.push({ ...hist[0], timestamp: new Date().toISOString() });
      }
      setHistory(hist);
    } catch (e) { console.error(e); }
    setLoadingHistory(false);
  };

  const loadReport = async () => {
    setReportLoading(true);
    try {
      const res = await apiFetch("/api/tracker/report");
      setReport(res.report);
    } catch (e) {
      console.error("Failed to load report", e);
      alert("Failed to load report.");
    }
    setReportLoading(false);
  };

  const deleteSnapshot = async () => {
    if (!selectedId) return;
    if (!window.confirm("Are you sure you want to delete this snapshot? All associated trades and history will be permanently removed.")) return;
    
    setLoading(true);
    try {
      await apiFetch(`/api/tracker/snapshot/${selectedId}`, { method: 'DELETE' });
      setData(null);
      setSelectedId("");
      setSelectedTrade(null);
      const sns = await apiFetch("/api/tracker/snapshots");
      setSnapshots(sns);
    } catch (e) { 
      console.error("Failed to delete snapshot", e); 
      alert("Failed to delete snapshot.");
    }
    setLoading(false);
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 12, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 18, color: theme.accent }}>Accuracy Tracker</h2>
        <select 
          value={selectedId} 
          onChange={e => loadSnapshot(e.target.value)}
          style={{
            padding: "8px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
            background: theme.card, color: theme.text, fontFamily: "inherit",
            fontSize: 13, minWidth: 260
          }}
        >
          <option value="">Select a previous snapshot...</option>
          {snapshots.map(s => (
            <option key={s.id} value={s.id}>
              {new Date(s.timestamp + (s.timestamp.endsWith("Z") ? "" : "Z")).toLocaleString("en-IN", { 
                day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' 
              })} — {s.trade_count} signals
            </option>
          ))}
        </select>
        <button onClick={() => loadSnapshot(selectedId)} disabled={!selectedId || loading}
          className="clickable-btn"
          style={{
            padding: "8px 16px", borderRadius: 6, background: theme.accent,
            color: "#fff", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600,
            opacity: (!selectedId || loading) ? 0.5 : 1
          }}>
          {loading ? "Loading..." : "↻ Refresh Prices"}
        </button>
        {selectedId && (
          <button onClick={deleteSnapshot} disabled={loading}
            className="clickable-btn"
            style={{
              padding: "8px 16px", borderRadius: 6, background: "transparent",
              color: theme.red, border: `1px solid ${theme.red}`, cursor: "pointer", fontSize: 13, fontWeight: 600,
              opacity: loading ? 0.5 : 1
            }}>
            Delete
          </button>
        )}

        <div style={{ flex: 1 }} />
        <button onClick={loadReport} disabled={reportLoading}
          className="clickable-btn"
          style={{
            padding: "8px 16px", borderRadius: 6, background: theme.accent + "22",
            color: theme.accent, border: `1px solid ${theme.border}`, cursor: "pointer", fontSize: 13, fontWeight: 600,
            display: "flex", alignItems: "center", gap: 6
          }}>
          {reportLoading ? "Generating..." : "📈 View Backtest Report"}
        </button>
      </div>

      {!data && !loading && (
        <Card theme={theme} style={{ textAlign: "center", padding: 60, color: theme.muted }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>📊</div>
          <div>Select a snapshot from the dropdown above to analyze signal accuracy.</div>
          <div style={{ fontSize: 11, marginTop: 8 }}>Snapshots are taken every 15 minutes during market hours.</div>
        </Card>
      )}

      {loading && <Loader theme={theme} />}

      {data && !loading && (
        <div style={{ animation: "fadeIn 0.3s ease" }}>
          <Card theme={theme} style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 11, color: theme.muted }}>SNAPSHOT TIMESTAMP</div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>
                {new Date(data.snapshot.timestamp + (data.snapshot.timestamp.endsWith("Z") ? "" : "Z")).toLocaleString("en-IN", { 
                   dateStyle: "medium", timeStyle: "short" 
                })}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 11, color: theme.muted }}>TOTAL SIGNALS</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: theme.accent }}>{data.trades.length}</div>
            </div>
          </Card>

          {/* Graph Section (Now at Top) */}
          {selectedTrade && (
            <Card theme={theme} style={{ marginBottom: 20, animation: "slideDown 0.3s ease", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <h3 style={{ margin: 0, fontSize: 16, color: theme.accent }}>
                      {selectedTrade.symbol} {selectedTrade.strike} {selectedTrade.type}
                    </h3>
                    <Badge label={`Score: ${selectedTrade.score}`} color={selectedTrade.score >= 85 ? theme.green : theme.accent} bg={theme.bg} />
                  </div>
                  <div style={{ fontSize: 12, color: theme.muted, marginTop: 4 }}>
                    Live Lot Price Performance (since {new Date(data.snapshot.timestamp + (data.snapshot.timestamp.endsWith("Z") ? "" : "Z")).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})
                  </div>
                </div>
                <button 
                  onClick={() => setSelectedTrade(null)} 
                  style={{ 
                    background: theme.bg, border: `1px solid ${theme.border}`, color: theme.muted, 
                    cursor: "pointer", width: 32, height: 32, borderRadius: "50%", display: "flex",
                    alignItems: "center", justifyContent: "center", transition: "all 0.2s"
                  }}
                  onMouseOver={e => e.currentTarget.style.color = theme.accent}
                  onMouseOut={e => e.currentTarget.style.color = theme.muted}
                >✕</button>
              </div>
              
              {loadingHistory ? <Loader theme={theme} height={200} /> : (
                history.length > 0 ? (
                  <div style={{ position: "relative" }}>
                    <ResponsiveContainer width="100%" height={260}>
                      <AreaChart data={history.map(h => ({ ...h, lot_price: h.price * selectedTrade.lot_size }))}>
                        <defs>
                          <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={theme.accent} stopOpacity={0.3}/>
                            <stop offset="95%" stopColor={theme.accent} stopOpacity={0}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke={theme.border} vertical={false} opacity={0.5} />
                        <XAxis 
                          dataKey="timestamp" 
                          tick={{ fontSize: 10, fill: theme.muted }} 
                          tickFormatter={t => new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          axisLine={false}
                          tickLine={false}
                        />
                        <YAxis 
                          domain={['auto', 'auto']} 
                          tick={{ fontSize: 10, fill: theme.muted }} 
                          tickFormatter={v => `₹${(v/1000).toFixed(1)}k`}
                          axisLine={false}
                          tickLine={false}
                        />
                        <Tooltip 
                          contentStyle={{ 
                            background: theme.card, border: `1px solid ${theme.border}`, 
                            borderRadius: 12, boxShadow: "0 10px 15px -3px rgba(0,0,0,0.1)"
                          }}
                          labelFormatter={t => new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          formatter={(v) => [`₹${v.toLocaleString("en-IN")}`, "Lot Price"]}
                        />
                        <Area 
                          type="monotone" 
                          dataKey="lot_price" 
                          stroke={theme.accent} 
                          fillOpacity={1} 
                          fill="url(#colorPrice)" 
                          strokeWidth={3} 
                          animationDuration={1000}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div style={{ textAlign: "center", padding: "60px 40px", color: theme.muted, background: theme.bg, borderRadius: 12 }}>
                    <div style={{ fontSize: 24, marginBottom: 12 }}>⏳</div>
                    <div style={{ fontWeight: 600 }}>Building performance history...</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>Price snapshots are taken every 5 minutes. Check back shortly.</div>
                  </div>
                )
              )}
            </Card>
          )}

          <div style={{ overflowX: "auto", background: theme.card, borderRadius: 8, border: `1px solid ${theme.border}` }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ color: theme.muted, borderBottom: `2px solid ${theme.border}`, textAlign: "left", background: theme.bg }}>
                  {[
                    { label: "Symbol", key: "symbol" },
                    { label: "Suggest Trade", key: "type" },
                    { label: "Score", key: "score", align: "center" },
                    { label: "Entry Price", key: "entry_price" },
                    { label: "LTP (Active)", key: "current_price" },
                    { label: "Lot Price", key: "lotPrice" },
                    { label: "5m Chg", key: "diff_5m_pct" },
                    { label: "Perf %", key: "pnl", align: "right" }
                  ].map(({ label, key, align }) => (
                    <th 
                      key={key} 
                      onClick={() => requestSort(key)}
                      style={{ 
                        padding: "12px 16px", textAlign: align || "left", 
                        cursor: "pointer", userSelect: "none" 
                      }}
                      onMouseOver={e => e.currentTarget.style.color = theme.text}
                      onMouseOut={e => e.currentTarget.style.color = theme.muted}
                    >
                      {label} {sortConfig.key === key ? (sortConfig.direction === "asc" ? "▲" : "▼") : "↕"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedTrades.map((t, idx) => {
                  const pnl = t.current_price && t.entry_price ? ((t.current_price - t.entry_price) / t.entry_price) * 100 : 0;
                  const color = pnl > 0 ? theme.green : pnl < 0 ? theme.red : theme.muted;
                  const lotPrice = (t.current_price || t.entry_price) * (t.lot_size || 1);
                  const diffColor = (t.diff_5m_pct || 0) > 0 ? theme.green : (t.diff_5m_pct || 0) < 0 ? theme.red : theme.muted;

                  return (
                    <tr key={idx} className="trade-row" onClick={() => loadHistory(t)}
                        style={{ 
                          borderBottom: `1px solid ${theme.border}`, 
                          cursor: "pointer",
                          backgroundColor: selectedTrade?.id === t.id ? `${theme.accent}08` : "transparent",
                          transition: "background 0.2s"
                        }}>
                      <td style={{ padding: "12px 16px", fontWeight: 700 }}>
                        {t.symbol}
                        <div style={{ fontSize: 10, color: theme.muted, fontWeight: 400 }}>Spot: ₹{fmt(t.stock_price)}</div>
                      </td>
                      <td style={{ padding: "12px 16px" }}>
                        <span style={{ 
                          padding: "3px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700,
                          background: t.type === "CE" ? "rgba(34,197,94,.15)" : "rgba(239,68,68,.15)",
                          color: t.type === "CE" ? theme.green : theme.red,
                          border: `1px solid ${t.type === "CE" ? "rgba(34,197,94,.2)" : "rgba(239,68,68,.2)"}`
                        }}>
                          {t.strike} {t.type}
                        </span>
                      </td>
                      <td style={{ padding: "12px 16px", textAlign: "center" }}>
                        <Badge label={t.score} color={t.score >= 85 ? theme.green : theme.accent} bg={theme.bg} />
                      </td>
                      <td style={{ padding: "12px 16px", fontWeight: 500 }}>₹{fmt(t.entry_price)}</td>
                      <td style={{ padding: "12px 16px", fontWeight: 500 }}>₹{fmt(t.current_price || t.entry_price)}</td>
                      <td style={{ padding: "12px 16px", fontWeight: 600 }}>
                         ₹{lotPrice.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                         <div style={{ fontSize: 9, color: theme.muted, fontWeight: 400 }}>Size: {t.lot_size}</div>
                      </td>
                      <td style={{ padding: "12px 16px", color: diffColor }}>
                        {t.diff_5m_pct ? (
                          <div style={{ fontWeight: 600 }}>
                            {t.diff_5m_pct > 0 ? "▲" : "▼"} {Math.abs(t.diff_5m_pct).toFixed(1)}%
                          </div>
                        ) : "—"}
                      </td>
                      <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: 700, color }}>
                        {pnl > 0 ? "+" : ""}{fmt(pnl, 2)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Report Modal */}
      {report && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0, 
          background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center",
          zIndex: 1000, padding: 20
        }}>
          <div style={{
            background: theme.bg, borderRadius: 12, border: `1px solid ${theme.border}`,
            maxWidth: 600, width: "100%", maxHeight: "90vh", overflowY: "auto",
            boxShadow: "0 10px 30px rgba(0,0,0,0.5)", animation: "slideDown 0.3s ease"
          }}>
            <div style={{ padding: "20px 24px", borderBottom: `1px solid ${theme.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0, color: theme.accent, display: "flex", alignItems: "center", gap: 8 }}>
                📈 Accuracy Tracker Backtest Report
              </h3>
              <button 
                onClick={() => setReport(null)}
                style={{ background: "transparent", border: "none", color: theme.muted, cursor: "pointer", fontSize: 18 }}
              >✕</button>
            </div>
            
            <div style={{ padding: 24 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
                <Card theme={theme} style={{ textAlign: "center", padding: "24px 16px" }}>
                  <div style={{ fontSize: 12, color: theme.muted, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Total Tracks</div>
                  <div style={{ fontSize: 32, fontWeight: 800, color: theme.text }}>{report.total_trades}</div>
                </Card>
                <Card theme={theme} style={{ textAlign: "center", padding: "24px 16px" }}>
                  <div style={{ fontSize: 12, color: theme.muted, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Overall Win Rate</div>
                  <div style={{ fontSize: 32, fontWeight: 800, color: report.win_rate > 50 ? theme.green : theme.red }}>
                    {report.win_rate}%
                  </div>
                </Card>
              </div>

              <h4 style={{ margin: "0 0 16px 0", color: theme.text }}>Performance by Initial Score</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 24 }}>
                {Object.entries(report.score_brackets).map(([bracket, data]) => (
                  <div key={bracket} style={{ 
                    display: "flex", alignItems: "center", justifyContent: "space-between", 
                    padding: "16px", background: theme.card, borderRadius: 8, border: `1px solid ${theme.border}` 
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <Badge label={`Score ${bracket}`} color={bracket === ">=90" ? theme.green : theme.accent} bg={theme.bg} />
                      <div style={{ fontSize: 13, color: theme.muted }}>{data.total} Trades</div>
                    </div>
                    <div style={{ display: "flex", gap: 24, textAlign: "right" }}>
                      <div>
                        <div style={{ fontSize: 11, color: theme.muted }}>WIN RATE</div>
                        <div style={{ fontSize: 14, fontWeight: 700, color: data.win_rate > 50 ? theme.green : theme.red }}>{data.win_rate}%</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 11, color: theme.muted }}>AVG MAX PNL</div>
                        <div style={{ fontSize: 14, fontWeight: 700, color: data.avg_pnl > 0 ? theme.green : theme.red }}>
                          {data.avg_pnl > 0 ? "+" : ""}{data.avg_pnl}%
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {report.best_trade && (
                <>
                  <h4 style={{ margin: "0 0 16px 0", color: theme.text }}>Top Performing Trade</h4>
                  <Card theme={theme} style={{ borderLeft: `4px solid ${theme.green}`, padding: 20 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 700, color: theme.text, marginBottom: 4 }}>
                          {report.best_trade.symbol} {report.best_trade.strike} {report.best_trade.type}
                        </div>
                        <div style={{ fontSize: 13, color: theme.muted }}>
                          Score: {report.best_trade.score} • Entry: ₹{report.best_trade.entry.toFixed(2)} • Peak: ₹{report.best_trade.max_price.toFixed(2)}
                        </div>
                      </div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: theme.green }}>
                        +{report.best_trade.pnl_pct}%
                      </div>
                    </div>
                  </Card>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════════════
// Backtest Tab
// ══════════════════════════════════════════════════════════════════════════════

function BacktestTab({ theme }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [params, setParams] = useState({
    start: "2023-01-01",
    end: "2024-12-31",
    score: 20,
    confidence: 0,
    tp: 40,
    sl: 25,
    signal: "ALL",
    regime: "ALL",
    symbols: ""
  });

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await apiFetch("/api/historical-backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      setResult(res);
    } catch (e) {
      console.error(e);
      alert("Backtest failed. See console for details.");
    }
    setLoading(false);
  };

  const ParamGroup = ({ label, desc, name, type = "text", options = null }) => (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <label style={{ fontWeight: 600, fontSize: 13 }}>{label}</label>
        <span style={{ fontSize: 11, color: theme.muted, cursor: "help" }} title={desc}>ⓘ Info</span>
      </div>
      {options ? (
        <select value={params[name]} onChange={e => setParams({ ...params, [name]: e.target.value })}
          style={{
            width: "100%", padding: "8px 10px", borderRadius: 6,
            background: theme.bg, color: theme.text, border: `1px solid ${theme.border}`,
            fontFamily: "inherit"
          }}>
          {options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input type={type} value={params[name]} onChange={e => setParams({ ...params, [name]: type === "number" ? Number(e.target.value) : e.target.value })}
          style={{
            width: "100%", padding: "8px 10px", borderRadius: 6,
            background: theme.bg, color: theme.text, border: `1px solid ${theme.border}`,
            fontFamily: "inherit"
          }} />
      )}
      <div style={{ fontSize: 11, color: theme.muted, marginTop: 4 }}>{desc}</div>
    </div>
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 20 }}>
      {/* Sidebar Controls */}
      <Card theme={theme} style={{ height: "fit-content" }}>
        <h3 style={{ margin: "0 0 20px 0", fontSize: 16 }}>Parameters</h3>
        
        <ParamGroup label="Date Range" desc="Simulate trades between these dates." name="start" />
        <ParamGroup label="End Date" desc="To Date" name="end" />
        
        <ParamGroup label="Score Hurdle" desc="Min strategy score (1-100) to enter trades. Lower scores allow more trades but might be lower quality." name="score" type="number" />
        <ParamGroup label="ML Confidence" desc="Min confidence (0.0 - 1.0) needed." name="confidence" type="number" />
        
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <ParamGroup label="Target %" desc="Profit exit percentage." name="tp" type="number" />
          <ParamGroup label="Stop %" desc="Risk exit percentage." name="sl" type="number" />
        </div>
        
        <ParamGroup label="Signal Bias" desc="Filter by direction bias." name="signal" options={["ALL", "BULLISH", "BEARISH"]} />
        <ParamGroup label="Market regime" desc="Specific gamma/volatility environment filter." name="regime" options={["ALL", "TRENDING", "PINNED", "EXPIRY", "SQUEEZE"]} />
        
        <ParamGroup label="Symbols" desc="Comma separated (e.g. NIFTY,RELIANCE). Blank = All." name="symbols" />

        <button onClick={run} disabled={loading}
          style={{
            width: "100%", padding: "12px", background: theme.accent,
            color: "#fff", border: "none", borderRadius: 6, cursor: "pointer",
            fontWeight: 700, marginTop: 10, opacity: loading ? 0.6 : 1
          }}>
          {loading ? "⌛ PROCESSING..." : "▶ RUN BACKTEST"}
        </button>
      </Card>

      {/* Results Workspace */}
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {!result && !loading && (
          <div style={{ textAlign: "center", padding: "100px", color: theme.muted, background: theme.card, borderRadius: 12, border: `1px dashed ${theme.border}` }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>📊</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: theme.text }}>Historical Backtest Engine</div>
            <p>Setup your parameters and click Run to see detailed historical performance over 2023-2024.</p>
          </div>
        )}

        {loading && <Card theme={theme}><Loader theme={theme} /></Card>}

        {result && result.error && (
          <div style={{ padding: 20, background: "rgba(239,68,68,0.1)", border: `1px solid ${theme.red}`, borderRadius: 8, color: theme.red }}>
            {result.error}
          </div>
        )}

        {result && !result.error && (
          <>
            {/* Meta Summary */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
              {[
                ["Total Trades", result.summary.total],
                ["Win Rate", `${result.summary.win_rate.toFixed(1)}%`],
                ["Profit Factor", result.summary.profit_factor.toFixed(2)],
                ["Expectancy", `${(result.summary.expectancy).toFixed(1)}%`]
              ].map(([k, v]) => (
                <Card theme={theme} key={k} style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 11, color: theme.muted }}>{k}</div>
                  <div style={{ fontSize: 20, fontWeight: 800 }}>{v}</div>
                </Card>
              ))}
            </div>

            {/* Equity Curve (Chart) */}
            <Card theme={theme}>
              <div style={{ fontWeight: 700, marginBottom: 16 }}>Equity Curve (₹)</div>
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={result.equity_curve.map((v, i) => ({ step: i, capital: v }))}>
                  <defs>
                    <linearGradient id="curveColor" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={theme.accent} stopOpacity={0.2}/>
                      <stop offset="95%" stopColor={theme.accent} stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={theme.border} opacity={0.3} />
                  <XAxis dataKey="step" hide />
                  <YAxis domain={['auto', 'auto']} tick={{fontSize: 10, fill: theme.muted}} />
                  <Tooltip 
                    contentStyle={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 8 }}
                    formatter={(v) => [`₹${Number(v).toLocaleString()}`, "Capital"]}
                  />
                  <Area type="monotone" dataKey="capital" stroke={theme.accent} fill="url(#curveColor)" strokeWidth={3} />
                </AreaChart>
              </ResponsiveContainer>
            </Card>

            {/* Drilldown Tables */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
              <Card theme={theme}>
                <div style={{ fontWeight: 700, marginBottom: 12 }}>Performance by Regime</div>
                <table style={{ width: "100%", fontSize: 12 }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: theme.muted }}><th>Regime</th><th>Trades</th><th>WR%</th></tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.by_regime).map(([k, v]) => (
                      <tr key={k} style={{ borderTop: `1px solid ${theme.border}` }}>
                        <td style={{ padding: "8px 0" }}>{k}</td>
                        <td>{v.trades}</td>
                        <td style={{ color: v.wr > 50 ? theme.green : theme.red, fontWeight: 700 }}>{v.wr.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              <Card theme={theme}>
                <div style={{ fontWeight: 700, marginBottom: 12 }}>Top Performing Symbols</div>
                <table style={{ width: "100%", fontSize: 12 }}>
                  <thead>
                    <tr style={{ textAlign: "left", color: theme.muted }}><th>Symbol</th><th>PnL</th><th>WR%</th></tr>
                  </thead>
                  <tbody>
                    {result.top_symbols.map((s, idx) => (
                      <tr key={idx} style={{ borderTop: `1px solid ${theme.border}` }}>
                        <td style={{ padding: "8px 0" }}>{s.symbol}</td>
                        <td style={{ color: s.pnl > 0 ? theme.green : theme.red }}>₹{fmt(s.pnl, 0)}</td>
                        <td>{s.wr.toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </div>
            
            <div style={{ fontSize: 11, color: theme.muted, textAlign: "center", marginTop: 10 }}>
              {result.summary.significant ? "✅ Statistically Significant" : "⚠️ Low Sample Size / High Luck Factor"} · 
              Max Drawdown: ₹{result.summary.max_drawdown.toLocaleString()} ({result.summary.max_drawdown_pct.toFixed(1)}%) · Sharpe: {fmt(result.summary.sharpe, 2)}
            </div>
          </>
        )}
      </div>
    </div>
  );
}


function SettingsTab({ theme }) {
  const [capital, setCapital] = useState(100000);
  const [wl, setWl] = useState([]);
  const [newSym, setNewSym] = useState("");
  const [saved, setSaved] = useState(false);
  const [fii, setFii] = useState([]);

  useEffect(() => {
    apiFetch("/api/settings/capital").then(r => setCapital(r.capital));
    apiFetch("/api/settings/watchlist").then(r => setWl(r.watchlist || []));
    apiFetch("/api/fii-dii").then(r => setFii(r.data || [])).catch(() => { });
  }, []);

  const saveCapital = async () => {
    await fetch(`${API}/api/settings/capital?amount=${capital}`, { method: "POST" });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const addToWl = async () => {
    if (!newSym) return;
    const next = [...new Set([...wl, newSym.toUpperCase()])];
    setWl(next);
    setNewSym("");
    await fetch(`${API}/api/settings/watchlist`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    });
  };

  const removeFromWl = async (sym) => {
    const next = wl.filter(s => s !== sym);
    setWl(next);
    await fetch(`${API}/api/settings/watchlist`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    });
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, maxWidth: 900 }}>
      {/* Capital */}
      <Card theme={theme}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>Trading Capital</div>
        <div style={{ color: theme.muted, fontSize: 11, marginBottom: 10 }}>
          Used for position sizing (2% risk per trade rule)
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input type="number" value={capital} onChange={e => setCapital(Number(e.target.value))}
            style={{
              flex: 1, padding: "6px 10px", borderRadius: 6,
              border: `1px solid ${theme.border}`, background: theme.bg,
              color: theme.text, fontFamily: "inherit"
            }} />
          <button onClick={saveCapital}
            style={{
              padding: "6px 14px", borderRadius: 6, background: theme.accent,
              color: "#fff", border: "none", cursor: "pointer"
            }}>
            {saved ? "✓ Saved" : "Save"}
          </button>
        </div>
        <div style={{ marginTop: 8, fontSize: 11, color: theme.muted }}>
          2% risk = ₹{(capital * 0.02).toLocaleString("en-IN")} per trade
        </div>
      </Card>

      {/* Watchlist */}
      <Card theme={theme}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>Watchlist</div>
        <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
          <input value={newSym} onChange={e => setNewSym(e.target.value.toUpperCase())}
            placeholder="Add symbol..."
            style={{
              flex: 1, padding: "6px 10px", borderRadius: 6,
              border: `1px solid ${theme.border}`, background: theme.bg,
              color: theme.text, fontFamily: "inherit"
            }} />
          <button onClick={addToWl}
            style={{
              padding: "6px 14px", borderRadius: 6, background: theme.accent,
              color: "#fff", border: "none", cursor: "pointer"
            }}>+</button>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {wl.map(sym => (
            <span key={sym} style={{
              padding: "3px 10px", borderRadius: 20, fontSize: 11,
              background: "rgba(99,102,241,.15)", color: theme.accent,
              display: "flex", alignItems: "center", gap: 4
            }}>
              {sym}
              <button onClick={() => removeFromWl(sym)}
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: theme.muted, fontSize: 12, padding: 0
                }}>×</button>
            </span>
          ))}
        </div>
      </Card>

      {/* FII/DII */}
      <Card theme={theme} style={{ gridColumn: "span 2" }}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>FII / DII Activity</div>
        {fii.length === 0 ? (
          <div style={{ color: theme.muted, fontSize: 12 }}>No FII/DII data available.</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
            {fii.map((row, i) => (
              <div key={i} style={{ background: theme.bg, borderRadius: 6, padding: "10px 14px" }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{row.category}</div>
                <div style={{ fontSize: 11, color: theme.muted }}>{row.date}</div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                  <div>
                    <div style={{ fontSize: 10, color: theme.muted }}>Net</div>
                    <div style={{ fontWeight: 700, color: row.net >= 0 ? theme.green : theme.red }}>
                      ₹{(row.net / 100).toFixed(0)} Cr
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 10, color: theme.muted }}>Buy / Sell</div>
                    <div style={{ fontSize: 11 }}>
                      <span style={{ color: theme.green }}>{(row.buy_value / 100).toFixed(0)}</span>
                      {" / "}
                      <span style={{ color: theme.red }}>{(row.sell_value / 100).toFixed(0)}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Keyboard shortcuts */}
      <Card theme={theme} style={{ gridColumn: "span 2" }}>
        <div style={{ fontWeight: 600, marginBottom: 10 }}>Keyboard Shortcuts</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, fontSize: 12 }}>
          {[["R", "Scanner"], ["C", "Chain"], ["G", "Greeks"], ["H", "OI Map"],
          ["S", "Sectors"], ["U", "UOA"], ["P", "Portfolio"], [",", "Settings"]].map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <kbd style={{
                padding: "2px 8px", borderRadius: 4, background: theme.bg,
                border: `1px solid ${theme.border}`, fontFamily: "monospace",
                fontSize: 12
              }}>{k}</kbd>
              <span style={{ color: theme.muted }}>{v}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}