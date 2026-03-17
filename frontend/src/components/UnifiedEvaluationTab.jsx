// UnifiedEvaluationTab.jsx - Unified Market Evaluation combining all models
// Displays the best F&O option per stock with unified scoring

import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from "recharts";

const API = "";

const UnifiedEvaluationTab = ({ darkMode }) => {
  const [loading, setLoading] = useState(false);
  const [evaluations, setEvaluations] = useState([]);
  const [accuracy, setAccuracy] = useState(null);
  const [includeTechnical, setIncludeTechnical] = useState(false);
  const [selectedStock, setSelectedStock] = useState(null);
  const [modelWeights, setModelWeights] = useState({});
  const [lastUpdate, setLastUpdate] = useState(null);
  const [accuracyLoading, setAccuracyLoading] = useState(false);

  // Theme colors
  const bg = darkMode ? "#1e293b" : "#ffffff";
  const cardBg = darkMode ? "#334155" : "#f8fafc";
  const text = darkMode ? "#f1f5f9" : "#1e293b";
  const border = darkMode ? "#475569" : "#e2e8f0";
  const mutedText = darkMode ? "#94a3b8" : "#64748b";

  const fetchEvaluations = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/unified-evaluation?include_technical=${includeTechnical}`);
      const data = await res.json();
      setEvaluations(data.evaluations || []);
      setModelWeights(data.model_weights || {});
      setLastUpdate(data.timestamp);
    } catch (err) {
      console.error("Failed to fetch unified evaluations:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAccuracy = async () => {
    setAccuracyLoading(true);
    try {
      const res = await fetch(`${API}/api/unified-evaluation/accuracy?min_unified_score=70&min_confidence=0.65&days_back=7`);
      const data = await res.json();
      setAccuracy(data);
    } catch (err) {
      console.error("Failed to fetch accuracy:", err);
    } finally {
      setAccuracyLoading(false);
    }
  };

  useEffect(() => {
    fetchEvaluations();
    fetchAccuracy();
  }, [includeTechnical]);

  const signalColor = (signal) => {
    if (signal === "BULLISH") return "#22c55e";
    if (signal === "BEARISH") return "#ef4444";
    return "#94a3b8";
  };

  const getScoreColor = (score) => {
    if (score >= 80) return "#22c55e";
    if (score >= 70) return "#3b82f6";
    if (score >= 60) return "#f59e0b";
    if (score >= 50) return "#94a3b8";
    return "#ef4444";
  };

  const getConfidenceLabel = (conf) => {
    if (conf >= 0.85) return "VERY HIGH";
    if (conf >= 0.75) return "HIGH";
    if (conf >= 0.65) return "MODERATE";
    if (conf >= 0.55) return "LOW";
    return "VERY LOW";
  };

  const renderModelWeights = () => {
    if (!modelWeights || Object.keys(modelWeights).length === 0) return null;

    const data = Object.entries(modelWeights).map(([model, weight]) => ({
      name: model.replace(/_/g, " ").toUpperCase(),
      value: weight * 100,
    }));

    return (
      <div style={{ background: cardBg, padding: "20px", borderRadius: "8px", border: `1px solid ${border}`, marginBottom: "20px" }}>
        <h3 style={{ color: text, marginBottom: "15px", fontSize: "16px", fontWeight: "600" }}>Model Weights</h3>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={70}
              label={(entry) => `${entry.name}: ${entry.value}%`}
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={["#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#ec4899"][index % 5]} />
              ))}
            </Pie>
            <Tooltip contentStyle={{ background: cardBg, border: `1px solid ${border}` }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  };

  const renderAccuracy = () => {
    if (!accuracy || accuracyLoading) {
      return (
        <div style={{ background: cardBg, padding: "20px", borderRadius: "8px", border: `1px solid ${border}`, marginBottom: "20px" }}>
          <h3 style={{ color: text, marginBottom: "15px", fontSize: "16px", fontWeight: "600" }}>Accuracy Tracking</h3>
          <p style={{ color: mutedText, fontSize: "14px" }}>
            {accuracyLoading ? "Loading accuracy data..." : "No accuracy data available"}
          </p>
        </div>
      );
    }

    const overall = accuracy.overall || {};

    return (
      <div style={{ background: cardBg, padding: "20px", borderRadius: "8px", border: `1px solid ${border}`, marginBottom: "20px" }}>
        <h3 style={{ color: text, marginBottom: "15px", fontSize: "16px", fontWeight: "600" }}>
          Accuracy Tracking (Last {accuracy.period_days || 7} Days)
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "15px", marginBottom: "15px" }}>
          <div>
            <div style={{ color: mutedText, fontSize: "12px", marginBottom: "5px" }}>Total Predictions</div>
            <div style={{ color: text, fontSize: "20px", fontWeight: "600" }}>{overall.total_predictions || 0}</div>
          </div>
          <div>
            <div style={{ color: mutedText, fontSize: "12px", marginBottom: "5px" }}>Correct</div>
            <div style={{ color: "#22c55e", fontSize: "20px", fontWeight: "600" }}>{overall.correct || 0}</div>
          </div>
          <div>
            <div style={{ color: mutedText, fontSize: "12px", marginBottom: "5px" }}>Incorrect</div>
            <div style={{ color: "#ef4444", fontSize: "20px", fontWeight: "600" }}>{overall.incorrect || 0}</div>
          </div>
          <div>
            <div style={{ color: mutedText, fontSize: "12px", marginBottom: "5px" }}>Accuracy</div>
            <div style={{ color: text, fontSize: "20px", fontWeight: "600" }}>{overall.accuracy_pct?.toFixed(1) || 0}%</div>
          </div>
        </div>

        {accuracy.by_signal && Object.keys(accuracy.by_signal).length > 0 && (
          <div style={{ marginTop: "15px" }}>
            <div style={{ color: mutedText, fontSize: "12px", marginBottom: "10px" }}>Accuracy by Signal</div>
            {Object.entries(accuracy.by_signal).map(([signal, stats]) => (
              <div key={signal} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <span style={{ color: signalColor(signal), fontWeight: "600", fontSize: "14px" }}>{signal}</span>
                <span style={{ color: text, fontSize: "14px" }}>
                  {stats.accuracy?.toFixed(1) || 0}% ({stats.correct}/{stats.correct + stats.incorrect})
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderStockDetail = (stock) => {
    if (!selectedStock || selectedStock.symbol !== stock.symbol) return null;

    const components = stock.component_scores || {};
    const normalized = stock.normalized_scores || {};
    const agreement = stock.model_agreement || {};

    return (
      <div style={{
        background: cardBg,
        padding: "20px",
        borderRadius: "8px",
        border: `2px solid ${signalColor(stock.unified_signal)}`,
        marginTop: "15px"
      }}>
        <h4 style={{ color: text, marginBottom: "15px", fontSize: "16px", fontWeight: "600" }}>
          {stock.symbol} - Detailed Analysis
        </h4>

        {/* Component Scores */}
        <div style={{ marginBottom: "20px" }}>
          <div style={{ color: mutedText, fontSize: "12px", marginBottom: "10px" }}>Component Scores (Normalized to 0-100)</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={Object.entries(normalized).map(([model, score]) => ({
              name: model.replace(/_/g, " ").toUpperCase(),
              score: score,
            }))}>
              <XAxis dataKey="name" tick={{ fill: mutedText, fontSize: 10 }} angle={-45} textAnchor="end" height={80} />
              <YAxis domain={[0, 100]} tick={{ fill: mutedText }} />
              <Tooltip contentStyle={{ background: cardBg, border: `1px solid ${border}` }} />
              <Bar dataKey="score">
                {Object.entries(normalized).map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getScoreColor(entry[1])} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Individual Model Details */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "15px", marginBottom: "15px" }}>
          {components.oi_based && (
            <div style={{ background: bg, padding: "12px", borderRadius: "6px", border: `1px solid ${border}` }}>
              <div style={{ color: mutedText, fontSize: "11px", marginBottom: "8px" }}>OI-BASED MODEL</div>
              <div style={{ color: signalColor(components.oi_based.signal), fontSize: "14px", fontWeight: "600", marginBottom: "4px" }}>
                {components.oi_based.signal}
              </div>
              <div style={{ color: text, fontSize: "12px" }}>Score: {components.oi_based.score}</div>
              <div style={{ color: mutedText, fontSize: "11px" }}>
                Conf: {(components.oi_based.confidence * 100).toFixed(0)}%
              </div>
            </div>
          )}

          {components.technical && (
            <div style={{ background: bg, padding: "12px", borderRadius: "6px", border: `1px solid ${border}` }}>
              <div style={{ color: mutedText, fontSize: "11px", marginBottom: "8px" }}>TECHNICAL MODEL</div>
              <div style={{ color: signalColor(components.technical.signal), fontSize: "14px", fontWeight: "600", marginBottom: "4px" }}>
                {components.technical.signal}
              </div>
              <div style={{ color: text, fontSize: "12px" }}>Score: {components.technical.score}</div>
              <div style={{ color: mutedText, fontSize: "11px" }}>
                Conf: {(components.technical.confidence * 100).toFixed(0)}%
              </div>
            </div>
          )}

          {components.ml_ensemble && (
            <div style={{ background: bg, padding: "12px", borderRadius: "6px", border: `1px solid ${border}` }}>
              <div style={{ color: mutedText, fontSize: "11px", marginBottom: "8px" }}>ML ENSEMBLE</div>
              <div style={{ color: text, fontSize: "12px", marginBottom: "4px" }}>
                Bullish Prob: {(components.ml_ensemble.bullish_probability * 100).toFixed(1)}%
              </div>
              {components.ml_ensemble.lgb_prob && (
                <div style={{ color: mutedText, fontSize: "11px" }}>
                  LGB: {(components.ml_ensemble.lgb_prob * 100).toFixed(0)}% |
                  NN: {(components.ml_ensemble.nn_prob * 100).toFixed(0)}%
                </div>
              )}
            </div>
          )}

          {components.oi_velocity && (
            <div style={{ background: bg, padding: "12px", borderRadius: "6px", border: `1px solid ${border}` }}>
              <div style={{ color: mutedText, fontSize: "11px", marginBottom: "8px" }}>OI VELOCITY</div>
              <div style={{ color: text, fontSize: "12px", marginBottom: "4px" }}>
                Score: {components.oi_velocity.score?.toFixed(2) || "N/A"}
              </div>
              {components.oi_velocity.uoa_detected && (
                <div style={{ color: "#f59e0b", fontSize: "11px", fontWeight: "600" }}>🎯 UOA Detected</div>
              )}
            </div>
          )}

          {components.global_cues && (
            <div style={{ background: bg, padding: "12px", borderRadius: "6px", border: `1px solid ${border}` }}>
              <div style={{ color: mutedText, fontSize: "11px", marginBottom: "8px" }}>GLOBAL CUES</div>
              <div style={{ color: text, fontSize: "12px", marginBottom: "4px" }}>
                Score: {components.global_cues.score?.toFixed(2) || "N/A"}
              </div>
              <div style={{ color: mutedText, fontSize: "11px" }}>
                Adj: {components.global_cues.adjustment > 0 ? "+" : ""}{components.global_cues.adjustment}
              </div>
            </div>
          )}
        </div>

        {/* Model Agreement */}
        {agreement.agreement_ratio && (
          <div style={{ marginTop: "15px", padding: "12px", background: bg, borderRadius: "6px", border: `1px solid ${border}` }}>
            <div style={{ color: mutedText, fontSize: "11px", marginBottom: "8px" }}>MODEL AGREEMENT</div>
            <div style={{ color: text, fontSize: "14px", fontWeight: "600" }}>
              {(agreement.agreement_ratio * 100).toFixed(0)}% of models agree
            </div>
            <div style={{ color: mutedText, fontSize: "11px", marginTop: "5px" }}>
              Signals: {agreement.signals?.map(s => s === 1 ? "🟢" : s === -1 ? "🔴" : "⚪").join(" ")}
            </div>
          </div>
        )}

        {/* Best Option Details */}
        {stock.best_option && (
          <div style={{ marginTop: "15px", padding: "12px", background: bg, borderRadius: "6px", border: `1px solid ${border}` }}>
            <div style={{ color: mutedText, fontSize: "11px", marginBottom: "8px" }}>BEST F&O OPTION</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "10px" }}>
              <div>
                <span style={{ color: mutedText, fontSize: "11px" }}>Strike: </span>
                <span style={{ color: text, fontSize: "12px", fontWeight: "600" }}>{stock.best_option.strike}</span>
              </div>
              <div>
                <span style={{ color: mutedText, fontSize: "11px" }}>Type: </span>
                <span style={{ color: text, fontSize: "12px", fontWeight: "600" }}>{stock.best_option.type}</span>
              </div>
              <div>
                <span style={{ color: mutedText, fontSize: "11px" }}>LTP: </span>
                <span style={{ color: text, fontSize: "12px", fontWeight: "600" }}>₹{stock.best_option.ltp?.toFixed(2)}</span>
              </div>
              <div>
                <span style={{ color: mutedText, fontSize: "11px" }}>IV: </span>
                <span style={{ color: text, fontSize: "12px", fontWeight: "600" }}>{stock.best_option.iv?.toFixed(1)}%</span>
              </div>
              <div>
                <span style={{ color: mutedText, fontSize: "11px" }}>Delta: </span>
                <span style={{ color: text, fontSize: "12px", fontWeight: "600" }}>{stock.best_option.delta?.toFixed(3)}</span>
              </div>
              <div>
                <span style={{ color: mutedText, fontSize: "11px" }}>Option Score: </span>
                <span style={{ color: text, fontSize: "12px", fontWeight: "600" }}>{stock.best_option.option_score}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ padding: "20px", background: bg, minHeight: "100vh" }}>
      <div style={{ marginBottom: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ color: text, marginBottom: "5px", fontSize: "24px", fontWeight: "700" }}>
            🎯 Unified Market Evaluation
          </h2>
          <p style={{ color: mutedText, fontSize: "14px" }}>
            Combining OI-based, Technical, ML, OI Velocity & Global Cues models
          </p>
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", color: text, fontSize: "14px" }}>
            <input
              type="checkbox"
              checked={includeTechnical}
              onChange={(e) => setIncludeTechnical(e.target.checked)}
            />
            Include Technical (slower)
          </label>
          <button
            onClick={fetchEvaluations}
            disabled={loading}
            style={{
              padding: "8px 16px",
              background: "#3b82f6",
              color: "white",
              border: "none",
              borderRadius: "6px",
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: "14px",
              fontWeight: "600",
            }}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {lastUpdate && (
        <div style={{ color: mutedText, fontSize: "12px", marginBottom: "15px" }}>
          Last updated: {new Date(lastUpdate).toLocaleString()}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "20px", marginBottom: "20px" }}>
        <div>
          {renderModelWeights()}
          {renderAccuracy()}
        </div>
        <div style={{ background: cardBg, padding: "20px", borderRadius: "8px", border: `1px solid ${border}` }}>
          <h3 style={{ color: text, marginBottom: "15px", fontSize: "16px", fontWeight: "600" }}>
            Top Opportunities ({evaluations.length})
          </h3>
          {loading ? (
            <p style={{ color: mutedText, fontSize: "14px" }}>Loading evaluations...</p>
          ) : evaluations.length === 0 ? (
            <p style={{ color: mutedText, fontSize: "14px" }}>No evaluations available. Run a scan first.</p>
          ) : (
            <div style={{ maxHeight: "calc(100vh - 300px)", overflowY: "auto" }}>
              {evaluations.map((stock, idx) => (
                <div key={idx}>
                  <div
                    onClick={() => setSelectedStock(selectedStock?.symbol === stock.symbol ? null : stock)}
                    style={{
                      padding: "15px",
                      background: bg,
                      borderRadius: "6px",
                      border: `1px solid ${border}`,
                      marginBottom: "10px",
                      cursor: "pointer",
                      transition: "all 0.2s",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <span style={{ color: text, fontSize: "16px", fontWeight: "600" }}>{stock.symbol}</span>
                        <span
                          style={{
                            padding: "3px 8px",
                            borderRadius: "4px",
                            background: signalColor(stock.unified_signal) + "20",
                            color: signalColor(stock.unified_signal),
                            fontSize: "12px",
                            fontWeight: "600",
                          }}
                        >
                          {stock.unified_signal}
                        </span>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ color: getScoreColor(stock.unified_score), fontSize: "20px", fontWeight: "700" }}>
                          {stock.unified_score.toFixed(1)}
                        </div>
                        <div style={{ color: mutedText, fontSize: "11px" }}>
                          {getConfidenceLabel(stock.unified_confidence)}
                        </div>
                      </div>
                    </div>

                    {stock.best_option && (
                      <div style={{ display: "flex", gap: "15px", fontSize: "12px", color: mutedText }}>
                        <span>
                          {stock.best_option.type} {stock.best_option.strike}
                        </span>
                        <span>₹{stock.best_option.ltp?.toFixed(2)}</span>
                        <span>IV: {stock.best_option.iv?.toFixed(1)}%</span>
                        <span>Δ: {stock.best_option.delta?.toFixed(3)}</span>
                      </div>
                    )}

                    {stock.signal_reasons && stock.signal_reasons.length > 0 && (
                      <div style={{ marginTop: "8px", fontSize: "11px", color: mutedText }}>
                        {stock.signal_reasons.slice(0, 2).join(" • ")}
                      </div>
                    )}
                  </div>

                  {renderStockDetail(stock)}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default UnifiedEvaluationTab;
