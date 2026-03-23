import { useState, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, RadarChart, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, Radar
} from "recharts";

// Add CSS for direction pulse animation
const styleElement = document.createElement('style');
styleElement.textContent = `
  @keyframes directionPulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.95; transform: scale(1.01); }
  }
`;
if (!document.head.querySelector('style[data-tech-score-animations]')) {
  styleElement.setAttribute('data-tech-score-animations', 'true');
  document.head.appendChild(styleElement);
}

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
  "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX", "INDIAVIX",
  "NIFTYIT", "NIFTYAUTO", "NIFTYFMCG", "NIFTYPHARMA", "NIFTYMETAL", "NIFTYENERGY", "NIFTYPSUBANK",
  "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE", 
  "TATAMOTORS", "ITC", "AXISBANK", "LT", "HINDUNILVR", "BHARTIARTL", "KOTAKBANK",
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
        Confidence: <span style={{ fontWeight: 700, color: color }}>{fmt(confidence * 100, 1)}%</span>
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

// ── Directional Banner (Hero Element) ───────────────────────────────────────
function DirectionalBanner({ tech, theme }) {
  if (!tech) return null;

  const direction = tech.direction;
  const strength = tech.direction_strength;
  const edge = tech.directional_edge || 0;
  const agreement = tech.agreement_pct || 0;

  const isStrong = strength === "STRONG";
  const isWeak = strength === "WEAK";
  const isSideways = strength === "SIDEWAYS";
  const isBullish = direction === "BULLISH";
  const isBearish = direction === "BEARISH";

  const baseColor = isBullish ? "#22c55e" : isBearish ? "#ef4444" : "#94a3b8";
  const bgColor = isBullish
    ? (isStrong ? "rgba(34,197,94,0.15)" : "rgba(34,197,94,0.08)")
    : isBearish
    ? (isStrong ? "rgba(239,68,68,0.15)" : "rgba(239,68,68,0.08)")
    : "rgba(148,163,184,0.05)";

  const arrowIcon = isBullish ? "▲▲▲" : isBearish ? "▼▼▼" : "◆◆◆";
  const emoji = isBullish ? "🚀" : isBearish ? "📉" : isStrong ? "➡️" : "〰️";

  const message = isStrong
    ? (isBullish ? "Strong Uptrend Detected" : isBearish ? "Strong Downtrend Detected" : "Strong Sideways Action")
    : isWeak
    ? (isBullish ? "Weak Bullish Bias" : isBearish ? "Weak Bearish Bias" : "Weak Direction")
    : "Consolidating / No Clear Direction";

  return (
    <div style={{
      background: bgColor,
      border: `3px solid ${baseColor}`,
      borderRadius: 12,
      padding: "24px",
      marginBottom: 20,
      textAlign: "center",
      animation: isStrong ? "directionPulse 2s ease-in-out infinite" : "none",
      boxShadow: isStrong ? `0 0 20px ${baseColor}30` : "none"
    }}>
      <div style={{
        fontSize: 48,
        fontWeight: 900,
        color: baseColor,
        letterSpacing: 4,
        marginBottom: 12,
        textShadow: isStrong ? `0 0 10px ${baseColor}60` : "none"
      }}>
        {arrowIcon}
      </div>
      <div style={{ fontSize: 40, fontWeight: 900, color: baseColor, marginBottom: 8, letterSpacing: 1 }}>
        {direction} {emoji}
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, color: theme.text, marginBottom: 16, opacity: 0.9 }}>
        {message}
      </div>
      <div style={{ display: "flex", justifyContent: "center", gap: 24, fontSize: 14, flexWrap: "wrap" }}>
        <div>
          <span style={{ color: theme.muted }}>Directional Edge: </span>
          <b style={{ color: baseColor }}>{(edge * 100).toFixed(1)}%</b>
        </div>
        <div>
          <span style={{ color: theme.muted }}>Agreement: </span>
          <b style={{ color: baseColor }}>{(agreement * 100).toFixed(0)}%</b>
        </div>
        <div>
          <span style={{ color: theme.muted }}>Strength: </span>
          <b style={{ color: baseColor }}>{strength}</b>
        </div>
      </div>
    </div>
  );
}

// ── Timeframe Consensus ──────────────────────────────────────────────────────
function TimeframeConsensus({ consensus, theme }) {
  if (!consensus) return null;

  const allAgree = consensus.all_agree;
  const strength = consensus.consensus_strength;
  const majorityDir = consensus.majority_direction;

  const bgColor = allAgree
    ? "rgba(34,197,94,0.1)"
    : strength >= 0.66
    ? "rgba(251,146,60,0.1)"
    : "rgba(239,68,68,0.1)";

  const borderColor = allAgree ? "#22c55e" : strength >= 0.66 ? "#f59e0b" : "#ef4444";
  const icon = allAgree ? "✓✓✓" : strength >= 0.66 ? "⚠" : "✗";
  const signalColor = majorityDir === "BULLISH" ? "#22c55e" : majorityDir === "BEARISH" ? "#ef4444" : "#94a3b8";

  return (
    <Card theme={theme} style={{ background: bgColor, border: `2px solid ${borderColor}`, padding: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, marginBottom: 12 }}>
        TIMEFRAME CONSENSUS
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginBottom: 12 }}>
        <div style={{ fontSize: 28, fontWeight: 800 }}>{icon}</div>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800, color: signalColor }}>{majorityDir}</div>
          <div style={{ fontSize: 11, color: theme.muted }}>
            <b>{(strength * 100).toFixed(0)}%</b> agreement
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "center", marginBottom: 12 }}>
        {["5m", "15m", "30m"].map(tf => {
          const aligned = consensus.timeframes_aligned.includes(tf);
          const tfDir = consensus.detail[tf];
          const tfColor = tfDir === "BULLISH" ? "#22c55e" : tfDir === "BEARISH" ? "#ef4444" : "#94a3b8";
          return (
            <div key={tf} style={{
              padding: "6px 12px", borderRadius: 6,
              background: aligned ? tfColor : theme.border,
              color: aligned ? "#fff" : theme.muted,
              fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", gap: 4
            }}>
              {tf} {aligned && <span>✓</span>}
            </div>
          );
        })}
      </div>
      {consensus.divergence_warning && (
        <div style={{
          padding: 8, background: "rgba(239,68,68,0.1)", borderRadius: 6,
          fontSize: 11, color: "#ef4444", fontWeight: 600, textAlign: "center",
          border: "1px solid rgba(239,68,68,0.3)"
        }}>
          ⚠ WARNING: All timeframes show different directions - wait for alignment
        </div>
      )}
      {allAgree && (
        <div style={{
          padding: 8, background: "rgba(34,197,94,0.1)", borderRadius: 6,
          fontSize: 11, color: "#22c55e", fontWeight: 600, textAlign: "center",
          border: "1px solid rgba(34,197,94,0.3)"
        }}>
          ✓✓✓ All timeframes aligned - high conviction setup
        </div>
      )}
    </Card>
  );
}

// ── Trend Strength Meter ─────────────────────────────────────────────────────
function TrendStrengthMeter({ adx, plusDI, minusDI, theme }) {
  if (!adx) return null;

  const level = adx < 15 ? "NO TREND" : adx < 25 ? "EMERGING" : adx < 40 ? "STRONG" : adx < 60 ? "VERY STRONG" : "EXTREME";
  const color = adx < 15 ? "#94a3b8" : adx < 25 ? "#f59e0b" : adx < 40 ? "#22c55e" : adx < 60 ? "#10b981" : "#059669";
  const barPct = Math.min(100, (adx / 60) * 100);

  const advice = adx < 15
    ? "⚠ Avoid directional trades - market is choppy"
    : adx < 25
    ? "📊 Trend developing - watch for continuation"
    : adx < 40
    ? "✓ Good trending environment - trade with confidence"
    : "✓✓ Exceptional trend strength - ride the move";

  const bullishDI = plusDI > minusDI;
  const diSpread = Math.abs(plusDI - minusDI);

  return (
    <Card theme={theme} style={{ padding: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, marginBottom: 12 }}>
        TREND STRENGTH (ADX)
      </div>
      <div style={{
        fontSize: 48, fontWeight: 900, color: color, marginBottom: 12, textAlign: "center",
        textShadow: adx >= 40 ? `0 0 10px ${color}40` : "none"
      }}>
        {adx.toFixed(0)}
      </div>
      <div style={{
        height: 14, background: theme.border, borderRadius: 7, overflow: "hidden",
        marginBottom: 12, position: "relative"
      }}>
        <div style={{
          height: "100%", background: `linear-gradient(to right, ${color}, ${color}dd)`,
          width: `${barPct}%`, transition: "width 0.8s ease",
          boxShadow: adx >= 40 ? `0 0 8px ${color}60` : "none"
        }} />
        <div style={{ position: "absolute", left: "25%", top: 0, bottom: 0, width: 2, background: "rgba(0,0,0,0.2)" }} />
        <div style={{ position: "absolute", left: "41.67%", top: 0, bottom: 0, width: 2, background: "rgba(0,0,0,0.2)" }} />
      </div>
      <div style={{ fontSize: 16, fontWeight: 800, color: color, textAlign: "center", marginBottom: 12, letterSpacing: 1 }}>
        {level}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12, fontSize: 12 }}>
        <div style={{ color: "#22c55e", fontWeight: bullishDI ? 700 : 600, opacity: bullishDI ? 1 : 0.6 }}>
          +DI: {plusDI.toFixed(1)}{bullishDI && diSpread > 10 && " ↑"}
        </div>
        <div style={{ color: "#ef4444", fontWeight: !bullishDI ? 700 : 600, opacity: !bullishDI ? 1 : 0.6 }}>
          -DI: {minusDI.toFixed(1)}{!bullishDI && diSpread > 10 && " ↓"}
        </div>
      </div>
      <div style={{
        fontSize: 11, color: theme.text, textAlign: "center", padding: 10,
        background: theme.bg, borderRadius: 6, lineHeight: 1.4, border: `1px solid ${theme.border}`
      }}>
        {advice}
      </div>
    </Card>
  );
}

// ── Main Tab Component ───────────────────────────────────────────────────────
export default function TechnicalScoreTab({ theme, scanData }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [inputVal, setInputVal] = useState("NIFTY");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sortIndicators, setSortIndicators] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchProgress, setBatchProgress] = useState(0);
  const [batchResults, setBatchResults] = useState([]);
  const [selectedTF, setSelectedTF] = useState("15m");

  // ... (skipped some unchanged lines handling effects and api)

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

  const tech = result?.timeframes ? result.timeframes[selectedTF] : result?.technical_score;
  const existing = result?.existing_score;
  const hasExistingScore = existing?.score != null;
  const indicatorEntries = tech ? Object.entries(tech.sub_scores) : [];
  const sortedIndicatorEntries = sortIndicators
    ? [...indicatorEntries].sort((a, b) => b[1] - a[1])
    : indicatorEntries;
  const blendedDenominator = hasExistingScore ? 2 : 1;
  const blendedScore = tech ? Math.round((tech.score + (hasExistingScore ? existing.score : 0)) / blendedDenominator) : null;

  const loadAll = async () => {
    if (batchLoading) return;
    if (!window.confirm("This will fetch technical scores for all popular symbols. It may take a minute. Continue?")) return;
    
    setBatchLoading(true);
    setBatchProgress(0);
    const results = [];
    
    for (let i = 0; i < POPULAR_SYMBOLS.length; i++) {
      const sym = POPULAR_SYMBOLS[i];
      try {
        const data = await apiFetch(`/api/score-technical/${sym}`);
        results.push({ symbol: sym, data });
      } catch (e) {
        console.error(`Failed to load ${sym}:`, e);
      }
      setBatchProgress(i + 1);
    }
    
    setBatchResults(results);
    setBatchLoading(false);
  };

  const exportBatchExcel = () => {
    if (batchResults.length === 0) return;
    const cols = ["Symbol", "Final Blended Score", "Technical Score", "Direction", "Confidence", "Existing Score", "Existing Signal"];
    const rowsHtml = batchResults.map(b => {
      const bTech = b.data?.technical_score;
      const bExist = b.data?.existing_score;
      const bHasExist = bExist?.score != null;
      const bBlended = bTech ? Math.round((bTech.score + (bHasExist ? bExist.score : 0)) / (bHasExist ? 2 : 1)) : "";
      
      const r = [
        b.symbol, 
        bBlended,
        bTech?.score ?? "",
        bTech?.direction ?? "",
        bTech?.confidence ? `${fmt(bTech.confidence * 100, 1)}%` : "",
        bExist?.score ?? "",
        bExist?.signal ?? ""
      ];
      return `<tr>${r.map(c => `<td style="border:1px solid #ccc;padding:4px;">${c}</td>`).join("")}</tr>`;
    }).join("");
    
    const table = `
      <table style="border-collapse:collapse;font-family:sans-serif;font-size:12px;">
        <thead><tr>${cols.map(c => `<th style="border:1px solid #ccc;padding:6px;text-align:left;">${c}</th>`).join("")}</tr></thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    `;
    const blob = new Blob([table], { type: "application/vnd.ms-excel" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `technical_score_batch_${new Date().toISOString()}.xls`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportTechExcel = () => {
    if (!tech) return;
    const cols = ["Symbol", "Final Score", "Technical Score", "Direction", "Confidence", "Existing Score", "Existing Signal"];
    const rows = [[
      symbol,
      blendedScore ?? "",
      tech.score,
      tech.direction,
      `${fmt((tech.confidence || 0) * 100, 1)}%`,
      existing?.score ?? "",
      existing?.signal ?? "",
    ]];
    const indicatorRows = sortedIndicatorEntries
      .map(([k, v]) => [INDICATOR_META[k]?.label || k, fmt(v, 1), WEIGHT_LABELS[k] || "", JSON.stringify(tech.indicators[k] || {})]);

    const summaryHeader = `<tr>${cols.map(c => `<th style="border:1px solid #ccc;padding:6px;text-align:left;">${c}</th>`).join("")}</tr>`;
    const summaryBody = rows.map(r => `<tr>${r.map(c => `<td style="border:1px solid #ccc;padding:4px;">${c}</td>`).join("")}</tr>`).join("");
    const indicatorHeader = `<tr>${["Indicator", "Score", "Weight", "Details"].map(c => `<th style="border:1px solid #ccc;padding:6px;text-align:left;">${c}</th>`).join("")}</tr>`;
    const indicatorBody = indicatorRows.map(r => `<tr>${r.map(c => `<td style="border:1px solid #ccc;padding:4px;">${c}</td>`).join("")}</tr>`).join("");
    const table = `
      <table style="border-collapse:collapse;font-family:sans-serif;font-size:12px;margin-bottom:12px;">
        <thead>${summaryHeader}</thead>
        <tbody>${summaryBody}</tbody>
      </table>
      <table style="border-collapse:collapse;font-family:sans-serif;font-size:12px;">
        <thead>${indicatorHeader}</thead>
        <tbody>${indicatorBody}</tbody>
      </table>
    `;
    const blob = new Blob([table], { type: "application/vnd.ms-excel" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `technical_score_${symbol}_${new Date().toISOString()}.xls`;
    a.click();
    URL.revokeObjectURL(url);
  };

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
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
        {POPULAR_SYMBOLS.map(s => {
          const bRes = batchResults.find(b => b.symbol === s);
          const sData = bRes && bRes.data.technical_score ? {
            signal: bRes.data.technical_score.direction,
            confidence: bRes.data.technical_score.confidence
          } : scanData?.find(r => r.symbol === s);
          
          const sig = sData?.signal || "NEUTRAL";
          const conf = sData?.confidence ? `${fmt(sData.confidence * 100, 0)}%` : "";
          const isBull = sig === "BULLISH";
          const isBear = sig === "BEARISH";
          const btnColor = isBull ? (theme.green || "#22c55e") : isBear ? (theme.red || "#ef4444") : theme.muted;
          const bg = symbol === s ? btnColor : theme.card;
          const textCol = symbol === s ? "#fff" : btnColor;

          return (
            <button key={s} onClick={() => analyse(s)}
              disabled={loading}
              style={{
                padding: "4px 10px", borderRadius: 4, border: `1px solid ${symbol === s ? btnColor : theme.border}`,
                background: bg,
                color: textCol,
                cursor: "pointer", fontSize: 11, fontWeight: symbol === s ? 700 : 600,
                fontFamily: "inherit", transition: "all 0.15s",
                display: "flex", alignItems: "center", gap: 6
              }}
            >
              {s}
              {conf && (
                <span style={{ fontSize: 9, opacity: 0.9, backgroundColor: "rgba(0,0,0,0.1)", padding: "1px 4px", borderRadius: 4 }}>
                  {conf}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12, flexWrap: "wrap", justifyContent: "space-between" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: 11, color: theme.muted, display: "flex", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={sortIndicators} onChange={() => setSortIndicators(v => !v)} />
            Sort indicators by score
          </label>
          <button
            onClick={exportTechExcel}
          disabled={!tech}
          style={{
            padding: "6px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
            background: tech ? "rgba(99,102,241,.1)" : theme.border,
            color: tech ? "#6366f1" : theme.muted,
            fontSize: 11, fontWeight: 700, cursor: tech ? "pointer" : "not-allowed",
          }}
        >
          ↓ Export Excel
        </button>
      </div>
        <button
          onClick={loadAll}
          disabled={batchLoading}
          style={{
             padding: "6px 16px", borderRadius: 6, border: `1px solid ${theme.border}`,
             background: batchLoading ? theme.border : theme.card,
             color: theme.text,
             fontSize: 11, fontWeight: 700, 
             cursor: batchLoading ? "default" : "pointer",
             position: "relative",
             overflow: "hidden"
          }}
        >
          {batchLoading && (
            <div style={{
              position: "absolute", top: 0, left: 0, height: "100%",
              background: "rgba(34,197,94,0.15)",
              width: `${(batchProgress / POPULAR_SYMBOLS.length) * 100}%`,
              transition: "width 0.3s ease", zIndex: 0
            }} />
          )}
          <span style={{ position: "relative", zIndex: 1 }}>
            {batchLoading ? `Loading... ${batchProgress} / ${POPULAR_SYMBOLS.length}` : "⚡ Load All Quick-Picks"}
          </span>
        </button>
      </div>

      {/* Loading */}
      {loading && <Loader theme={theme} />}

      {/* Error */}
      {error && (
        <Card theme={theme} style={{ textAlign: "center", padding: 24, color: theme.red || "#ef4444" }}>
          <div style={{ fontSize: 20, marginBottom: 6 }}>⚠</div>
          <div style={{ fontWeight: 600 }}>{error}</div>
        </Card>
      )}
      {/* Multi-Timeframe UI */}
      {result && result.timeframes && (
        <Card theme={theme} style={{ padding: "16px 20px", marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, marginBottom: 16 }}>MULTI-TIMEFRAME TREND</div>
          <div style={{ display: "flex", gap: 12, justifyContent: "space-around", flexWrap: "wrap" }}>
            {["5m", "15m", "30m"].map(tf => {
              const d = result.timeframes[tf];
              if (!d) return null;
              const isSel = selectedTF === tf;
              return (
                <div key={tf} 
                  onClick={() => setSelectedTF(tf)}
                  style={{
                    flex: 1, minWidth: 90, textAlign: "center", padding: "12px", 
                    borderRadius: 8, border: `2px solid ${isSel ? theme.accent : theme.border}`,
                    background: isSel ? "rgba(99,102,241,.05)" : theme.bg,
                    cursor: "pointer", transition: "all 0.15s"
                  }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: theme.muted }}>{tf} TIMEFRAME</div>
                  <div style={{ fontSize: 22, fontWeight: 800, color: signalColor(d.direction), margin: "6px 0" }}>{d.score}</div>
                  <div style={{ fontSize: 10, fontWeight: 700, color: signalColor(d.direction), background: signalBg(d.direction), display: "inline-block", padding: "2px 8px", borderRadius: 12 }}>{d.direction}</div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Results */}
      {result && tech && (
        <div style={{ animation: "fadeIn 0.3s ease" }}>

          {/* HERO: Directional Banner */}
          <DirectionalBanner tech={tech} theme={theme} />

          {/* Row 1: Key metrics + Trend Strength + Timeframe Consensus */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>

            {/* Score gauge (compact) */}
            <Card theme={theme} style={{ textAlign: "center", padding: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, marginBottom: 8 }}>
                COMPOSITE SCORE
              </div>
              <div style={{ fontSize: 42, fontWeight: 900, color: signalColor(tech.direction) }}>
                {tech.score}
              </div>
              <div style={{ fontSize: 11, color: theme.muted }}>/ 100</div>
            </Card>

            {/* Confidence */}
            <Card theme={theme} style={{ textAlign: "center", padding: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, marginBottom: 8 }}>
                CONFIDENCE
              </div>
              <div style={{ fontSize: 42, fontWeight: 900, color: signalColor(tech.direction) }}>
                {fmt(tech.confidence * 100, 0)}%
              </div>
              <div style={{ fontSize: 11, color: theme.muted }}>
                {tech.confidence >= 0.7 ? "High" : tech.confidence >= 0.5 ? "Medium" : "Low"}
              </div>
            </Card>

            {/* Trend Strength */}
            <TrendStrengthMeter
              adx={tech.indicators.adx?.adx}
              plusDI={tech.indicators.adx?.plus_di}
              minusDI={tech.indicators.adx?.minus_di}
              theme={theme}
            />

            {/* Timeframe Consensus */}
            {result.timeframe_consensus && (
              <TimeframeConsensus
                consensus={result.timeframe_consensus}
                theme={theme}
              />
            )}
          </div>

          {/* Row 2: Model Comparison */}
          <Card theme={theme} style={{ padding: 24, marginBottom: 16 }}>
              <div style={{ fontSize: 11, color: theme.muted, marginBottom: 12, fontWeight: 600 }}>MODEL COMPARISON</div>
              {blendedScore !== null && (
                <div style={{ marginBottom: 10, padding: "6px 10px", borderRadius: 6, background: "rgba(99,102,241,.08)", fontSize: 12 }}>
                  Blended score: <b style={{ color: "#6366f1" }}>{blendedScore}</b>
                </div>
              )}
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
            {sortedIndicatorEntries.map(([name, subScore]) => (
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
        <Card theme={theme} style={{ textAlign: "center", padding: 40, marginBottom: 16 }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>📊</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Technical Indicator Score</div>
          <div style={{ fontSize: 12, color: theme.muted, maxWidth: 420, margin: "0 auto", lineHeight: 1.6 }}>
            Select a symbol above or type one in to compute a technical score
            using 8 classical indicators. Results are compared side-by-side with the
            existing OI/IV/Greeks model.
          </div>
        </Card>
      )}

      {batchResults.length > 0 && (
        <Card theme={theme} style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 700 }}>Batch Results ({batchResults.length})</div>
            <button
              onClick={exportBatchExcel}
              style={{
                padding: "4px 10px", borderRadius: 4, background: theme.accent, color: "#fff", border: "none", cursor: "pointer", fontSize: 11
              }}>
              ↓ Export All to Excel
            </button>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr style={{ background: "rgba(0,0,0,0.05)", textAlign: "left" }}>
                  <th style={{ padding: "6px" }}>Symbol</th>
                  <th style={{ padding: "6px", textAlign: "right" }}>Tech Score</th>
                  <th style={{ padding: "6px", textAlign: "center" }}>Signal</th>
                  <th style={{ padding: "6px", textAlign: "right" }}>Confidence</th>
                  <th style={{ padding: "6px", textAlign: "right" }}>OI Score</th>
                  <th style={{ padding: "6px", textAlign: "center" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {[...batchResults].sort((a, b) => (b.data?.technical_score?.score || 0) - (a.data?.technical_score?.score || 0)).map(b => (
                  <tr key={b.symbol} style={{ borderBottom: `1px solid ${theme.border}` }}>
                    <td style={{ padding: "6px", fontWeight: 600 }}>{b.symbol}</td>
                    <td style={{ padding: "6px", textAlign: "right", color: signalColor(b.data?.technical_score?.direction), fontWeight: 700 }}>{b.data?.technical_score?.score ?? "—"}</td>
                    <td style={{ padding: "6px", textAlign: "center", color: signalColor(b.data?.technical_score?.direction), fontWeight: 700 }}>{b.data?.technical_score?.direction || "—"}</td>
                    <td style={{ padding: "6px", textAlign: "right" }}>{b.data?.technical_score?.confidence ? `${fmt(b.data.technical_score.confidence*100, 1)}%` : "—"}</td>
                    <td style={{ padding: "6px", textAlign: "right", color: b.data?.existing_score ? signalColor(b.data.existing_score.signal) : theme.muted }}>{b.data?.existing_score?.score ?? "—"}</td>
                    <td style={{ padding: "6px", textAlign: "center" }}>
                      <button onClick={() => { setSymbol(b.symbol); setInputVal(b.symbol); setResult(b.data); window.scrollTo({ top: 0, behavior: 'smooth' }); }} style={{ padding: "4px 8px", fontSize: 10, cursor: "pointer", background: theme.bg, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 4 }}>View Details</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
