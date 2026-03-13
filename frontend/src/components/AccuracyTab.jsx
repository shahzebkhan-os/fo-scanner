import { useState, useEffect, useMemo, useCallback } from "react";

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

const fmt = (n, d = 2) => Number(n || 0).toFixed(d);

/* ─── Small table for a single CSV session ─────────────────────────────────── */
function CsvSessionCard({ session, theme, onDelete }) {
  const [trades, setTrades] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    if (expanded) { setExpanded(false); return; }
    if (!trades) {
      setLoading(true);
      try {
        const res = await apiFetch(`/api/tracker/snapshot/${session.snapshot_id}/trades-with-history`);
        setTrades(res.trades || []);
      } catch (e) { console.error(e); }
      setLoading(false);
    }
    setExpanded(true);
  };

  const pnlColor = session.avg_pnl_pct >= 0 ? theme.green : theme.red;
  const created = session.created_at || "";
  const timeStr = created.replace("T", " ").slice(0, 19);

  return (
    <Card theme={theme} style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>📄 {session.filename}</span>
          <span style={{ fontSize: 12, color: theme.muted }}>{timeStr}</span>
          <Badge label={`${session.trade_count} trades`} color={theme.accent} bg={theme.bg} />
          <Badge label={`Avg Score: ${fmt(session.avg_score, 1)}`} color={theme.text} bg={theme.bg} />
          <span style={{ fontWeight: 700, fontSize: 13, color: pnlColor }}>
            Avg PnL: {session.avg_pnl_pct >= 0 ? "+" : ""}{fmt(session.avg_pnl_pct)}%
          </span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={toggle}
            style={{ padding: "6px 14px", borderRadius: 6, background: theme.accent + "22", color: theme.accent, border: `1px solid ${theme.border}`, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
            {expanded ? "▲ Collapse" : "▼ Expand"}
          </button>
          <a href={`/api/tracker/csv-exports/${session.id}/download`} download
            style={{ padding: "6px 14px", borderRadius: 6, background: theme.accent, color: "#fff", textDecoration: "none", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center" }}>
            ⬇️ CSV
          </a>
          <button onClick={() => onDelete(session.id)}
            style={{ padding: "6px 14px", borderRadius: 6, background: theme.red + "22", color: theme.red, border: `1px solid ${theme.border}`, cursor: "pointer", fontSize: 12, fontWeight: 600 }}>
            🗑️
          </button>
        </div>
      </div>

      {expanded && loading && <Loader theme={theme} />}

      {expanded && trades && !loading && (
        <div style={{ overflowX: "auto", marginTop: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ color: theme.muted, borderBottom: `2px solid ${theme.border}`, textAlign: "left" }}>
                <th style={{ padding: "8px 10px" }}>Symbol</th>
                <th style={{ padding: "8px 10px" }}>Contract</th>
                <th style={{ padding: "8px 10px", textAlign: "center" }}>Signal</th>
                <th style={{ padding: "8px 10px", textAlign: "center" }}>AI Prob</th>
                <th style={{ padding: "8px 10px", textAlign: "center" }}>Score</th>
                <th style={{ padding: "8px 10px" }}>Entry</th>
                <th style={{ padding: "8px 10px" }}>Current</th>
                <th style={{ padding: "8px 10px", textAlign: "right" }}>PnL %</th>
                <th style={{ padding: "8px 10px", textAlign: "right" }}>Max PnL %</th>
                <th style={{ padding: "8px 10px", textAlign: "center" }}>Updates</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t, idx) => {
                const pnl = t.pnl_pct || 0;
                const maxPnl = t.max_pnl_pct || 0;
                const histLen = (t.price_history || []).length;
                return (
                  <tr key={idx} style={{ borderBottom: `1px solid ${theme.border}` }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700 }}>{t.symbol}</td>
                    <td style={{ padding: "8px 10px" }}>
                      <Badge label={`${t.strike} ${t.type}`} color={t.type === "CE" ? theme.green : theme.red} bg={theme.bg} />
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "center" }}>
                      {t.signal && t.signal !== "NEUTRAL" && (
                        <Badge label={t.signal} color={t.signal === "BULLISH" ? theme.green : theme.red} bg={theme.bg} />
                      )}
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "center" }}>
                      {t.ml_prob !== null && t.ml_prob !== undefined ? (
                        <span style={{ color: t.ml_prob > 0.7 ? theme.green : t.ml_prob < 0.3 ? theme.red : theme.muted }}>
                          {fmt(t.ml_prob * 100, 0)}%
                        </span>
                      ) : "—"}
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "center" }}>{t.score}</td>
                    <td style={{ padding: "8px 10px" }}>₹{fmt(t.entry_price)}</td>
                    <td style={{ padding: "8px 10px" }}>₹{fmt(t.current_price || t.entry_price)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: pnl >= 0 ? theme.green : theme.red }}>
                      {pnl >= 0 ? "+" : ""}{fmt(pnl)}%
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 700, color: maxPnl >= 0 ? theme.green : theme.red }}>
                      {maxPnl >= 0 ? "+" : ""}{fmt(maxPnl)}%
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "center", color: theme.muted }}>{histLen}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/* ─── Main AccuracyTab ─────────────────────────────────────────────────────── */
export default function AccuracyTab({ theme }) {
  const [csvExports, setCsvExports] = useState([]);
  const [csvLoading, setCsvLoading] = useState(false);

  const loadCsvExports = useCallback(async () => {
    setCsvLoading(true);
    try {
      const res = await apiFetch("/api/tracker/csv-exports");
      setCsvExports(res.exports || []);
    } catch (e) { console.error(e); }
    setCsvLoading(false);
  }, []);

  useEffect(() => {
    loadCsvExports();
    const timer = setInterval(loadCsvExports, 60000);
    return () => clearInterval(timer);
  }, [loadCsvExports]);

  const deleteCsvExport = async (exportId) => {
    if (!confirm("Delete this CSV session?")) return;
    try {
      await apiFetch(`/api/tracker/csv-exports/${exportId}`, { method: "DELETE" });
      setCsvExports(prev => prev.filter(e => e.id !== exportId));
    } catch (e) { console.error(e); }
  };

  // Group CSV exports by date
  const groupedExports = useMemo(() => {
    const groups = {};
    for (const exp of csvExports) {
      const dateKey = (exp.created_at || "").slice(0, 10) || "Unknown";
      if (!groups[dateKey]) groups[dateKey] = [];
      groups[dateKey].push(exp);
    }
    return groups;
  }, [csvExports]);

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 18, color: theme.accent }}>Accuracy Tracker</h2>
      </div>

      {/* ── CSV Sessions View ──────────────────────────────────────────────── */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <p style={{ margin: 0, fontSize: 13, color: theme.muted }}>
            Auto-saved every 10 min · Prices updated every 5 min · {csvExports.length} session(s)
          </p>
          <button onClick={loadCsvExports} style={{ padding: "6px 14px", borderRadius: 6, background: theme.card, color: theme.accent, border: `1px solid ${theme.border}`, cursor: "pointer", fontSize: 12 }}>
            🔄 Refresh
          </button>
        </div>

        {csvLoading && <Loader theme={theme} />}

        {!csvLoading && csvExports.length === 0 && (
          <Card theme={theme} style={{ textAlign: "center", padding: 60, color: theme.muted }}>
            No CSV sessions yet. Sessions are auto-saved every 10 minutes during market hours.
          </Card>
        )}

        {!csvLoading && Object.entries(groupedExports).map(([dateKey, sessions]) => (
          <div key={dateKey} style={{ marginBottom: 20 }}>
            <h3 style={{ margin: "0 0 8px", fontSize: 14, color: theme.muted, borderBottom: `1px solid ${theme.border}`, paddingBottom: 6 }}>
              📅 {dateKey} — {sessions.length} session(s)
            </h3>
            {sessions.map(s => (
              <CsvSessionCard key={s.id} session={s} theme={theme} onDelete={deleteCsvExport} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
