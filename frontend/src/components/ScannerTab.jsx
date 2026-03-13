import { useState, useEffect, useCallback } from "react";

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

        {/* Score Blend Panel (Phase: Frontend) */}
        {r.blend_weights && (
          <div style={{ marginTop: 8, padding: "6px 8px", background: "rgba(255,255,255,.04)", borderRadius: 4 }}>
            <div style={{ fontSize: 10, color: theme.muted, marginBottom: 4 }}>Score Blend</div>
            <div style={{ display: "flex", height: 14, borderRadius: 3, overflow: "hidden", gap: 1 }}>
              <span style={{
                background: "#3b82f6", fontSize: 9, display: "flex", alignItems: "center",
                padding: "0 4px", color: "#fff", width: `${Math.round(r.blend_weights.quant * 100)}%`, minWidth: 20
              }}>
                Q {Math.round(r.blend_weights.quant * 100)}%
              </span>
              {r.blend_weights.ml > 0.01 && (
                <span style={{
                  background: "#8b5cf6", fontSize: 9, display: "flex", alignItems: "center",
                  padding: "0 4px", color: "#fff", width: `${Math.round(r.blend_weights.ml * 100)}%`, minWidth: 20
                }}>
                  ML {Math.round(r.blend_weights.ml * 100)}%
                </span>
              )}
              {r.blend_weights.engine > 0.01 && (
                <span style={{
                  background: "#22c55e", fontSize: 9, display: "flex", alignItems: "center",
                  padding: "0 4px", color: "#fff", width: `${Math.round(r.blend_weights.engine * 100)}%`, minWidth: 20
                }}>
                  S {Math.round(r.blend_weights.engine * 100)}%
                </span>
              )}
            </div>
            {r.recommended_strategy && (
              <span style={{
                marginTop: 4, fontSize: 10, background: "rgba(59,130,246,.15)",
                color: "#3b82f6", padding: "2px 6px", borderRadius: 10, display: "inline-block"
              }}>
                {r.recommended_strategy}
              </span>
            )}
            {r.blackout && (
              <div style={{ fontSize: 10, color: "#f59e0b", marginTop: 4 }}>
                ⚠️ Event blackout active — no new signals
              </div>
            )}
          </div>
        )}

        {/* 12-Signal Breakdown (Collapsible) */}
        {r.individual_signals && Object.keys(r.individual_signals).length > 0 && (
          <details style={{ marginTop: 6 }}>
            <summary style={{ fontSize: 11, cursor: "pointer", color: theme.muted }}>
              12 Signals ▾
            </summary>
            <table style={{ width: "100%", fontSize: 11, marginTop: 4, borderCollapse: "collapse" }}>
              <tbody>
                {Object.entries(r.individual_signals).map(([name, sig]) => (
                  <tr key={name}>
                    <td style={{ padding: "2px 4px", borderBottom: "1px solid rgba(255,255,255,.05)" }}>{name}</td>
                    <td style={{
                      padding: "2px 4px", borderBottom: "1px solid rgba(255,255,255,.05)",
                      color: sig.score > 0.3 ? "#22c55e" : sig.score < -0.3 ? "#ef4444" : theme.muted
                    }}>
                      {Math.round(sig.score * 100)}
                    </td>
                    <td style={{ padding: "2px 4px", borderBottom: "1px solid rgba(255,255,255,.05)", color: theme.muted }}>
                      {Math.round(sig.confidence * 100)}%
                    </td>
                    <td style={{
                      padding: "2px 4px", borderBottom: "1px solid rgba(255,255,255,.05)",
                      color: "#aaa", fontSize: 10, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis"
                    }}>
                      {sig.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
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

export default function ScannerTab({ theme, onChain, onGreeks, onData }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [watchlist, setWatchlist] = useState([]);
  const [showWL, setShowWL] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [countdown, setCountdown] = useState(60);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [savingSnapshot, setSavingSnapshot] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiFetch("/api/scan?limit=51");
      const rows = r.data || [];
      setData(rows);
      if (onData) onData(rows);
      setLastUpdated(new Date());
      setCountdown(60);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [onData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { load(); return 60; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [autoRefresh, load]);

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
        <button onClick={() => { load(); setCountdown(60); }} disabled={loading}
          className="clickable-btn"
          style={{
            padding: "6px 14px", borderRadius: 6, background: theme.accent,
            color: "#fff", border: "none", cursor: "pointer"
          }}>
          {loading ? "⟳ Scanning..." : "⟳ Refresh"}
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

      {loading && <Loader theme={theme} />}

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
