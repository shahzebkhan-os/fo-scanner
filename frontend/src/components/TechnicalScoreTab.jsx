import { useState, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, RadarChart, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, Radar
} from "recharts";

// ── Helpers ──────────────────────────────────────────────────────────────────
async function apiFetch(path) {
  const r = await fetch(path);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${r.status}`);
  }
  return r.json();
}

function Loader({ theme }) {
  return (
    <div style={{ textAlign: "center", padding: 40, color: theme.muted }}>
      <div style={{ fontSize: 24, animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</div>
      <div style={{ marginTop: 8, fontSize: 12 }}>Analysing indicators...</div>
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

const signalColor = (s) =>
  s === "BULLISH" ? "#22c55e" : s === "BEARISH" ? "#ef4444" : "#94a3b8";
const signalBg = (s) =>
  s === "BULLISH" ? "rgba(34,197,94,.15)" : s === "BEARISH" ? "rgba(239,68,68,.15)" : "rgba(148,163,184,.1)";

const POPULAR_SYMBOLS = [
  "NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "INFY", "HDFCBANK",
  "ICICIBANK", "SBIN", "BAJFINANCE", "TATAMOTORS", "ITC",
  "AXISBANK", "LT", "HINDUNILVR", "BHARTIARTL", "KOTAKBANK",
  "TATASTEEL", "HCLTECH", "WIPRO", "MARUTI",
];

// Indicator display config: friendly names, icons, descriptions
const INDICATOR_META = {
  rsi:           { label: "RSI (14)",        icon: "📈", desc: "Relative Strength Index — momentum oscillator (overbought >70, oversold <30)" },
  macd:          { label: "MACD",            icon: "〰️",  desc: "Moving Average Convergence Divergence — trend + momentum crossover" },
  adx:           { label: "ADX",             icon: "💪", desc: "Average Directional Index — trend strength (+DI vs −DI)" },
  stochastic:    { label: "Stochastic",      icon: "🔄", desc: "Stochastic %K/%D — overbought/oversold oscillator" },
  ema_alignment: { label: "EMA Alignment",   icon: "📊", desc: "EMA 9/21/50 stack — multi-timeframe trend consensus" },
  bollinger:     { label: "Bollinger %B",    icon: "📐", desc: "Bollinger Bands — volatility + mean-reversion context" },
  volume:        { label: "Volume",          icon: "📢", desc: "Volume ratio vs 20-bar average — move confirmation" },
  vwap:          { label: "VWAP",            icon: "⚖️",  desc: "Volume-Weighted Average Price deviation — institutional interest" },
};

const WEIGHT_LABELS = {
  rsi: "15%", macd: "20%", adx: "15%", stochastic: "10%",
  ema_alignment: "15%", bollinger: "10%", volume: "10%", vwap: "5%",
};

// ── Score Gauge ──────────────────────────────────────────────────────────────
function ScoreGauge({ score, direction, confidence, theme }) {
  const color = direction === "BULLISH" ? "#22c55e" : direction === "BEARISH" ? "#ef4444" : "#94a3b8";
  const pctValue = Math.min(100, Math.max(0, score));
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (pctValue / 100) * circumference;

  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ position: "relative", width: 120, height: 120, margin: "0 auto" }}>
        <svg width="120" height="120" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="40" fill="none" stroke={theme.border} strokeWidth="8" />
          <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="8"
            strokeDasharray={circumference} strokeDashoffset={offset}
            strokeLinecap="round" transform="rotate(-90 50 50)"
            style={{ transition: "stroke-dashoffset 0.8s ease" }} />
        </svg>
        <div style={{
          position: "absolute", top: "50%", left: "50%",
          transform: "translate(-50%, -50%)", textAlign: "center"
        }}>
          <div style={{ fontSize: 28, fontWeight: 800, color }}>{score}</div>
          <div style={{ fontSize: 9, color: theme.muted }}>/ 100</div>
        </div>
      </div>
      <div style={{
        marginTop: 8, padding: "4px 14px", borderRadius: 20, display: "inline-block",
        fontWeight: 700, fontSize: 13, color, background: signalBg(direction),
      }}>
        {direction === "BULLISH" ? "▲" : direction === "BEARISH" ? "▼" : "◆"} {direction}
      </div>
      <div style={{ marginTop: 6, fontSize: 11, color: theme.muted }}>
        Confidence: <span style={{ fontWeight: 700, color: theme.text }}>{fmt(confidence * 100, 1)}%</span>
      </div>
    </div>
  );
}

// ── Indicator Card ───────────────────────────────────────────────────────────
function IndicatorCard({ name, data, subScore, theme }) {
  const meta = INDICATOR_META[name] || { label: name, icon: "•", desc: "" };
  const weight = WEIGHT_LABELS[name] || "";
  const barPct = Math.min(100, Math.max(0, subScore));
  const barColor = barPct >= 70 ? "#22c55e" : barPct >= 50 ? "#f59e0b" : barPct >= 30 ? "#fb923c" : "#ef4444";

  return (
    <Card theme={theme} style={{ padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 16 }}>{meta.icon}</span>
          <span style={{ fontWeight: 700, fontSize: 13 }}>{meta.label}</span>
          <span style={{ fontSize: 10, color: theme.muted, fontStyle: "italic" }}>({weight})</span>
        </div>
        <span style={{
          fontWeight: 800, fontSize: 16,
          color: barColor,
        }}>
          {fmt(subScore, 1)}
        </span>
      </div>
      {/* Progress bar */}
      <div style={{
        height: 6, borderRadius: 3, background: theme.border, overflow: "hidden", marginBottom: 8
      }}>
        <div style={{
          height: "100%", borderRadius: 3, background: barColor,
          width: `${barPct}%`, transition: "width 0.6s ease"
        }} />
      </div>
      {/* Indicator details */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {Object.entries(data || {}).map(([k, v]) => (
          <div key={k} style={{
            padding: "2px 8px", borderRadius: 4, fontSize: 11,
            background: theme.bg, border: `1px solid ${theme.border}`,
          }}>
            <span style={{ color: theme.muted }}>{k}: </span>
            <span style={{ fontWeight: 600 }}>{typeof v === "number" ? fmt(v, 2) : String(v)}</span>
          </div>
        ))}
      </div>
      <div style={{ fontSize: 10, color: theme.muted, marginTop: 6 }}>{meta.desc}</div>
    </Card>
  );
}

// ── Main Tab Component ───────────────────────────────────────────────────────
export default function TechnicalScoreTab({ theme }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [inputVal, setInputVal] = useState("NIFTY");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const analyse = useCallback(async (sym) => {
    const s = (sym || symbol).toUpperCase().trim();
    if (!s) return;
    setSymbol(s);
    setInputVal(s);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await apiFetch(`/api/score-technical/${s}`);
      setResult(data);
    } catch (e) {
      setError(e.message || "Failed to fetch");
    }
    setLoading(false);
  }, [symbol]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter") analyse(inputVal);
  };

  // Prepare chart data
  const radarData = result ? Object.entries(result.technical_score.sub_scores).map(([k, v]) => ({
    indicator: (INDICATOR_META[k]?.label || k).replace(/ \([^)]+\)/, ""),
    score: v,
    fullMark: 100,
  })) : [];

  const barData = result ? Object.entries(result.technical_score.sub_scores).map(([k, v]) => ({
    name: (INDICATOR_META[k]?.label || k).replace(/ \([^)]+\)/, ""),
    score: v,
    weight: parseFloat(WEIGHT_LABELS[k]) || 0,
  })) : [];

  const tech = result?.technical_score;
  const existing = result?.existing_score;

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8 }}>
        <div>
          <h2 style={{ fontSize: 18, margin: 0 }}>📊 Technical Score</h2>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>
            RSI · MACD · ADX · Stochastic · EMA · Bollinger · Volume · VWAP
          </div>
        </div>

        {/* Search */}
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value.toUpperCase())}
            onKeyDown={handleKeyDown}
            placeholder="Symbol..."
            style={{
              padding: "7px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
              background: theme.bg, color: theme.text, fontFamily: "inherit", fontSize: 13,
              width: 130, outline: "none",
            }}
          />
          <button
            onClick={() => analyse(inputVal)}
            disabled={loading}
            style={{
              padding: "7px 16px", borderRadius: 6, background: theme.accent, color: "#fff",
              border: "none", cursor: loading ? "wait" : "pointer", fontWeight: 600, fontSize: 13,
            }}
          >
            {loading ? "⟳" : "Analyse"}
          </button>
        </div>
      </div>

      {/* Quick-pick buttons */}
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 16 }}>
        {POPULAR_SYMBOLS.map(s => (
          <button key={s} onClick={() => analyse(s)}
            disabled={loading}
            style={{
              padding: "3px 10px", borderRadius: 4, border: `1px solid ${theme.border}`,
              background: symbol === s ? theme.accent : theme.card,
              color: symbol === s ? "#fff" : theme.muted,
              cursor: "pointer", fontSize: 11, fontWeight: symbol === s ? 700 : 400,
              fontFamily: "inherit", transition: "all 0.15s",
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading && <Loader theme={theme} />}

      {/* Error */}
      {error && (
        <Card theme={theme} style={{ textAlign: "center", padding: 24, color: theme.red || "#ef4444" }}>
          <div style={{ fontSize: 20, marginBottom: 6 }}>⚠</div>
          <div style={{ fontWeight: 600 }}>{error}</div>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 4 }}>
            Make sure the backend is running and yfinance is installed.
          </div>
        </Card>
      )}

      {/* Results */}
      {!loading && !error && result && tech && (
        <div style={{ animation: "fadeIn 0.3s ease" }}>

          {/* Top row: Score Gauge + Comparison + Summary */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>

            {/* Score Gauge */}
            <Card theme={theme} style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 24 }}>
              <div style={{ fontSize: 11, color: theme.muted, marginBottom: 8, fontWeight: 600 }}>TECHNICAL SCORE</div>
              <ScoreGauge score={tech.score} direction={tech.direction} confidence={tech.confidence} theme={theme} />
              <div style={{ fontSize: 10, color: theme.muted, marginTop: 10 }}>
                {result.bars_used} price bars analysed
              </div>
            </Card>

            {/* Comparison */}
            <Card theme={theme} style={{ padding: 24 }}>
              <div style={{ fontSize: 11, color: theme.muted, marginBottom: 12, fontWeight: 600 }}>MODEL COMPARISON</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {/* Technical model */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 12 }}>📊 Technical (new)</span>
                    <span style={{ fontWeight: 800, color: signalColor(tech.direction) }}>{tech.score}</span>
                  </div>
                  <div style={{ height: 8, borderRadius: 4, background: theme.border, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 4, background: signalColor(tech.direction),
                      width: `${tech.score}%`, transition: "width 0.6s ease"
                    }} />
                  </div>
                  <div style={{ fontSize: 10, color: signalColor(tech.direction), fontWeight: 600, marginTop: 2 }}>
                    {tech.direction} • {fmt(tech.confidence * 100, 0)}% conf
                  </div>
                </div>
                {/* OI-based model */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 12 }}>⚡ OI/IV/Greeks (current)</span>
                    <span style={{ fontWeight: 800, color: existing ? signalColor(existing.signal) : theme.muted }}>
                      {existing ? existing.score : "—"}
                    </span>
                  </div>
                  <div style={{ height: 8, borderRadius: 4, background: theme.border, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 4,
                      background: existing ? signalColor(existing.signal) : theme.muted,
                      width: `${existing ? existing.score : 0}%`, transition: "width 0.6s ease"
                    }} />
                  </div>
                  <div style={{ fontSize: 10, color: existing ? signalColor(existing.signal) : theme.muted, fontWeight: 600, marginTop: 2 }}>
                    {existing ? `${existing.signal} • ${fmt((existing.confidence || 0) * 100, 0)}% conf` : "Chain data unavailable"}
                  </div>
                </div>
                {/* Agreement */}
                {existing && (
                  <div style={{
                    textAlign: "center", padding: "6px 0", borderTop: `1px solid ${theme.border}`,
                    fontSize: 11, marginTop: 4,
                  }}>
                    {tech.direction === existing.signal ? (
                      <span style={{ color: "#22c55e", fontWeight: 700 }}>✓ Both models agree: {tech.direction}</span>
                    ) : (
                      <span style={{ color: "#f59e0b", fontWeight: 700 }}>⚠ Models diverge: {tech.direction} vs {existing.signal}</span>
                    )}
                  </div>
                )}
              </div>
            </Card>

            {/* Reasons / Signals */}
            <Card theme={theme} style={{ padding: 24 }}>
              <div style={{ fontSize: 11, color: theme.muted, marginBottom: 12, fontWeight: 600 }}>SIGNAL REASONS</div>
              {tech.reasons && tech.reasons.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {tech.reasons.map((r, i) => (
                    <div key={i} style={{
                      fontSize: 11, padding: "5px 10px", borderRadius: 4,
                      background: theme.bg, border: `1px solid ${theme.border}`,
                      lineHeight: 1.4,
                    }}>
                      {r}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: theme.muted, fontSize: 12, textAlign: "center", padding: 20 }}>
                  No strong signals detected
                </div>
              )}
            </Card>
          </div>

          {/* Charts row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            {/* Radar Chart */}
            <Card theme={theme}>
              <div style={{ fontSize: 11, color: theme.muted, marginBottom: 8, fontWeight: 600 }}>INDICATOR RADAR</div>
              <ResponsiveContainer width="100%" height={280}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke={theme.border} />
                  <PolarAngleAxis dataKey="indicator" tick={{ fill: theme.muted, fontSize: 10 }} />
                  <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: theme.muted, fontSize: 9 }} />
                  <Radar name="Score" dataKey="score" stroke={theme.accent} fill={theme.accent} fillOpacity={0.25} strokeWidth={2} />
                </RadarChart>
              </ResponsiveContainer>
            </Card>

            {/* Bar Chart */}
            <Card theme={theme}>
              <div style={{ fontSize: 11, color: theme.muted, marginBottom: 8, fontWeight: 600 }}>SUB-SCORE BREAKDOWN</div>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={barData} layout="vertical" margin={{ left: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                  <XAxis type="number" domain={[0, 100]} tick={{ fill: theme.muted, fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" tick={{ fill: theme.muted, fontSize: 10 }} width={58} />
                  <Tooltip
                    contentStyle={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 11 }}
                    formatter={(v) => [fmt(v, 1), "Score"]}
                  />
                  <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={18}>
                    {barData.map((entry, i) => (
                      <Cell key={i} fill={entry.score >= 70 ? "#22c55e" : entry.score >= 50 ? "#f59e0b" : entry.score >= 30 ? "#fb923c" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          {/* Indicator detail cards */}
          <div style={{ fontSize: 11, color: theme.muted, marginBottom: 8, fontWeight: 600 }}>INDICATOR DETAILS</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            {Object.entries(tech.sub_scores).map(([name, subScore]) => (
              <IndicatorCard
                key={name}
                name={name}
                data={tech.indicators[name]}
                subScore={subScore}
                theme={theme}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && !result && (
        <Card theme={theme} style={{ textAlign: "center", padding: 40 }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>📊</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Technical Indicator Score</div>
          <div style={{ fontSize: 12, color: theme.muted, maxWidth: 420, margin: "0 auto", lineHeight: 1.6 }}>
            Select a symbol above or type one in to compute a technical score
            using 8 classical indicators. Results are compared side-by-side with the
            existing OI/IV/Greeks model.
          </div>
        </Card>
      )}
    </div>
  );
}
