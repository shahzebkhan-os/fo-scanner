// App.jsx — NSE F&O Scanner v5 Frontend
// Features: Scanner, Chain, Greeks, OI Heatmap, Sector Map, UOA,
//           Straddle Screen, Portfolio Dashboard, Settings, Dark Mode
// v5: QoL improvements — auto-refresh, hover effects, TP/SL indicators

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, ReferenceLine, AreaChart, Area
} from "recharts";
import MLTab from "./components/MLTab";
import SuggestionsTab from "./components/SuggestionsTab";
import PaperTradingTab from "./components/PaperTradingTab";

// ── Constants ─────────────────────────────────────────────────────────────────
const API = "http://localhost:8000";   // same-origin; set to http://localhost:8000 for dev

const TABS = [
  { id: "scanner", label: "Scanner", icon: "⚡" },
  { id: "suggestions", label: "Suggestions", icon: "💡" },
  { id: "paper", label: "Paper Trade", icon: "📝" },
  { id: "chain", label: "Chain", icon: "🔗" },
  { id: "greeks", label: "Greeks", icon: "Δ" },
  { id: "heatmap", label: "OI Map", icon: "🌡" },
  { id: "sector", label: "Sectors", icon: "🗺" },
  { id: "uoa", label: "UOA", icon: "🎯" },
  { id: "straddle", label: "Straddle", icon: "⚖" },
  { id: "ml", label: "ML/NN", icon: "🧠" },
  { id: "backtest", label: "Backtest", icon: "🕰" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n, d = 2) => Number(n || 0).toFixed(d);
const pct = (n) => `${n >= 0 ? "+" : ""}${fmt(n, 1)}%`;
const signalColor = (s) =>
  s === "BULLISH" ? "#22c55e" : s === "BEARISH" ? "#ef4444" : "#94a3b8";
const signalBg = (s) =>
  s === "BULLISH" ? "rgba(34,197,94,.15)" : s === "BEARISH" ? "rgba(239,68,68,.15)" : "rgba(148,163,184,.1)";

// Parse timestamp safely - handles both ISO format with and without Z suffix
const parseTimestamp = (ts) => {
  if (!ts) return new Date();
  try {
    // If timestamp doesn't have timezone info, treat it as UTC by appending Z
    // Check for timezone: Z, +HH:MM, or -HH:MM (the minus after position 10 is for timezone, not date separator)
    const hasTimezone = ts.endsWith("Z") || ts.includes("+") || (ts.length > 10 && ts.slice(10).includes("-"));
    const normalized = hasTimezone ? ts : ts + "Z";
    return new Date(normalized);
  } catch {
    return new Date();
  }
};

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
        borderBottom: `1px solid ${theme.border}`,
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
        <div style={{ display: tab === "scanner"   ? "block" : "none" }}><ScannerTab theme={theme} onChain={goChain} onGreeks={goGreeks} onData={setScanData} marketStatus={marketStatus} /></div>
        <div style={{ display: tab === "suggestions" ? "block" : "none" }}><SuggestionsTab theme={theme} goChain={goChain} /></div>
        <div style={{ display: tab === "paper"   ? "block" : "none" }}><PaperTradingTab theme={theme} /></div>
        <div style={{ display: tab === "chain"     ? "block" : "none" }}><ChainTab theme={theme} symbol={chainSymbol} setSymbol={setChainSymbol} /></div>
        <div style={{ display: tab === "greeks"    ? "block" : "none" }}><GreeksTab theme={theme} symbol={greeksSymbol} /></div>
        <div style={{ display: tab === "heatmap"   ? "block" : "none" }}><HeatmapTab theme={theme} /></div>
        <div style={{ display: tab === "sector"    ? "block" : "none" }}><SectorTab theme={theme} onChain={goChain} /></div>
        <div style={{ display: tab === "uoa"       ? "block" : "none" }}><UOATab theme={theme} onChain={goChain} /></div>
        <div style={{ display: tab === "straddle"  ? "block" : "none" }}><StraddleTab theme={theme} /></div>
        <div style={{ display: tab === "ml"        ? "block" : "none" }}><MLTab theme={theme} /></div>
        <div style={{ display: tab === "backtest"  ? "block" : "none" }}><BacktestTab theme={theme} /></div>
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

function ScannerTab({ theme, onChain, onGreeks, onData, marketStatus }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [watchlist, setWatchlist] = useState([]);
  const [showWL, setShowWL] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [scanInterval, setScanInterval] = useState(() => {
    const saved = localStorage.getItem("scanInterval");
    return saved ? parseInt(saved, 10) : 120;
  });
  const [countdown, setCountdown] = useState(() => {
    const saved = localStorage.getItem("scanInterval");
    return saved ? parseInt(saved, 10) : 120;
  });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [scanMeta, setScanMeta] = useState({ stale: false, stale_count: 0 });
  const [mlStatus, setMlStatus] = useState({ trained: false });
  const [scanProgress, setScanProgress] = useState(0);
  const eventSourceRef = useRef(null);
  const scanningRef = useRef(false);

  // Market-aware auto-scan: ON when market open, OFF when closed
  useEffect(() => {
    if (!marketStatus) return;
    setAutoRefresh(marketStatus.open);
  }, [marketStatus?.open]);

  const load = useCallback(() => {
    // Prevent duplicate scans — if already scanning, skip
    if (scanningRef.current) return;
    scanningRef.current = true;

    // Close any existing SSE connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setLoading(true);
    setData([]);
    setScanProgress(0);

    let sseTimedOut = false;

    const es = new EventSource(`${API}/api/scan-stream?limit=90`);
    eventSourceRef.current = es;
    const incoming = [];

    // Timeout: if no result event arrives within 30s, fall back to regular scan
    const sseTimeout = setTimeout(() => {
      if (incoming.length === 0 && es.readyState !== 2) {
        sseTimedOut = true;
        es.close();
        eventSourceRef.current = null;
        console.warn("SSE timeout — falling back to /api/scan");
        apiFetch("/api/scan?limit=90")
          .then((r) => {
            const rows = r.data || [];
            setData(rows);
            setScanMeta({ stale: r.stale, stale_count: r.stale_count || 0, _fetched_at: r._fetched_at });
            if (onData) onData(rows);
            setLastUpdated(new Date());
            setCountdown(scanInterval);
          })
          .catch(console.error)
          .finally(() => { setLoading(false); setScanProgress(0); scanningRef.current = false; });
      }
    }, 30000);

    es.addEventListener("result", (e) => {
      try {
        const row = JSON.parse(e.data);
        incoming.push(row);
        setScanProgress(incoming.length);
        // Update data progressively — sorted by score
        setData([...incoming].sort((a, b) => (b.score || 0) - (a.score || 0)));
      } catch (err) { console.error("SSE parse error:", err); }
    });

    es.addEventListener("done", (e) => {
      clearTimeout(sseTimeout);
      if (sseTimedOut) return; // Already handled by timeout fallback
      try {
        const meta = JSON.parse(e.data);
        setScanMeta({ stale: false, stale_count: 0, _fetched_at: meta.timestamp });
        const sorted = [...incoming].sort((a, b) => (b.score || 0) - (a.score || 0));
        setData(sorted);
        if (onData) onData(sorted);
      } catch (err) { console.error("SSE done parse error:", err); }
      setLastUpdated(new Date());
      setCountdown(scanInterval);
      setLoading(false);
      setScanProgress(0);
      scanningRef.current = false;
      es.close();
      eventSourceRef.current = null;
    });

    es.onerror = () => {
      clearTimeout(sseTimeout);
      if (sseTimedOut) return; // Already handled by timeout fallback
      // On error, fall back to regular scan endpoint
      es.close();
      eventSourceRef.current = null;
      apiFetch("/api/scan?limit=90")
        .then((r) => {
          const rows = r.data || [];
          setData(rows);
          setScanMeta({ stale: r.stale, stale_count: r.stale_count || 0, _fetched_at: r._fetched_at });
          if (onData) onData(rows);
          setLastUpdated(new Date());
          setCountdown(scanInterval);
        })
        .catch(console.error)
        .finally(() => { setLoading(false); setScanProgress(0); scanningRef.current = false; });
    };
  }, [scanInterval]);

  // Save scan interval to localStorage
  const changeScanInterval = (secs) => {
    setScanInterval(secs);
    setCountdown(secs);
    localStorage.setItem("scanInterval", String(secs));
  };

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
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
        const nn = result.nn || {};
        const nnMsg = nn.nn_cv_log_loss_mean
          ? ` | NN Loss: ${nn.nn_cv_log_loss_mean}`
          : nn.error ? ` | NN: ${nn.error}` : "";
        alert(`Model trained! LGB CV Log Loss: ${result.cv_log_loss_mean}${nnMsg}`);
        apiFetch("/api/ml/status").then(setMlStatus).catch(() => {});
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
        if (prev <= 1) { load(); return scanInterval; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [autoRefresh, load, scanInterval]);

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
              ML Models Not Trained
            </div>
            <div style={{ fontSize: 11, color: theme.muted }}>
              Train LightGBM + Neural Network (LSTM) to get AI-powered signal refinement.
            </div>
          </div>
          <button 
            onClick={trainMLModel}
            style={{
              padding: "6px 12px", borderRadius: 6,
              background: "#6366f1", color: "#fff", border: "none",
              cursor: "pointer", fontWeight: 600, fontSize: 11
            }}>
            Train Models
          </button>
        </div>
      )}
      {mlStatus.trained && (
        <div style={{
          background: "rgba(34, 197, 94, 0.08)",
          border: "1px solid rgba(34, 197, 94, 0.3)",
          borderRadius: 8,
          padding: "8px 16px",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 10,
          fontSize: 11
        }}>
          <span style={{ fontSize: 14 }}>🧠</span>
          <span style={{ color: theme.muted }}>
            LightGBM {mlStatus.lgb_trained ? "✅" : "❌"}
            {" · "}
            Neural Network {mlStatus.nn_trained ? "✅" : "❌"}
            {mlStatus.nn_trained ? " (LSTM)" : mlStatus.torch_available === false ? " (torch not installed)" : ""}
          </span>
          <button
            onClick={trainMLModel}
            style={{
              marginLeft: "auto", padding: "4px 10px", borderRadius: 5,
              background: "transparent", color: "#6366f1", border: "1px solid #6366f1",
              cursor: "pointer", fontWeight: 600, fontSize: 10
            }}>
            Retrain
          </button>
        </div>
      )}

      {/* Controls */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={() => { load(); setCountdown(scanInterval); }} disabled={loading}
          className="clickable-btn"
          style={{
            padding: "6px 14px", borderRadius: 6, background: theme.accent,
          }}>
          {loading ? `⟳ Scanning${scanProgress ? ` (${scanProgress})` : ""}...` : "⟳ Refresh"}
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
          <select value={scanInterval} onChange={e => changeScanInterval(Number(e.target.value))}
            style={{
              padding: "3px 6px", borderRadius: 4, border: `1px solid ${theme.border}`,
              background: theme.bg, color: theme.text, fontSize: 10, fontFamily: "inherit",
              cursor: "pointer",
            }}>
            <option value={60}>1 min</option>
            <option value={120}>2 min</option>
            <option value={300}>5 min</option>
          </select>
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

      {loading && data.length === 0 && <Loader theme={theme} />}
      {!loading && data.length === 0 && lastUpdated && (
        <div style={{
          textAlign: "center", padding: "40px 20px",
          color: theme.muted
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>📡</div>
          <div style={{ fontWeight: 600, fontSize: 14, color: theme.text, marginBottom: 6 }}>
            No scan results available
          </div>
          <div style={{ fontSize: 12, marginBottom: 16 }}>
            The data source may be temporarily unavailable. This can happen when the
            market is closed or the upstream provider is slow to respond.
          </div>
          <button onClick={() => { load(); setCountdown(scanInterval); }}
            style={{
              padding: "8px 20px", borderRadius: 6, background: theme.accent,
              color: "#fff", border: "none", cursor: "pointer", fontWeight: 600
            }}>
            🔄 Retry Scan
          </button>
        </div>
      )}
      {loading && data.length > 0 && (
        <div style={{
          background: "rgba(99, 102, 241, 0.1)",
          borderRadius: 6,
          padding: "6px 14px",
          marginBottom: 12,
          display: "flex",
          alignItems: "center",
          gap: 10,
          fontSize: 11,
          color: theme.muted,
        }}>
          <div style={{
            fontSize: 14, animation: "spin 1s linear infinite",
            display: "inline-block"
          }}>⟳</div>
          <span>Scanning... {scanProgress} symbols loaded</span>
          <div style={{ flex: 1, height: 4, background: theme.border, borderRadius: 2, overflow: "hidden" }}>
            <div style={{
              height: "100%", background: theme.accent, borderRadius: 2,
              width: `${Math.min(100, (scanProgress / 90) * 100)}%`,
              transition: "width 0.3s ease",
            }} />
          </div>
        </div>
      )}

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

    </div>
  );
}