import { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, ReferenceLine
} from "recharts";

async function apiFetch(path, options = {}) {
  const API = "";
  const r = await fetch(API + path, options);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function Loader({ theme }) {
  return (
    <div style={{ textAlign: "center", padding: 40, color: theme.muted }}>
      <div style={{ fontSize: 24, animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</div>
      <div style={{ marginTop: 8, fontSize: 12 }}>Loading ML details...</div>
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
const pctBar = (v) => `${fmt(v, 1)}%`;

export default function MLTab({ theme }) {
  const [details, setDetails] = useState(null);
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const [trainResult, setTrainResult] = useState(null);
  const [activeSection, setActiveSection] = useState("overview");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, p] = await Promise.all([
        apiFetch("/api/ml/details"),
        apiFetch("/api/ml/predictions"),
      ]);
      setDetails(d);
      setPredictions(p.predictions || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const trainModels = async () => {
    setTraining(true);
    setTrainResult(null);
    try {
      const result = await apiFetch("/api/ml/train", { method: "POST" });
      setTrainResult(result);
      load(); // Reload details after training
    } catch (e) {
      setTrainResult({ error: e.message });
    }
    setTraining(false);
  };

  if (loading) return <Loader theme={theme} />;
  if (!details) return <Card theme={theme}><div style={{ color: theme.muted, textAlign: "center" }}>Failed to load ML details. Is the backend running?</div></Card>;

  const sections = [
    { id: "overview", label: "Overview", icon: "🧠" },
    { id: "architecture", label: "Architecture", icon: "🏗" },
    { id: "training", label: "Training", icon: "⚡" },
    { id: "predictions", label: "Predictions", icon: "📊" },
    { id: "howto", label: "How to Run", icon: "📖" },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>🧠 ML Neural Network Dashboard</h2>
        <button onClick={load} style={{ padding: "6px 14px", borderRadius: 6, background: theme.accent, color: "#fff", border: "none", cursor: "pointer", fontSize: 12 }}>⟳ Refresh</button>
      </div>

      {/* Section Nav */}
      <div style={{ display: "flex", gap: 4, marginBottom: 16, overflowX: "auto" }}>
        {sections.map(s => (
          <button key={s.id} onClick={() => setActiveSection(s.id)}
            style={{
              padding: "8px 14px", borderRadius: 6, border: "none", cursor: "pointer",
              background: activeSection === s.id ? theme.accent : theme.card,
              color: activeSection === s.id ? "#fff" : theme.muted,
              fontWeight: activeSection === s.id ? 700 : 400,
              fontSize: 12, whiteSpace: "nowrap",
            }}>
            {s.icon} {s.label}
          </button>
        ))}
      </div>

      {activeSection === "overview" && <OverviewSection details={details} theme={theme} training={training} trainModels={trainModels} trainResult={trainResult} />}
      {activeSection === "architecture" && <ArchitectureSection details={details} theme={theme} />}
      {activeSection === "training" && <TrainingSection details={details} theme={theme} training={training} trainModels={trainModels} trainResult={trainResult} />}
      {activeSection === "predictions" && <PredictionsSection predictions={predictions} details={details} theme={theme} />}
      {activeSection === "howto" && <HowToRunSection details={details} theme={theme} />}
    </div>
  );
}


// ── Overview Section ──────────────────────────────────────────────────────────
function OverviewSection({ details, theme, training, trainModels, trainResult }) {
  const lgb = details.lgb || {};
  const nn = details.nn || {};
  const ens = details.ensemble || {};
  const data = details.training_data || {};

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Model Status Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
        <StatusCard
          theme={theme}
          icon="🌲"
          title="LightGBM"
          trained={lgb.trained}
          available={lgb.available}
          subtitle={lgb.trained ? `${lgb.num_trees || 200} trees` : lgb.available ? "Ready to train" : "lightgbm not installed"}
        />
        <StatusCard
          theme={theme}
          icon="🧬"
          title="Neural Network (LSTM)"
          trained={nn.trained}
          available={nn.available}
          subtitle={nn.trained ? "2-Layer LSTM + MLP" : nn.available ? "Ready to train" : "torch not installed"}
        />
        <StatusCard
          theme={theme}
          icon="🤖"
          title="Ensemble"
          trained={details.trained}
          available={lgb.available || nn.available}
          subtitle={details.trained ? ens.description : "Train models to enable"}
        />
      </div>

      {/* Ensemble Weights Visualization */}
      {details.trained && (
        <Card theme={theme}>
          <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>Ensemble Blend Weights</h3>
          <div style={{ display: "flex", gap: 4, height: 32, borderRadius: 6, overflow: "hidden" }}>
            <div style={{
              flex: ens.lgb_weight, background: lgb.trained ? "#22c55e" : "#374151",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontWeight: 700, fontSize: 12,
            }}>
              LightGBM {(ens.lgb_weight * 100).toFixed(0)}%
            </div>
            <div style={{
              flex: ens.nn_weight, background: nn.trained ? "#6366f1" : "#374151",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontWeight: 700, fontSize: 12,
            }}>
              LSTM NN {(ens.nn_weight * 100).toFixed(0)}%
            </div>
          </div>
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 8 }}>
            {ens.description}
            {(!lgb.trained || !nn.trained) && " • Missing models have their weight redistributed."}
          </div>
        </Card>
      )}

      {/* Training Data Summary */}
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>Training Data</h3>
        {data.available ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            <MetricBox theme={theme} label="Total Snapshots" value={data.total_rows?.toLocaleString()} color={data.ready_to_train ? "#22c55e" : "#f59e0b"} />
            <MetricBox theme={theme} label="Unique Symbols" value={data.unique_symbols} />
            <MetricBox theme={theme} label="Min Required" value={data.min_rows_required?.toLocaleString()} />
            <MetricBox theme={theme} label="Ready to Train" value={data.ready_to_train ? "✅ Yes" : "❌ No"} color={data.ready_to_train ? "#22c55e" : "#ef4444"} />
          </div>
        ) : (
          <div style={{ color: theme.muted, fontSize: 12 }}>
            No training data available. Run the scanner to collect market snapshots, or run a historical backfill.
          </div>
        )}
        {data.date_range && (
          <div style={{ fontSize: 11, color: theme.muted, marginTop: 8 }}>
            Date range: {data.date_range.from} → {data.date_range.to}
          </div>
        )}
      </Card>

      {/* Train Button */}
      <Card theme={theme} style={{ textAlign: "center" }}>
        <button
          onClick={trainModels}
          disabled={training}
          style={{
            padding: "12px 32px", borderRadius: 8, border: "none", cursor: training ? "wait" : "pointer",
            background: training ? "#374151" : "#6366f1", color: "#fff",
            fontWeight: 700, fontSize: 14,
          }}>
          {training ? "⏳ Training in progress..." : "⚡ Train LightGBM + Neural Network"}
        </button>
        <div style={{ fontSize: 11, color: theme.muted, marginTop: 8 }}>
          Auto-retrains daily at 15:45 IST (after market close)
        </div>
        {trainResult && <TrainResultBanner result={trainResult} theme={theme} />}
      </Card>

      {/* Feature Importances */}
      {lgb.feature_importances && (
        <Card theme={theme}>
          <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>LightGBM Feature Importances (% gain)</h3>
          <FeatureImportanceChart importances={lgb.feature_importances} theme={theme} />
        </Card>
      )}
    </div>
  );
}


// ── Architecture Section ─────────────────────────────────────────────────────
function ArchitectureSection({ details, theme }) {
  const lgb = details.lgb || {};
  const nn = details.nn || {};
  const ens = details.ensemble || {};

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* High-level diagram */}
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>Ensemble Architecture</h3>
        <div style={{ fontFamily: "monospace", fontSize: 12, lineHeight: 1.8, color: theme.fg, whiteSpace: "pre", overflowX: "auto" }}>
{`  ┌─────────────────┐    ┌──────────────────────────┐
  │  market_snapshot │───▶│  Feature Extraction (5-7) │
  │   (DB rows)      │    │  weighted_score, gex,     │
  └─────────────────┘    │  iv_skew, pcr, regime     │
                          └────────┬─────────┬────────┘
                                   │         │
                    ┌──────────────┘         └──────────────┐
                    ▼                                        ▼
          ┌─────────────────┐                   ┌────────────────────┐
          │    LightGBM     │                   │  LSTM Neural Net   │
          │  200 trees      │                   │  2-layer, h=64     │
          │  lr=0.05        │                   │  10-bar sequences  │
          │  (Point-in-time)│                   │  (Temporal pattern)│
          └────────┬────────┘                   └─────────┬──────────┘
                   │                                       │
                   │  P_lgb (calibrated)                   │  P_nn
                   │                                       │
                   ▼                                       ▼
          ┌──────────────────────────────────────────────────────┐
          │           Ensemble Blend                              │
          │  P = ${(ens.lgb_weight * 100).toFixed(0)}% × P_lgb + ${(ens.nn_weight * 100).toFixed(0)}% × P_nn                        │
          │  (If one model missing → 100% the other)             │
          └───────────────────────┬──────────────────────────────┘
                                  │
                                  ▼
                      P(bullish) ∈ [0, 1]`}
        </div>
      </Card>

      {/* LightGBM Details */}
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>🌲 LightGBM — Gradient Boosted Trees</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Model Type</div>
            <div style={{ fontSize: 11, color: theme.muted }}>{lgb.model_type}</div>
            <div style={{ fontSize: 12, fontWeight: 600, marginTop: 12, marginBottom: 8 }}>Features ({lgb.features?.length})</div>
            <ul style={{ fontSize: 11, color: theme.muted, margin: 0, paddingLeft: 16 }}>
              {lgb.features?.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Hyperparameters</div>
            <table style={{ fontSize: 11, color: theme.muted, width: "100%" }}>
              <tbody>
                {Object.entries(lgb.hyperparameters || {}).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ padding: "2px 8px 2px 0", fontWeight: 500 }}>{k}</td>
                    <td style={{ fontFamily: "monospace" }}>{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ fontSize: 12, fontWeight: 600, marginTop: 12, marginBottom: 4 }}>Calibration</div>
            <div style={{ fontSize: 11, color: theme.muted }}>{lgb.calibration}</div>
          </div>
        </div>
      </Card>

      {/* Neural Network Details */}
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>🧬 LSTM Neural Network</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Architecture</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, lineHeight: 1.8, color: theme.muted, whiteSpace: "pre" }}>
{`Input: (batch, ${nn.sequence_length}, ${nn.features?.length})
  ↓
LSTM Layer 1: h=${nn.architecture?.hidden_size}
  ↓
LSTM Layer 2: h=${nn.architecture?.hidden_size}
  ↓  (dropout=${nn.architecture?.dropout})
  ↓  [last time-step only]
FC Layer: ${nn.architecture?.hidden_size} → ${nn.architecture?.mlp_hidden}
  ↓  ReLU
FC Layer: ${nn.architecture?.mlp_hidden} → 1
  ↓  Sigmoid
Output: P(bullish)`}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Sequence Features ({nn.features?.length})</div>
            <ul style={{ fontSize: 11, color: theme.muted, margin: 0, paddingLeft: 16 }}>
              {nn.features?.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
            <div style={{ fontSize: 12, fontWeight: 600, marginTop: 12, marginBottom: 8 }}>Training Hyperparameters</div>
            <table style={{ fontSize: 11, color: theme.muted, width: "100%" }}>
              <tbody>
                {Object.entries(nn.hyperparameters || {}).map(([k, v]) => (
                  <tr key={k}>
                    <td style={{ padding: "2px 8px 2px 0", fontWeight: 500 }}>{k}</td>
                    <td style={{ fontFamily: "monospace" }}>{String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Card>
    </div>
  );
}


// ── Training Section ─────────────────────────────────────────────────────────
function TrainingSection({ details, theme, training, trainModels, trainResult }) {
  const data = details.training_data || {};
  const lgb = details.lgb || {};
  const schedule = details.schedule || {};

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* Training Data Status */}
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>Training Data Status</h3>
        {data.available ? (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 16 }}>
              <MetricBox theme={theme} label="Total Snapshots" value={data.total_rows?.toLocaleString()} color={data.ready_to_train ? "#22c55e" : "#f59e0b"} />
              <MetricBox theme={theme} label="Unique Symbols" value={data.unique_symbols} />
              <MetricBox theme={theme} label="Min Required" value={data.min_rows_required?.toLocaleString()} />
            </div>
            {data.date_range && (
              <div style={{ fontSize: 11, color: theme.muted }}>
                Data range: {data.date_range.from} → {data.date_range.to}
              </div>
            )}
            {data.regime_distribution && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Regime Distribution</div>
                <div style={{ display: "flex", gap: 12 }}>
                  {Object.entries(data.regime_distribution).map(([regime, count]) => (
                    <div key={regime} style={{
                      padding: "6px 12px", borderRadius: 6,
                      background: theme.bg, textAlign: "center"
                    }}>
                      <div style={{ fontSize: 10, color: theme.muted }}>{regime}</div>
                      <div style={{ fontWeight: 700, fontSize: 14 }}>{count.toLocaleString()}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <div style={{ color: theme.muted, fontSize: 12, padding: 16, textAlign: "center" }}>
            No training data available. Run the scanner or a historical backfill to collect market snapshots.
          </div>
        )}
      </Card>

      {/* Train Controls */}
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>Train Models</h3>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <button
            onClick={trainModels}
            disabled={training || !data.ready_to_train}
            style={{
              padding: "12px 24px", borderRadius: 8, border: "none",
              cursor: training || !data.ready_to_train ? "not-allowed" : "pointer",
              background: training ? "#374151" : !data.ready_to_train ? "#374151" : "#6366f1",
              color: "#fff", fontWeight: 700, fontSize: 13,
            }}>
            {training ? "⏳ Training..." : "⚡ Train LightGBM + Neural Network"}
          </button>
          <div style={{ fontSize: 11, color: theme.muted }}>
            {!data.ready_to_train
              ? `Need ${data.min_rows_required} snapshots (have ${data.total_rows || 0})`
              : "Both models will be trained together. This may take 1-3 minutes."}
          </div>
        </div>
        {trainResult && <TrainResultBanner result={trainResult} theme={theme} />}
      </Card>

      {/* Schedule */}
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>Training Schedule</h3>
        <div style={{ fontSize: 12, color: theme.muted, lineHeight: 1.8 }}>
          <div><strong>Auto-retrain:</strong> {schedule.auto_retrain}</div>
          <div><strong>Manual trigger:</strong> <code style={{ background: theme.bg, padding: "2px 6px", borderRadius: 4 }}>POST {schedule.manual_train}</code></div>
          <div><strong>Min data required:</strong> {schedule.min_rows} market snapshots</div>
          <div style={{ marginTop: 8 }}>
            <strong>Training pipeline:</strong>
          </div>
          <ol style={{ paddingLeft: 20, marginTop: 4 }}>
            <li>Load market_snapshots from DB (score, GEX, IV skew, PCR, regime)</li>
            <li>Create next-bar labels (bullish = next close {">"} current close)</li>
            <li>Time-series cross-validation (no future data leakage)</li>
            <li>Train LightGBM (200 trees, early stopping)</li>
            <li>Calibrate with isotonic regression</li>
            <li>Build sliding-window sequences (10 bars per symbol)</li>
            <li>Train LSTM neural network (30 epochs, patience=5)</li>
            <li>Save only if CV loss {"<"} 0.693 (better than random coin flip)</li>
          </ol>
        </div>
      </Card>

      {/* Feature Importances */}
      {lgb.feature_importances && (
        <Card theme={theme}>
          <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>LightGBM Feature Importances</h3>
          <FeatureImportanceChart importances={lgb.feature_importances} theme={theme} />
        </Card>
      )}
    </div>
  );
}


// ── Predictions Section ──────────────────────────────────────────────────────
function PredictionsSection({ predictions, details, theme }) {
  if (!predictions.length) {
    return (
      <Card theme={theme} style={{ textAlign: "center", color: theme.muted, padding: 32 }}>
        No predictions available. Train the models and run the scanner first.
      </Card>
    );
  }

  const signalColor = (s) => s === "BULLISH" ? "#22c55e" : s === "BEARISH" ? "#ef4444" : "#f59e0b";

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>Per-Symbol Prediction Breakdown</h3>
        <div style={{ fontSize: 11, color: theme.muted, marginBottom: 12 }}>
          Showing LightGBM vs Neural Network individual probabilities and the ensemble blend for each symbol.
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${theme.border}` }}>
                <th style={{ textAlign: "left", padding: "8px 12px", color: theme.muted, fontWeight: 600 }}>Symbol</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: theme.muted, fontWeight: 600 }}>Spot</th>
                <th style={{ textAlign: "center", padding: "8px 12px", color: theme.muted, fontWeight: 600 }}>Regime</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: "#22c55e", fontWeight: 600 }}>🌲 LGB P(bull)</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: "#6366f1", fontWeight: 600 }}>🧬 NN P(bull)</th>
                <th style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600 }}>🤖 Ensemble</th>
                <th style={{ textAlign: "center", padding: "8px 12px", fontWeight: 600 }}>Signal</th>
                <th style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>Blend</th>
              </tr>
            </thead>
            <tbody>
              {predictions.map((p, i) => {
                const lgbW = details.ensemble?.lgb_weight || 0.6;
                const nnW = details.ensemble?.nn_weight || 0.4;
                const hasLgb = p.lgb_probability != null;
                const hasNn = p.nn_probability != null;
                return (
                  <tr key={i} style={{ borderBottom: `1px solid ${theme.border}22` }}>
                    <td style={{ padding: "8px 12px", fontWeight: 700 }}>{p.symbol}</td>
                    <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace" }}>{fmt(p.spot_price, 1)}</td>
                    <td style={{ padding: "8px 12px", textAlign: "center" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600, background: theme.bg }}>{p.regime}</span>
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace", color: hasLgb ? "#22c55e" : theme.muted }}>
                      {hasLgb ? fmt(p.lgb_probability * 100, 1) + "%" : "—"}
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace", color: hasNn ? "#6366f1" : theme.muted }}>
                      {hasNn ? fmt(p.nn_probability * 100, 1) + "%" : "—"}
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace", fontWeight: 700 }}>
                      {p.ensemble_probability != null ? fmt(p.ensemble_probability * 100, 1) + "%" : "—"}
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "center" }}>
                      <span style={{ color: signalColor(p.signal), fontWeight: 700, fontSize: 11 }}>{p.signal}</span>
                    </td>
                    <td style={{ padding: "8px 12px", minWidth: 100 }}>
                      {hasLgb && hasNn && (
                        <div style={{ display: "flex", gap: 1, height: 14, borderRadius: 3, overflow: "hidden" }}>
                          <div style={{ flex: lgbW, background: "#22c55e", opacity: 0.8 }} title={`LGB: ${(lgbW * 100).toFixed(0)}%`} />
                          <div style={{ flex: nnW, background: "#6366f1", opacity: 0.8 }} title={`NN: ${(nnW * 100).toFixed(0)}%`} />
                        </div>
                      )}
                      {hasLgb && !hasNn && <div style={{ height: 14, borderRadius: 3, background: "#22c55e", opacity: 0.5 }} title="LGB only" />}
                      {!hasLgb && hasNn && <div style={{ height: 14, borderRadius: 3, background: "#6366f1", opacity: 0.5 }} title="NN only" />}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Prediction Distribution Chart */}
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 12px 0" }}>Ensemble Probability Distribution</h3>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={predictions.filter(p => p.ensemble_probability != null).map(p => ({
            symbol: p.symbol,
            probability: +(p.ensemble_probability * 100).toFixed(1),
          }))}>
            <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
            <XAxis dataKey="symbol" tick={{ fontSize: 10, fill: theme.muted }} angle={-45} textAnchor="end" height={60} />
            <YAxis tick={{ fontSize: 10, fill: theme.muted }} domain={[0, 100]} />
            <Tooltip contentStyle={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 8, fontSize: 12 }} />
            <ReferenceLine y={50} stroke={theme.muted} strokeDasharray="3 3" label={{ value: "50% neutral", fill: theme.muted, fontSize: 10 }} />
            <Bar dataKey="probability" name="P(bullish) %" radius={[4, 4, 0, 0]}>
              {predictions.filter(p => p.ensemble_probability != null).map((p, i) => (
                <Cell key={i} fill={p.ensemble_probability > 0.55 ? "#22c55e" : p.ensemble_probability < 0.45 ? "#ef4444" : "#f59e0b"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}

// ── How to Run Section ───────────────────────────────────────────────────────
function HowToRunSection({ details, theme }) {
  const data = details.training_data || {};

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Card theme={theme}>
        <h3 style={{ fontSize: 14, margin: "0 0 16px 0" }}>📖 How to Run the ML Neural Network</h3>
        <div style={{ fontSize: 12, color: theme.muted, lineHeight: 1.8 }}>
          <h4 style={{ color: theme.fg, fontSize: 13, marginTop: 0 }}>Step 1: Install Dependencies</h4>
          <code style={{ display: "block", background: theme.bg, padding: 12, borderRadius: 6, marginBottom: 12, whiteSpace: "pre-wrap" }}>
{`pip install lightgbm scikit-learn pandas
pip install torch          # For LSTM Neural Network`}
          </code>

          <h4 style={{ color: theme.fg, fontSize: 13 }}>Step 2: Collect Training Data</h4>
          <p>The ML models need at least <strong>{data.min_rows_required || 500}</strong> market snapshots in the database.
          You currently have <strong>{data.total_rows?.toLocaleString() || 0}</strong> snapshots.</p>
          <p>Data is collected automatically every time the scanner runs. You can also run a historical backfill:</p>
          <code style={{ display: "block", background: theme.bg, padding: 12, borderRadius: 6, marginBottom: 12, whiteSpace: "pre-wrap" }}>
{`# In the UI: Go to Settings tab → Historical Backfill
# Or via API:
curl -X POST http://localhost:8000/api/backfill/start`}
          </code>

          <h4 style={{ color: theme.fg, fontSize: 13 }}>Step 3: Train the Models</h4>
          <p>There are three ways to trigger training:</p>
          <ol style={{ paddingLeft: 20 }}>
            <li><strong>This UI:</strong> Click the <em>"Train LightGBM + Neural Network"</em> button in the Overview or Training section above.</li>
            <li><strong>Scanner tab:</strong> The Scanner tab shows an ML status banner with a Train button.</li>
            <li><strong>API call:</strong>
              <code style={{ display: "block", background: theme.bg, padding: 8, borderRadius: 6, margin: "8px 0", whiteSpace: "pre-wrap" }}>
{`curl -X POST http://localhost:8000/api/ml/train`}
              </code>
            </li>
          </ol>
          <p>Training runs both LightGBM and LSTM together. It takes 1-3 minutes depending on data size.</p>

          <h4 style={{ color: theme.fg, fontSize: 13 }}>Step 4: Automatic Retraining</h4>
          <p>Once trained, the models <strong>auto-retrain daily at 15:45 IST</strong> (after market close) via the built-in scheduler. No manual intervention needed.</p>

          <h4 style={{ color: theme.fg, fontSize: 13 }}>Step 5: Using Predictions</h4>
          <p>Once trained, ML predictions are automatically used in the Scanner:</p>
          <ul style={{ paddingLeft: 20 }}>
            <li><strong>ML Score dial</strong> — appears next to the Quant Score in each symbol card</li>
            <li><strong>AI Confirmation</strong> — boosts score by +5 when both Quant and ML agree on high probability</li>
            <li><strong>AI Divergence Guard</strong> — downgrades signal to NEUTRAL when Quant and ML disagree</li>
            <li><strong>Auto-trade gate</strong> — paper trades require ML probability {">"} 65% (bull) or {"<"} 35% (bear)</li>
          </ul>

          <h4 style={{ color: theme.fg, fontSize: 13 }}>API Endpoints</h4>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${theme.border}` }}>
                <th style={{ textAlign: "left", padding: "6px 12px" }}>Endpoint</th>
                <th style={{ textAlign: "left", padding: "6px 12px" }}>Method</th>
                <th style={{ textAlign: "left", padding: "6px 12px" }}>Description</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["/api/ml/status", "GET", "Check model training status"],
                ["/api/ml/details", "GET", "Full model architecture, metrics, data stats"],
                ["/api/ml/train", "POST", "Train LightGBM + LSTM Neural Network"],
                ["/api/ml/predictions", "GET", "Per-symbol prediction breakdown"],
              ].map(([ep, m, d], i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${theme.border}22` }}>
                  <td style={{ padding: "6px 12px", fontFamily: "monospace" }}>{ep}</td>
                  <td style={{ padding: "6px 12px" }}>{m}</td>
                  <td style={{ padding: "6px 12px", color: theme.muted }}>{d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}


// ── Shared Components ────────────────────────────────────────────────────────

function StatusCard({ theme, icon, title, trained, available, subtitle }) {
  const borderColor = trained ? "#22c55e" : available ? "#f59e0b" : "#ef4444";
  return (
    <div style={{
      background: theme.card, border: `1px solid ${borderColor}33`,
      borderRadius: 8, padding: 16, textAlign: "center",
    }}>
      <div style={{ fontSize: 28 }}>{icon}</div>
      <div style={{ fontWeight: 700, fontSize: 13, marginTop: 6 }}>{title}</div>
      <div style={{
        fontSize: 11, fontWeight: 600, marginTop: 4,
        color: trained ? "#22c55e" : available ? "#f59e0b" : "#ef4444",
      }}>
        {trained ? "✅ Trained" : available ? "⚠️ Not Trained" : "❌ Unavailable"}
      </div>
      <div style={{ fontSize: 10, color: theme.muted, marginTop: 4 }}>{subtitle}</div>
    </div>
  );
}

function MetricBox({ theme, label, value, color }) {
  return (
    <div style={{ background: theme.bg, borderRadius: 6, padding: "8px 12px", textAlign: "center" }}>
      <div style={{ fontSize: 10, color: theme.muted }}>{label}</div>
      <div style={{ fontWeight: 700, fontSize: 16, color: color || theme.fg }}>{value}</div>
    </div>
  );
}

function TrainResultBanner({ result, theme }) {
  const isError = !!result.error;
  return (
    <div style={{
      marginTop: 12, padding: 12, borderRadius: 6,
      background: isError ? "rgba(239,68,68,.1)" : "rgba(34,197,94,.1)",
      border: `1px solid ${isError ? "rgba(239,68,68,.3)" : "rgba(34,197,94,.3)"}`,
      fontSize: 12,
    }}>
      {isError ? (
        <div style={{ color: "#ef4444" }}>❌ {result.error}</div>
      ) : (
        <div>
          <div style={{ color: "#22c55e", fontWeight: 600 }}>✅ Training Complete!</div>
          <div style={{ marginTop: 6, color: theme.muted }}>
            <strong>LightGBM:</strong> CV Loss = {result.cv_log_loss_mean} (±{result.cv_log_loss_std}) | Rows: {result.training_rows?.toLocaleString()}
          </div>
          {result.nn && !result.nn.error && (
            <div style={{ color: theme.muted }}>
              <strong>LSTM NN:</strong> CV Loss = {result.nn.nn_cv_log_loss_mean} (±{result.nn.nn_cv_log_loss_std}) | Sequences: {result.nn.nn_training_sequences?.toLocaleString()}
            </div>
          )}
          {result.nn?.error && (
            <div style={{ color: "#f59e0b" }}>⚠️ NN: {result.nn.error}</div>
          )}
        </div>
      )}
    </div>
  );
}

function FeatureImportanceChart({ importances, theme }) {
  const data = Object.entries(importances)
    .map(([name, value]) => ({ name, value: +value }))
    .sort((a, b) => b.value - a.value);

  const colors = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#ec4899", "#06b6d4", "#8b5cf6"];

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, data.length * 36)}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
        <XAxis type="number" tick={{ fontSize: 10, fill: theme.muted }} tickFormatter={pctBar} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: theme.muted }} width={120} />
        <Tooltip
          contentStyle={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 8, fontSize: 12 }}
          formatter={(v) => [`${fmt(v, 1)}%`, "Importance"]}
        />
        <Bar dataKey="value" name="Importance %" radius={[0, 4, 4, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={colors[i % colors.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
