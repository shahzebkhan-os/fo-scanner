// AccuracyTab.jsx — Model Accuracy Tracking & Visualization
// Real-time and historical accuracy monitoring for prediction models
// Features: Live tracking, historical backtesting, detailed visualizations, configurable settings

import { useState, useEffect } from "react";
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, AreaChart, Area,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, Legend
} from "recharts";

const API = "";  // Same origin (uses Vite proxy in dev)

const COLORS = {
  primary: "#6366f1",
  success: "#22c55e",
  danger: "#ef4444",
  warning: "#f59e0b",
  info: "#3b82f6",
  purple: "#a855f7",
  cyan: "#06b6d4"
};

function DailyTradeCard({ trade, theme }) {
  const pnl = trade.current_price && trade.entry_price 
    ? ((trade.current_price - trade.entry_price) / trade.entry_price) * 100 
    : 0;
  
  const isProfit = pnl >= 0;

  return (
    <div style={{
      padding: 16,
      background: theme.card,
      border: `1px solid ${theme.border}`,
      borderRadius: 8,
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center"
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ fontWeight: 700, fontSize: 16, color: theme.text }}>{trade.symbol}</span>
          <span style={{ 
            fontSize: 10, 
            padding: "2px 6px", 
            borderRadius: 4,
            fontWeight: 700,
            background: trade.signal === "BULLISH" ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
            color: trade.signal === "BULLISH" ? COLORS.success : COLORS.danger
          }}>
            {trade.signal}
          </span>
          <span style={{ color: theme.muted, fontSize: 12, fontWeight: 500 }}>
            {trade.strike} {trade.option_type || "CE"}
          </span>
        </div>
        <div style={{ fontSize: 11, color: theme.muted }}>
          Captured: <b>{trade.snapshot_time ? new Date(trade.snapshot_time.replace(" ", "T")).toLocaleTimeString() : "—"}</b> | Score: <b>{trade.score}</b>
        </div>
      </div>

      <div style={{ textAlign: "right", minWidth: 140 }}>
        <div style={{ fontSize: 10, color: theme.muted, fontWeight: 700, textTransform: "uppercase", marginBottom: 2 }}>Current P&L</div>
        <div style={{ 
          fontSize: 22, 
          fontWeight: 800, 
          color: isProfit ? COLORS.success : COLORS.danger 
        }}>
          {isProfit ? "+" : ""}{pnl.toFixed(2)}%
        </div>
        <div style={{ fontSize: 11, color: theme.muted, fontWeight: 500 }}>
          ₹{trade.entry_price?.toFixed(2)} → <span style={{ color: theme.text }}>₹{trade.current_price?.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}

export default function AccuracyTab({ theme }) {
  const [view, setView] = useState("runs");  // runs, newRun, runDetail
  const [viewMode, setViewMode] = useState("DAILY"); // DAILY or MODEL
  const [runs, setRuns] = useState([]);
  const [dailyTrades, setDailyTrades] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [visualizations, setVisualizations] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Form state for new runs
  const [runType, setRunType] = useState("HISTORICAL");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  useEffect(() => {
    if (viewMode === "MODEL") loadRuns();
    if (viewMode === "DAILY") loadDailyTrades();
    loadConfig();
  }, [viewMode]);

  const loadDailyTrades = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API}/api/accuracy/today-trades`);
      const data = await response.json();
      setDailyTrades(data.trades || []);
    } catch (err) {
      console.error("Failed to load daily trades:", err);
      setError("Failed to load daily tracking data");
    } finally {
      setLoading(false);
    }
  };

  const loadRuns = async () => {
    try {
      const response = await fetch(`${API}/api/accuracy/runs`);
      const data = await response.json();
      setRuns(data.runs || []);
    } catch (err) {
      console.error("Failed to load runs:", err);
    }
  };

  const loadConfig = async () => {
    try {
      const response = await fetch(`${API}/api/accuracy/config`);
      const data = await response.json();
      setConfig(data);
    } catch (err) {
      console.error("Failed to load config:", err);
    }
  };

  const saveConfig = async (newConfig) => {
    try {
      await fetch(`${API}/api/accuracy/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newConfig)
      });
      setConfig(newConfig);
      alert("Configuration saved successfully!");
    } catch (err) {
      alert("Failed to save configuration");
      console.error(err);
    }
  };

  const startNewRun = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        run_type: runType,
        ...(runType === "HISTORICAL" && { start_date: startDate, end_date: endDate })
      });

      const response = await fetch(`${API}/api/accuracy/start?${params}`, {
        method: "POST"
      });

      const data = await response.json();

      if (data.success !== false) {
        alert(`Run started successfully! Run ID: ${data.run_id || data.summary?.run?.id}`);
        loadRuns();
        setView("runs");
      } else {
        setError(data.error || "Failed to start run");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadRunDetail = async (runId) => {
    setLoading(true);
    try {
      const [detailResponse, vizResponse] = await Promise.all([
        fetch(`${API}/api/accuracy/runs/${runId}`),
        fetch(`${API}/api/accuracy/runs/${runId}/visualizations`)
      ]);

      const detail = await detailResponse.json();
      const viz = await vizResponse.json();

      setRunDetail(detail);
      setVisualizations(viz);
      setSelectedRun(runId);
      setView("runDetail");
    } catch (err) {
      setError("Failed to load run details");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const finalizeRun = async (runId) => {
    try {
      await fetch(`${API}/api/accuracy/runs/${runId}/finalize`, { method: "POST" });
      loadRunDetail(runId);  // Reload to show updated stats
    } catch (err) {
      alert("Failed to finalize run");
      console.error(err);
    }
  };

  const renderDailySuggestions = () => (
    <div style={{ padding: 20 }}>
      {/* View Toggle */}
      <div style={{ 
        display: "flex", 
        gap: 12, 
        marginBottom: 24,
        background: theme.bg,
        padding: 4,
        borderRadius: 8,
        width: "fit-content"
      }}>
        <button
          onClick={() => setViewMode("DAILY")}
          style={{
            padding: "6px 16px",
            borderRadius: 6,
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
            border: "none",
            background: viewMode === "DAILY" ? theme.card : "transparent",
            color: viewMode === "DAILY" ? COLORS.primary : theme.muted,
            boxShadow: viewMode === "DAILY" ? "0 2px 8px rgba(0,0,0,0.1)" : "none",
            transition: "all 0.2s"
          }}
        >
          Daily Signal Tracking
        </button>
        <button
          onClick={() => setViewMode("MODEL")}
          style={{
            padding: "6px 16px",
            borderRadius: 6,
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
            border: "none",
            background: viewMode === "MODEL" ? theme.card : "transparent",
            color: viewMode === "MODEL" ? COLORS.primary : theme.muted,
            boxShadow: viewMode === "MODEL" ? "0 2px 8px rgba(0,0,0,0.1)" : "none",
            transition: "all 0.2s"
          }}
        >
          Model Performance Runs
        </button>
      </div>

      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: 20
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Real-time Signal Accuracy</h2>
          <div style={{ fontSize: 12, color: theme.muted, marginTop: 4 }}>
            Today's top-ranked signals and their intraday premium movement
          </div>
        </div>
        <button
          onClick={loadDailyTrades}
          disabled={loading}
          style={{
            padding: "8px 16px",
            background: "transparent",
            color: COLORS.primary,
            border: `1px solid ${COLORS.primary}`,
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 600
          }}
        >
          {loading ? "⟳ Refreshing..." : "Refresh Data"}
        </button>
      </div>

      {dailyTrades.length === 0 ? (
        <div style={{
          padding: 60,
          textAlign: "center",
          background: theme.card,
          borderRadius: 12,
          border: `1px solid ${theme.border}`
        }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>📊</div>
          <h3 style={{ margin: "0 0 8px 0" }}>No Data Yet</h3>
          <p style={{ color: theme.muted, margin: 0, fontSize: 14 }}>
            Intraday tracking snapshots are captured every 15 minutes during market hours.
          </p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {dailyTrades.map((trade) => (
            <DailyTradeCard key={trade.id} trade={trade} theme={theme} />
          ))}
        </div>
      )}
    </div>
  );

  // ── Render: Runs List ──────────────────────────────────────────────────────

  const renderRunsList = () => (
    <div style={{ padding: 20 }}>
      {/* View Toggle */}
      <div style={{ 
        display: "flex", 
        gap: 12, 
        marginBottom: 24,
        background: theme.bg,
        padding: 4,
        borderRadius: 8,
        width: "fit-content"
      }}>
        <button
          onClick={() => setViewMode("DAILY")}
          style={{
            padding: "6px 16px",
            borderRadius: 6,
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
            border: "none",
            background: viewMode === "DAILY" ? theme.card : "transparent",
            color: viewMode === "DAILY" ? COLORS.primary : theme.muted,
            boxShadow: viewMode === "DAILY" ? "0 2px 8px rgba(0,0,0,0.1)" : "none",
            transition: "all 0.2s"
          }}
        >
          Daily Signal Tracking
        </button>
        <button
          onClick={() => setViewMode("MODEL")}
          style={{
            padding: "6px 16px",
            borderRadius: 6,
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
            border: "none",
            background: viewMode === "MODEL" ? theme.card : "transparent",
            color: viewMode === "MODEL" ? COLORS.primary : theme.muted,
            boxShadow: viewMode === "MODEL" ? "0 2px 8px rgba(0,0,0,0.1)" : "none",
            transition: "all 0.2s"
          }}
        >
          Model Performance Runs
        </button>
      </div>

      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: 20
      }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>Accuracy Tracking Runs</h2>
        <button
          onClick={() => setView("newRun")}
          style={{
            padding: "8px 16px",
            background: COLORS.primary,
            color: "white",
            border: "none",
            borderRadius: 6,
            cursor: "pointer",
            fontWeight: 500
          }}
        >
          + New Run
        </button>
      </div>

      {runs.length === 0 ? (
        <div style={{
          padding: 40,
          textAlign: "center",
          background: theme.card,
          borderRadius: 8,
          border: `1px solid ${theme.border}`
        }}>
          <p style={{ color: theme.muted, margin: 0 }}>
            No accuracy runs yet. Start a new run to track model performance.
          </p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          {runs.map((run) => (
            <div
              key={run.id}
              onClick={() => loadRunDetail(run.id)}
              style={{
                padding: 16,
                background: theme.card,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                cursor: "pointer",
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-2px)";
                e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.1)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: 16 }}>Run #{run.id}</span>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: 4,
                        fontSize: 11,
                        background: run.run_type === "LIVE" ? "rgba(34,197,94,0.1)" : "rgba(59,130,246,0.1)",
                        color: run.run_type === "LIVE" ? COLORS.success : COLORS.info
                      }}
                    >
                      {run.run_type}
                    </span>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: 4,
                        fontSize: 11,
                        background: run.status === "COMPLETED" ? "rgba(34,197,94,0.1)" :
                                   run.status === "RUNNING" ? "rgba(245,158,11,0.1)" : "rgba(239,68,68,0.1)",
                        color: run.status === "COMPLETED" ? COLORS.success :
                               run.status === "RUNNING" ? COLORS.warning : COLORS.danger
                      }}
                    >
                      {run.status}
                    </span>
                  </div>

                  <div style={{ color: theme.muted, fontSize: 12, marginBottom: 4 }}>
                    Started: {new Date(run.start_time).toLocaleString()}
                  </div>

                  {run.date_range_start && run.date_range_end && (
                    <div style={{ color: theme.muted, fontSize: 12, marginBottom: 8 }}>
                      Date Range: {run.date_range_start} to {run.date_range_end}
                    </div>
                  )}

                  {run.status === "COMPLETED" && (
                    <div style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                      gap: 12,
                      marginTop: 12
                    }}>
                      <div>
                        <div style={{ fontSize: 11, color: theme.muted }}>Accuracy</div>
                        <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.success }}>
                          {run.accuracy_pct?.toFixed(1)}%
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 11, color: theme.muted }}>Win Rate</div>
                        <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.primary }}>
                          {(run.win_rate * 100)?.toFixed(1)}%
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 11, color: theme.muted }}>Predictions</div>
                        <div style={{ fontSize: 18, fontWeight: 600 }}>
                          {run.correct_predictions}/{run.total_predictions}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 11, color: theme.muted }}>Avg P&L</div>
                        <div style={{
                          fontSize: 18,
                          fontWeight: 600,
                          color: run.avg_profit_per_trade >= 0 ? COLORS.success : COLORS.danger
                        }}>
                          {run.avg_profit_per_trade >= 0 ? "+" : ""}{run.avg_profit_per_trade?.toFixed(2)}%
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // ── Render: New Run Form ───────────────────────────────────────────────────

  const renderNewRunForm = () => (
    <div style={{ padding: 20 }}>
      <button
        onClick={() => setView("runs")}
        style={{
          padding: "6px 12px",
          background: "transparent",
          color: theme.text,
          border: `1px solid ${theme.border}`,
          borderRadius: 6,
          cursor: "pointer",
          marginBottom: 20
        }}
      >
        ← Back to Runs
      </button>

      <div style={{
        maxWidth: 600,
        background: theme.card,
        border: `1px solid ${theme.border}`,
        borderRadius: 8,
        padding: 24
      }}>
        <h2 style={{ margin: "0 0 20px 0", fontSize: 20, fontWeight: 600 }}>Start New Accuracy Run</h2>

        {error && (
          <div style={{
            padding: 12,
            background: "rgba(239,68,68,0.1)",
            color: COLORS.danger,
            borderRadius: 6,
            marginBottom: 16
          }}>
            {error}
          </div>
        )}

        <div style={{ marginBottom: 20 }}>
          <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>Run Type</label>
          <select
            value={runType}
            onChange={(e) => setRunType(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px",
              background: theme.bg,
              color: theme.text,
              border: `1px solid ${theme.border}`,
              borderRadius: 6,
              fontSize: 14
            }}
          >
            <option value="HISTORICAL">Historical Backtest</option>
            <option value="LIVE">Live Tracking</option>
          </select>
          <div style={{ fontSize: 12, color: theme.muted, marginTop: 4 }}>
            {runType === "HISTORICAL"
              ? "Test accuracy on historical market_snapshots data"
              : "Track accuracy in real-time during market hours"}
          </div>
        </div>

        {runType === "HISTORICAL" && (
          <>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: theme.bg,
                  color: theme.text,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6,
                  fontSize: 14
                }}
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: theme.bg,
                  color: theme.text,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6,
                  fontSize: 14
                }}
              />
            </div>
          </>
        )}

        {config && (
          <div style={{
            padding: 16,
            background: theme.bg,
            borderRadius: 6,
            marginBottom: 20
          }}>
            <div style={{ fontWeight: 500, marginBottom: 12 }}>Current Settings</div>
            <div style={{ display: "grid", gap: 8, fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: theme.muted }}>Min Score Threshold:</span>
                <span>{config.min_score_threshold}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: theme.muted }}>Min Confidence:</span>
                <span>{config.min_confidence_threshold}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: theme.muted }}>Profit Target:</span>
                <span>{config.profit_target_pct}%</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: theme.muted }}>Stop Loss:</span>
                <span>{config.stop_loss_pct}%</span>
              </div>
            </div>
            <button
              onClick={() => setView("config")}
              style={{
                marginTop: 12,
                padding: "6px 12px",
                background: "transparent",
                color: COLORS.primary,
                border: `1px solid ${COLORS.primary}`,
                borderRadius: 6,
                cursor: "pointer",
                fontSize: 12,
                width: "100%"
              }}
            >
              Edit Settings
            </button>
          </div>
        )}

        <button
          onClick={startNewRun}
          disabled={loading || (runType === "HISTORICAL" && (!startDate || !endDate))}
          style={{
            width: "100%",
            padding: "12px",
            background: loading ? theme.muted : COLORS.primary,
            color: "white",
            border: "none",
            borderRadius: 6,
            cursor: loading ? "not-allowed" : "pointer",
            fontWeight: 600,
            fontSize: 15
          }}
        >
          {loading ? "Starting..." : "Start Run"}
        </button>
      </div>
    </div>
  );

  // ── Render: Run Detail ─────────────────────────────────────────────────────

  const renderRunDetail = () => {
    if (!runDetail || !visualizations) return null;

    const run = runDetail.run;
    const stats = runDetail.stats;

    return (
      <div style={{ padding: 20 }}>
        <button
          onClick={() => setView("runs")}
          style={{
            padding: "6px 12px",
            background: "transparent",
            color: theme.text,
            border: `1px solid ${theme.border}`,
            borderRadius: 6,
            cursor: "pointer",
            marginBottom: 20
          }}
        >
          ← Back to Runs
        </button>

        {/* Run Header */}
        <div style={{
          background: theme.card,
          border: `1px solid ${theme.border}`,
          borderRadius: 8,
          padding: 24,
          marginBottom: 20
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
                <h2 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>Run #{run.id}</h2>
                <span style={{
                  padding: "4px 12px",
                  borderRadius: 6,
                  fontSize: 12,
                  background: run.run_type === "LIVE" ? "rgba(34,197,94,0.1)" : "rgba(59,130,246,0.1)",
                  color: run.run_type === "LIVE" ? COLORS.success : COLORS.info
                }}>
                  {run.run_type}
                </span>
              </div>

              <div style={{ color: theme.muted, fontSize: 14 }}>
                {new Date(run.start_time).toLocaleString()}
                {run.end_time && ` — ${new Date(run.end_time).toLocaleString()}`}
              </div>

              {run.date_range_start && run.date_range_end && (
                <div style={{ color: theme.muted, fontSize: 14, marginTop: 4 }}>
                  Testing period: {run.date_range_start} to {run.date_range_end}
                </div>
              )}
            </div>

            {run.status === "RUNNING" && (
              <button
                onClick={() => finalizeRun(run.id)}
                style={{
                  padding: "8px 16px",
                  background: COLORS.primary,
                  color: "white",
                  border: "none",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontWeight: 500
                }}
              >
                Finalize Run
              </button>
            )}
          </div>

          {/* Key Metrics */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
            gap: 20,
            marginTop: 24
          }}>
            <div>
              <div style={{ fontSize: 12, color: theme.muted, marginBottom: 4 }}>Accuracy</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.success }}>
                {run.accuracy_pct?.toFixed(1)}%
              </div>
              <div style={{ fontSize: 11, color: theme.muted }}>
                {run.correct_predictions} / {run.total_predictions} correct
              </div>
            </div>

            <div>
              <div style={{ fontSize: 12, color: theme.muted, marginBottom: 4 }}>Win Rate</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.primary }}>
                {(run.win_rate * 100)?.toFixed(1)}%
              </div>
              <div style={{ fontSize: 11, color: theme.muted }}>
                Profitable trades
              </div>
            </div>

            <div>
              <div style={{ fontSize: 12, color: theme.muted, marginBottom: 4 }}>Avg P&L</div>
              <div style={{
                fontSize: 28,
                fontWeight: 700,
                color: run.avg_profit_per_trade >= 0 ? COLORS.success : COLORS.danger
              }}>
                {run.avg_profit_per_trade >= 0 ? "+" : ""}{run.avg_profit_per_trade?.toFixed(2)}%
              </div>
              <div style={{ fontSize: 11, color: theme.muted }}>
                Per trade average
              </div>
            </div>

            <div>
              <div style={{ fontSize: 12, color: theme.muted, marginBottom: 4 }}>Total Profit</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.success }}>
                +{run.total_profit?.toFixed(2)}%
              </div>
            </div>

            <div>
              <div style={{ fontSize: 12, color: theme.muted, marginBottom: 4 }}>Total Loss</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.danger }}>
                -{run.total_loss?.toFixed(2)}%
              </div>
            </div>
          </div>
        </div>

        {/* Visualizations */}
        {visualizations.timeline && visualizations.timeline.length > 0 && (
          <div style={{
            background: theme.card,
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            padding: 24,
            marginBottom: 20
          }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: 18, fontWeight: 600 }}>Accuracy Over Time</h3>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={visualizations.timeline}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                <XAxis
                  dataKey="time"
                  tickFormatter={(t) => new Date(t).toLocaleDateString()}
                  stroke={theme.muted}
                  style={{ fontSize: 11 }}
                />
                <YAxis stroke={theme.muted} style={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    background: theme.card,
                    border: `1px solid ${theme.border}`,
                    borderRadius: 6
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="accuracy"
                  stroke={COLORS.primary}
                  fill={COLORS.primary}
                  fillOpacity={0.3}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Score Accuracy Breakdown */}
        {visualizations.score_accuracy && visualizations.score_accuracy.ranges.length > 0 && (
          <div style={{
            background: theme.card,
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            padding: 24,
            marginBottom: 20
          }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: 18, fontWeight: 600 }}>Accuracy by Score Range</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={visualizations.score_accuracy.ranges.map((range, i) => ({
                range,
                accuracy: visualizations.score_accuracy.accuracy[i],
                count: visualizations.score_accuracy.counts[i]
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                <XAxis dataKey="range" stroke={theme.muted} style={{ fontSize: 11 }} />
                <YAxis stroke={theme.muted} style={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    background: theme.card,
                    border: `1px solid ${theme.border}`,
                    borderRadius: 6
                  }}
                />
                <Bar dataKey="accuracy" fill={COLORS.success} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* By Signal & Regime */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
          <div style={{
            background: theme.card,
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            padding: 24
          }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: 18, fontWeight: 600 }}>By Signal</h3>
            <div style={{ display: "grid", gap: 12 }}>
              {Object.entries(stats.by_signal || {}).map(([signal, data]) => (
                <div key={signal}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontWeight: 500 }}>{signal}</span>
                    <span style={{ color: COLORS.success }}>{(data.win_rate * 100).toFixed(1)}%</span>
                  </div>
                  <div style={{ fontSize: 12, color: theme.muted }}>
                    {data.wins}W / {data.losses}L ({data.predictions} total)
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{
            background: theme.card,
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            padding: 24
          }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: 18, fontWeight: 600 }}>By Regime</h3>
            <div style={{ display: "grid", gap: 12 }}>
              {Object.entries(stats.by_regime || {}).map(([regime, data]) => (
                <div key={regime}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontWeight: 500 }}>{regime}</span>
                    <span style={{ color: COLORS.primary }}>{(data.win_rate * 100).toFixed(1)}%</span>
                  </div>
                  <div style={{ fontSize: 12, color: theme.muted }}>
                    {data.wins}W / {data.losses}L ({data.predictions} total)
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Top Symbols */}
        {stats.by_symbol && Object.keys(stats.by_symbol).length > 0 && (
          <div style={{
            background: theme.card,
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            padding: 24
          }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: 18, fontWeight: 600 }}>Performance by Symbol</h3>
            <div style={{ display: "grid", gap: 8 }}>
              {Object.entries(stats.by_symbol)
                .sort(([, a], [, b]) => b.win_rate - a.win_rate)
                .slice(0, 10)
                .map(([symbol, data]) => (
                  <div
                    key={symbol}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      padding: "8px 12px",
                      background: theme.bg,
                      borderRadius: 6
                    }}
                  >
                    <span style={{ fontWeight: 500 }}>{symbol}</span>
                    <div style={{ display: "flex", gap: 16, fontSize: 13 }}>
                      <span style={{ color: COLORS.success }}>
                        {(data.win_rate * 100).toFixed(1)}% WR
                      </span>
                      <span style={{ color: theme.muted }}>
                        {data.wins}W / {data.losses}L
                      </span>
                      <span style={{
                        color: data.avg_pnl >= 0 ? COLORS.success : COLORS.danger
                      }}>
                        {data.avg_pnl >= 0 ? "+" : ""}{data.avg_pnl.toFixed(2)}% avg
                      </span>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── Render: Config Editor ──────────────────────────────────────────────────

  const renderConfigEditor = () => {
    if (!config) return null;

    const [editedConfig, setEditedConfig] = useState(config);

    return (
      <div style={{ padding: 20 }}>
        <button
          onClick={() => setView("newRun")}
          style={{
            padding: "6px 12px",
            background: "transparent",
            color: theme.text,
            border: `1px solid ${theme.border}`,
            borderRadius: 6,
            cursor: "pointer",
            marginBottom: 20
          }}
        >
          ← Back
        </button>

        <div style={{
          maxWidth: 600,
          background: theme.card,
          border: `1px solid ${theme.border}`,
          borderRadius: 8,
          padding: 24
        }}>
          <h2 style={{ margin: "0 0 20px 0", fontSize: 20, fontWeight: 600 }}>Accuracy Tracking Settings</h2>

          <div style={{ display: "grid", gap: 20 }}>
            <div>
              <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>
                Min Score Threshold
              </label>
              <input
                type="number"
                value={editedConfig.min_score_threshold}
                onChange={(e) => setEditedConfig({ ...editedConfig, min_score_threshold: parseInt(e.target.value) })}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: theme.bg,
                  color: theme.text,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6
                }}
              />
              <div style={{ fontSize: 12, color: theme.muted, marginTop: 4 }}>
                Only track predictions with score ≥ this value
              </div>
            </div>

            <div>
              <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>
                Min Confidence Threshold
              </label>
              <input
                type="number"
                step="0.01"
                value={editedConfig.min_confidence_threshold}
                onChange={(e) => setEditedConfig({ ...editedConfig, min_confidence_threshold: parseFloat(e.target.value) })}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: theme.bg,
                  color: theme.text,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6
                }}
              />
              <div style={{ fontSize: 12, color: theme.muted, marginTop: 4 }}>
                Only track predictions with confidence ≥ this value
              </div>
            </div>

            <div>
              <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>
                Profit Target %
              </label>
              <input
                type="number"
                step="1"
                value={editedConfig.profit_target_pct}
                onChange={(e) => setEditedConfig({ ...editedConfig, profit_target_pct: parseFloat(e.target.value) })}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: theme.bg,
                  color: theme.text,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6
                }}
              />
              <div style={{ fontSize: 12, color: theme.muted, marginTop: 4 }}>
                Mark prediction as WIN when profit reaches this %
              </div>
            </div>

            <div>
              <label style={{ display: "block", marginBottom: 8, fontWeight: 500 }}>
                Stop Loss %
              </label>
              <input
                type="number"
                step="1"
                value={editedConfig.stop_loss_pct}
                onChange={(e) => setEditedConfig({ ...editedConfig, stop_loss_pct: parseFloat(e.target.value) })}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: theme.bg,
                  color: theme.text,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6
                }}
              />
              <div style={{ fontSize: 12, color: theme.muted, marginTop: 4 }}>
                Mark prediction as LOSS when loss reaches this %
              </div>
            </div>
          </div>

          <button
            onClick={() => {
              saveConfig(editedConfig);
              setView("newRun");
            }}
            style={{
              width: "100%",
              padding: "12px",
              background: COLORS.primary,
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 15,
              marginTop: 24
            }}
          >
            Save Settings
          </button>
        </div>
      </div>
    );
  };

  // ── Main Render ────────────────────────────────────────────────────────────

  if (loading && !runDetail) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: theme.muted }}>
        Loading...
      </div>
    );
  }

  if (view === "runs") {
    return viewMode === "DAILY" ? renderDailySuggestions() : renderRunsList();
  }
  if (view === "newRun") return renderNewRunForm();
  if (view === "runDetail") return renderRunDetail();
  if (view === "config") return renderConfigEditor();

  return null;
}
