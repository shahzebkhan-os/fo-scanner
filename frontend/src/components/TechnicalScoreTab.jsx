import { useState, useCallback, useEffect, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, RadarChart, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, Radar, LineChart, Line
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

// ── Components: Auto-Trade Monitor ───────────────────────────────────────────

function TradeChart({ tradeId, theme }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function fetchHistory() {
      try {
        const data = await apiFetch(`/api/paper-trades/history/${tradeId}`);
        if (active) setHistory(data.map(d => ({
          time: new Date(d.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          price: d.price
        })));
      } catch (e) { console.error(e); }
      finally { if (active) setLoading(false); }
    }
    fetchHistory();
    const inv = setInterval(fetchHistory, 60000); // 1m refresh for history
    return () => { active = false; clearInterval(inv); };
  }, [tradeId]);

  if (loading) return <div style={{ height: 120, background: theme.bg, borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10 }}>Loading history...</div>;
  if (history.length < 2) return <div style={{ height: 120, background: theme.bg, borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: theme.muted }}>Awaiting more data points...</div>;

  return (
    <div style={{ height: 120, marginTop: 8 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={history}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.border} vertical={false} />
          <XAxis dataKey="time" hide />
          <YAxis hide domain={['auto', 'auto']} />
          <Tooltip 
            contentStyle={{ background: theme.card, border: `1px solid ${theme.border}`, fontSize: 10, borderRadius: 4 }}
            labelStyle={{ color: theme.muted }}
          />
          <Line type="monotone" dataKey="price" stroke={theme.accent} strokeWidth={2} dot={false} animationDuration={500} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TechnicalTradeMonitor({ theme }) {
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    async function load() {
      try {
        const data = await apiFetch("/api/paper-trades/active-technical");
        setTrades(data);
      } catch (e) { console.error(e); }
    }
    load();
    const inv = setInterval(load, 30000); // 30s refresh for trade list
    return () => clearInterval(inv);
  }, []);

  if (trades.length === 0) return null;

  return (
    <Card theme={theme} style={{ marginBottom: 20, border: `1px solid ${theme.accent}33` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: theme.text }}>
          🎯 ACTIVE TECHNICAL TRADES <span style={{ color: theme.muted, fontWeight: 400, marginLeft: 8 }}>Auto-executed for Score {'>'}= 70%</span>
        </div>
        <div style={{ fontSize: 10, background: `${theme.accent}22`, color: theme.accent, padding: '2px 8px', borderRadius: 4 }}>
          {trades.length} Positions Open
        </div>
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
        {trades.map(t => {
          const pnl = t.pnl_pct || 0;
          const isGreen = pnl >= 0;
          return (
            <div key={t.id} style={{ background: theme.bg, borderRadius: 6, padding: 12, border: `1px solid ${theme.border}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>{t.symbol}</div>
                  <div style={{ fontSize: 10, color: theme.muted }}>{t.type} {t.strike} • Entry @ {fmt(t.entry_price)}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ color: isGreen ? '#22c55e' : '#ef4444', fontWeight: 700, fontSize: 14 }}>
                    {isGreen ? '+' : ''}{fmt(pnl)}%
                  </div>
                  <div style={{ fontSize: 10, color: theme.muted }}>LTP: {fmt(t.current_price)}</div>
                </div>
              </div>
              <TradeChart tradeId={t.id} theme={theme} />
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const r = await fetch(path, options);
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
  "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX",
  "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE", 
  "TATAMOTORS", "ITC", "AXISBANK", "LT", "HINDUNILVR", "BHARTIARTL", "KOTAKBANK",
  "TATASTEEL", "HCLTECH", "WIPRO", "MARUTI",
  "ADANIENT", "SUNPHARMA", "TITAN", "ULTRACEMCO", "ASIANPAINT", "MM", "NTPC",
  "POWERGRID", "ONGC", "COALINDIA", "JSWSTEEL", "GRASIM", "BPCL", "INDUSINDBK", "BAJAJFINSV"
];

// Indicator display config: friendly names, icons, descriptions
const INDICATOR_META = {
  rsi:           { label: "RSI (14)",        icon: "📈", desc: "Relative Strength Index — momentum oscillator (overbought >70, oversold <30)" },
  macd:          { label: "MACD",            icon: "〰️",  desc: "Moving Average Convergence Divergence — trend + momentum crossover" },
  adx:           { label: "ADX",             icon: "💪", desc: "Average Directional Index — trend strength (+DI vs −DI)" },
  stochastic:    { label: "Stochastic",      icon: "🔄", desc: "Stochastic %K/%D — overbought/oversold oscillator" },
  ema_alignment: { label: "EMA Alignment",   icon: "📊", desc: "EMA 9/21/50 stack — multi-timeframe trend consensus" },
  bollinger:     { label: "Bollinger %B",    icon: "📐", desc: "Bollinger Bands — volatility + mean-reversion context" },
  volume:        { label: "Volume Flow",     icon: "📢", desc: "OBV slope + Chaikin Money Flow — cumulative buying/selling pressure" },
  vwap:          { label: "VWAP",            icon: "⚖️",  desc: "Volume-Weighted Average Price deviation — institutional interest" },
  supertrend:    { label: "Supertrend",      icon: "🎯", desc: "ATR-based directional flip — clean binary bullish/bearish signal" },
  divergence:    { label: "Divergence",      icon: "⚡", desc: "RSI + MACD divergence detection — reversal early warning" },
  ichimoku:      { label: "Ichimoku Cloud",  icon: "☁️",  desc: "5-component trend system — price vs cloud, TK cross, Senkou spans" },
};

const WEIGHT_LABELS = {
  rsi: "11%", macd: "15%", adx: "11%", stochastic: "7%",
  ema_alignment: "11%", bollinger: "7%", volume: "8%", vwap: "4%",
  supertrend: "9%", divergence: "10%", ichimoku: "7%",
};

const clamp = (n, min, max) => Math.min(max, Math.max(min, n));

function deriveTargetStopFromIndicators(ltp, technicalScore) {
  const price = Number(ltp);
  if (!Number.isFinite(price) || price <= 0 || !technicalScore) {
    return { target: null, stopLoss: null, targetPct: 0, stopPct: 0 };
  }

  const isBear = technicalScore.direction === "BEARISH";
  const inds = technicalScore.indicators || {};
  const supertrendValue = Number(inds.supertrend?.value);
  const adx = Number(inds.adx?.adx || 0);
  const bbUpper = Number(inds.bollinger?.upper);
  const bbLower = Number(inds.bollinger?.lower);

  const supertrendRiskPct = Number.isFinite(supertrendValue) && supertrendValue > 0
    ? Math.abs(price - supertrendValue) / price
    : 0;
  const bollingerWidthPct = Number.isFinite(bbUpper) && Number.isFinite(bbLower)
    ? Math.abs(bbUpper - bbLower) / price
    : 0;

  const stopPct = clamp(Math.max(supertrendRiskPct, bollingerWidthPct * 0.25, 0.0075), 0.0075, 0.03);
  const rewardRisk = adx >= 25 ? 2 : 1.4;
  const targetPct = clamp(stopPct * rewardRisk, 0.012, 0.06);

  return {
    target: price * (isBear ? 1 - targetPct : 1 + targetPct),
    stopLoss: price * (isBear ? 1 + stopPct : 1 - stopPct),
    targetPct,
    stopPct,
  };
}

function getBestEntryWindow(technicalScore) {
  if (!technicalScore) return "—";
  const inds = technicalScore.indicators || {};
  const adx = Number(inds.adx?.adx || 0);
  const rsi = Number(inds.rsi?.value || 50);
  const confidence = Number(technicalScore.confidence || 0);

  if (technicalScore.direction === "NEUTRAL") return "Wait • No edge";
  if (adx >= 25 && technicalScore.direction_strength === "STRONG" && confidence >= 0.75) return "Now • Momentum";
  if (adx < 20) return "Wait • 15m breakout";

  const overExtendedBull = technicalScore.direction === "BULLISH" && rsi >= 65;
  const overExtendedBear = technicalScore.direction === "BEARISH" && rsi <= 35;
  if (overExtendedBull || overExtendedBear) return "Wait • Pullback";

  return "Staggered entry";
}

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
const INDICATOR_GOOD_RANGE = {
  rsi: "Bullish: > 60 | Bearish: < 40",
  macd: "Bulls: Line > Signal & Hist > 0",
  adx: "Trending: > 25 (Strength Indicator)",
  stochastic: "Bullish: < 20 (Rev.) | Bearish: > 80",
  ema_alignment: "Bullish: Price > 9 > 21 > 50 EMA",
  bollinger: "Bulls: < 0 (Reversal) / > 0.8 (Mom.)",
  volume: "Bulls: Ratio > 1.2x | CMF > 0.1",
  vwap: "Bullish: Price > VWAP (Bias)",
  supertrend: "Bullish: Price > SuperTrend Line",
  ichimoku: "Bullish: Price > Cloud & Tenkan > Kijun",
  divergence: "Bullish: Price Lows vs Ind. Highs",
};

function IndicatorCard({ name, data, subScore, theme }) {
  const meta = INDICATOR_META[name] || { label: name, icon: "•", desc: "" };
  const rangeInfo = INDICATOR_GOOD_RANGE[name] || "";
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
        height: 6, borderRadius: 3, background: theme.border, overflow: "hidden", marginBottom: 4
      }}>
        <div style={{
          height: "100%", borderRadius: 3, background: barColor,
          width: `${barPct}%`, transition: "width 0.6s ease"
        }} />
      </div>

      {/* Range Info */}
      <div style={{ fontSize: 9, fontWeight: 600, color: theme.muted, marginBottom: 8, textAlign: "right", letterSpacing: 0.5 }}>
        GOOD RANGE: <span style={{ color: theme.text }}>{rangeInfo}</span>
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
function DirectionalBanner({ tech, theme, accuracySummary }) {
  if (!tech) return null;

  const direction = tech.direction;
  const strength = tech.direction_strength;
  const pValue = accuracySummary?.stats?.p_value;
  const isVerified = pValue != null && pValue < 0.05;

  const isStrong = strength === "STRONG";
  const baseColor = direction === "BULLISH" ? "#22c55e" : direction === "BEARISH" ? "#ef4444" : "#94a3b8";
  const bgColor = direction === "BULLISH"
    ? (isStrong ? "rgba(34,197,94,0.15)" : "rgba(34,197,94,0.08)")
    : direction === "BEARISH"
    ? (isStrong ? "rgba(239,68,68,0.15)" : "rgba(239,68,68,0.08)")
    : "rgba(148,163,184,0.05)";

  const arrowIcon = direction === "BULLISH" ? "▲▲▲" : direction === "BEARISH" ? "▼▼▼" : "◆◆◆";
  const emoji = direction === "BULLISH" ? "🚀" : direction === "BEARISH" ? "📉" : isStrong ? "➡️" : "〰️";

  const message = isStrong
    ? (direction === "BULLISH" ? "Strong Uptrend Detected" : direction === "BEARISH" ? "Strong Downtrend Detected" : "Strong Sideways Action")
    : "Consolidating / No Clear Direction";

  return (
    <div style={{
      background: bgColor,
      border: `3px solid ${baseColor}`,
      borderRadius: 12,
      padding: "24px",
      marginBottom: 20,
      textAlign: "center",
      position: "relative",
      animation: isStrong ? "directionPulse 2s ease-in-out infinite" : "none",
      boxShadow: isStrong ? `0 0 20px ${baseColor}30` : "none"
    }}>
      {isVerified && (
        <div style={{
          position: "absolute", top: 12, right: 12,
          background: "#22c55e", color: "#fff", 
          padding: "4px 10px", borderRadius: 20,
          fontSize: 10, fontWeight: 800, letterSpacing: 0.5,
          boxShadow: "0 2px 10px rgba(34,197,94,0.3)",
          display: "flex", alignItems: "center", gap: 6
        }}>
          <span>🛡️ VERIFIED SIGNAL</span>
          <span style={{ opacity: 0.8, fontSize: 8 }}>p={pValue.toFixed(3)}</span>
        </div>
      )}
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
          <span style={{ color: theme.muted }}>Confidence: </span>
          <b style={{ color: baseColor }}>{(tech.confidence * 100).toFixed(1)}%</b>
        </div>
        <div>
          <span style={{ color: theme.muted }}>Score: </span>
          <b style={{ color: baseColor }}>{tech.score.toFixed(0)}</b>
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
      <div style={{ display: "flex", gap: 8, justifyContent: "center", marginBottom: 12, flexWrap: "wrap" }}>
        {["1m", "2m", "5m", "10m", "15m"].map(tf => {
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

// ── Accuracy Summary Card ───────────────────────────────────────────────────
function AccuracySummaryCard({ summary, theme }) {
  if (!summary || summary.total_runs === 0) {
    return (
      <Card theme={theme} style={{ textAlign: "center", padding: 30 }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>📉</div>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>No Signal Accuracy Data</div>
        <div style={{ fontSize: 11, color: theme.muted }}>
          Run a technical backtest to see win rates and statistical validity.
        </div>
      </Card>
    );
  }

  const latest = summary.latest_run;
  const isSignificant = latest.statistical_significance?.is_significant;
  const pVal = latest.statistical_significance?.p_value;
  const sigColor = isSignificant ? "#22c55e" : "#f59e0b";

  return (
    <Card theme={theme} style={{ padding: 20, border: isSignificant ? `2px solid ${theme.accent}44` : `1px solid ${theme.border}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, marginBottom: 4 }}>SIGNAL ACCURACY (LATEST RUN)</div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ fontSize: 24, fontWeight: 800 }}>{fmt(latest.win_rate * 100, 1)}% Win Rate</div>
            {isSignificant && (
              <span style={{ 
                background: "rgba(34,197,94,0.15)", color: "#22c55e", 
                fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                border: "1px solid rgba(34,197,94,0.3)"
              }}>
                ✓ STATISTICALLY VALID
              </span>
            )}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 11, color: theme.muted }}>Profit Factor</div>
          <div style={{ fontSize: 20, fontWeight: 800, color: latest.profit_factor >= 1.5 ? "#22c55e" : latest.profit_factor >= 1 ? "#f59e0b" : "#ef4444" }}>
            {fmt(latest.profit_factor, 2)}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 16 }}>
        <div style={{ background: theme.bg, padding: 10, borderRadius: 6, textAlign: "center" }}>
          <div style={{ fontSize: 10, color: theme.muted }}>Bullish Win Rate</div>
          <div style={{ fontWeight: 700, color: "#22c55e" }}>{fmt(latest.by_direction.bullish_win_rate * 100, 0)}%</div>
        </div>
        <div style={{ background: theme.bg, padding: 10, borderRadius: 6, textAlign: "center" }}>
          <div style={{ fontSize: 10, color: theme.muted }}>Bearish Win Rate</div>
          <div style={{ fontWeight: 700, color: "#ef4444" }}>{fmt(latest.by_direction.bearish_win_rate * 100, 0)}%</div>
        </div>
        <div style={{ background: theme.bg, padding: 10, borderRadius: 6, textAlign: "center" }}>
          <div style={{ fontSize: 10, color: theme.muted }}>Sample Size</div>
          <div style={{ fontWeight: 700 }}>{latest.total_trades} trades</div>
        </div>
      </div>

      <div style={{ borderTop: `1px solid ${theme.border}`, paddingTop: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 10, color: theme.muted }}>
          p-value: <b style={{ color: sigColor }}>{pVal != null ? fmt(pVal, 4) : "N/A"}</b>
          <span style={{ marginLeft: 8 }}>Signal Age: <b>NEW</b></span>
        </div>
        <div style={{ fontSize: 10, fontStyle: "italic", color: theme.muted }}>
          Based on {latest.symbols.length} symbols • {latest.run_time.split(" ")[0]}
        </div>
      </div>
    </Card>
  );
}

// ── Backtest Control Panel ──────────────────────────────────────────────────
function BacktestPanel({ theme, onComplete }) {
  const [symbols, setSymbols] = useState("NIFTY,BANKNIFTY,RELIANCE,TCS,HDFCBANK");
  const [days, setDays] = useState(30);
  const [timeframe, setTimeframe] = useState("15m");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    try {
      const symList = symbols.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
      const endDate = new Date().toISOString().split("T")[0];
      const startDate = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString().split("T")[0];

      await apiFetch("/api/technical-backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbols: symList,
          start_date: startDate,
          end_date: endDate,
          timeframe: timeframe,
          min_score_threshold: 70,
          min_confidence: 0.65
        })
      });
      if (onComplete) onComplete();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card theme={theme} style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 16 }}>⚡ RUN TECHNICAL BACKTEST</div>
      
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 12, alignItems: "flex-end" }}>
        <div>
          <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 4 }}>Symbols (comma separated)</label>
          <input 
            value={symbols}
            onChange={e => setSymbols(e.target.value)}
            style={{ 
              width: "100%", padding: "8px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
              background: theme.bg, color: theme.text, fontSize: 12
            }}
          />
        </div>
        <div>
          <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 4 }}>Lookback Days</label>
          <select 
            value={days}
            onChange={e => setDays(parseInt(e.target.value))}
            style={{ 
              padding: "8px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
              background: theme.bg, color: theme.text, fontSize: 12
            }}
          >
            <option value={7}>7 Days</option>
            <option value={14}>14 Days</option>
            <option value={30}>30 Days</option>
            <option value={60}>60 Days</option>
            <option value={90}>90 Days</option>
          </select>
        </div>
        <div>
          <label style={{ fontSize: 10, color: theme.muted, display: "block", marginBottom: 4 }}>Timeframe</label>
          <select 
            value={timeframe}
            onChange={e => setTimeframe(e.target.value)}
            style={{ 
              padding: "8px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
              background: theme.bg, color: theme.text, fontSize: 12
            }}
          >
            <option value="5m">5m</option>
            <option value="10m">10m</option>
            <option value="15m">15m</option>
            <option value="30m">30m</option>
            <option value="1h">1h</option>
          </select>
        </div>
        <button 
          onClick={runBacktest}
          disabled={loading}
          style={{ 
            height: 35, padding: "0 20px", borderRadius: 6, background: theme.accent, color: "#fff",
            border: "none", fontWeight: 700, cursor: loading ? "wait" : "pointer"
          }}
        >
          {loading ? "⌛ Testing..." : "🚀 Run Backtest"}
        </button>
      </div>

      {error && <div style={{ color: "#ef4444", fontSize: 11, marginTop: 8 }}>❌ Error: {error}</div>}
      
      <div style={{ marginTop: 12, padding: "8px 12px", background: "rgba(99,102,241,0.05)", borderRadius: 6, fontSize: 10, color: theme.muted }}>
        <b>Tip:</b> Running a backtest helps calibrate the Composite Score weights. 
        Aim for a sample size of {'>'}30 trades for statistical significance.
      </div>
    </Card>
  );
}

function BacktestHistory({ theme }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const data = await apiFetch("/api/technical-backtest/runs?limit=5");
      setRuns(data.runs || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return <div style={{ fontSize: 11, color: theme.muted, padding: 20 }}>Loading runs...</div>;
  if (runs.length === 0) return null;

  return (
    <div style={{ marginTop: 20 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, marginBottom: 10 }}>RECENT BACKTEST RUNS</div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
        <thead>
          <tr style={{ textAlign: "left", color: theme.muted, borderBottom: `1px solid ${theme.border}` }}>
            <th style={{ padding: 8 }}>Date</th>
            <th style={{ padding: 8 }}>Win Rate</th>
            <th style={{ padding: 8 }}>Trades</th>
            <th style={{ padding: 8 }}>PF</th>
            <th style={{ padding: 8 }}>Sig.</th>
          </tr>
        </thead>
        <tbody>
          {runs.map(r => {
            const isSig = r.metrics?.is_significant || false;
            return (
              <tr key={r.id} style={{ borderBottom: `1px solid ${theme.border}` }}>
                <td style={{ padding: 8 }}>{r.run_time.split(" ")[0]}</td>
                <td style={{ padding: 8, fontWeight: 700, color: signalColor(r.win_rate >= 0.5 ? "BULLISH" : "BEARISH") }}>{fmt(r.win_rate * 100, 1)}%</td>
                <td style={{ padding: 8 }}>{r.total_trades}</td>
                <td style={{ padding: 8 }}>{fmt(r.profit_factor, 2)}</td>
                <td style={{ padding: 8 }}>{isSig ? "✅" : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Main Tab Component ───────────────────────────────────────────────────────
export default function TechnicalScoreTab({ theme, scanData }) {
  const [symbol, setSymbol] = useState("NIFTY");
  const [activeTab, setActiveTab] = useState("analysis"); // analysis or batch
  const [activeTrades, setActiveTrades] = useState([]);
  const [inputVal, setInputVal] = useState("NIFTY");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sortIndicators, setSortIndicators] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchProgress, setBatchProgress] = useState(0);
  const [batchResults, setBatchResults] = useState([]);
  const [selectedTF, setSelectedTF] = useState("15m");
  const [sortConfig, setSortConfig] = useState({ key: "blended", dir: "desc" });
  const [localScanMap, setLocalScanMap] = useState(null);
  const [showScanInfo, setShowScanInfo] = useState(false);

  const [accuracySummary, setAccuracySummary] = useState(null);
  const scanMap = useMemo(() => {
    if (localScanMap) return localScanMap;
    const map = {};
    (scanData || []).forEach((row) => {
      map[row.symbol] = row;
    });
    return map;
  }, [scanData, localScanMap]);

  const fetchAccuracySummary = useCallback(async () => {
    try {
      const data = await apiFetch("/api/technical-backtest/accuracy-summary");
      setAccuracySummary(data);
    } catch (e) {
      console.error("Failed to fetch accuracy summary:", e);
    }
  }, []);

  useEffect(() => {
    fetchAccuracySummary();
  }, [fetchAccuracySummary]);

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

  const loadAll = useCallback(async (isAuto = false) => {
    if (batchLoading) return;
    if (!isAuto && !window.confirm("This will fetch technical scores for all popular symbols. It may take a minute. Continue?")) return;
    
    setBatchLoading(true);
    setBatchProgress(0);
    const results = [];
    
    // Fetch latest scan data in parallel with technical fetches
    const scanPromise = apiFetch("/api/scan?limit=500")
      .then((scanRes) => {
        const smap = {};
        (scanRes.data || []).forEach(r => { smap[r.symbol] = r; });
        setLocalScanMap(smap);
      })
      .catch((e) => console.warn("Failed to fetch fresh scan map", e));

    const concurrency = 6;
    let processed = 0;
    for (let i = 0; i < POPULAR_SYMBOLS.length; i += concurrency) {
      const chunk = POPULAR_SYMBOLS.slice(i, i + concurrency);
      await Promise.allSettled(chunk.map(async (sym) => {
        try {
          const data = await apiFetch(`/api/score-technical/${sym}`);
          results.push({ symbol: sym, data });
        } catch (e) {
          console.error(`Failed to load ${sym}:`, e);
        } finally {
          processed += 1;
          setBatchProgress(processed);
        }
      }));
      setBatchResults([...results]);
    }

    await scanPromise;
    
    setBatchResults(results);
    setBatchLoading(false);
  }, [batchLoading]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const timer = setInterval(() => {
      console.log("Auto-refreshing Technical Scores...");
      loadAll(true);
    }, 5 * 60 * 1000);
    return () => clearInterval(timer);
  }, [loadAll]);

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
    <div style={{ animation: "fadeIn 0.3s ease" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8 }}>
        <div>
          <h2 style={{ fontSize: 18, margin: 0 }}>📊 Technical Score</h2>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 2 }}>
            RSI · MACD · ADX · Stochastic · EMA · Bollinger · Volume · VWAP
          </div>
        </div>
      </div>

      {/* Sub-Tab Navigation */}
      <div style={{ display: "flex", gap: 20, borderBottom: `1px solid ${theme.border}`, marginBottom: 20 }}>
        {["analysis", "batch", "backtest"].map(tab => (
          <div
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "10px 4px", fontSize: 13, fontWeight: 700, cursor: "pointer",
              color: activeTab === tab ? theme.accent : theme.muted,
              borderBottom: activeTab === tab ? `3px solid ${theme.accent}` : "3px solid transparent",
              transition: "all 0.2s", textTransform: "uppercase", letterSpacing: 0.5
            }}
          >
            {tab === "analysis" ? "🔍 Analysis" : tab === "batch" ? "⚡ Market Scan" : "🧪 Backtesting"}
          </div>
        ))}
      </div>

      {activeTab === "backtest" && (
        <div style={{ animation: "fadeIn 0.3s ease" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
            <div>
              <BacktestPanel theme={theme} onComplete={fetchAccuracySummary} />
              <BacktestHistory theme={theme} />
            </div>
            <AccuracySummaryCard summary={accuracySummary} theme={theme} />
          </div>
          
          <Card theme={theme} style={{ padding: 24, background: "rgba(34,197,94,0.03)", border: "1px dashed rgba(34,197,94,0.3)" }}>
            <div style={{ display: "flex", gap: 16 }}>
              <div style={{ fontSize: 24 }}>💡</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4, color: "#22c55e" }}>Accuracy Verification Protocol</div>
                <div style={{ fontSize: 11, color: theme.text, opacity: 0.8, lineHeight: 1.5 }}>
                  The F&O Scanner distinguishes between <b>Active Trade Health</b> (real-time monitoring) and 
                  <b>Historical Accuracy</b> (backtesting). Always verify a signal's statistical validity before 
                  increasing position sizes. A "Verified Signal" badge appears on the main gauge when p-value {'<'} 0.05.
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {activeTab === "analysis" && (
        <>
          {/* Search */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8 }}>
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

            {/* Actions for current symbol */}
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <label style={{ fontSize: 11, color: theme.muted, display: "flex", alignItems: "center", gap: 6 }}>
                <input type="checkbox" checked={sortIndicators} onChange={() => setSortIndicators(v => !v)} />
                Sort indicators
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
          </div>

          {/* Quick-pick buttons only in analysis tab */}
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
              <div style={{ display: "flex", gap: 12, justifyContent: "space-around", flexWrap: "wrap", overflowX: "auto" }}>
                {["1m", "2m", "5m", "10m", "15m"].map(tf => {
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

          {/* Market Scan (rendered below Multi-Timeframe Trend) */}
          <Card theme={theme} style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, gap: 12, flexWrap: "wrap" }}>
              <div style={{ fontSize: 12, fontWeight: 700 }}>⚡ Market Scan Table</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button
                  onClick={() => setShowScanInfo(v => !v)}
                  title="What is this scan?"
                  style={{
                    width: 26, height: 26, borderRadius: "50%",
                    border: `1px solid ${theme.border}`, background: theme.bg, color: theme.text,
                    fontWeight: 800, cursor: "pointer"
                  }}
                >
                  i
                </button>
                <button
                  onClick={loadAll}
                  disabled={batchLoading}
                  style={{
                    padding: "8px 16px", borderRadius: 6, background: theme.accent, color: "#fff",
                    border: "none", cursor: "pointer", fontWeight: 700
                  }}
                >
                  {batchLoading ? `⚡ Scanning (${batchProgress}/${POPULAR_SYMBOLS.length})...` : "⚡ Start Market Scan"}
                </button>
              </div>
            </div>

            {showScanInfo && (
              <div style={{
                marginBottom: 12, padding: "10px 12px", borderRadius: 6,
                background: "rgba(99,102,241,0.08)", border: `1px solid ${theme.border}`, fontSize: 11, lineHeight: 1.5
              }}>
                This table quickly scans popular symbols and ranks them by combined technical + options context.
                Use <b>View</b> to open full indicator analysis for any row.
              </div>
            )}

            {batchResults.length > 0 && (() => {
              const sorted = [...batchResults].filter(b => b.data?.technical_score?.score != null).sort((a, b) => {
                const aTech = a.data.technical_score;
                const aExist = a.data.existing_score;
                const aBlended = Math.round((aTech.score + (aExist?.score != null ? aExist.score : 0)) / (aExist?.score != null ? 2 : 1));
                
                const bTech = b.data.technical_score;
                const bExist = b.data.existing_score;
                const bBlended = Math.round((bTech.score + (bExist?.score != null ? bExist.score : 0)) / (bExist?.score != null ? 2 : 1));
                
                let valA = 0, valB = 0;
                if (sortConfig.key === "symbol") { valA = a.symbol; valB = b.symbol; }
                else if (sortConfig.key === "blended") { valA = aBlended; valB = bBlended; }
                else if (sortConfig.key === "technical") { valA = aTech.score; valB = bTech.score; }
                else if (sortConfig.key === "confidence") { valA = aTech.confidence; valB = bTech.confidence; }
                else if (sortConfig.key === "direction") { valA = aTech.direction; valB = bTech.direction; }
                
                if (valA < valB) return sortConfig.dir === "asc" ? -1 : 1;
                if (valA > valB) return sortConfig.dir === "asc" ? 1 : -1;
                return 0;
              });

              const handleSort = (k) => {
                if (sortConfig.key === k) setSortConfig({ key: k, dir: sortConfig.dir === "asc" ? "desc" : "asc" });
                else setSortConfig({ key: k, dir: "desc" });
              };
              const SortIcon = ({ k }) => <span style={{ opacity: sortConfig.key === k ? 1 : 0.2, marginLeft: 4 }}>{sortConfig.key === k && sortConfig.dir === "asc" ? "↑" : "↓"}</span>;

              return (
                <>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                      <thead>
                        <tr style={{ background: "rgba(0,0,0,0.06)", textAlign: "left" }}>
                          <th title="Ticker symbol of the stock being analyzed" style={{ padding: "10px 8px", cursor: "pointer" }} onClick={() => handleSort("symbol")}>Symbol <SortIcon k="symbol" /></th>
                          <th title="A weighted combination of the Option Score and the True Composite Technical Score" style={{ padding: "10px 8px", cursor: "pointer" }} onClick={() => handleSort("blended")}>Blended <SortIcon k="blended" /></th>
                          <th title="True Composite Technical Score (Avg. of 1m, 2m, 5m, 10m, and 15m intervals)" style={{ padding: "10px 8px", cursor: "pointer" }} onClick={() => handleSort("technical")}>Technical <SortIcon k="technical" /></th>
                          <th title="Overall Technical Direction based purely on indicators (Price Action / Momentum)" style={{ padding: "10px 8px", cursor: "pointer" }} onClick={() => handleSort("direction")}>Direction <SortIcon k="direction" /></th>
                          <th title="Current stock LTP" style={{ padding: "10px 8px" }}>LTP</th>
                          <th title="Dynamic target derived from Supertrend/volatility and trend regime" style={{ padding: "10px 8px" }}>Target</th>
                          <th title="Dynamic stop-loss derived from Supertrend/volatility and trend regime" style={{ padding: "10px 8px" }}>Stop Loss</th>
                          <th title="Best timing to enter based on trend strength, ADX, confidence, and momentum state" style={{ padding: "10px 8px" }}>Best Entry</th>
                          <th title="Underlying Technical Triggers: 🎯 Supertrend, 🟢/🔴 Ichimoku, ⚡ Divergence" style={{ padding: "10px 8px" }}>Signals</th>
                          <th title="Market Regime: TREND is directional movement (ADX > 25), RANGE is choppy movement (ADX < 25)" style={{ padding: "10px 8px" }}>Regime</th>
                          <th title="Probability of the setup succeeding computed from indicator confluence" style={{ padding: "10px 8px", cursor: "pointer" }} onClick={() => handleSort("confidence")}>Confidence <SortIcon k="confidence" /></th>
                          <th title="Trade options and detailed symbol view" style={{ padding: "10px 8px" }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sorted.map((b, idx) => {
                           const bTech = b.data.technical_score;
                           const bExist = b.data.existing_score;
                           const bHasExist = bExist?.score != null;
                           const bBlended = Math.round((bTech.score + (bHasExist ? bExist.score : 0)) / (bHasExist ? 2 : 1));
                           
                           const scanRow = scanMap[b.symbol];
                           const ltp = Number(scanRow?.ltp || 0);
                           const hasLtp = Number.isFinite(ltp) && ltp > 0;
                           const { target, stopLoss, targetPct, stopPct } = deriveTargetStopFromIndicators(ltp, bTech);
                           const bestEntry = getBestEntryWindow(bTech);

                           const inds = bTech.indicators || {};
                           const st = inds.supertrend?.direction;
                           const ichi = inds.ichimoku?.position;
                           const div = inds.divergence?.type;
                           const isTrending = inds.adx?.adx >= 25;
                          const isBest = idx === 0 && bTech.score >= 70 && bTech.confidence >= 0.7;

                          return (
                            <tr key={b.symbol} style={{ 
                              borderBottom: `1px solid ${theme.border}`, 
                              background: isBest ? "rgba(234,179,8,0.05)" : "transparent",
                              transition: "background 0.2s" 
                            }}>
                              <td style={{ padding: "8px" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                  <b>{b.symbol}</b>
                                  {isBest && <span title="Best Trend Detected" style={{ color: "#eab308" }}>👑</span>}
                                </div>
                              </td>
                              <td style={{ padding: "8px" }}>
                                <span style={{ 
                                  fontWeight: 800, 
                                  color: isBest ? "#eab308" : signalColor(bBlended > 50 ? "BULLISH" : "BEARISH") 
                                }}>{bBlended}</span>
                              </td>
                              <td style={{ padding: "8px", opacity: 0.8 }}>{bTech.score}</td>
                                <td style={{ padding: "8px" }}>
                                  <span style={{ 
                                    color: signalColor(bTech.direction), fontWeight: 700, fontSize: 10,
                                    background: signalBg(bTech.direction), padding: "2px 6px", borderRadius: 4
                                  }}>
                                    {bTech.direction}
                                  </span>
                                </td>
                                <td style={{ padding: "8px" }}>{hasLtp ? `₹${fmt(ltp, 2)}` : "—"}</td>
                                <td style={{ padding: "8px", color: "#22c55e", fontWeight: 700 }} title={target ? `Target ${fmt(targetPct * 100, 1)}%` : undefined}>{target ? `₹${fmt(target, 2)}` : "—"}</td>
                                <td style={{ padding: "8px", color: "#ef4444", fontWeight: 700 }} title={stopLoss ? `Stop ${fmt(stopPct * 100, 1)}%` : undefined}>{stopLoss ? `₹${fmt(stopLoss, 2)}` : "—"}</td>
                                <td style={{ padding: "8px", fontSize: 10, fontWeight: 700 }}>{bestEntry}</td>
                                <td style={{ padding: "8px" }}>
                                  <div style={{ display: "flex", gap: 6, fontSize: 14 }}>
                                    <span title="Supertrend" style={{ opacity: st ? 1 : 0.2 }}>{st === "BULLISH" ? "🎯" : st === "BEARISH" ? "⭕" : "🎯"}</span>
                                    <span title="Ichimoku" style={{ opacity: ichi ? 1 : 0.2 }}>{ichi === "above_cloud" ? "🟢" : ichi === "below_cloud" ? "🔴" : "⚪"}</span>
                                    <span title="Divergence" style={{ opacity: div && div !== "none" ? 1 : 0.2 }}>{div?.includes("bullish") ? "⚡" : div?.includes("bearish") ? "⛈️" : "⚡"}</span>
                                </div>
                              </td>
                              <td style={{ padding: "8px" }}>
                                <span style={{ 
                                  fontSize: 9, fontWeight: 700, color: isTrending ? "#6366f1" : theme.muted,
                                  border: `1px solid ${isTrending ? "#6366f144" : theme.border}`,
                                  padding: "1px 5px", borderRadius: 4
                                }}>
                                  {isTrending ? "📈 TREND" : "↔️ RANGE"}
                                </span>
                              </td>
                              <td style={{ padding: "8px" }}>{fmt(bTech.confidence * 100, 0)}%</td>
                              <td style={{ padding: "8px" }}>
                                <button 
                                  onClick={() => { analyse(b.symbol); window.scrollTo({ top: 0, behavior: 'smooth' }); }} 
                                  style={{ 
                                    padding: "4px 10px", borderRadius: 6, 
                                    border: `1px solid ${isBest ? "#eab308" : theme.border}`,
                                    background: isBest ? "#eab308" : theme.bg, 
                                    color: isBest ? "#fff" : theme.text, 
                                    fontSize: 10, fontWeight: 700, cursor: "pointer",
                                    transition: "all 0.2s"
                                  }}
                                >
                                  {isBest ? "★ Analyse" : "View"}
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ marginTop: 10, fontSize: 10, color: theme.muted, lineHeight: 1.6 }}>
                    <div><b>Blended:</b> average of Technical score and existing scanner score (when available).</div>
                    <div><b>Technical:</b> true composite indicator score computed from multi-timeframe technicals.</div>
                    <div><b>Confidence:</b> indicator confluence confidence from the technical model.</div>
                    <div><b>Target / Stop Loss:</b> adaptive levels from Supertrend and volatility regime (not fixed percentages).</div>
                    <div><b>Best Entry:</b> timing cue from ADX trend strength, direction quality, confidence, and RSI extension.</div>
                  </div>
                </>
              );
            })()}
          </Card>

          {/* Results */}
          {result && tech && (
            <div style={{ animation: "fadeIn 0.3s ease" }}>
              {/* HERO: Directional Banner */}
              <DirectionalBanner tech={tech} theme={theme} accuracySummary={accuracySummary} />

              {/* ADX Warning Banner */}
              {tech.indicators.adx?.adx < 25 && (
                <div style={{
                  background: "rgba(251,146,60,0.15)",
                  border: "2px solid rgba(251,146,60,0.5)",
                  borderRadius: 8,
                  padding: "12px 16px",
                  marginBottom: 16,
                  display: "flex",
                  alignItems: "center",
                  gap: 12
                }}>
                  <div style={{ fontSize: 24 }}>⚠️</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: "#f97316", marginBottom: 4 }}>
                      Low ADX ({tech.indicators.adx.adx.toFixed(1)}) - Ranging Market Detected
                    </div>
                    <div style={{ fontSize: 11, color: theme.text, opacity: 0.9 }}>
                      Technical signals are less reliable in ranging markets (ADX {'<'} 25).
                      Consider waiting for ADX ≥ 25 (trending market) for higher accuracy trades.
                    </div>
                  </div>
                </div>
              )}

              {/* Row 1: Key metrics */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
                <Card theme={theme} style={{ textAlign: "center", padding: 16, display: "flex", flexDirection: "column", justifyContent: "center", background: `linear-gradient(135deg, ${signalBg(tech.direction)} 0%, transparent 100%)` }}>
                  <div style={{ fontSize: 11, fontWeight: 800, color: theme.muted, marginBottom: 8 }}>TRUE COMPOSITE (1m-15m)</div>
                  <div style={{ fontSize: 46, fontWeight: 900, color: signalColor(tech.direction), textShadow: "0px 2px 10px rgba(0,0,0,0.1)" }}>{tech.score}</div>
                  <div style={{ fontSize: 11, color: theme.muted }}>/ 100</div>
                </Card>

                <Card theme={theme} style={{ textAlign: "center", padding: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: theme.muted, marginBottom: 8 }}>OVERALL TREND</div>
                  <div style={{ fontSize: 24, fontWeight: 800, color: signalColor(tech.direction), margin: "8px 0" }}>{tech.direction_strength} {tech.direction}</div>
                  <div style={{ fontSize: 11, color: theme.muted }}>Confidence: {fmt(tech.confidence * 100, 0)}%</div>
                </Card>

                <TrendStrengthMeter
                  adx={tech.indicators.adx?.adx}
                  plusDI={tech.indicators.adx?.plus_di}
                  minusDI={tech.indicators.adx?.minus_di}
                  theme={theme}
                />

                {result.timeframe_consensus && (
                  <TimeframeConsensus consensus={result.timeframe_consensus} theme={theme} />
                )}
              </div>

              {/* Charts row */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
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

                <Card theme={theme}>
                  <div style={{ fontSize: 11, color: theme.muted, marginBottom: 8, fontWeight: 600 }}>SUB-SCORE BREAKDOWN</div>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={barData} layout="vertical" margin={{ left: 60 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                      <XAxis type="number" domain={[0, 100]} tick={{ fill: theme.muted, fontSize: 10 }} />
                      <YAxis type="category" dataKey="name" tick={{ fill: theme.muted, fontSize: 10 }} width={58} />
                      <Tooltip formatter={(v) => [fmt(v, 1), "Score"]} />
                      <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={18}>
                        {barData.map((entry, i) => (
                          <Cell key={i} fill={entry.score >= 70 ? "#22c55e" : entry.score >= 50 ? "#f59e0b" : entry.score >= 30 ? "#fb923c" : "#ef4444"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </Card>
              </div>

              {/* Indicator details */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {sortedIndicatorEntries.map(([name, subScore]) => (
                  <IndicatorCard key={name} name={name} data={tech.indicators[name]} subScore={subScore} theme={theme} />
                ))}
              </div>
            </div>
          )}

          {/* Empty state */}
          {!loading && !error && !result && (
            <Card theme={theme} style={{ textAlign: "center", padding: 40 }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>📊</div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>Select a symbol to begin analysis</div>
            </Card>
          )}
        </>
      )}

      {activeTab === "batch" && (
        <div style={{ animation: "fadeIn 0.3s ease" }}>
          <Card theme={theme} style={{ textAlign: "center", padding: 30 }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>📍</div>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Market Scan table moved to 🔍 Analysis</div>
            <div style={{ fontSize: 11, color: theme.muted, marginBottom: 12 }}>
              Start the scan and review symbol rankings directly in the Analysis tab.
            </div>
            <button
              onClick={() => setActiveTab("analysis")}
              style={{
                padding: "8px 14px", borderRadius: 6, border: `1px solid ${theme.border}`,
                background: theme.bg, color: theme.text, cursor: "pointer", fontWeight: 700
              }}
            >
              Go to 🔍 Analysis
            </button>
          </Card>
        </div>
      )}

      {/* Persistence Monitor (Always visible) */}
      <div style={{ marginTop: 30 }}>
        <TechnicalTradeMonitor theme={theme} />
      </div>
    </div>
  );
}
