// StrategyBuilder.jsx
// Strategy Builder UI for backtesting with user-configurable parameters
// Lets user configure backtest_runner.py parameters via UI,
// then run and view results without touching code.

import { useState, useEffect } from 'react';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend
} from 'recharts';

// Strategy parameters configuration (maps to backtest_runner.py args)
const STRATEGY_PARAMS = {
  symbol: {
    type: "select",
    options: ["NIFTY", "BANKNIFTY", "FINNIFTY"],
    default: "NIFTY",
    label: "Symbol"
  },
  regime_filter: {
    type: "multiselect",
    options: ["PINNED", "TRENDING", "EXPIRY", "SQUEEZE"],
    default: ["TRENDING", "SQUEEZE"],
    label: "Regime Filter"
  },
  min_score: {
    type: "slider",
    min: 0,
    max: 1,
    step: 0.05,
    default: 0.6,
    label: "Minimum Score"
  },
  strategy_type: {
    type: "select",
    options: ["LONG_STRADDLE", "SHORT_STRADDLE", "IRON_CONDOR", "BULL_SPREAD", "BEAR_SPREAD"],
    default: "SHORT_STRADDLE",
    label: "Strategy Type"
  },
  entry_time: {
    type: "select",
    options: ["09:15", "10:00", "11:00", "12:00"],
    default: "10:00",
    label: "Entry Time"
  },
  exit_time: {
    type: "select",
    options: ["14:00", "14:30", "15:00", "15:15"],
    default: "15:00",
    label: "Exit Time"
  },
  stop_loss_pct: {
    type: "slider",
    min: 10,
    max: 100,
    step: 5,
    default: 50,
    label: "Stop Loss %"
  },
  target_pct: {
    type: "slider",
    min: 10,
    max: 100,
    step: 5,
    default: 75,
    label: "Target %"
  },
  lookback_days: {
    type: "slider",
    min: 30,
    max: 365,
    step: 30,
    default: 90,
    label: "Lookback Days"
  },
  lot_size: {
    type: "number",
    min: 1,
    max: 20,
    default: 1,
    label: "Lot Size"
  },
};

// Initialize params with defaults
const getDefaultParams = () => {
  const params = {};
  Object.entries(STRATEGY_PARAMS).forEach(([key, config]) => {
    params[key] = config.default;
  });
  return params;
};

// Load saved strategies from localStorage
const loadSavedStrategies = () => {
  try {
    const saved = localStorage.getItem('fo_scanner_strategies');
    return saved ? JSON.parse(saved) : {};
  } catch {
    return {};
  }
};

// Save strategies to localStorage
const saveStrategiesToStorage = (strategies) => {
  localStorage.setItem('fo_scanner_strategies', JSON.stringify(strategies));
};

export default function StrategyBuilder() {
  const [params, setParams] = useState(getDefaultParams());
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [savedStrategies, setSavedStrategies] = useState(loadSavedStrategies());
  const [strategyName, setStrategyName] = useState('');

  // Update a single parameter
  const updateParam = (key, value) => {
    setParams(prev => ({ ...prev, [key]: value }));
  };

  // Toggle multiselect value
  const toggleMultiselect = (key, value) => {
    setParams(prev => {
      const current = prev[key] || [];
      const updated = current.includes(value)
        ? current.filter(v => v !== value)
        : [...current, value];
      return { ...prev, [key]: updated };
    });
  };

  // Run backtest
  const runBacktest = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      });
      if (!response.ok) {
        throw new Error(`Backtest failed: ${response.statusText}`);
      }
      const data = await response.json();
      setResults(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Save current strategy
  const saveStrategy = () => {
    if (!strategyName.trim()) {
      alert('Please enter a strategy name');
      return;
    }
    const updated = {
      ...savedStrategies,
      [strategyName]: { ...params, savedAt: new Date().toISOString() },
    };
    setSavedStrategies(updated);
    saveStrategiesToStorage(updated);
    setStrategyName('');
  };

  // Load a saved strategy
  const loadStrategy = (name) => {
    const strategy = savedStrategies[name];
    if (strategy) {
      const { savedAt, ...loadedParams } = strategy;
      setParams(prev => ({ ...prev, ...loadedParams }));
    }
  };

  // Delete a saved strategy
  const deleteStrategy = (name) => {
    const updated = { ...savedStrategies };
    delete updated[name];
    setSavedStrategies(updated);
    saveStrategiesToStorage(updated);
  };

  // Render parameter input based on type
  const renderParamInput = (key, config) => {
    const value = params[key];

    switch (config.type) {
      case 'select':
        return (
          <select
            value={value}
            onChange={(e) => updateParam(key, e.target.value)}
            className="param-select"
          >
            {config.options.map(opt => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        );

      case 'multiselect':
        return (
          <div className="multiselect-container">
            {config.options.map(opt => (
              <label key={opt} className="multiselect-option">
                <input
                  type="checkbox"
                  checked={(value || []).includes(opt)}
                  onChange={() => toggleMultiselect(key, opt)}
                />
                <span>{opt}</span>
              </label>
            ))}
          </div>
        );

      case 'slider':
        return (
          <div className="slider-container">
            <input
              type="range"
              min={config.min}
              max={config.max}
              step={config.step}
              value={value}
              onChange={(e) => updateParam(key, parseFloat(e.target.value))}
              className="param-slider"
            />
            <span className="slider-value">{value}</span>
          </div>
        );

      case 'number':
        return (
          <input
            type="number"
            min={config.min}
            max={config.max}
            value={value}
            onChange={(e) => updateParam(key, parseInt(e.target.value) || config.default)}
            className="param-number"
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="strategy-builder">
      <div className="builder-layout">
        {/* Left Panel - Parameters */}
        <div className="params-panel">
          <h3 className="panel-title">Strategy Parameters</h3>
          
          {/* Saved Strategies Dropdown */}
          {Object.keys(savedStrategies).length > 0 && (
            <div className="saved-strategies">
              <label>Load Saved Strategy:</label>
              <select
                onChange={(e) => e.target.value && loadStrategy(e.target.value)}
                className="param-select"
              >
                <option value="">Select...</option>
                {Object.keys(savedStrategies).map(name => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </div>
          )}

          {/* Parameter Form */}
          <div className="params-form">
            {Object.entries(STRATEGY_PARAMS).map(([key, config]) => (
              <div key={key} className="param-group">
                <label className="param-label">{config.label}</label>
                {renderParamInput(key, config)}
              </div>
            ))}
          </div>

          {/* Action Buttons */}
          <div className="action-buttons">
            <button
              onClick={runBacktest}
              disabled={loading}
              className="btn btn-primary"
            >
              {loading ? 'Running...' : 'Run Backtest'}
            </button>
          </div>

          {/* Save Strategy */}
          <div className="save-strategy">
            <input
              type="text"
              placeholder="Strategy name..."
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
              className="strategy-name-input"
            />
            <button onClick={saveStrategy} className="btn btn-secondary">
              Save Strategy
            </button>
          </div>

          {/* Saved Strategies List */}
          {Object.keys(savedStrategies).length > 0 && (
            <div className="saved-list">
              <h4>Saved Strategies</h4>
              <ul>
                {Object.entries(savedStrategies).map(([name, strategy]) => (
                  <li key={name} className="saved-item">
                    <span className="saved-name">{name}</span>
                    <span className="saved-date">
                      {new Date(strategy.savedAt).toLocaleDateString()}
                    </span>
                    <button
                      onClick={() => deleteStrategy(name)}
                      className="btn-delete"
                      title="Delete"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Right Panel - Results */}
        <div className="results-panel">
          {error && (
            <div className="error-banner">
              ⚠️ {error}
            </div>
          )}

          {loading && (
            <div className="loading-indicator">
              <div className="spinner"></div>
              <span>Running backtest...</span>
            </div>
          )}

          {results && !loading && (
            <>
              {/* Stats Summary */}
              <div className="stats-summary">
                <h3 className="panel-title">Performance Summary</h3>
                <div className="stats-grid">
                  <div className="stat-card">
                    <span className="stat-label">Total Trades</span>
                    <span className="stat-value">{results.stats?.total_trades || 0}</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">Win Rate</span>
                    <span className="stat-value">
                      {((results.stats?.win_rate || 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">Avg P&L</span>
                    <span className={`stat-value ${(results.stats?.avg_pnl || 0) >= 0 ? 'positive' : 'negative'}`}>
                      {(results.stats?.avg_pnl || 0).toFixed(2)}%
                    </span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">Max Drawdown</span>
                    <span className="stat-value negative">
                      {(results.stats?.max_drawdown || 0).toFixed(2)}%
                    </span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-label">Sharpe Ratio</span>
                    <span className="stat-value">{(results.stats?.sharpe || 0).toFixed(2)}</span>
                  </div>
                </div>
              </div>

              {/* Equity Curve */}
              {results.equity_curve?.length > 0 && (
                <div className="chart-section">
                  <h3 className="panel-title">Equity Curve</h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={results.equity_curve}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="date" tick={{ fill: '#888' }} />
                      <YAxis tick={{ fill: '#888' }} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                        labelStyle={{ color: '#0f0' }}
                      />
                      <Area
                        type="monotone"
                        dataKey="cumulative_pnl"
                        stroke="#00ff88"
                        fill="#00ff8833"
                        name="Cumulative P&L"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Regime Breakdown */}
              {results.regime_breakdown && Object.keys(results.regime_breakdown).length > 0 && (
                <div className="chart-section">
                  <h3 className="panel-title">Win Rate by Regime</h3>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={Object.entries(results.regime_breakdown).map(([regime, data]) => ({
                        regime,
                        win_rate: (data.win_rate || 0) * 100,
                        trades: data.trades || 0,
                      }))}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="regime" tick={{ fill: '#888' }} />
                      <YAxis tick={{ fill: '#888' }} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333' }}
                      />
                      <Bar dataKey="win_rate" fill="#00ff88" name="Win Rate %" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Trade Log */}
              {results.trades?.length > 0 && (
                <div className="trade-log">
                  <h3 className="panel-title">Trade Log</h3>
                  <div className="table-container">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Symbol</th>
                          <th>Signal</th>
                          <th>Entry</th>
                          <th>Exit</th>
                          <th>P&L</th>
                          <th>Regime</th>
                        </tr>
                      </thead>
                      <tbody>
                        {results.trades.slice(0, 50).map((trade, idx) => (
                          <tr key={idx}>
                            <td>{trade.date}</td>
                            <td>{trade.symbol}</td>
                            <td className={trade.signal?.toLowerCase()}>{trade.signal}</td>
                            <td>₹{trade.entry?.toFixed(2)}</td>
                            <td>₹{trade.exit?.toFixed(2)}</td>
                            <td className={trade.pnl >= 0 ? 'positive' : 'negative'}>
                              ₹{trade.pnl?.toFixed(2)}
                            </td>
                            <td>{trade.regime}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {results.trades.length > 50 && (
                      <p className="table-note">Showing first 50 of {results.trades.length} trades</p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {!results && !loading && !error && (
            <div className="empty-state">
              <div className="empty-icon">📊</div>
              <h3>Configure & Run</h3>
              <p>Set your strategy parameters on the left and click "Run Backtest" to see results.</p>
            </div>
          )}
        </div>
      </div>

      <style>{`
        .strategy-builder {
          padding: 1rem;
          height: 100%;
          background: var(--bg-dark, #0a0a0a);
          color: var(--text-primary, #e0e0e0);
        }

        .builder-layout {
          display: flex;
          gap: 1.5rem;
          height: calc(100vh - 120px);
        }

        .params-panel {
          width: 320px;
          min-width: 280px;
          background: var(--bg-card, #1a1a1a);
          border-radius: 8px;
          padding: 1rem;
          overflow-y: auto;
          border: 1px solid var(--border-color, #333);
        }

        .results-panel {
          flex: 1;
          background: var(--bg-card, #1a1a1a);
          border-radius: 8px;
          padding: 1rem;
          overflow-y: auto;
          border: 1px solid var(--border-color, #333);
        }

        .panel-title {
          margin: 0 0 1rem 0;
          font-size: 1rem;
          color: var(--accent-color, #00ff88);
          border-bottom: 1px solid var(--border-color, #333);
          padding-bottom: 0.5rem;
        }

        .params-form {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .param-group {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .param-label {
          font-size: 0.85rem;
          color: var(--text-secondary, #888);
        }

        .param-select,
        .param-number,
        .strategy-name-input {
          width: 100%;
          padding: 0.5rem;
          background: var(--bg-dark, #0a0a0a);
          border: 1px solid var(--border-color, #333);
          border-radius: 4px;
          color: var(--text-primary, #e0e0e0);
          font-size: 0.9rem;
        }

        .param-select:focus,
        .param-number:focus,
        .strategy-name-input:focus {
          outline: none;
          border-color: var(--accent-color, #00ff88);
        }

        .slider-container {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .param-slider {
          flex: 1;
          -webkit-appearance: none;
          height: 6px;
          background: var(--border-color, #333);
          border-radius: 3px;
        }

        .param-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 16px;
          height: 16px;
          background: var(--accent-color, #00ff88);
          border-radius: 50%;
          cursor: pointer;
        }

        .slider-value {
          min-width: 40px;
          text-align: right;
          font-family: monospace;
          color: var(--accent-color, #00ff88);
        }

        .multiselect-container {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem;
        }

        .multiselect-option {
          display: flex;
          align-items: center;
          gap: 0.25rem;
          padding: 0.25rem 0.5rem;
          background: var(--bg-dark, #0a0a0a);
          border: 1px solid var(--border-color, #333);
          border-radius: 4px;
          cursor: pointer;
          font-size: 0.8rem;
        }

        .multiselect-option:has(input:checked) {
          border-color: var(--accent-color, #00ff88);
          background: var(--accent-color, #00ff88)22;
        }

        .multiselect-option input {
          display: none;
        }

        .action-buttons {
          margin-top: 1rem;
        }

        .btn {
          padding: 0.75rem 1rem;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 0.9rem;
          width: 100%;
          transition: all 0.2s;
        }

        .btn-primary {
          background: var(--accent-color, #00ff88);
          color: #000;
          font-weight: bold;
        }

        .btn-primary:hover:not(:disabled) {
          background: var(--accent-hover, #00cc66);
        }

        .btn-primary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .btn-secondary {
          background: var(--bg-dark, #0a0a0a);
          color: var(--text-primary, #e0e0e0);
          border: 1px solid var(--border-color, #333);
          margin-top: 0.5rem;
        }

        .btn-secondary:hover {
          border-color: var(--accent-color, #00ff88);
        }

        .save-strategy {
          margin-top: 1.5rem;
          padding-top: 1rem;
          border-top: 1px solid var(--border-color, #333);
        }

        .saved-strategies {
          margin-bottom: 1rem;
        }

        .saved-list {
          margin-top: 1rem;
        }

        .saved-list h4 {
          font-size: 0.85rem;
          color: var(--text-secondary, #888);
          margin-bottom: 0.5rem;
        }

        .saved-list ul {
          list-style: none;
          padding: 0;
          margin: 0;
        }

        .saved-item {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem;
          background: var(--bg-dark, #0a0a0a);
          border-radius: 4px;
          margin-bottom: 0.25rem;
          font-size: 0.85rem;
        }

        .saved-name {
          flex: 1;
        }

        .saved-date {
          color: var(--text-secondary, #888);
          font-size: 0.75rem;
        }

        .btn-delete {
          background: none;
          border: none;
          color: #ff4444;
          cursor: pointer;
          font-size: 1.2rem;
          padding: 0;
          line-height: 1;
        }

        .stats-summary {
          margin-bottom: 1.5rem;
        }

        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
          gap: 1rem;
        }

        .stat-card {
          background: var(--bg-dark, #0a0a0a);
          padding: 1rem;
          border-radius: 6px;
          text-align: center;
          border: 1px solid var(--border-color, #333);
        }

        .stat-label {
          display: block;
          font-size: 0.75rem;
          color: var(--text-secondary, #888);
          margin-bottom: 0.25rem;
        }

        .stat-value {
          display: block;
          font-size: 1.25rem;
          font-weight: bold;
          font-family: monospace;
        }

        .stat-value.positive { color: #00ff88; }
        .stat-value.negative { color: #ff4444; }

        .chart-section {
          margin-bottom: 1.5rem;
        }

        .trade-log {
          margin-top: 1.5rem;
        }

        .table-container {
          overflow-x: auto;
        }

        .data-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.85rem;
        }

        .data-table th,
        .data-table td {
          padding: 0.5rem;
          text-align: left;
          border-bottom: 1px solid var(--border-color, #333);
        }

        .data-table th {
          color: var(--text-secondary, #888);
          font-weight: normal;
        }

        .data-table .positive { color: #00ff88; }
        .data-table .negative { color: #ff4444; }
        .data-table .bullish { color: #00ff88; }
        .data-table .bearish { color: #ff4444; }

        .table-note {
          font-size: 0.75rem;
          color: var(--text-secondary, #888);
          text-align: center;
          margin-top: 0.5rem;
        }

        .error-banner {
          background: #ff444422;
          border: 1px solid #ff4444;
          color: #ff4444;
          padding: 1rem;
          border-radius: 4px;
          margin-bottom: 1rem;
        }

        .loading-indicator {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 1rem;
          padding: 3rem;
          color: var(--text-secondary, #888);
        }

        .spinner {
          width: 24px;
          height: 24px;
          border: 2px solid var(--border-color, #333);
          border-top-color: var(--accent-color, #00ff88);
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .empty-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100%;
          color: var(--text-secondary, #888);
          text-align: center;
        }

        .empty-icon {
          font-size: 4rem;
          margin-bottom: 1rem;
        }

        .empty-state h3 {
          margin: 0 0 0.5rem 0;
          color: var(--text-primary, #e0e0e0);
        }

        .empty-state p {
          max-width: 300px;
        }
      `}</style>
    </div>
  );
}
