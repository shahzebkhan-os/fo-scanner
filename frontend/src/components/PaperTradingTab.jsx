import { useState, useEffect, useCallback } from "react";
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
  BarChart, Bar,
} from "recharts";

const API = "";
const IST_TZ = "Asia/Kolkata";

async function apiFetch(path, options = {}) {
  const r = await fetch(API + path, options);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function Loader({ theme }) {
  return (
    <div style={{ textAlign: "center", padding: 40, color: theme.muted }}>
      <div style={{ fontSize: 24, animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</div>
      <div style={{ marginTop: 8, fontSize: 12 }}>Loading paper trades...</div>
    </div>
  );
}

function Card({ children, theme, style = {} }) {
  return (
    <div style={{
      background: theme.card, border: `1px solid ${theme.border}`,
      borderRadius: 8, padding: 16, ...style
    }}>{children}</div>
  );
}

function StatCard({ label, value, color, theme, icon }) {
  return (
    <Card theme={theme} style={{ textAlign: "center", padding: 12, flex: "1 1 120px" }}>
      {icon && <div style={{ fontSize: 16, marginBottom: 2 }}>{icon}</div>}
      <div style={{ fontSize: 22, fontWeight: 700, color: color || theme.text }}>{value}</div>
      <div style={{ fontSize: 10, color: theme.muted }}>{label}</div>
    </Card>
  );
}

function isAutoTrade(trade) {
  return (trade.reason || "").startsWith("Auto:");
}

/* ── Win-Rate Ring ──────────────────────────────────────────────────── */
function WinRateRing({ winRate, wins, losses, total, theme, size = 110 }) {
  const wr = Number(winRate) || 0;
  if (total === 0) {
    return (
      <div style={{ width: size, height: size, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: "50%", border: `3px solid ${theme.border}` }}>
        <span style={{ fontSize: size * 0.12, color: theme.muted }}>No data</span>
      </div>
    );
  }
  const data = [
    { name: "Wins", value: wins || 0 },
    { name: "Losses", value: losses || 0 },
  ];

  const COLORS = ["#22c55e", "#ef4444"];

  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            innerRadius={size * 0.35}
            outerRadius={size * 0.47}
            startAngle={90}
            endAngle={-270}
            paddingAngle={2}
            stroke="none"
          >
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      {/* Center label */}
      <div style={{
        position: "absolute", inset: 0, display: "flex",
        flexDirection: "column", alignItems: "center", justifyContent: "center",
        pointerEvents: "none",
      }}>
        <span style={{ fontSize: size * 0.22, fontWeight: 800, color: wr >= 50 ? "#22c55e" : "#ef4444" }}>
          {wr.toFixed(0)}%
        </span>
        <span style={{ fontSize: size * 0.1, color: theme.muted }}>Win Rate</span>
      </div>
    </div>
  );
}

/* ── Equity Curve Chart ─────────────────────────────────────────────── */
function EquityCurve({ curve, theme, height = 180 }) {
  if (!curve || curve.length === 0) return null;
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={curve} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
          <XAxis dataKey="date" tick={{ fontSize: 9, fill: theme.muted }} tickLine={false} />
          <YAxis tick={{ fontSize: 9, fill: theme.muted }} tickLine={false} axisLine={false}
            tickFormatter={v => `₹${v}`} />
          <Tooltip
            contentStyle={{
              background: theme.card, border: `1px solid ${theme.border}`,
              borderRadius: 6, fontSize: 11,
            }}
            formatter={(v, name) => [`₹${Number(v).toFixed(2)}`, name === "cumulative" ? "Cumulative P&L" : "Trade P&L"]}
          />
          <Area type="monotone" dataKey="cumulative" stroke="#6366f1" fill="url(#equityGrad)" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Per-Symbol Bar Chart ───────────────────────────────────────────── */
function SymbolPnlChart({ bySymbol, theme, height = 160 }) {
  if (!bySymbol || Object.keys(bySymbol).length === 0) return null;
  const chartData = Object.entries(bySymbol)
    .map(([sym, s]) => ({ symbol: sym, pnl: s.pnl, trades: s.trades, win_rate: s.win_rate }))
    .sort((a, b) => b.pnl - a.pnl);

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
          <XAxis dataKey="symbol" tick={{ fontSize: 9, fill: theme.muted }} tickLine={false} />
          <YAxis tick={{ fontSize: 9, fill: theme.muted }} tickLine={false} axisLine={false}
            tickFormatter={v => `₹${v}`} />
          <Tooltip
            contentStyle={{
              background: theme.card, border: `1px solid ${theme.border}`,
              borderRadius: 6, fontSize: 11,
            }}
            formatter={(v, name) => {
              if (name === "pnl") return [`₹${Number(v).toFixed(2)}`, "P&L"];
              return [v, name];
            }}
          />
          <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.pnl >= 0 ? "#22c55e" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Per-trade price history ───────────────────────────────────────────── */
function TradePriceHistory({ history, trade, theme, loading }) {
  if (!trade) return null;
  const data = (history || []).map(p => {
    const hasTZ = typeof p.ts === "string" && p.ts.endsWith("Z");
    if (typeof p.ts === "string" && !hasTZ) {
      console.warn("Paper trade history timestamp missing timezone suffix, assuming UTC:", p.ts);
    }
    const iso = hasTZ ? p.ts : `${p.ts}Z`;
    const tsText = new Date(iso).toLocaleTimeString("en-IN", { timeZone: IST_TZ, hour: "2-digit", minute: "2-digit" });
    return { ts: tsText, price: p.price };
  });
  const fallback = [
    { ts: "Entry", price: trade.entry_price },
    { ts: "Current", price: trade.current_price || trade.entry_price },
  ];
  const chartData = data.length > 1 ? data : fallback;

  return (
    <Card theme={theme} style={{ marginTop: 12, padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: theme.text }}>
          📈 {trade.symbol} {trade.type} {trade.strike} price history
        </div>
        {loading && <span style={{ fontSize: 11, color: theme.muted }}>Loading…</span>}
      </div>
      <div style={{ width: "100%", height: 180 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
            <XAxis dataKey="ts" tick={{ fontSize: 9, fill: theme.muted }} tickLine={false} />
            <YAxis tick={{ fontSize: 9, fill: theme.muted }} tickLine={false} axisLine={false}
              tickFormatter={v => `₹${v}`} />
            <Tooltip
              contentStyle={{
                background: theme.card, border: `1px solid ${theme.border}`,
                borderRadius: 6, fontSize: 11,
              }}
              formatter={(v) => [`₹${Number(v).toFixed(2)}`, "Price"]}
            />
            <Area type="monotone" dataKey="price" stroke="#22c55e" fill="url(#priceGrad)" strokeWidth={2} dot />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {data.length === 0 && (
        <div style={{ fontSize: 11, color: theme.muted, marginTop: 6 }}>
          No intraday history yet — showing entry vs current price.
        </div>
      )}
    </Card>
  );
}

function TradeRow({ trade, theme }) {
  const pnl = trade.pnl || 0;
  const pnlPct = trade.pnl_pct || 0;
  const isOpen = trade.status === "OPEN";
  const isProfit = pnl > 0;
  const isAuto = isAutoTrade(trade);
  const isSuggestion = (trade.reason || "").includes("Suggestion");

  return (
    <div className="trade-row" style={{
      display: "grid",
      gridTemplateColumns: "1.2fr 0.6fr 0.8fr 0.8fr 0.8fr 0.8fr 1fr 0.6fr",
      gap: 8,
      padding: "10px 12px",
      borderBottom: `1px solid ${theme.border}`,
      fontSize: 12,
      alignItems: "center",
      cursor: "pointer",
    }} onClick={trade.onSelect}>
      <div>
        <span style={{ fontWeight: 700 }}>{trade.symbol}</span>
        <span style={{
          marginLeft: 6, padding: "1px 6px", borderRadius: 3, fontSize: 10, fontWeight: 600,
          background: trade.type === "CE" ? "rgba(34,197,94,.12)" : "rgba(239,68,68,.12)",
          color: trade.type === "CE" ? "#22c55e" : "#ef4444",
        }}>{trade.type}</span>
        {isAuto && <span style={{ marginLeft: 4, fontSize: 9, color: "#6366f1" }}>⚡auto</span>}
        {isSuggestion && <span style={{ marginLeft: 4, fontSize: 9, color: "#f59e0b" }}>💡sugg</span>}
      </div>
      <div style={{ color: theme.muted }}>{trade.strike}</div>
      <div>₹{Number(trade.entry_price || 0).toFixed(2)}</div>
      <div>₹{Number(trade.current_price || trade.entry_price || 0).toFixed(2)}</div>
      <div style={{ color: isProfit ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
        {pnl >= 0 ? "+" : ""}₹{pnl.toFixed(2)}
      </div>
      <div style={{ color: isProfit ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
        {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%
      </div>
      <div style={{ fontSize: 10, color: theme.muted }}>
        {trade.entry_time ? new Date(trade.entry_time + "Z").toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"}
      </div>
      <div>
        <span style={{
          padding: "2px 6px", borderRadius: 4, fontSize: 10, fontWeight: 600,
          background: isOpen ? "rgba(99,102,241,.12)" : pnl > 0 ? "rgba(34,197,94,.12)" : "rgba(239,68,68,.12)",
          color: isOpen ? "#6366f1" : pnl > 0 ? "#22c55e" : "#ef4444",
        }}>
          {trade.status}
        </span>
      </div>
    </div>
  );
}

export default function PaperTradingTab({ theme }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");
  const [autoTradeEnabled, setAutoTradeEnabled] = useState(
    () => localStorage.getItem("autoTradeFromSuggestions") !== "false"
  );
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);
  const [configSaving, setConfigSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const apiFilter = filter === "auto" ? "all" : filter;
      const result = await apiFetch(`/api/paper-trades?status=${apiFilter}`);
      setData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  const fetchTradeHistory = async (trade) => {
    if (!trade?.id) return;
    setSelectedTrade(trade);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const res = await apiFetch(`/api/paper-trades/${trade.id}/history`);
      setTradeHistory(res.history || []);
    } catch (e) {
      setHistoryError(e.message || "Failed to load history");
      setTradeHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const updateAutoConfig = async (field, value) => {
    setConfigSaving(true);
    setData(prev => prev ? { ...prev, config: { ...prev.config, [field]: value } } : prev);
    try {
      await apiFetch("/api/paper-trades/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
    } catch (e) {
      setError(e.message || "Failed to update config");
    } finally {
      setConfigSaving(false);
    }
  };

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 60s
  useEffect(() => {
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [load]);

  const toggleAutoTrade = () => {
    const next = !autoTradeEnabled;
    setAutoTradeEnabled(next);
    localStorage.setItem("autoTradeFromSuggestions", next ? "true" : "false");
  };

  if (loading && !data) return <Loader theme={theme} />;

  const trades = data?.trades || [];
  const stats = data?.stats || {};
  const autoAcc = data?.auto_accuracy || {};
  const manualAcc = data?.manual_accuracy || {};
  const mktStatus = data?.market_status || {};
  const marketOpen = mktStatus.open === true;
  const config = data?.config || {};
  const openAuto = data?.open_auto || 0;
  const openManual = data?.open_manual || 0;

  const openTrades = trades.filter(t => t.status === "OPEN");
  const closedTrades = trades.filter(t => t.status === "CLOSED");
  const autoTrades = trades.filter(t => isAutoTrade(t));

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
            📝 Paper Trading
          </h2>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>
            Auto paper trades when confidence &gt; 80 · Managed with adaptive SL/TP · Tracked for better exit
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button onClick={toggleAutoTrade} style={{
            padding: "5px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600,
            background: autoTradeEnabled ? "rgba(34,197,94,.12)" : "rgba(148,163,184,.1)",
            color: autoTradeEnabled ? "#22c55e" : theme.muted,
            border: `1px solid ${autoTradeEnabled ? "rgba(34,197,94,.3)" : theme.border}`,
            cursor: "pointer",
          }}>
            {autoTradeEnabled ? "✓ Auto-Trade ON" : "○ Auto-Trade OFF"}
          </button>
          <span style={{
            padding: "3px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600,
            background: marketOpen ? "rgba(34,197,94,.12)" : "rgba(239,68,68,.12)",
            color: marketOpen ? "#22c55e" : "#ef4444",
          }}>
            {marketOpen ? "● LIVE" : "○ CLOSED"}
          </span>
          <button onClick={load} disabled={loading} style={{
            padding: "6px 14px", borderRadius: 6, fontSize: 11, fontWeight: 700,
            background: loading ? theme.border : "#6366f1",
            color: "#fff", border: "none", cursor: loading ? "wait" : "pointer"
          }}>{loading ? "⟳" : "Refresh"}</button>
        </div>
      </div>

      {error && (
        <div style={{
          background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.3)",
          borderRadius: 8, padding: 12, marginBottom: 16, color: "#ef4444", fontSize: 12
        }}>⚠ {error}</div>
      )}

      {/* Stats Summary */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
        <StatCard label="Open Trades" value={openTrades.length} color="#6366f1" theme={theme} icon="📂" />
        <StatCard label="Total Closed" value={stats.total || 0} color={theme.text} theme={theme} icon="✅" />
        <StatCard label="Win Rate" value={`${stats.win_rate || 0}%`} color={(stats.win_rate || 0) >= 50 ? "#22c55e" : "#ef4444"} theme={theme} icon="🎯" />
        <StatCard label="Total P&L" value={`₹${(stats.total_pnl || 0).toLocaleString()}`} color={(stats.total_pnl || 0) >= 0 ? "#22c55e" : "#ef4444"} theme={theme} icon="💰" />
        <StatCard label="Avg P&L %" value={`${(stats.avg_pnl_pct || 0).toFixed(1)}%`} color={(stats.avg_pnl_pct || 0) >= 0 ? "#22c55e" : "#ef4444"} theme={theme} icon="📈" />
        <StatCard label="Max Drawdown" value={`₹${(stats.max_drawdown || 0).toLocaleString()}`} color="#ef4444" theme={theme} icon="📉" />
      </div>

      {/* ═══ Auto-Trade Accuracy Dashboard ═══ */}
      <Card theme={theme} style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
        {/* Section header */}
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "12px 16px",
          background: "linear-gradient(135deg, rgba(99,102,241,.08), rgba(139,92,246,.06))",
          borderBottom: `1px solid ${theme.border}`,
        }}>
          <h3 style={{ margin: 0, fontSize: 15, display: "flex", alignItems: "center", gap: 6 }}>
            ⚡ Auto-Trade Accuracy
            <span style={{
              fontSize: 10, padding: "2px 8px", borderRadius: 10,
              background: "rgba(99,102,241,.12)", color: "#6366f1", fontWeight: 600,
            }}>confidence &gt; {config.score_threshold || 80}</span>
          </h3>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ fontSize: 10, color: theme.muted }}>
              {openAuto} open · {autoAcc.total || 0} closed
            </span>
            {config.daily_trades_today != null && (
              <span style={{
                fontSize: 9, padding: "2px 6px", borderRadius: 4,
                background: "rgba(99,102,241,.08)", color: "#6366f1",
              }}>
                Today: {config.daily_trades_today}/{config.max_daily_trades ?? "∞"}
              </span>
            )}
          </div>
        </div>

        <div style={{ padding: 16 }}>
          {autoAcc.total > 0 ? (
            <>
              {/* Top row: Ring + Stats + Best/Worst */}
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16, alignItems: "center" }}>
                {/* Win Rate Ring */}
                <WinRateRing
                  winRate={autoAcc.win_rate}
                  wins={autoAcc.wins}
                  losses={autoAcc.losses}
                  total={autoAcc.total}
                  theme={theme}
                  size={120}
                />
                {/* Stat cards */}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, flex: 1 }}>
                  <StatCard label="Auto Wins" value={autoAcc.wins || 0} color="#22c55e" theme={theme} icon="🟢" />
                  <StatCard label="Auto Losses" value={autoAcc.losses || 0} color="#ef4444" theme={theme} icon="🔴" />
                  <StatCard label="Total P&L" value={`₹${(autoAcc.total_pnl || 0).toLocaleString()}`}
                    color={(autoAcc.total_pnl || 0) >= 0 ? "#22c55e" : "#ef4444"} theme={theme} icon="💰" />
                  <StatCard label="Avg Return" value={`${(autoAcc.avg_pnl_pct || 0).toFixed(1)}%`}
                    color={(autoAcc.avg_pnl_pct || 0) >= 0 ? "#22c55e" : "#ef4444"} theme={theme} icon="📊" />
                  <StatCard label="Max Drawdown" value={`₹${(autoAcc.max_drawdown || 0).toLocaleString()}`}
                    color="#ef4444" theme={theme} icon="⬇" />
                </div>
              </div>

              {/* Best & Worst Trade */}
              {(autoAcc.best || autoAcc.worst) && (
                <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
                  {autoAcc.best && (
                    <Card theme={theme} style={{
                      flex: "1 1 200px", padding: 10,
                      borderLeft: "3px solid #22c55e",
                    }}>
                      <div style={{ fontSize: 10, color: "#22c55e", fontWeight: 700, marginBottom: 4 }}>🏆 Best Auto Trade</div>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>
                        {autoAcc.best.symbol} {autoAcc.best.type} {autoAcc.best.strike}
                      </div>
                      <div style={{ fontSize: 11, color: "#22c55e" }}>
                        +₹{(autoAcc.best.pnl || 0).toFixed(2)} ({(autoAcc.best.pnl_pct || 0).toFixed(1)}%)
                      </div>
                    </Card>
                  )}
                  {autoAcc.worst && (
                    <Card theme={theme} style={{
                      flex: "1 1 200px", padding: 10,
                      borderLeft: "3px solid #ef4444",
                    }}>
                      <div style={{ fontSize: 10, color: "#ef4444", fontWeight: 700, marginBottom: 4 }}>📉 Worst Auto Trade</div>
                      <div style={{ fontSize: 13, fontWeight: 700 }}>
                        {autoAcc.worst.symbol} {autoAcc.worst.type} {autoAcc.worst.strike}
                      </div>
                      <div style={{ fontSize: 11, color: "#ef4444" }}>
                        ₹{(autoAcc.worst.pnl || 0).toFixed(2)} ({(autoAcc.worst.pnl_pct || 0).toFixed(1)}%)
                      </div>
                    </Card>
                  )}
                </div>
              )}

              {/* Equity Curve */}
              {autoAcc.equity_curve && autoAcc.equity_curve.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: theme.text }}>
                    📈 Auto-Trade Equity Curve
                  </div>
                  <EquityCurve curve={autoAcc.equity_curve} theme={theme} height={180} />
                </div>
              )}

              {/* Per-Symbol Bar Chart for Auto Trades */}
              {autoAcc.by_symbol && Object.keys(autoAcc.by_symbol).length > 0 && (
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: theme.text }}>
                    📊 Auto P&L by Symbol
                  </div>
                  <SymbolPnlChart bySymbol={autoAcc.by_symbol} theme={theme} height={160} />
                </div>
              )}
            </>
          ) : (
            <div style={{
              textAlign: "center", padding: "24px 16px", color: theme.muted,
            }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>🤖</div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>No closed auto-trades yet</div>
              <div style={{ fontSize: 11, maxWidth: 400, margin: "0 auto" }}>
                Auto-trades are created during market hours when a stock scores above {config.score_threshold || 80} with ML confirmation
                (bullish &gt; {((config.ml_bullish_gate || 0.6) * 100).toFixed(0)}% / bearish &lt; {((config.ml_bearish_gate || 0.4) * 100).toFixed(0)}%).
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Auto vs Manual Comparison */}
      {(autoAcc.total > 0 || manualAcc.total > 0) && (
        <Card theme={theme} style={{ marginBottom: 16, padding: 14 }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: 14, display: "flex", alignItems: "center", gap: 6 }}>
            ⚖ Auto vs Manual Comparison
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {/* Auto column */}
            <div style={{
              padding: 12, borderRadius: 8,
              background: "rgba(99,102,241,.06)", border: "1px solid rgba(99,102,241,.15)",
            }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#6366f1", marginBottom: 8 }}>⚡ Auto Trades</div>
              <div style={{ fontSize: 11, color: theme.muted, display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Closed</span><span style={{ fontWeight: 600, color: theme.text }}>{autoAcc.total || 0}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Win Rate</span>
                  <span style={{ fontWeight: 600, color: (autoAcc.win_rate || 0) >= 50 ? "#22c55e" : "#ef4444" }}>
                    {autoAcc.win_rate || 0}%
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Total P&L</span>
                  <span style={{ fontWeight: 600, color: (autoAcc.total_pnl || 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                    ₹{(autoAcc.total_pnl || 0).toLocaleString()}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Avg Return</span>
                  <span style={{ fontWeight: 600, color: (autoAcc.avg_pnl_pct || 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                    {(autoAcc.avg_pnl_pct || 0).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
            {/* Manual column */}
            <div style={{
              padding: 12, borderRadius: 8,
              background: "rgba(245,158,11,.06)", border: "1px solid rgba(245,158,11,.15)",
            }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#f59e0b", marginBottom: 8 }}>🖐 Manual Trades</div>
              <div style={{ fontSize: 11, color: theme.muted, display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Closed</span><span style={{ fontWeight: 600, color: theme.text }}>{manualAcc.total || 0}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Win Rate</span>
                  <span style={{ fontWeight: 600, color: (manualAcc.win_rate || 0) >= 50 ? "#22c55e" : "#ef4444" }}>
                    {manualAcc.win_rate || 0}%
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Total P&L</span>
                  <span style={{ fontWeight: 600, color: (manualAcc.total_pnl || 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                    ₹{(manualAcc.total_pnl || 0).toLocaleString()}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>Avg Return</span>
                  <span style={{ fontWeight: 600, color: (manualAcc.avg_pnl_pct || 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                    {(manualAcc.avg_pnl_pct || 0).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Filter Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {["all", "open", "closed", "auto"].map(f => {
          const counts = { all: trades.length, open: openTrades.length, closed: closedTrades.length, auto: autoTrades.length };
          return (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding: "5px 14px", borderRadius: 6, fontSize: 11, fontWeight: 600,
              background: filter === f ? "rgba(99,102,241,.12)" : "none",
              color: filter === f ? "#6366f1" : theme.muted,
              border: `1px solid ${filter === f ? "rgba(99,102,241,.3)" : theme.border}`,
              cursor: "pointer", textTransform: "uppercase",
            }}>{f} ({counts[f] || 0})</button>
          );
        })}
      </div>

      {/* Trades Table */}
      <Card theme={theme} style={{ padding: 0, overflow: "hidden" }}>
        {/* Table Header */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1.2fr 0.6fr 0.8fr 0.8fr 0.8fr 0.8fr 1fr 0.6fr",
          gap: 8,
          padding: "10px 12px",
          background: theme.bg,
          borderBottom: `1px solid ${theme.border}`,
          fontSize: 10,
          fontWeight: 700,
          color: theme.muted,
          textTransform: "uppercase",
        }}>
          <div>Symbol</div>
          <div>Strike</div>
          <div>Entry</div>
          <div>Current</div>
          <div>P&L</div>
          <div>P&L %</div>
          <div>Time</div>
          <div>Status</div>
        </div>

        {(() => {
          const displayTrades = filter === "auto" ? autoTrades : trades;
          return displayTrades.length === 0 ? (
            <div style={{ textAlign: "center", padding: 32, color: theme.muted, fontSize: 13 }}>
              <div style={{ fontSize: 28, marginBottom: 8 }}>📋</div>
              {filter === "auto"
                ? `No auto-trades yet. Auto-trades are created when confidence > ${config.score_threshold || 80} during market hours.`
                : "No paper trades yet. Trades are auto-created from high-conviction scans during market hours."}
            </div>
          ) : (
            displayTrades.map((t, i) => (
              <TradeRow
                key={t.id || i}
                trade={{ ...t, onSelect: () => fetchTradeHistory(t) }}
                theme={theme}
              />
            ))
          );
        })()}
      </Card>

      {/* Trade price history viewer */}
      {(selectedTrade || historyError) && (
        <div style={{ marginTop: 12 }}>
          {historyError && (
            <Card theme={theme} style={{ marginBottom: 8, color: "#ef4444", fontSize: 11 }}>
              ⚠ {historyError}
            </Card>
          )}
          <TradePriceHistory history={tradeHistory} trade={selectedTrade} theme={theme} loading={historyLoading} />
        </div>
      )}

      {/* Equity Curve (All trades) */}
      {stats.equity_curve && stats.equity_curve.length > 0 && (
        <Card theme={theme} style={{ marginTop: 16, padding: 14 }}>
          <h3 style={{ margin: "0 0 10px 0", fontSize: 14, color: theme.text }}>📈 Overall Equity Curve</h3>
          <EquityCurve curve={stats.equity_curve} theme={theme} height={200} />
        </Card>
      )}

      {/* Per-Symbol Breakdown */}
      {stats.by_symbol && Object.keys(stats.by_symbol).length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 14, marginBottom: 10, color: theme.text }}>📊 Per-Symbol Performance</h3>
          <SymbolPnlChart bySymbol={stats.by_symbol} theme={theme} height={180} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10, marginTop: 12 }}>
            {Object.entries(stats.by_symbol)
              .sort((a, b) => b[1].pnl - a[1].pnl)
              .map(([sym, s]) => (
                <Card key={sym} theme={theme} style={{ padding: 10 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{sym}</div>
                  <div style={{ fontSize: 11, color: theme.muted }}>
                    <div>Trades: {s.trades} · WR: {s.win_rate}%</div>
                    <div style={{ color: s.pnl >= 0 ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
                      P&L: ₹{s.pnl.toLocaleString()}
                    </div>
                  </div>
                </Card>
              ))}
          </div>
        </div>
      )}

      {/* Auto-Trade Config Panel */}
      {Object.keys(config).length > 0 && (
        <Card theme={theme} style={{ marginTop: 16, padding: 14 }}>
          <h3 style={{ margin: "0 0 10px 0", fontSize: 13, color: theme.text, display: "flex", alignItems: "center", gap: 6 }}>
            ⚙ Auto-Trade Configuration
          </h3>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: theme.muted }}>
              Confidence threshold
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                <input
                  type="range"
                  min={60}
                  max={100}
                  value={config.score_threshold || 80}
                  onChange={(e) => updateAutoConfig("score_threshold", Number(e.target.value))}
                  style={{ accentColor: "#6366f1" }}
                />
                <span style={{ fontWeight: 700, color: theme.text }}>{config.score_threshold || 80}</span>
              </div>
            </div>
            <div style={{ fontSize: 11, color: theme.muted }}>
              ML gates
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={config.ml_bullish_gate || 0.6}
                  onChange={(e) => updateAutoConfig("ml_bullish_gate", Number(e.target.value))}
                  style={{ width: 70, padding: 4, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bg, color: theme.text }}
                  title="Bullish ML probability gate"
                />
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={config.ml_bearish_gate || 0.4}
                  onChange={(e) => updateAutoConfig("ml_bearish_gate", Number(e.target.value))}
                  style={{ width: 70, padding: 4, borderRadius: 4, border: `1px solid ${theme.border}`, background: theme.bg, color: theme.text }}
                  title="Bearish ML probability gate"
                />
                {configSaving && <span style={{ fontSize: 10, color: theme.muted }}>Saving…</span>}
              </div>
            </div>
          </div>
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
            gap: 8, fontSize: 11,
          }}>
            <div style={{ padding: 8, borderRadius: 6, background: "rgba(99,102,241,.05)" }}>
              <div style={{ color: theme.muted, marginBottom: 2 }}>Score Threshold</div>
              <div style={{ fontWeight: 700, color: theme.text }}>&gt; {config.score_threshold || 80}</div>
            </div>
            <div style={{ padding: 8, borderRadius: 6, background: "rgba(34,197,94,.05)" }}>
              <div style={{ color: theme.muted, marginBottom: 2 }}>ML Bullish Gate</div>
              <div style={{ fontWeight: 700, color: "#22c55e" }}>&gt; {((config.ml_bullish_gate || 0.6) * 100).toFixed(0)}%</div>
            </div>
            <div style={{ padding: 8, borderRadius: 6, background: "rgba(239,68,68,.05)" }}>
              <div style={{ color: theme.muted, marginBottom: 2 }}>ML Bearish Gate</div>
              <div style={{ fontWeight: 700, color: "#ef4444" }}>&lt; {((config.ml_bearish_gate || 0.4) * 100).toFixed(0)}%</div>
            </div>
            <div style={{ padding: 8, borderRadius: 6, background: "rgba(245,158,11,.05)" }}>
              <div style={{ color: theme.muted, marginBottom: 2 }}>Max Daily Trades</div>
              <div style={{ fontWeight: 700, color: theme.text }}>{config.max_daily_trades ?? "∞"}</div>
            </div>
            <div style={{ padding: 8, borderRadius: 6, background: "rgba(99,102,241,.05)" }}>
              <div style={{ color: theme.muted, marginBottom: 2 }}>Max Sector Trades</div>
              <div style={{ fontWeight: 700, color: theme.text }}>{config.max_sector_trades ?? "∞"}</div>
            </div>
            <div style={{ padding: 8, borderRadius: 6, background: "rgba(139,92,246,.05)" }}>
              <div style={{ color: theme.muted, marginBottom: 2 }}>Trades Today</div>
              <div style={{ fontWeight: 700, color: "#8b5cf6" }}>{config.daily_trades_today ?? "—"}</div>
            </div>
          </div>
        </Card>
      )}

      {/* Info */}
      <div style={{
        fontSize: 9, color: theme.muted, textAlign: "center",
        marginTop: 20, padding: "12px 0", borderTop: `1px solid ${theme.border}`, opacity: 0.7
      }}>
        ⚠ Paper trades are simulated and do not involve real money. Auto SL/TP managed by backend.
      </div>
    </div>
  );
}
