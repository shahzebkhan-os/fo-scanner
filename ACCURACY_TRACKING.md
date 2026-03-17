# Model Accuracy Tracking System

## Overview

The accuracy tracking system monitors and analyzes the prediction performance of the LightGBM + LSTM ensemble models in real-time and historically. It provides detailed visual representations of model accuracy and allows retesting with configurable settings.

## Architecture

### Components

1. **Backend Module** (`backend/accuracy_tracker.py`)
   - `AccuracyTracker` class for tracking and analysis
   - Database tables for storing accuracy runs and predictions
   - Configuration management system
   - Historical backtesting engine

2. **API Endpoints** (`backend/main.py`)
   - `/api/accuracy/config` - Get/update tracking configuration
   - `/api/accuracy/start` - Start new accuracy run
   - `/api/accuracy/runs` - List all runs
   - `/api/accuracy/runs/{run_id}` - Get run details
   - `/api/accuracy/runs/{run_id}/visualizations` - Get visualization data
   - `/api/accuracy/runs/{run_id}/finalize` - Finalize run statistics

3. **Frontend Component** (`frontend/src/components/AccuracyTab.jsx`)
   - Interactive UI for managing accuracy runs
   - Real-time visualization of accuracy metrics
   - Configuration editor for tweakable settings

## Database Schema

### accuracy_runs
Stores metadata about each accuracy tracking session.

```sql
CREATE TABLE accuracy_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    run_type TEXT NOT NULL,  -- 'LIVE' or 'HISTORICAL'
    date_range_start TEXT,
    date_range_end TEXT,
    total_predictions INTEGER DEFAULT 0,
    correct_predictions INTEGER DEFAULT 0,
    accuracy_pct REAL DEFAULT 0,
    total_profit REAL DEFAULT 0,
    total_loss REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    avg_profit_per_trade REAL DEFAULT 0,
    config_json TEXT,
    status TEXT DEFAULT 'RUNNING'
);
```

### accuracy_predictions
Detailed prediction outcomes for each tracked prediction.

```sql
CREATE TABLE accuracy_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    prediction_time TEXT NOT NULL,
    signal TEXT NOT NULL,
    score INTEGER NOT NULL,
    confidence REAL NOT NULL,
    ml_probability REAL,
    lgb_probability REAL,
    nn_probability REAL,
    regime TEXT,
    spot_price REAL,

    -- Option details
    option_type TEXT,
    strike REAL,
    entry_price REAL,

    -- Outcome tracking
    exit_price REAL,
    exit_time TEXT,
    pnl_pct REAL,
    pnl_absolute REAL,
    outcome TEXT,  -- WIN, LOSS, NEUTRAL, PENDING

    -- Additional context
    iv_rank REAL,
    pcr REAL,
    max_pain REAL,
    days_to_expiry INTEGER,
    gex REAL,
    iv_skew REAL
);
```

### accuracy_price_updates
Tracks option prices over time during live monitoring.

```sql
CREATE TABLE accuracy_price_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER NOT NULL,
    price REAL NOT NULL,
    timestamp TEXT NOT NULL,
    spot_price REAL
);
```

## Configuration Settings

Default configuration (stored in `accuracy_config.json`):

```json
{
    "min_score_threshold": 70,
    "min_confidence_threshold": 0.50,
    "min_ml_probability": 0.55,
    "profit_target_pct": 20.0,
    "stop_loss_pct": 20.0,
    "tracking_interval_seconds": 300,
    "track_during_market_hours": true,
    "market_start_hour": 9,
    "market_start_minute": 15,
    "market_end_hour": 15,
    "market_end_minute": 30
}
```

### Configuration Parameters

- **min_score_threshold**: Only track predictions with score ≥ this value (0-100)
- **min_confidence_threshold**: Only track predictions with confidence ≥ this value (0-1)
- **min_ml_probability**: Minimum ML probability to consider (0-1)
- **profit_target_pct**: Mark prediction as WIN when profit reaches this %
- **stop_loss_pct**: Mark prediction as LOSS when loss reaches this %
- **tracking_interval_seconds**: How often to update prices during live tracking
- **track_during_market_hours**: Only track during market hours
- **market_start_hour/minute**: Market opening time (IST)
- **market_end_hour/minute**: Market closing time (IST)

## Usage

### Starting a Historical Accuracy Test

Via API:
```bash
curl -X POST "http://localhost:8000/api/accuracy/start?run_type=HISTORICAL&start_date=2024-01-01&end_date=2024-12-31"
```

Via UI:
1. Navigate to Accuracy tab
2. Click "New Run"
3. Select "Historical Backtest"
4. Enter date range
5. Click "Start Run"

### Starting Live Tracking

Via API:
```bash
curl -X POST "http://localhost:8000/api/accuracy/start?run_type=LIVE"
```

Via UI:
1. Navigate to Accuracy tab
2. Click "New Run"
3. Select "Live Tracking"
4. Click "Start Run"

### Viewing Results

1. Navigate to Accuracy tab
2. Click on any run to view detailed results
3. View visualizations including:
   - Accuracy over time
   - Win rate by score range
   - Performance by signal type (BULLISH/BEARISH)
   - Performance by regime (PINNED/TRENDING/SQUEEZE/EXPIRY)
   - Performance by symbol

### Updating Configuration

Via API:
```bash
curl -X POST "http://localhost:8000/api/accuracy/config" \
  -H "Content-Type: application/json" \
  -d '{
    "min_score_threshold": 75,
    "profit_target_pct": 25.0,
    "stop_loss_pct": 20.0
  }'
```

Via UI:
1. Navigate to Accuracy tab
2. Click "New Run"
3. Click "Edit Settings"
4. Adjust parameters
5. Click "Save Settings"

## Metrics Tracked

### Overall Metrics
- **Accuracy %**: Percentage of correct predictions (wins / total completed)
- **Win Rate**: Percentage of profitable trades
- **Average P&L**: Average profit/loss per trade
- **Total Profit**: Sum of all winning trade profits
- **Total Loss**: Sum of all losing trade losses

### Breakdown Metrics
- **By Score Range**: Accuracy for different score ranges (70-79, 80-89, 90-100)
- **By Signal**: Performance by prediction signal (BULLISH/BEARISH)
- **By Regime**: Performance by market regime (PINNED/TRENDING/SQUEEZE/EXPIRY)
- **By Symbol**: Performance for each individual stock/index

## Visualizations

### 1. Accuracy Over Time (Line Chart)
Shows cumulative accuracy percentage as predictions are made over time. Helps identify if model performance is improving or degrading.

### 2. Accuracy by Score Range (Bar Chart)
Shows how accurate the model is at different confidence levels. Higher scores should have higher accuracy.

### 3. P&L Distribution (Histogram)
Shows distribution of P&L percentages across all trades. Helps understand risk/reward profile.

### 4. Performance Tables
- By Signal: Win rate and prediction count for BULLISH/BEARISH signals
- By Regime: Win rate and prediction count for each market regime
- By Symbol: Win rate, average P&L, and prediction count per symbol

## Best Practices

### 1. Historical Testing
- Test on at least 3-6 months of data for statistically significant results
- Use rolling date ranges to test across different market conditions
- Compare performance across bull markets, bear markets, and consolidation periods

### 2. Live Tracking
- Run during market hours to track real-time performance
- Monitor for at least 1 full week to see performance across different days
- Compare live results with historical backtest results

### 3. Configuration Tuning
- Start with default settings and adjust based on results
- Lower thresholds to track more predictions (more data, lower quality)
- Raise thresholds to track only high-confidence predictions (less data, higher quality)
- Adjust profit/loss targets based on typical option price movements

### 4. Performance Analysis
- Focus on high-score predictions (>80) for best results
- Check which regimes the model performs best in
- Identify consistently performing symbols
- Look for patterns in losing trades to improve model

## Troubleshooting

### No Predictions in Historical Test
- Check that market_snapshots table has data for the date range
- Verify min_score_threshold and min_confidence_threshold aren't too high
- Ensure trade_result or pick_pnl_pct_next columns have data

### Low Accuracy
- Model may need retraining with more recent data
- Check if market conditions have changed significantly
- Review configuration thresholds (too low may track low-quality predictions)

### API Errors
- Ensure database has been initialized (`db.init_db()`)
- Check that accuracy_tracker tables exist
- Verify date formats are YYYY-MM-DD

## Integration with Existing Systems

### Scanner Integration
The accuracy tracker can be integrated with the main scanner to automatically track all predictions:

```python
# In main.py scan endpoint
if scan_result['score'] >= 70:
    tracker = get_accuracy_tracker()
    run_id = get_current_live_run_id()  # Your implementation
    tracker.record_prediction(run_id, symbol, scan_result, top_pick)
```

### Paper Trading Integration
Link accuracy tracking with paper trades to compare predicted vs actual outcomes:

```python
# When paper trade is closed
prediction_id = find_prediction_for_trade(trade_id)
if prediction_id:
    tracker.evaluate_prediction(prediction_id, exit_price)
```

## Future Enhancements

Potential improvements for the accuracy tracking system:

1. **Real-time Alerts**
   - Telegram notifications when accuracy drops below threshold
   - Email reports with daily/weekly summaries

2. **Model Comparison**
   - Compare LightGBM vs LSTM performance separately
   - A/B testing different model configurations

3. **Advanced Analytics**
   - Sharpe ratio and max drawdown calculations
   - Correlation analysis between features and outcomes
   - Feature importance based on actual outcomes

4. **Auto-Retraining**
   - Automatically trigger model retraining when accuracy drops
   - Adaptive threshold adjustment based on recent performance

5. **Strategy Optimization**
   - Suggest optimal profit/loss thresholds based on historical data
   - Recommend best symbols and regimes to trade

## Summary

The accuracy tracking system provides comprehensive monitoring and analysis of model predictions:

✅ **Real-time tracking** during market hours
✅ **Historical backtesting** with configurable date ranges
✅ **Detailed visualizations** for easy analysis
✅ **Tweakable settings** for retesting with different parameters
✅ **Comprehensive metrics** by signal, regime, and symbol
✅ **Persistent storage** of all prediction metadata
✅ **User-friendly interface** for managing tracking runs

This system enables continuous improvement of the prediction models by providing clear visibility into their performance and identifying areas for enhancement.
