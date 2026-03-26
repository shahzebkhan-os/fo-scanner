import { useState, useEffect, useCallback } from "react";
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
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
      <div style={{ marginTop: 8, fontSize: 12 }}>Loading alert history...</div>
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
    <Card theme={theme} style={{
      textAlign: "center",
      padding: 12,
      flex: "1 1 120px",
    }}>
      {icon && <div style={{ fontSize: 16, marginBottom: 2 }}>{icon}</div>}
      <div style={{ fontSize: 22, fontWeight: 700, color: color || theme.text }}>{value}</div>
      <div style={{ fontSize: 10, color: theme.muted }}>{label}</div>
    </Card>
  );
}

function WinRateRing({ winRate, wins, losses, total, theme, size = 100 }) {
  const wr = Number(winRate) || 0;
  if (total === 0) return <div style={{ width: size, height: size, borderRadius: "50%", border: `3px solid ${theme.border}` }} />;
  
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
            data={data} dataKey="value" innerRadius={size * 0.35} outerRadius={size * 0.47}
            startAngle={90} endAngle={-270} paddingAngle={2} stroke="none"
          >
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div style={{
        position: "absolute", inset: 0, display: "flex",
        flexDirection: "column", alignItems: "center", justifyContent: "center",
        pointerEvents: "none",
      }}>
        <span style={{ fontSize: size * 0.2, fontWeight: 800, color: wr >= 50 ? "#22c55e" : "#ef4444" }}>
          {wr.toFixed(0)}%
        </span>
        <span style={{ fontSize: size * 0.08, color: theme.muted }}>Win Rate</span>
      </div>
    </div>
  );
}

export default function AlertTrackerTab({ theme }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all"); // all, open, closed

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // Use the existing paper-trades API which returns all trades include AUTO
      const statusFilter = filter === "all" ? "all" : filter;
      const result = await apiFetch(`/api/paper-trades?status=${statusFilter}`);
      
      // Filter for automated trades (those starting with "Auto:")
      if (result.trades) {
        result.trades = result.trades.filter(t => (t.reason || "").startsWith("Auto:"));
      }
      setData(result);
    } catch (e) {
      console.error("Failed to load alerts:", e);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) return <Loader theme={theme} />;

  const trades = data?.trades || [];
  const autoAcc = data?.auto_accuracy || {};
  
  // Stats
  const wins = trades.filter(t => t.status === "CLOSED" && (t.pnl || 0) > 0).length;
  const losses = trades.filter(t => t.status === "CLOSED" && (t.pnl || 0) <= 0).length;
  const closedCount = wins + losses;
  const winRate = closedCount > 0 ? (wins / closedCount) * 100 : 0;
  const totalPnl = trades.reduce((sum, t) => sum + (t.pnl || 0), 0);

  return (
    <div style={{ animation: "fadeIn 0.4s ease-out" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18 }}>🔔 Telegram Alert Tracker</h2>
          <div style={{ fontSize: 11, color: theme.muted }}>Live performance of "Good Entry" alerts dispatched to Telegram.</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {["all", "open", "closed"].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              style={{
                padding: "4px 12px", borderRadius: 6, border: `1px solid ${theme.border}`,
                background: filter === f ? "rgba(99,102,241,.15)" : "none",
                color: filter === f ? theme.accent : theme.muted, textTransform: "capitalize",
                cursor: "pointer", fontSize: 11, fontWeight: 600
              }}>
              {f}
            </button>
          ))}
          <button onClick={load} style={{
            padding: "4px 12px", borderRadius: 6, background: theme.accent, color: "#fff",
            border: "none", cursor: "pointer", fontSize: 11, fontWeight: 600
          }}>⟳ Refresh</button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center" }}>
        <Card theme={theme} style={{ display: "flex", alignItems: "center", gap: 16, padding: "12px 20px" }}>
          <WinRateRing winRate={autoAcc.win_rate || winRate} wins={autoAcc.wins || wins} losses={autoAcc.losses || losses} total={autoAcc.total || closedCount} theme={theme} />
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: theme.text }}>{autoAcc.total || closedCount}</div>
              <div style={{ fontSize: 9, color: theme.muted, textTransform: "uppercase" }}>Total Alerts</div>
            </div>
            <div style={{ width: 1, background: theme.border, height: 24, alignSelf: "center" }} />
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: (autoAcc.total_pnl || totalPnl) >= 0 ? theme.green : theme.red }}>
                ₹{Math.abs(autoAcc.total_pnl || totalPnl).toFixed(0)}
              </div>
              <div style={{ fontSize: 9, color: theme.muted, textTransform: "uppercase" }}>{ (autoAcc.total_pnl || totalPnl) >= 0 ? "Profit" : "Loss" }</div>
            </div>
          </div>
        </Card>
        
        <div style={{ display: "flex", gap: 10, flex: 1 }}>
          <StatCard label="Live Alerts" value={trades.filter(t => t.status === "OPEN").length} color={theme.accent} theme={theme} icon="📡" />
          <StatCard label="Avg Return" value={`${(autoAcc.avg_pnl_pct || 0).toFixed(1)}%`} color={(autoAcc.avg_pnl_pct || 0) >= 0 ? theme.green : theme.red} theme={theme} icon="📊" />
        </div>
      </div>

      <Card theme={theme} style={{ padding: 0, overflow: "hidden" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "1.2fr 0.8fr 0.8fr 1fr 1fr 1fr 1.5fr 0.8fr",
          background: theme.bg, padding: "10px 16px", fontSize: 11, fontWeight: 700,
          color: theme.muted, borderBottom: `1px solid ${theme.border}`, textTransform: "uppercase", letterSpacing: 0.5
        }}>
          <div>Symbol</div>
          <div>Entry</div>
          <div>Current</div>
          <div>P&L ₹</div>
          <div>P&L %</div>
          <div>Sent At</div>
          <div>Reason</div>
          <div style={{ textAlign: "right" }}>Status</div>
        </div>
        <div style={{ maxHeight: "calc(100vh - 350px)", overflowY: "auto" }}>
          {trades.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: theme.muted }}>No alerts found in this category.</div>
          ) : (
            trades.map(t => {
              const pnl = t.pnl || 0;
              const pnlPct = t.pnl_pct || 0;
              const isProfit = pnl >= 0;
              return (
                <div key={t.id} style={{
                  display: "grid", gridTemplateColumns: "1.2fr 0.8fr 0.8fr 1fr 1fr 1fr 1.5fr 0.8fr",
                  padding: "12px 16px", borderBottom: `1px solid ${theme.border}`, fontSize: 12,
                  alignItems: "center", transition: "background 0.2s", cursor: "default"
                }}>
                  <div style={{ fontWeight: 700, color: t.type === "CE" ? theme.green : theme.red }}>
                    {t.symbol} <span style={{ fontSize: 10, opacity: 0.8 }}>{t.type} {t.strike}</span>
                  </div>
                  <div>₹{Number(t.entry_price || 0).toFixed(2)}</div>
                  <div style={{ fontWeight: 600 }}>₹{Number(t.current_price || t.entry_price || 0).toFixed(2)}</div>
                  <div style={{ color: isProfit ? theme.green : theme.red, fontWeight: 700 }}>
                    {isProfit ? "+" : ""}₹{pnl.toFixed(2)}
                  </div>
                  <div style={{ color: isProfit ? theme.green : theme.red, fontWeight: 700 }}>
                    {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%
                  </div>
                  <div style={{ color: theme.muted, fontSize: 11 }}>
                    {new Date(t.entry_time + "Z").toLocaleString("en-IN", { timeZone: IST_TZ, hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" })}
                  </div>
                  <div style={{ fontSize: 10, color: theme.muted, fontStyle: "italic" }}>
                    {(t.reason || "").replace("Auto: ", "")}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span style={{
                      padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 700,
                      background: t.status === "OPEN" ? "rgba(99,102,241,.1)" : isProfit ? "rgba(34,197,94,.1)" : "rgba(239,68,68,.1)",
                      color: t.status === "OPEN" ? theme.accent : isProfit ? theme.green : theme.red,
                    }}>
                      {t.status}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Card>
    </div>
  );
}
