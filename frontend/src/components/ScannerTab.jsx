import { useState, useEffect, useCallback, useRef } from "react";

const signalColor = (s) =>
  s === "BULLISH" ? "#22c55e" : s === "BEARISH" ? "#ef4444" : "#94a3b8";
const signalBg = (s) =>
  s === "BULLISH" ? "rgba(34,197,94,.15)" : s === "BEARISH" ? "rgba(239,68,68,.15)" : "rgba(148,163,184,.1)";

const fmt = (n, d = 2) => Number(n || 0).toFixed(d);
const pct = (n) => `${n >= 0 ? "+" : ""}${fmt(n, 1)}%`;

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
      <div style={{ marginTop: 8, fontSize: 12 }}>Loading...</div>
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

function ScoreDial({ score, theme, label: topLabel = null, subLabel: bottomLabel = null }) {
  const color = score >= 85 ? "#22c55e" : score >= 70 ? "#f59e0b" : score >= 50 ? "#fb923c" : "#ef4444";
  const defLabel = score >= 85 ? "HIGH" : score >= 70 ? "MED" : "LOW";
  const label = topLabel || defLabel;
  const pctValue = Math.min(100, score);
  return (
    <div style={{ textAlign: "center", minWidth: 52 }}>
      {bottomLabel && <div style={{ fontSize: 9, color: theme.muted, fontWeight: 700, marginBottom: 4 }}>{bottomLabel}</div>}
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
          <div style={{ display: "flex", gap: 10 }}>
            <ScoreDial score={r.score} theme={theme} subLabel="QUANT SCORE" />
            <ScoreDial score={r.ml_score || 0} theme={theme} subLabel="ML SCORE" />
          </div>
        </div>

        {r.uoa_detected && (
          <div style={{
            display: "flex", alignItems: "center", gap: 6, marginTop: 6,
            padding: "4px 8px", background: "rgba(239,68,68,.1)",
            border: "0.5px solid rgba(239,68,68,.3)", borderRadius: 4, fontSize: 11
          }}>
            <span>⚡</span>
            <span style={{ color: "#ef4444", fontWeight: 500 }}>
              UOA Detected: {r.uoa_side} at {r.uoa_strike}
            </span>
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 12 }}>
          {[["PCR", fmt(r.pcr, 3)], ["IV", `${fmt(r.iv)}%`], ["V/OI", fmt(r.vol_spike, 3)]].map(([k, v]) => (
            <div key={k} style={{ background: theme.bg, borderRadius: 6, padding: "6px 10px", textAlign: "center" }}>
              <div style={{ color: theme.muted, fontSize: 10 }}>{k}</div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{v}</div>
            </div>
          ))}
        </div>

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

        {r.max_pain && (
          <div style={{ marginTop: 8, fontSize: 11, color: theme.muted }}>
            Max Pain: <span style={{ color: theme.text }}>₹{r.max_pain}</span>
            {r.days_to_expiry && <span style={{ marginLeft: 8 }}>DTE: {r.days_to_expiry}d</span>}
          </div>
        )}

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

function GlobalSentimentPanel({ theme }) {
  const [sentiment, setSentiment] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiFetch("/api/market-sentiment");
      setSentiment(d);
    } catch (e) {
      console.error("GlobalSentiment fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 5 * 60 * 1000); // refresh every 5 min
    return () => clearInterval(timer);
  }, [load]);

  if (!sentiment && !loading) return null;
  if (loading && !sentiment) return null;

  const gc = sentiment?.global_cues || {};
  const md = sentiment?.market_data || {};
  const score = gc.score || 0;
  const sentLabel = gc.sentiment || "NEUTRAL";

  const sentColor =
    sentLabel.includes("BULLISH") ? "#22c55e" :
    sentLabel.includes("BEARISH") ? "#ef4444" : "#94a3b8";
  const sentBg =
    sentLabel.includes("BULLISH") ? "rgba(34,197,94,.08)" :
    sentLabel.includes("BEARISH") ? "rgba(239,68,68,.08)" : "rgba(148,163,184,.06)";

  const scoreBar = Math.round((score + 1) / 2 * 100); // map -1..+1 → 0..100

  const factors = [
    { label: "S&P 500", value: md.spx_change_pct != null ? `${md.spx_change_pct >= 0 ? "+" : ""}${Number(md.spx_change_pct).toFixed(2)}%` : "—", positive: md.spx_change_pct >= 0 },
    { label: "NASDAQ", value: md.nasdaq_change_pct != null ? `${md.nasdaq_change_pct >= 0 ? "+" : ""}${Number(md.nasdaq_change_pct).toFixed(2)}%` : "—", positive: md.nasdaq_change_pct >= 0 },
    { label: "DXY", value: md.dxy ? Number(md.dxy).toFixed(2) : "—", positive: null },
    { label: "Crude (WTI)", value: md.crude_oil ? `$${Number(md.crude_oil).toFixed(1)}` : "—", positive: null },
    { label: "USD/INR", value: md.usdinr ? Number(md.usdinr).toFixed(2) : "—", positive: null },
    { label: "CBOE VIX", value: md.cboe_vix ? Number(md.cboe_vix).toFixed(1) : "—", positive: md.cboe_vix > 0 && md.cboe_vix < 20 },
  ];

  return (
    <div style={{
      border: `1px solid ${theme.border}`,
      borderRadius: 8,
      padding: "12px 16px",
      marginBottom: 14,
      borderLeft: `3px solid ${sentColor}`,
      background: sentBg,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14 }}>🌐</span>
          <span style={{ fontWeight: 700, fontSize: 13 }}>Global Market Sentiment</span>
          <span style={{
            padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600,
            color: sentColor, background: `${sentColor}20`,
          }}>{sentLabel}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 10, color: theme.muted }}>GLOBAL SCORE</div>
            <div style={{ fontWeight: 700, fontSize: 14, color: sentColor }}>{score >= 0 ? "+" : ""}{score.toFixed(2)}</div>
          </div>
          <button onClick={load} disabled={loading}
            style={{
              background: "none", border: `1px solid ${theme.border}`,
              borderRadius: 4, color: theme.muted, cursor: "pointer",
              fontSize: 12, padding: "2px 7px",
            }}>
            {loading ? "⟳" : "↻"}
          </button>
        </div>
      </div>

      <div style={{
        height: 4, background: theme.border, borderRadius: 2, marginBottom: 10, overflow: "hidden",
      }}>
        <div style={{
          height: "100%", borderRadius: 2,
          width: `${scoreBar}%`,
          background: `linear-gradient(to right, #ef4444, #f59e0b, #22c55e)`,
          transition: "width 0.5s ease",
        }} />
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {factors.map(({ label, value, positive }) => (
          <div key={label} style={{
            background: theme.bg, borderRadius: 6,
            padding: "5px 10px", minWidth: 80, textAlign: "center",
            border: `1px solid ${theme.border}`,
          }}>
            <div style={{ fontSize: 9, color: theme.muted, marginBottom: 2 }}>{label}</div>
            <div style={{
              fontWeight: 600, fontSize: 12,
              color: positive === null ? theme.text : positive ? "#22c55e" : "#ef4444",
            }}>{value}</div>
          </div>
        ))}
      </div>

      {gc.reason && gc.reason !== "No significant global cues" && (
        <div style={{
          marginTop: 8, fontSize: 10, color: theme.muted,
          fontStyle: "italic", lineHeight: 1.4,
        }}>
          {gc.reason}
        </div>
      )}
      {md.last_updated && (
        <div style={{ marginTop: 6, fontSize: 9, color: theme.muted }}>
          Data: {new Date(md.last_updated).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })} IST
          {sentiment?.source_stale && <span style={{ color: "#f59e0b", marginLeft: 6 }}>⚠ stale</span>}
          {gc.time_multiplier != null && <span style={{ marginLeft: 6 }}>Weight: {Math.round(gc.time_multiplier * 100)}%</span>}
        </div>
      )}
    </div>
  );
}

export default function ScannerTab({ theme, onChain, onGreeks, onData, marketStatus }) {
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
  const [autoRefresh, setAutoRefresh] = useState(() => {
    // Default based on market status — will be updated once marketStatus is available
    return localStorage.getItem("autoRefresh") !== "false";
  });
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [scanProgress, setScanProgress] = useState(0);
  const eventSourceRef = useRef(null);
  const scanningRef = useRef(false);

  // Market-aware auto-scan: auto-enable when market opens, auto-disable when closed
  useEffect(() => {
    if (!marketStatus) return;
    if (marketStatus.open) {
      setAutoRefresh(true);
    } else {
      setAutoRefresh(false);
    }
  }, [marketStatus?.open]);

  const load = useCallback(() => {
    // Prevent duplicate scans — if already scanning, skip
    if (scanningRef.current) return;
    scanningRef.current = true;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setLoading(true);
    setData([]);
    setScanProgress(0);

    const API = "";
    const es = new EventSource(`${API}/api/scan-stream?limit=90`);
    eventSourceRef.current = es;
    const incoming = [];

    es.addEventListener("result", (e) => {
      try {
        const row = JSON.parse(e.data);
        incoming.push(row);
        setScanProgress(incoming.length);
        setData([...incoming].sort((a, b) => (b.score || 0) - (a.score || 0)));
      } catch (err) { console.error("SSE parse error:", err); }
    });

    es.addEventListener("done", (e) => {
      const sorted = [...incoming].sort((a, b) => (b.score || 0) - (a.score || 0));
      setData(sorted);
      if (onData) onData(sorted);
      setLastUpdated(new Date());
      setCountdown(scanInterval);
      setLoading(false);
      setScanProgress(0);
      scanningRef.current = false;
      es.close();
      eventSourceRef.current = null;
    });

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      apiFetch("/api/scan?limit=90")
        .then((r) => {
          const rows = r.data || [];
          setData(rows);
          if (onData) onData(rows);
          setLastUpdated(new Date());
          setCountdown(scanInterval);
        })
        .catch(console.error)
        .finally(() => { setLoading(false); setScanProgress(0); scanningRef.current = false; });
    };
  }, [onData, scanInterval]);

  // Save scan interval to localStorage
  const changeScanInterval = (secs) => {
    setScanInterval(secs);
    setCountdown(secs);
    localStorage.setItem("scanInterval", String(secs));
  };

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

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

  useEffect(() => { 
    load(); 
    apiFetch("/api/settings/watchlist").then(r => setWatchlist(r.watchlist || [])); 
  }, []);

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
    await fetch(`http://localhost:8000/api/settings/watchlist`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(next),
    });
  };

  const signalCounts = { ALL: data.length, BULLISH: 0, BEARISH: 0, NEUTRAL: 0 };
  data.forEach(r => { if (signalCounts[r.signal] !== undefined) signalCounts[r.signal]++; });

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={() => { load(); setCountdown(scanInterval); }} disabled={loading}
          className="clickable-btn"
          style={{
            padding: "6px 14px", borderRadius: 6, background: theme.accent,
            color: "#fff", border: "none", cursor: "pointer"
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
              height: "100%", background: theme.accent || "#6366f1", borderRadius: 2,
              width: `${Math.min(100, (scanProgress / 90) * 100)}%`,
              transition: "width 0.3s ease",
            }} />
          </div>
        </div>
      )}

      <GlobalSentimentPanel theme={theme} />

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
