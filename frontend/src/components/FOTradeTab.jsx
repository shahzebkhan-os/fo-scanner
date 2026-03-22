import { useState, useEffect, useCallback } from "react";

async function apiFetch(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

const signalColor = (s) =>
  s === "BULLISH" ? "#22c55e" : s === "BEARISH" ? "#ef4444" : "#94a3b8";
const signalBg = (s) =>
  s === "BULLISH" ? "rgba(34,197,94,.15)" : s === "BEARISH" ? "rgba(239,68,68,.15)" : "rgba(148,163,184,.1)";
const convictionColor = (c) =>
  c >= 85 ? "#22c55e" : c >= 70 ? "#f59e0b" : c >= 60 ? "#fb923c" : "#ef4444";
const timeQualityColor = (q) =>
  q === "optimal" ? "#22c55e" : q === "good" ? "#3b82f6" : q === "okay" ? "#f59e0b" : "#ef4444";
const timeQualityIcon = (q) =>
  q === "optimal" ? "🟢" : q === "good" ? "🔵" : q === "okay" ? "🟡" : "🔴";

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

/* ── Pipeline Funnel ──────────────────────────────────────────────────────── */
function PipelineFunnel({ pipeline, theme }) {
  const stages = [
    { key: "scanned",          label: "Scanned",    icon: "📡", color: "#6366f1" },
    { key: "after_liquidity",  label: "Liquid",     icon: "💧", color: "#3b82f6" },
    { key: "after_confluence", label: "Confluence",  icon: "🎯", color: "#f59e0b" },
    { key: "after_dte",        label: "DTE Valid",   icon: "📅", color: "#22c55e" },
    { key: "final",            label: "Final",       icon: "✅", color: "#10b981" },
  ];

  return (
    <div style={{
      display: "flex", gap: 4, alignItems: "center",
      background: "rgba(99,102,241,.04)", borderRadius: 8, padding: "10px 14px",
      marginBottom: 16, overflowX: "auto",
    }}>
      {stages.map((s, i) => {
        const val = pipeline[s.key] ?? 0;
        const prev = i > 0 ? (pipeline[stages[i - 1].key] ?? 0) : val;
        const filterRate = prev > 0 ? Math.round((1 - val / prev) * 100) : 0;

        return (
          <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{
              textAlign: "center", minWidth: 70,
              padding: "6px 10px", borderRadius: 6,
              background: i === stages.length - 1 ? "rgba(16,185,129,.12)" : "rgba(99,102,241,.06)",
              border: i === stages.length - 1 ? "1px solid rgba(16,185,129,.3)" : `1px solid ${theme.border}`,
            }}>
              <div style={{ fontSize: 16 }}>{s.icon}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: s.color }}>{val}</div>
              <div style={{ fontSize: 9, color: theme.muted }}>{s.label}</div>
              {i > 0 && filterRate > 0 && (
                <div style={{ fontSize: 8, color: "#ef4444", fontWeight: 600 }}>-{filterRate}%</div>
              )}
            </div>
            {i < stages.length - 1 && (
              <span style={{ color: theme.muted, fontSize: 14 }}>→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Confluence Dots ──────────────────────────────────────────────────────── */
function ConfluenceDots({ confluence, theme }) {
  if (!confluence || !confluence.factors) return null;
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
      {confluence.factors.map((f, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 4,
          padding: "3px 8px", borderRadius: 12, fontSize: 10,
          background: f.aligned ? "rgba(34,197,94,.1)" : "rgba(239,68,68,.06)",
          border: `1px solid ${f.aligned ? "rgba(34,197,94,.3)" : "rgba(239,68,68,.15)"}`,
          color: f.aligned ? "#22c55e" : theme.muted,
        }}>
          <span style={{ fontSize: 8 }}>{f.aligned ? "●" : "○"}</span>
          <span style={{ fontWeight: 600 }}>{f.name}</span>
          <span style={{ opacity: 0.7 }}>{typeof f.value === "number" ? f.value : f.value}</span>
        </div>
      ))}
      <span style={{
        padding: "3px 8px", borderRadius: 12, fontSize: 10, fontWeight: 700,
        background: confluence.aligned >= 3 ? "rgba(34,197,94,.15)" : "rgba(239,68,68,.1)",
        color: confluence.aligned >= 3 ? "#22c55e" : "#ef4444",
      }}>
        {confluence.aligned}/{confluence.total}
      </span>
    </div>
  );
}

/* ── Conviction Ring ──────────────────────────────────────────────────────── */
function ConvictionRing({ conviction, label, theme }) {
  const color = convictionColor(conviction);
  const pct = Math.min(100, conviction);
  return (
    <div style={{ textAlign: "center", minWidth: 60 }}>
      <div style={{ position: "relative", width: 52, height: 52, margin: "0 auto" }}>
        <svg width="52" height="52" viewBox="0 0 60 60">
          <circle cx="30" cy="30" r="25" fill="none" stroke={theme.border} strokeWidth="4" />
          <circle cx="30" cy="30" r="25" fill="none" stroke={color} strokeWidth="4"
            strokeDasharray={`${pct * 1.57} 157`} strokeLinecap="round"
            transform="rotate(-90 30 30)" style={{ transition: "stroke-dasharray 0.5s ease" }} />
        </svg>
        <div style={{
          position: "absolute", top: "50%", left: "50%",
          transform: "translate(-50%, -50%)", fontSize: 14, fontWeight: 700, color
        }}>{conviction}</div>
      </div>
      <div style={{ fontSize: 8, color: theme.muted, fontWeight: 700, marginTop: 3 }}>{label}</div>
    </div>
  );
}

/* ── Trade Card ───────────────────────────────────────────────────────────── */
function TradeCard({ trade, theme, goChain }) {
  const strat = trade.strategy || {};
  const entry = trade.entry || {};
  const rr = trade.risk_reward || {};
  const sizing = trade.sizing || {};
  const [tradeStatus, setTradeStatus] = useState(null);
  const [tradeMsg, setTradeMsg] = useState("");

  const optType = entry.primary_type || (trade.signal === "BEARISH" ? "PE" : "CE");

  async function handlePaperTrade() {
    if (tradeStatus === "loading") return;
    const ok = window.confirm(
      `Paper trade: ${trade.symbol} ${optType} ${entry.primary_strike} @ ₹${entry.entry_premium}\nProceed?`
    );
    if (!ok) return;
    setTradeStatus("loading");
    try {
      const res = await apiFetch("/api/fo-suggestions/paper-trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: trade.symbol, opt_type: optType, strike: entry.primary_strike,
          entry_price: entry.entry_premium, lot_size: sizing.lot_size || 1,
          reason: `FO Trade: ${trade.signal} | Conv ${trade.conviction} | ${strat.strategy || ""}`,
        }),
      });
      setTradeStatus("ok");
      setTradeMsg(res?.message || "Trade added!");
    } catch (e) {
      setTradeStatus("err");
      setTradeMsg(e.message);
    }
  }

  return (
    <Card theme={theme} style={{
      borderLeft: `4px solid ${signalColor(trade.signal)}`,
      marginBottom: 14,
      animation: "fadeIn 0.3s ease",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: 17, fontWeight: 700 }}>{trade.symbol}</span>
            <Badge label={trade.signal} color={signalColor(trade.signal)} bg={signalBg(trade.signal)} />
            {strat.strategy && <Badge label={strat.strategy} color="#6366f1" bg="rgba(99,102,241,.12)" />}
            {trade.bulk_aligned && (
              <Badge label="📦 Bulk Deal" color="#f59e0b" bg="rgba(245,158,11,.12)" />
            )}
            {trade.max_pain_conv?.converging && (
              <Badge label="🧲 Max Pain" color="#8b5cf6" bg="rgba(139,92,246,.12)" />
            )}
          </div>
          <div style={{ fontSize: 11, color: theme.muted }}>{strat.description}</div>
        </div>
        <ConvictionRing conviction={trade.conviction} label={trade.conviction_label} theme={theme} />
      </div>

      {/* Confluence Analysis */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 9, color: theme.muted, fontWeight: 700, marginBottom: 4, textTransform: "uppercase" }}>
          Confluence Analysis
        </div>
        <ConfluenceDots confluence={trade.confluence} theme={theme} />
      </div>

      {/* Entry / Target / Position Grid */}
      {entry.primary_strike && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 10 }}>
          <div style={{ background: "rgba(99,102,241,.05)", borderRadius: 6, padding: 10 }}>
            <div style={{ fontSize: 9, color: theme.muted, fontWeight: 700, marginBottom: 4, textTransform: "uppercase" }}>Entry</div>
            <div style={{ fontSize: 12 }}>
              <div>Strike: <b>{entry.primary_strike} {entry.primary_type}</b></div>
              <div>Entry: <b style={{ color: "#6366f1" }}>₹{entry.entry_premium}</b></div>
              <div>Spot: ₹{trade.spot}</div>
            </div>
          </div>
          <div style={{ background: "rgba(34,197,94,.05)", borderRadius: 6, padding: 10 }}>
            <div style={{ fontSize: 9, color: theme.muted, fontWeight: 700, marginBottom: 4, textTransform: "uppercase" }}>Target / SL</div>
            <div style={{ fontSize: 12 }}>
              <div>R:R → <b style={{ color: "#22c55e" }}>{rr.risk_reward_ratio}</b></div>
              <div>Target: <b style={{ color: "#22c55e" }}>₹{rr.target_price}</b></div>
              <div>Stop: <span style={{ color: "#ef4444" }}>₹{rr.stop_loss_price}</span></div>
            </div>
          </div>
          <div style={{ background: "rgba(245,158,11,.05)", borderRadius: 6, padding: 10 }}>
            <div style={{ fontSize: 9, color: theme.muted, fontWeight: 700, marginBottom: 4, textTransform: "uppercase" }}>Position</div>
            <div style={{ fontSize: 12 }}>
              <div>Lot: <b>{sizing.lot_size}</b></div>
              <div>Cost: <b>₹{(sizing.lot_entry_price || 0).toLocaleString()}</b></div>
              <div>P&L: <span style={{ color: "#22c55e" }}>+₹{(sizing.target_pnl_per_lot || 0).toLocaleString()}</span></div>
            </div>
          </div>
        </div>
      )}

      {/* Context Row */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: 10, fontSize: 10, color: theme.muted,
        padding: "6px 0", borderTop: `1px solid ${theme.border}`, marginBottom: 6,
      }}>
        <span>Regime: <b style={{ color: theme.text }}>{trade.regime}</b></span>
        <span>IV Rank: <b style={{ color: trade.iv_rank > 60 ? "#f59e0b" : theme.text }}>{trade.iv_rank}</b></span>
        <span>PCR: <b style={{ color: trade.pcr > 1.2 ? "#22c55e" : trade.pcr < 0.8 ? "#ef4444" : theme.text }}>
          {typeof trade.pcr === "number" ? trade.pcr.toFixed(2) : trade.pcr}
        </b></span>
        <span>DTE: <b style={{ color: trade.dte <= 3 ? "#ef4444" : theme.text }}>{trade.dte}d</b></span>
        <span>Sector: <b style={{ color: theme.text }}>{trade.sector}</b></span>
        {trade.max_pain && <span>Max Pain: <b>{trade.max_pain}</b></span>}
        {trade.ml_prob != null && (
          <span>ML: <b style={{ color: trade.ml_prob > 0.6 ? "#22c55e" : "#ef4444" }}>
            {(trade.ml_prob * 100).toFixed(0)}%
          </b></span>
        )}
        {trade.bulk_deals > 0 && (
          <span>Bulk Deals: <b style={{ color: "#f59e0b" }}>{trade.bulk_deals}</b></span>
        )}
      </div>

      {/* Time Window + Actions */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        {trade.time_window && (
          <div style={{
            display: "flex", alignItems: "center", gap: 6, fontSize: 10,
            padding: "3px 10px", borderRadius: 12,
            background: `${timeQualityColor(trade.time_window.quality)}11`,
            border: `1px solid ${timeQualityColor(trade.time_window.quality)}33`,
            color: timeQualityColor(trade.time_window.quality),
          }}>
            {timeQualityIcon(trade.time_window.quality)}
            <span style={{ fontWeight: 600 }}>{trade.time_window.quality?.toUpperCase()}</span>
            <span style={{ opacity: 0.8 }}>{trade.time_window.reason}</span>
          </div>
        )}
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <button onClick={() => goChain && goChain(trade.symbol)} style={{
            padding: "4px 12px", borderRadius: 4, fontSize: 10, fontWeight: 600,
            background: "rgba(99,102,241,.1)", color: "#6366f1", border: "1px solid rgba(99,102,241,.3)",
            cursor: "pointer",
          }}>View Chain →</button>
          <button onClick={handlePaperTrade} disabled={tradeStatus === "loading"} style={{
            padding: "4px 12px", borderRadius: 4, fontSize: 10, fontWeight: 600,
            background: tradeStatus === "ok" ? "rgba(34,197,94,.15)" : "rgba(34,197,94,.08)",
            color: tradeStatus === "ok" ? "#22c55e" : tradeStatus === "err" ? "#ef4444" : "#22c55e",
            border: `1px solid ${tradeStatus === "ok" ? "rgba(34,197,94,.4)" : "rgba(34,197,94,.25)"}`,
            cursor: tradeStatus === "loading" ? "wait" : "pointer",
          }}>
            {tradeStatus === "loading" ? "⟳ Adding…" : tradeStatus === "ok" ? "✓ Added" : "📝 Paper Trade"}
          </button>
          {tradeMsg && <span style={{ fontSize: 9, color: tradeStatus === "ok" ? "#22c55e" : "#ef4444" }}>{tradeMsg}</span>}
        </div>
      </div>
    </Card>
  );
}

/* ── Main Tab Component ───────────────────────────────────────────────────── */
export default function FOTradeTab({ theme, goChain }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [filter, setFilter] = useState("ALL");
  const [minConviction, setMinConviction] = useState(55);

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch("/api/fo-trades");
      setData(result);
      setLastRefresh(new Date().toLocaleTimeString("en-IN", { hour12: false }));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTrades(); }, [fetchTrades]);

  const trades = (data?.trades || [])
    .filter(t => filter === "ALL" || t.signal === filter)
    .filter(t => t.conviction >= minConviction);

  const pipeline = data?.pipeline || {};
  const timeWindow = data?.time_window || {};

  const bullish = (data?.trades || []).filter(t => t.signal === "BULLISH").length;
  const bearish = (data?.trades || []).filter(t => t.signal === "BEARISH").length;

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
            🎯 F&O Trade Discovery
          </h2>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>
            Tiered pipeline: Liquidity → Confluence → DTE → Max Pain → Bulk Deals
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Time Window Badge */}
          {timeWindow.quality && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6, fontSize: 11,
              padding: "4px 12px", borderRadius: 6,
              background: `${timeQualityColor(timeWindow.quality)}11`,
              border: `1px solid ${timeQualityColor(timeWindow.quality)}33`,
              color: timeQualityColor(timeWindow.quality), fontWeight: 600,
            }}>
              {timeQualityIcon(timeWindow.quality)} {timeWindow.time} — {timeWindow.quality?.toUpperCase()}
            </div>
          )}
          <button onClick={fetchTrades} disabled={loading} style={{
            padding: "6px 14px", borderRadius: 6, fontSize: 11, fontWeight: 700,
            background: loading ? theme.border : "#6366f1",
            color: "#fff", border: "none", cursor: loading ? "wait" : "pointer",
          }}>
            {loading ? "⟳ Scanning..." : "⟳ Refresh"}
          </button>
          {lastRefresh && <span style={{ fontSize: 9, color: theme.muted }}>Last: {lastRefresh}</span>}
        </div>
      </div>

      {error && (
        <div style={{
          background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.3)",
          borderRadius: 8, padding: 12, marginBottom: 16, color: "#ef4444", fontSize: 12
        }}>⚠ {error}</div>
      )}

      {/* Pipeline Funnel */}
      {pipeline.scanned > 0 && <PipelineFunnel pipeline={pipeline} theme={theme} />}

      {/* Summary Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8, marginBottom: 16 }}>
        <Card theme={theme} style={{ textAlign: "center", padding: 10 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#10b981" }}>{data?.count ?? 0}</div>
          <div style={{ fontSize: 9, color: theme.muted }}>Trades Found</div>
        </Card>
        <Card theme={theme} style={{ textAlign: "center", padding: 10 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#22c55e" }}>{bullish}</div>
          <div style={{ fontSize: 9, color: theme.muted }}>Bullish</div>
        </Card>
        <Card theme={theme} style={{ textAlign: "center", padding: 10 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#ef4444" }}>{bearish}</div>
          <div style={{ fontSize: 9, color: theme.muted }}>Bearish</div>
        </Card>
        <Card theme={theme} style={{ textAlign: "center", padding: 10 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#6366f1" }}>
            {trades.length > 0 ? Math.round(trades.reduce((s, t) => s + t.conviction, 0) / trades.length) : 0}
          </div>
          <div style={{ fontSize: 9, color: theme.muted }}>Avg Conviction</div>
        </Card>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
        {["ALL", "BULLISH", "BEARISH"].map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: "4px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
            background: filter === f ? signalBg(f) : "none",
            color: filter === f ? (f === "ALL" ? theme.accent : signalColor(f)) : theme.muted,
            cursor: "pointer", fontSize: 11, fontWeight: filter === f ? 600 : 400,
          }}>{f}</button>
        ))}
        <span style={{ color: theme.muted, fontSize: 10 }}>Min Conviction:</span>
        <select value={minConviction} onChange={e => setMinConviction(Number(e.target.value))} style={{
          padding: "3px 6px", borderRadius: 4, border: `1px solid ${theme.border}`,
          background: theme.bg, color: theme.text, fontSize: 10, cursor: "pointer",
        }}>
          {[50, 55, 60, 65, 70, 75, 80].map(v => <option key={v} value={v}>{v}+</option>)}
        </select>
        <span style={{ marginLeft: "auto", fontSize: 10, color: theme.muted }}>
          {trades.length} trade{trades.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Loading */}
      {loading && !data && (
        <div style={{ textAlign: "center", padding: 40, color: theme.muted }}>
          <div style={{ fontSize: 24, animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</div>
          <div style={{ marginTop: 8, fontSize: 12 }}>Running discovery pipeline...</div>
        </div>
      )}

      {/* Trade Cards */}
      {!loading && trades.length === 0 && (
        <Card theme={theme} style={{ textAlign: "center", padding: 32 }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
          <div style={{ fontSize: 14, color: theme.muted }}>No trades passed all pipeline filters</div>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 4 }}>
            Try lowering conviction threshold or wait for market hours
          </div>
        </Card>
      )}

      {trades.map((trade, idx) => (
        <TradeCard key={`${trade.symbol}-${idx}`} trade={trade} theme={theme} goChain={goChain} />
      ))}

      {/* Disclaimer */}
      <div style={{
        fontSize: 9, color: theme.muted, textAlign: "center",
        marginTop: 20, padding: "12px 0", borderTop: `1px solid ${theme.border}`, opacity: 0.7,
      }}>
        ⚠ Trades are algorithmically filtered, not financial advice. Always do your own research.
      </div>
    </div>
  );
}
