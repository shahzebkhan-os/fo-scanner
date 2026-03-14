import { useState, useEffect, useCallback } from "react";

const API = "";

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

function StatCard({ label, value, color, theme }) {
  return (
    <Card theme={theme} style={{ textAlign: "center", padding: 12, flex: "1 1 120px" }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || theme.text }}>{value}</div>
      <div style={{ fontSize: 10, color: theme.muted }}>{label}</div>
    </Card>
  );
}

function TradeRow({ trade, theme }) {
  const pnl = trade.pnl || 0;
  const pnlPct = trade.pnl_pct || 0;
  const isOpen = trade.status === "OPEN";
  const isProfit = pnl > 0;
  const isAuto = (trade.reason || "").startsWith("Auto:");
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
    }}>
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch(`/api/paper-trades?status=${filter}`);
      setData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filter]);

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
  const mktStatus = data?.market_status || {};
  const marketOpen = mktStatus.open === true;

  const openTrades = trades.filter(t => t.status === "OPEN");
  const closedTrades = trades.filter(t => t.status === "CLOSED");

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
            📝 Paper Trading
          </h2>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>
            Auto paper trades from suggestions & manual entries · Managed with adaptive SL/TP
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
        <StatCard label="Open Trades" value={openTrades.length} color="#6366f1" theme={theme} />
        <StatCard label="Total Closed" value={stats.total || 0} color={theme.text} theme={theme} />
        <StatCard label="Win Rate" value={`${stats.win_rate || 0}%`} color={(stats.win_rate || 0) >= 50 ? "#22c55e" : "#ef4444"} theme={theme} />
        <StatCard label="Total P&L" value={`₹${(stats.total_pnl || 0).toLocaleString()}`} color={(stats.total_pnl || 0) >= 0 ? "#22c55e" : "#ef4444"} theme={theme} />
        <StatCard label="Avg P&L %" value={`${(stats.avg_pnl_pct || 0).toFixed(1)}%`} color={(stats.avg_pnl_pct || 0) >= 0 ? "#22c55e" : "#ef4444"} theme={theme} />
        <StatCard label="Max Drawdown" value={`₹${(stats.max_drawdown || 0).toLocaleString()}`} color="#ef4444" theme={theme} />
      </div>

      {/* Filter Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        {["all", "open", "closed"].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: "5px 14px", borderRadius: 6, fontSize: 11, fontWeight: 600,
            background: filter === f ? "rgba(99,102,241,.12)" : "none",
            color: filter === f ? "#6366f1" : theme.muted,
            border: `1px solid ${filter === f ? "rgba(99,102,241,.3)" : theme.border}`,
            cursor: "pointer", textTransform: "uppercase",
          }}>{f} ({f === "all" ? trades.length : f === "open" ? openTrades.length : closedTrades.length})</button>
        ))}
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

        {trades.length === 0 ? (
          <div style={{ textAlign: "center", padding: 32, color: theme.muted, fontSize: 13 }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>📋</div>
            No paper trades yet. Trades are auto-created from high-conviction suggestions during market hours.
          </div>
        ) : (
          trades.map((t, i) => <TradeRow key={t.id || i} trade={t} theme={theme} />)
        )}
      </Card>

      {/* Per-Symbol Breakdown */}
      {stats.by_symbol && Object.keys(stats.by_symbol).length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 14, marginBottom: 10, color: theme.text }}>📊 Per-Symbol Performance</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
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
