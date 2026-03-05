// App.jsx — NSE F&O Scanner v4 Frontend
// Features: Scanner, Chain, Greeks, OI Heatmap, Sector Map, UOA,
//           Straddle Screen, Portfolio Dashboard, Settings, Dark Mode

import { useState, useEffect, useCallback, useRef } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, ReferenceLine
} from "recharts";

// ── Constants ─────────────────────────────────────────────────────────────────
const API = "";   // same-origin; set to http://localhost:8000 for dev

const TABS = [
  { id: "scanner", label: "Scanner", icon: "⚡" },
  { id: "chain", label: "Chain", icon: "🔗" },
  { id: "greeks", label: "Greeks", icon: "Δ" },
  { id: "heatmap", label: "OI Map", icon: "🌡" },
  { id: "sector", label: "Sectors", icon: "🗺" },
  { id: "uoa", label: "UOA", icon: "🎯" },
  { id: "straddle", label: "Straddle", icon: "⚖" },
  { id: "portfolio", label: "P&L", icon: "💰" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n, d = 2) => (n ?? 0).toFixed(d);
const pct = (n) => `${n >= 0 ? "+" : ""}${fmt(n, 1)}%`;
const signalColor = (s) =>
  s === "BULLISH" ? "#22c55e" : s === "BEARISH" ? "#ef4444" : "#94a3b8";
const signalBg = (s) =>
  s === "BULLISH" ? "rgba(34,197,94,.15)" : s === "BEARISH" ? "rgba(239,68,68,.15)" : "rgba(148,163,184,.1)";

async function apiFetch(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ── Root App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState("scanner");
  const [dark, setDark] = useState(() => localStorage.getItem("theme") !== "light");
  const [chainSymbol, setChainSymbol] = useState("NIFTY");
  const [marketStatus, setMarketStatus] = useState(null);

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
        s: "sector", u: "uoa", p: "portfolio", ",": "settings"
      };
      if (keys[e.key]) setTab(keys[e.key]);
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, []);

  useEffect(() => {
    apiFetch("/health").then(d => setMarketStatus(d)).catch(() => { });
    const id = setInterval(() => apiFetch("/health").then(setMarketStatus).catch(() => { }), 30000);
    return () => clearInterval(id);
  }, []);

  const goChain = (sym) => { setChainSymbol(sym); setTab("chain"); };

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
      {/* Header */}
      <header style={{
        background: theme.card, borderBottom: `1px solid ${theme.border}`,
        padding: "0 16px", display: "flex", alignItems: "center",
        justifyContent: "space-between", height: 52, position: "sticky",
        top: 0, zIndex: 100
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: theme.accent }}>F&O</span>
          <span style={{ color: theme.muted }}>Scanner v4</span>
          {marketStatus && (
            <span style={{
              padding: "2px 8px", borderRadius: 4, fontSize: 11,
              background: signalBg(marketStatus.open ? "BULLISH" : "BEARISH"),
              color: marketStatus.open ? theme.green : theme.red
            }}>
              {marketStatus.open ? "● LIVE" : "○ CLOSED"}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => {
            const rows = filteredResults.length ? filteredResults : scanResults;
            if (!rows.length) return;
            const cols = ["symbol", "signal", "score", "ltp", "change_pct", "volume", "pcr", "iv", "oi_change", "vol_spike"];
            const csv = [cols.join(","), ...rows.map(r => cols.map(c => r[c] ?? "").join(","))].join("\n");
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
            style={{
              padding: "10px 16px", border: "none", cursor: "pointer",
              background: "none", color: tab === t.id ? theme.accent : theme.muted,
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
        {tab === "scanner" && <ScannerTab theme={theme} onChain={goChain} />}
        {tab === "chain" && <ChainTab theme={theme} symbol={chainSymbol} setSymbol={setChainSymbol} />}
        {tab === "greeks" && <GreeksTab theme={theme} />}
        {tab === "heatmap" && <HeatmapTab theme={theme} />}
        {tab === "sector" && <SectorTab theme={theme} onChain={goChain} />}
        {tab === "uoa" && <UOATab theme={theme} onChain={goChain} />}
        {tab === "straddle" && <StraddleTab theme={theme} />}
        {tab === "portfolio" && <PortfolioTab theme={theme} />}
        {tab === "settings" && <SettingsTab theme={theme} />}
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
      <div style={{ marginTop: 8 }}>Loading...</div>
      <style>{`@keyframes spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }`}</style>
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

function ScannerTab({ theme, onChain }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [watchlist, setWatchlist] = useState([]);
  const [showWL, setShowWL] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/api/scan?limit=51");
      setData(r.data || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

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

  return (
    <div>
      {/* Controls */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={load} disabled={loading}
          style={{
            padding: "6px 14px", borderRadius: 6, background: theme.accent,
            color: "#fff", border: "none", cursor: "pointer"
          }}>
          {loading ? "⟳ Scanning..." : "⟳ Refresh"}
        </button>
        {["ALL", "BULLISH", "BEARISH", "NEUTRAL"].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            style={{
              padding: "4px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
              background: filter === f ? signalBg(f) : "none",
              color: filter === f ? signalColor(f) : theme.muted,
              cursor: "pointer", fontFamily: "inherit", fontSize: 12
            }}>
            {f}
          </button>
        ))}
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search..."
          style={{
            padding: "5px 10px", borderRadius: 6, border: `1px solid ${theme.border}`,
            background: theme.bg, color: theme.text, fontFamily: "inherit", fontSize: 12
          }} />
        <button onClick={() => setShowWL(w => !w)}
          style={{
            padding: "4px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
            background: showWL ? "rgba(99,102,241,.15)" : "none",
            color: showWL ? theme.accent : theme.muted, cursor: "pointer"
          }}>
          ★ Watchlist
        </button>
        <span style={{ color: theme.muted, fontSize: 11 }}>{filtered.length} symbols</span>
      </div>

      {loading && <Loader theme={theme} />}

      {/* Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
        {filtered.map(r => (
          <ScanCard key={r.symbol} r={r} theme={theme} onChain={onChain}
            isWatched={watchlist.includes(r.symbol)} onToggleWL={toggleWL} />
        ))}
      </div>
    </div>
  );
}

function ScanCard({ r, theme, onChain, isWatched, onToggleWL }) {
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
          <ScoreDial score={r.score} theme={theme} />
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
            fontSize: 11, borderRight: `1px solid ${theme.border}`
          }}>
          View Chain
        </button>
        <button onClick={() => onChain(r.symbol)}
          style={{
            flex: 1, padding: "8px", background: "none", border: "none",
            cursor: "pointer", color: theme.muted, fontFamily: "inherit", fontSize: 11
          }}>
          Track →
        </button>
      </div>
    </div>
  );
}

function ScoreDial({ score, theme }) {
  const color = score >= 75 ? "#22c55e" : score >= 50 ? "#f59e0b" : "#ef4444";
  return (
    <div style={{ textAlign: "center", minWidth: 48 }}>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{score}</div>
      <div style={{ fontSize: 9, color: theme.muted }}>SCORE</div>
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

  useEffect(() => { load(symbol, expiry); }, [symbol]);

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

function GreeksTab({ theme }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [input, setInput] = useState("NIFTY");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async (sym) => {
    setLoading(true);
    try { setData(await apiFetch(`/api/greeks/${sym}`)); }
    catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(symbol); }, []);

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <SymbolInput value={input} onChange={setInput}
          onSubmit={() => { setSymbol(input); load(input); }} theme={theme} />
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
// Portfolio Tab
// ══════════════════════════════════════════════════════════════════════════════

function PortfolioTab({ theme }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [openTrades, setOpenTrades] = useState([]);
  const [noteInput, setNoteInput] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const [p, o] = await Promise.all([
        apiFetch("/api/portfolio"),
        apiFetch("/api/paper-trades/active"),
      ]);
      setData(p);
      setOpenTrades(o);
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

  if (loading) return <Loader theme={theme} />;
  if (!data) return null;

  const stats = data.closed_trades;
  const equity = stats.equity_curve || [];

  return (
    <div>
      {/* Summary Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
        {[
          ["Total P&L", `₹${stats.total_pnl?.toLocaleString("en-IN") || 0}`, stats.total_pnl >= 0 ? theme.green : theme.red],
          ["Unrealised", `₹${data.unrealised_pnl?.toLocaleString("en-IN") || 0}`, data.unrealised_pnl >= 0 ? theme.green : theme.red],
          ["Win Rate", `${stats.win_rate}%`, stats.win_rate >= 50 ? theme.green : theme.red],
          ["Trades", `${stats.wins}W / ${stats.losses}L`, theme.text],
          ["Avg P&L%", `${pct(stats.avg_pnl_pct)}`, stats.avg_pnl_pct >= 0 ? theme.green : theme.red],
          ["Max Drawdown", `₹${(stats.max_drawdown || 0).toLocaleString("en-IN")}`, theme.red],
          ["Capital", `₹${data.capital?.toLocaleString("en-IN")}`, theme.muted],
          ["Open", `${data.open_positions} pos`, theme.accent],
        ].map(([label, value, color]) => (
          <Card key={label} theme={theme}>
            <div style={{ color: theme.muted, fontSize: 10, marginBottom: 4 }}>{label}</div>
            <div style={{ fontWeight: 700, fontSize: 16, color }}>{value}</div>
          </Card>
        ))}
      </div>

      {/* Equity Curve */}
      {equity.length > 1 && (
        <Card theme={theme} style={{ marginBottom: 20 }}>
          <div style={{ color: theme.muted, fontSize: 11, marginBottom: 8 }}>EQUITY CURVE</div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={equity} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: theme.muted }} />
              <YAxis tickFormatter={v => `₹${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 10, fill: theme.muted }} />
              <Tooltip formatter={v => [`₹${v.toLocaleString("en-IN")}`, "Cumulative P&L"]} />
              <ReferenceLine y={0} stroke={theme.muted} strokeDasharray="4 4" />
              <Line dataKey="cumulative" dot={false} stroke={theme.accent} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

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

      {/* Open Positions with Journal */}
      {openTrades.length > 0 && (
        <Card theme={theme}>
          <div style={{ color: theme.muted, fontSize: 11, marginBottom: 10 }}>OPEN POSITIONS</div>
          {openTrades.map(t => {
            const pnlPct = t.pnl_pct || 0;
            return (
              <div key={t.id} style={{ borderBottom: `1px solid ${theme.border}`, padding: "10px 0" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <div>
                    <span style={{ fontWeight: 600 }}>{t.symbol}</span>
                    <span style={{ margin: "0 6px", color: theme.muted }}>·</span>
                    <Badge label={`${t.strike} ${t.type}`}
                      color={t.type === "CE" ? theme.green : theme.red}
                      bg={signalBg(t.type === "CE" ? "BULLISH" : "BEARISH")} />
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontWeight: 600, color: pnlPct >= 0 ? theme.green : theme.red }}>
                      {pct(pnlPct)} · ₹{(t.pnl || 0).toLocaleString("en-IN")}
                    </div>
                    <div style={{ fontSize: 11, color: theme.muted }}>
                      Entry ₹{t.entry_price} → ₹{t.current_price || "—"}
                    </div>
                  </div>
                </div>
                {/* Journal note input */}
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <input value={noteInput[t.id] || ""}
                    onChange={e => setNoteInput(prev => ({ ...prev, [t.id]: e.target.value }))}
                    placeholder="Add journal note..."
                    style={{
                      flex: 1, padding: "4px 8px", borderRadius: 4,
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
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Settings Tab
// ══════════════════════════════════════════════════════════════════════════════

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