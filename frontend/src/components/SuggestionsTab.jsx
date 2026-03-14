import { useState, useEffect, useCallback } from "react";

const REFRESH_INTERVAL_MS = 120000; // 2 minutes

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
      <div style={{ marginTop: 8, fontSize: 12 }}>Loading suggestions...</div>
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

function ConvictionMeter({ conviction, label, theme }) {
  const color = conviction >= 85 ? "#22c55e" : conviction >= 70 ? "#f59e0b" : conviction >= 60 ? "#fb923c" : "#ef4444";
  const pct = Math.min(100, conviction);
  return (
    <div style={{ textAlign: "center", minWidth: 64 }}>
      <div style={{ position: "relative", width: 56, height: 56, margin: "0 auto" }}>
        <svg width="56" height="56" viewBox="0 0 60 60">
          <circle cx="30" cy="30" r="25" fill="none" stroke={theme.border} strokeWidth="4" />
          <circle cx="30" cy="30" r="25" fill="none" stroke={color} strokeWidth="4"
            strokeDasharray={`${pct * 1.57} 157`} strokeLinecap="round"
            transform="rotate(-90 30 30)" style={{ transition: "stroke-dasharray 0.5s ease" }} />
        </svg>
        <div style={{
          position: "absolute", top: "50%", left: "50%",
          transform: "translate(-50%, -50%)", fontSize: 15, fontWeight: 700, color
        }}>{conviction}</div>
      </div>
      <div style={{ fontSize: 9, color: theme.muted, fontWeight: 700, marginTop: 4 }}>{label}</div>
    </div>
  );
}

const signalColor = (s) =>
  s === "BULLISH" ? "#22c55e" : s === "BEARISH" ? "#ef4444" : "#94a3b8";
const signalBg = (s) =>
  s === "BULLISH" ? "rgba(34,197,94,.15)" : s === "BEARISH" ? "rgba(239,68,68,.15)" : "rgba(148,163,184,.1)";

function SuggestionCard({ item, theme, goChain }) {
  const strat = item.strategy || {};
  const entry = item.entry || {};
  const rr = item.risk_reward || {};
  const sizing = item.sizing || {};
  const ctx = item.context || {};
  const ml = item.ml || {};
  const tags = item.tags || [];
  const reasons = item.reasons || [];

  const borderColor = item.signal === "BULLISH" ? "rgba(34,197,94,.4)"
    : item.signal === "BEARISH" ? "rgba(239,68,68,.4)" : "rgba(148,163,184,.3)";

  return (
    <Card theme={theme} style={{
      borderLeft: `4px solid ${signalColor(item.signal)}`,
      border: `1px solid ${borderColor}`,
      marginBottom: 12,
      transition: "transform 0.15s, box-shadow 0.15s",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <span style={{ fontSize: 18, fontWeight: 700, color: theme.text }}>{item.symbol}</span>
            <Badge label={item.signal} color={signalColor(item.signal)} bg={signalBg(item.signal)} />
            <Badge label={strat.strategy || "—"} color="#6366f1" bg="rgba(99,102,241,.12)" />
            {strat.risk_type && (
              <Badge
                label={strat.risk_type === "defined" ? "Defined Risk" : "Undefined Risk"}
                color={strat.risk_type === "defined" ? "#22c55e" : "#f59e0b"}
                bg={strat.risk_type === "defined" ? "rgba(34,197,94,.1)" : "rgba(245,158,11,.1)"}
              />
            )}
          </div>
          <div style={{ fontSize: 11, color: theme.muted }}>{strat.description}</div>
        </div>
        <ConvictionMeter conviction={item.conviction} label={item.conviction_label} theme={theme} />
      </div>

      {/* Tags */}
      {tags.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
          {tags.map((tag, i) => (
            <span key={i} style={{
              padding: "2px 8px", borderRadius: 12, fontSize: 10, fontWeight: 600,
              background: "rgba(99,102,241,.08)", color: "#818cf8", border: "1px solid rgba(99,102,241,.2)"
            }}>{tag}</span>
          ))}
        </div>
      )}

      {/* Entry & Risk/Reward Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
        {/* Entry Details */}
        <div style={{ background: "rgba(99,102,241,.05)", borderRadius: 6, padding: 10 }}>
          <div style={{ fontSize: 10, color: theme.muted, fontWeight: 700, marginBottom: 6, textTransform: "uppercase" }}>Entry</div>
          <div style={{ fontSize: 12 }}>
            <div>Strike: <b>{entry.primary_strike} {entry.primary_type}</b></div>
            <div>Premium: <b style={{ color: "#6366f1" }}>₹{entry.entry_premium}</b></div>
            <div>Spot: ₹{entry.spot_at_signal}</div>
          </div>
        </div>

        {/* Risk/Reward */}
        <div style={{ background: "rgba(34,197,94,.05)", borderRadius: 6, padding: 10 }}>
          <div style={{ fontSize: 10, color: theme.muted, fontWeight: 700, marginBottom: 6, textTransform: "uppercase" }}>Risk / Reward</div>
          <div style={{ fontSize: 12 }}>
            <div>R:R → <b style={{ color: "#22c55e" }}>{rr.risk_reward_ratio}</b></div>
            <div>Target: <span style={{ color: "#22c55e" }}>₹{rr.target}</span></div>
            <div>Stop Loss: <span style={{ color: "#ef4444" }}>₹{rr.stop_loss}</span></div>
          </div>
        </div>

        {/* Sizing */}
        <div style={{ background: "rgba(245,158,11,.05)", borderRadius: 6, padding: 10 }}>
          <div style={{ fontSize: 10, color: theme.muted, fontWeight: 700, marginBottom: 6, textTransform: "uppercase" }}>Position</div>
          <div style={{ fontSize: 12 }}>
            <div>Lot Size: <b>{sizing.lot_size}</b></div>
            <div>Capital/Lot: <b>₹{(sizing.capital_per_lot || 0).toLocaleString()}</b></div>
            <div>Max Loss: <span style={{ color: "#ef4444" }}>₹{rr.max_loss}</span></div>
          </div>
        </div>
      </div>

      {/* Market Context Row */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: 12, fontSize: 11, color: theme.muted,
        padding: "8px 0", borderTop: `1px solid ${theme.border}`, marginBottom: 8
      }}>
        <span>Regime: <b style={{ color: theme.text }}>{ctx.regime}</b></span>
        <span>IV: <b style={{ color: theme.text }}>{ctx.iv}%</b></span>
        <span>IVR: <b style={{ color: ctx.iv_rank > 60 ? "#f59e0b" : theme.text }}>{ctx.iv_rank}</b></span>
        <span>PCR: <b style={{ color: ctx.pcr > 1.2 ? "#22c55e" : ctx.pcr < 0.8 ? "#ef4444" : theme.text }}>{ctx.pcr}</b></span>
        <span>DTE: <b style={{ color: ctx.dte <= 3 ? "#ef4444" : theme.text }}>{ctx.dte}d</b></span>
        {ctx.max_pain && <span>Max Pain: <b style={{ color: theme.text }}>{ctx.max_pain}</b></span>}
        {ml.probability != null && (
          <span>ML Prob: <b style={{
            color: ml.probability > 0.6 ? "#22c55e" : ml.probability < 0.4 ? "#ef4444" : theme.text
          }}>{(ml.probability * 100).toFixed(1)}%</b></span>
        )}
      </div>

      {/* Reasons */}
      {reasons.length > 0 && (
        <div style={{ fontSize: 10, color: theme.muted }}>
          {reasons.map((r, i) => (
            <span key={i} style={{ marginRight: 8 }}>{r}</span>
          ))}
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button
          onClick={() => goChain && goChain(item.symbol)}
          style={{
            padding: "4px 12px", borderRadius: 4, fontSize: 10, fontWeight: 600,
            background: "rgba(99,102,241,.1)", color: "#6366f1", border: "1px solid rgba(99,102,241,.3)",
            cursor: "pointer",
          }}
        >View Chain →</button>
      </div>
    </Card>
  );
}

export default function SuggestionsTab({ theme, goChain }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);

  const fetchSuggestions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch("/api/fo-suggestions");
      setData(result);
      setLastRefresh(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSuggestions();
    const id = setInterval(fetchSuggestions, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchSuggestions]);

  if (loading && !data) return <Loader theme={theme} />;

  const suggestions = data?.suggestions || [];
  const mktStatus = data?.market_status || {};

  const bullish = suggestions.filter(s => s.signal === "BULLISH");
  const bearish = suggestions.filter(s => s.signal === "BEARISH");
  const neutral = suggestions.filter(s => s.signal === "NEUTRAL");

  return (
    <div>
      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 16, flexWrap: "wrap", gap: 8
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, display: "flex", alignItems: "center", gap: 8 }}>
            💡 Best F&O Trade Suggestions
          </h2>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>
            AI-powered ranked trade ideas with strategies, risk/reward & conviction scores
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {lastRefresh && <span style={{ fontSize: 10, color: theme.muted }}>Updated: {lastRefresh}</span>}
          <button
            onClick={fetchSuggestions}
            disabled={loading}
            style={{
              padding: "6px 14px", borderRadius: 6, fontSize: 11, fontWeight: 700,
              background: loading ? theme.border : "#6366f1",
              color: "#fff", border: "none", cursor: loading ? "wait" : "pointer"
            }}
          >{loading ? "⟳" : "Refresh"}</button>
        </div>
      </div>

      {error && (
        <div style={{
          background: "rgba(239,68,68,.1)", border: "1px solid rgba(239,68,68,.3)",
          borderRadius: 8, padding: 12, marginBottom: 16, color: "#ef4444", fontSize: 12
        }}>⚠ {error}</div>
      )}

      {/* Summary Stats */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
        gap: 10, marginBottom: 16
      }}>
        <Card theme={theme} style={{ textAlign: "center", padding: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#6366f1" }}>{suggestions.length}</div>
          <div style={{ fontSize: 10, color: theme.muted }}>Total Suggestions</div>
        </Card>
        <Card theme={theme} style={{ textAlign: "center", padding: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#22c55e" }}>{bullish.length}</div>
          <div style={{ fontSize: 10, color: theme.muted }}>Bullish</div>
        </Card>
        <Card theme={theme} style={{ textAlign: "center", padding: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#ef4444" }}>{bearish.length}</div>
          <div style={{ fontSize: 10, color: theme.muted }}>Bearish</div>
        </Card>
        <Card theme={theme} style={{ textAlign: "center", padding: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#94a3b8" }}>{neutral.length}</div>
          <div style={{ fontSize: 10, color: theme.muted }}>Neutral</div>
        </Card>
        <Card theme={theme} style={{ textAlign: "center", padding: 12 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: mktStatus.open ? "#22c55e" : "#ef4444" }}>
            {mktStatus.open ? "OPEN" : "CLOSED"}
          </div>
          <div style={{ fontSize: 10, color: theme.muted }}>Market</div>
        </Card>
      </div>

      {/* Suggestions List */}
      {suggestions.length === 0 ? (
        <Card theme={theme} style={{ textAlign: "center", padding: 32 }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📊</div>
          <div style={{ fontSize: 14, color: theme.muted }}>
            No trade suggestions available right now.
          </div>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 4 }}>
            Suggestions are generated when scan finds stocks with score ≥ 60
          </div>
        </Card>
      ) : (
        suggestions.map((item, idx) => (
          <SuggestionCard key={`${item.symbol}-${idx}`} item={item} theme={theme} goChain={goChain} />
        ))
      )}

      {/* Disclaimer */}
      <div style={{
        fontSize: 9, color: theme.muted, textAlign: "center",
        marginTop: 20, padding: "12px 0", borderTop: `1px solid ${theme.border}`,
        opacity: 0.7
      }}>
        ⚠ Suggestions are for informational purposes only. Not financial advice. Always do your own research before trading.
      </div>
    </div>
  );
}
