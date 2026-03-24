# Technical Signal Tab - Accuracy Testing System

## Overview

This document describes the comprehensive accuracy testing and validation system for the Technical Score Tab. The system enables rigorous backtesting and performance measurement of technical signals to continuously improve their reliability.

---

## What Has Been Implemented

### 1. Technical Backtesting Framework (`backend/technical_backtest.py`)

A dedicated backtesting engine specifically for technical scoring signals that:

- **Simulates Real Trading**: Enters positions based on technical score thresholds and direction signals
- **Tracks Multiple Dimensions**: Analyzes performance across direction (bullish/bearish), strength (strong/weak), and market regime (trending/ranging)
- **Statistical Validation**: Includes Z-score testing to determine if results are statistically significant
- **Flexible Configuration**: Supports customizable holding periods, score thresholds, and exit strategies

### 2. Database Schema for Results Tracking

Three new tables store comprehensive backtest data:

#### `technical_backtest_runs`
Stores metadata for each backtest execution:
- Date range and symbols tested
- Configuration parameters
- Aggregate metrics (win rate, profit factor)
- Statistical significance results

#### `technical_backtest_trades`
Individual trade records with full context:
- Entry/exit timestamps and prices
- Direction and strength at entry
- Market regime (trending/ranging)
- Indicator values and scores
- P&L percentage and outcome

#### `technical_indicator_performance`
Tracks which indicators contribute to wins vs losses:
- Per-indicator win rates
- Average scores on winning vs losing trades
- Contribution frequency

### 3. API Endpoints for Testing

Four new REST endpoints enable comprehensive testing:

#### `POST /api/technical-backtest/run`
**Purpose**: Execute a new backtest with custom parameters

**Request Body**:
```json
{
  "symbols": ["NIFTY", "BANKNIFTY", "RELIANCE"],
  "start_date": "2024-01-01",
  "end_date": "2024-03-24",
  "timeframe": "15m",
  "min_score_threshold": 70,
  "min_confidence": 0.65,
  "holding_period_minutes": 1440,
  "exit_on_direction_flip": true
}
```

**Response**: Complete metrics breakdown + first 10 trades

#### `GET /api/technical-backtest/runs?limit=10`
**Purpose**: List recent backtest runs

**Response**:
```json
{
  "runs": [
    {
      "id": 1,
      "run_time": "2024-03-24T10:30:00",
      "start_date": "2024-01-01",
      "end_date": "2024-03-24",
      "symbols": ["NIFTY", "BANKNIFTY"],
      "timeframe": "15m",
      "total_trades": 45,
      "win_rate": 0.6222,
      "profit_factor": 1.85,
      "metrics": { ... }
    }
  ]
}
```

#### `GET /api/technical-backtest/runs/{run_id}`
**Purpose**: Get detailed results for a specific backtest

**Response**: Full run metadata + all individual trades

#### `GET /api/technical-backtest/accuracy-summary`
**Purpose**: Aggregate statistics across all backtests

**Response**:
```json
{
  "total_runs": 5,
  "total_trades_across_runs": 230,
  "avg_win_rate": 0.5891,
  "avg_profit_factor": 1.67,
  "latest_run": {
    "by_direction": {
      "bullish_win_rate": 0.65,
      "bearish_win_rate": 0.58
    },
    "by_strength": {
      "strong_win_rate": 0.71,
      "weak_win_rate": 0.48
    },
    "by_regime": {
      "trending_win_rate": 0.68,
      "ranging_win_rate": 0.42
    },
    "statistical_significance": {
      "z_score": 2.34,
      "p_value": 0.019,
      "is_significant": true
    }
  }
}
```

---

## Key Metrics Tracked

### Overall Performance
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Total profit ÷ total loss (> 1.0 is profitable)
- **Average Win %**: Average gain on winning trades
- **Average Loss %**: Average loss on losing trades
- **Max Consecutive Wins/Losses**: Risk assessment

### Dimensional Analysis

#### By Direction
- **Bullish vs Bearish Win Rates**: Which direction is more accurate?
- Helps identify systematic bias in the model

#### By Strength
- **Strong vs Weak Win Rates**: Does "STRONG" direction strength actually predict better outcomes?
- Validates the directional strength classification

#### By Market Regime
- **Trending vs Ranging Win Rates**: Should we filter out ranging markets?
- Critical for understanding when the model works best

### Statistical Significance
- **Z-Score**: Measures how many standard deviations away from random (50% win rate)
- **P-Value**: Probability results are due to chance
- **Is Significant**: True if p-value < 0.05 (95% confidence)

**Example Interpretation**:
- Win rate: 62.5%
- Z-score: 2.8
- P-value: 0.005
- **Conclusion**: Results are statistically significant (not random), model has genuine edge

---

## How to Use the System

### Step 1: Run Your First Backtest

Using the API:
```bash
curl -X POST http://localhost:8000/api/technical-backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS"],
    "start_date": "2024-01-01",
    "end_date": "2024-03-20",
    "timeframe": "15m",
    "min_score_threshold": 70,
    "min_confidence": 0.65,
    "holding_period_minutes": 1440,
    "exit_on_direction_flip": true
  }'
```

This will:
1. Download historical price data for the symbols
2. Compute technical scores for each bar
3. Simulate trades based on your criteria
4. Return comprehensive metrics

**Expected Duration**: 2-5 minutes for 3 months of 15-minute data across 4 symbols

### Step 2: Analyze Results

Check the response for:

**High-Level Metrics**:
- Is the win rate > 55%? (Edge over random)
- Is the profit factor > 1.5? (Good risk/reward)
- Is the result statistically significant? (Not luck)

**Directional Analysis**:
- Are bullish signals more accurate than bearish?
- Should you trade both directions or focus on one?

**Regime Analysis**:
- If trending win rate is 70% but ranging is 40%, filter out ADX < 25 signals

### Step 3: Iterate and Optimize

Based on results, adjust:

1. **Score Threshold**: Try 75 or 80 if 70 has too many false signals
2. **Confidence Minimum**: Increase to 0.70 or 0.75 to filter low-quality setups
3. **Holding Period**: Test shorter (360 min = 6 hours) or longer (2880 min = 2 days) periods
4. **Exit Strategy**: Compare direction-flip exits vs fixed holding period

### Step 4: Compare Across Configurations

Run multiple backtests with different parameters:

```bash
# Conservative (high threshold)
{"min_score_threshold": 80, "min_confidence": 0.75}

# Moderate (default)
{"min_score_threshold": 70, "min_confidence": 0.65}

# Aggressive (low threshold)
{"min_score_threshold": 60, "min_confidence": 0.55}
```

Then call `/api/technical-backtest/accuracy-summary` to see which configuration performs best.

---

## Interpreting Results - Real Examples

### Example 1: Good Technical Signal System

```json
{
  "win_rate": 0.6444,
  "profit_factor": 2.1,
  "avg_win_pct": 3.2,
  "avg_loss_pct": 2.1,
  "bullish_win_rate": 0.67,
  "bearish_win_rate": 0.61,
  "strong_win_rate": 0.72,
  "weak_win_rate": 0.51,
  "trending_win_rate": 0.71,
  "ranging_win_rate": 0.48,
  "z_score": 3.2,
  "p_value": 0.001,
  "is_significant": true
}
```

**Interpretation**:
- ✅ **64% win rate** - Strong edge
- ✅ **2.1 profit factor** - Excellent risk/reward
- ✅ **Z-score 3.2** - Highly significant, not random
- 📊 **Strong signals (72%)** much better than weak (51%) - filter out weak signals
- 📊 **Trending markets (71%)** much better than ranging (48%) - add ADX filter
- ✅ **Bullish slightly better** than bearish but both profitable

**Action**: Deploy this system! Add filters:
- Only trade `direction_strength == "STRONG"`
- Only trade when `ADX > 25` (trending)
- Expected win rate: ~72%

### Example 2: Needs Improvement

```json
{
  "win_rate": 0.5123,
  "profit_factor": 1.05,
  "avg_win_pct": 2.8,
  "avg_loss_pct": 2.6,
  "bullish_win_rate": 0.58,
  "bearish_win_rate": 0.44,
  "strong_win_rate": 0.56,
  "weak_win_rate": 0.48,
  "trending_win_rate": 0.61,
  "ranging_win_rate": 0.41,
  "z_score": 0.7,
  "p_value": 0.48,
  "is_significant": false
}
```

**Interpretation**:
- ⚠️ **51% win rate** - Barely better than random
- ⚠️ **1.05 profit factor** - Minimal edge
- ❌ **Not statistically significant** - Could be luck
- 📊 **Bearish signals (44%)** are losing - don't trade bearish
- 📊 **Weak signals (48%)** are losing - filter out
- 📊 **Trending (61%)** vs Ranging (41%) - must filter regime

**Action**: System needs improvement. Options:
1. Increase thresholds (try 75+ score, 0.70+ confidence)
2. Only trade bullish + strong + trending
3. Adjust indicator weights or add new indicators
4. Investigate why bearish signals fail

### Example 3: Overfitting Warning

```json
{
  "win_rate": 0.8500,
  "profit_factor": 5.2,
  "total_trades": 8,
  "z_score": 1.2,
  "p_value": 0.23,
  "is_significant": false
}
```

**Interpretation**:
- 🚨 **85% win rate looks great BUT...**
- 🚨 **Only 8 trades** - insufficient sample size
- ❌ **Not statistically significant** - need 30+ trades minimum
- ⚠️ **Risk of overfitting** to specific market conditions

**Action**:
- Extend backtest period to get 30+ trades
- Test on out-of-sample data (different date range)
- Don't deploy until validated on larger sample

---

## Advanced Features

### Walk-Forward Analysis

To avoid overfitting, use rolling backtests:

```python
# Test Q1 2024
backtest_1 = run_backtest("2024-01-01", "2024-03-31", params)

# Test Q2 2024
backtest_2 = run_backtest("2024-04-01", "2024-06-30", params)

# Test Q3 2024
backtest_3 = run_backtest("2024-07-01", "2024-09-30", params)

# Compare consistency
if all(run['win_rate'] > 0.55 for run in [backtest_1, backtest_2, backtest_3]):
    print("Consistent performance - likely robust")
else:
    print("Inconsistent - may be curve-fitted")
```

### Indicator Contribution Analysis

After running a backtest, query `technical_indicator_performance` table to see:
- Which indicators appear most often in winning trades
- Which indicators have the highest win rate when they contribute
- Should you increase/decrease weights for specific indicators?

### Time-Based Analysis

Analyze trades by:
- **Hour of day**: Do morning signals work better than afternoon?
- **Day of week**: Are Mondays different from Fridays?
- **Month**: Seasonal patterns?

### Monte Carlo Simulation

To test robustness:
1. Run 1000 backtests with random entry timing (±30 min)
2. Plot distribution of win rates
3. If 95% of simulations still show win rate > 55%, system is robust

---

## Best Practices

### 1. Minimum Sample Size
- Need **at least 30 trades** for statistical significance
- Preferably 50+ for reliable conclusions
- If you have < 30, extend the backtest period

### 2. Out-of-Sample Testing
- Don't optimize parameters on the same data you test
- Use 70% of data for optimization, 30% for validation
- Best: optimize on 2023 data, validate on 2024 data

### 3. Transaction Costs
- The backtest assumes perfect fills at close prices
- In reality, add ~0.5-1% slippage for intraday options
- Adjust profit factor expectations accordingly

### 4. Multiple Timeframe Validation
- If 15m signals work, test on 5m and 30m too
- Consistent results across timeframes = more reliable
- If only 15m works, might be overfitted

### 5. Regime Filtering is Critical
- **Key finding from research**: Technical signals work best in trending markets
- Always check `trending_win_rate` vs `ranging_win_rate`
- If difference > 15%, add ADX filter (e.g., ADX > 25)

### 6. Direction Bias Check
- If bullish win rate is 70% but bearish is 45%, only trade bullish
- Don't force symmetry if market has directional bias
- This is especially important in structurally trending markets

---

## Integration with Frontend

### Accuracy Dashboard Component (To Be Built)

The frontend should display:

1. **Summary Card**
   - Current accuracy across all backtests
   - Average win rate, profit factor
   - Number of backtests run

2. **Latest Run Details**
   - Win rate by direction, strength, regime
   - Statistical significance badge
   - Trade-by-trade breakdown

3. **Historical Trend Chart**
   - Win rate over time (last 10 runs)
   - Profit factor trend
   - Shows if system is improving or degrading

4. **Configuration Comparison**
   - Table comparing different parameter sets
   - Best configuration highlighted
   - "Use These Settings" button

5. **Run New Backtest Form**
   - Symbol selector (multi-select)
   - Date range picker
   - Parameter sliders (threshold, confidence)
   - "Run Backtest" button with progress indicator

---

## Troubleshooting

### "Insufficient data for symbol XYZ"
- Yahoo Finance may not have intraday data for all symbols
- Try a different symbol or use daily timeframe
- Check `YFINANCE_TICKER_MAP` in `constants.py` for correct ticker

### "Backtest completed with 0 trades"
- Thresholds too high (no signals met criteria)
- Lower `min_score_threshold` or `min_confidence`
- Or extend date range for more opportunities

### "Not statistically significant"
- Need more trades (extend date range or add more symbols)
- Or accept that sample is too small for conclusions

### "Win rate < 50%"
- System is not working on this data
- Check if you're in a different market regime
- Review indicator weights and parameters
- Consider that the market may have changed

---

## Future Enhancements

Potential additions to the accuracy testing system:

1. **Equity Curve Visualization**: Plot cumulative P&L over time
2. **Drawdown Analysis**: Maximum peak-to-trough decline
3. **Sharpe Ratio**: Risk-adjusted returns
4. **Monte Carlo Simulation**: Randomized entry timing tests
5. **Parameter Optimization**: Grid search for best configuration
6. **Indicator Attribution**: Which indicators drive wins?
7. **Time Decay Analysis**: Do signals degrade over time?
8. **Market Regime Detection**: Auto-classify trending vs ranging periods
9. **Live Accuracy Tracking**: Real-time validation on paper trades
10. **Comparison with Other Models**: Technical vs OI vs ML ensemble

---

## Conclusion

This accuracy testing system transforms the Technical Score Tab from an experimental model into a **validated, data-driven trading signal generator**.

### Key Takeaways:

1. **Always backtest before trading** - Don't trust intuition
2. **Statistical significance matters** - 30+ trades minimum
3. **Filter by regime** - Trending markets are key
4. **Strong signals outperform** - Weak signals often fail
5. **Iterate based on data** - Use metrics to improve

### Success Criteria:

A successful technical signal system should achieve:
- ✅ Win rate > 55% (better than random)
- ✅ Profit factor > 1.5 (good risk/reward)
- ✅ Statistically significant (p-value < 0.05)
- ✅ Consistent across time periods
- ✅ Clear regime/strength patterns

**The system is now production-ready for rigorous validation and continuous improvement.**
