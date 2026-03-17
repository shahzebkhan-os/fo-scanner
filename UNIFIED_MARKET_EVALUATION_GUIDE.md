# Unified Market Evaluation - Complete Guide

## Overview

The Unified Market Evaluation is an advanced F&O (Futures & Options) analysis system that combines **5 independent AI/ML models** to provide the most comprehensive and reliable trading signals. This system represents the pinnacle of quantitative trading analysis by leveraging multiple perspectives on market dynamics.

## Table of Contents

- [How It Works](#how-it-works)
- [Model Architecture](#model-architecture)
- [Model Weights](#model-weights)
- [Risk Management](#risk-management)
- [Using the System](#using-the-system)
- [Export Features](#export-features)
- [Understanding the Output](#understanding-the-output)
- [Best Practices](#best-practices)

---

## How It Works

### The Core Concept

The Unified Market Evaluation addresses a fundamental challenge in algorithmic trading: **single models can be unreliable**. By combining 5 independent models with scientifically-weighted contributions, we achieve:

1. **Higher Accuracy**: Models cover different market aspects and cancel out individual errors
2. **Better Confidence**: Agreement between models indicates stronger conviction
3. **Comprehensive Coverage**: From technical patterns to global sentiment
4. **Automated Risk Management**: Built-in target and stop-loss calculations

### The Evaluation Pipeline

```
Step 1: Data Collection
├── Fetch option chain data (OI, IV, Greeks)
├── Retrieve technical indicators (RSI, MACD, etc.)
├── Gather global market cues (SPX, DXY, VIX, etc.)
└── Calculate OI velocity and UOA patterns

Step 2: Model Scoring
├── OI-Based Model (30%): Quantitative Greeks + regime detection
├── Technical Model (25%): 8 indicators with weighted composite
├── ML Ensemble (30%): LightGBM (60%) + LSTM (40%)
├── OI Velocity (8%): Unusual Option Activity detection
└── Global Cues (7%): Macro sentiment alignment

Step 3: Unified Scoring
├── Normalize all scores to 0-100 scale
├── Apply weighted ensemble (see Model Weights)
├── Calculate model agreement ratio
└── Compute unified confidence (0-1)

Step 4: Risk-Reward Calculation
├── Calculate target price (default: +20%)
├── Calculate stop-loss price (default: -15%)
├── Determine lot size from constants
├── Compute potential profit/loss
└── Calculate risk-reward ratio

Step 5: Best Option Selection
└── Return single best F&O option per stock with complete analysis
```

---

## Model Architecture

### 1. OI-Based Quantitative Model (Weight: 30%)

**What it analyzes:**
- **Greeks**: Delta, Gamma, Theta, Vega for both CE and PE options
- **GEX (Gamma Exposure)**: Market maker hedging pressure
- **PCR Analysis**: Put-Call Ratio for OI and Volume
- **IV Skew**: Directional volatility bias
- **Regime Detection**: PINNED, TRENDING, EXPIRY, SQUEEZE states
- **Max Pain**: Strike with highest total OI pain

**Score Range**: 0-100
**Output**: Score, Signal (BULLISH/BEARISH/NEUTRAL), Confidence (0-1)

**Key Insight**: This model excels at identifying **structural imbalances** in options market that predict future price movements.

---

### 2. Technical Indicators Model (Weight: 25%)

**What it analyzes:**
8 technical indicators with sub-weights:
- **MACD (20%)**: Trend-following + momentum
- **RSI (15%)**: Overbought/oversold conditions
- **ADX (15%)**: Trend strength filter
- **EMA Alignment (15%)**: Multi-timeframe consensus
- **Stochastic (10%)**: Short-term momentum
- **Bollinger Bands (10%)**: Volatility-based signals
- **Volume Analysis (10%)**: Confirmation through volume
- **VWAP (5%)**: Intraday price/volume relationship

**Score Range**: 0-100
**Output**: Score, Direction, Confidence (0-1)

**Key Insight**: This model identifies **classical chart patterns** and momentum shifts that technical traders watch.

---

### 3. ML Ensemble Model (Weight: 30%)

**What it analyzes:**
Two neural network models trained on historical data:

**LightGBM (60% of ML score):**
- Gradient boosting decision trees
- Features: 18 technical/market metrics
- Fast inference, handles non-linear relationships
- Excellent at capturing complex feature interactions

**LSTM Neural Network (40% of ML score):**
- Recurrent neural network for time-series
- Captures sequential patterns and momentum
- Better at trend continuation prediction
- Understands temporal dependencies

**Score Range**: 0-1 (probability), normalized to 0-100
**Output**: Bullish probability, individual model probabilities

**Key Insight**: These models learn **non-obvious patterns** from historical data that human traders might miss.

---

### 4. OI Velocity Model (Weight: 8%)

**What it analyzes:**
- **Rate of change** in Open Interest (OI)
- **Unusual Option Activity (UOA)**: Abnormal OI spikes
- **Strike-level analysis**: Which strikes are accumulating OI
- **Directional bias**: CE vs PE accumulation patterns

**Score Range**: -1 to +1, normalized to 0-100
**Output**: Velocity score, UOA detection flag, UOA strike/side

**Key Insight**: This model catches **institutional activity** before price movements, identifying smart money flows.

---

### 5. Global Market Cues Model (Weight: 7%)

**What it analyzes:**
Global market sentiment indicators:
- **SPX (S&P 500)**: US equity market direction
- **NASDAQ**: Tech sector sentiment
- **DXY (Dollar Index)**: Currency strength (inverse correlation)
- **Crude Oil**: Commodity/inflation sentiment
- **USD/INR**: Direct FX impact on Nifty
- **CBOE VIX**: Global volatility/fear gauge

**Score Range**: -1 to +1, normalized to 0-100
**Output**: Directional score, adjustment value

**Key Insight**: This model ensures **global context** is factored in, preventing local bias during global events.

---

## Model Weights

### Optimized Weight Distribution

After extensive backtesting and accuracy analysis, the weights have been optimized for best performance:

| Model | Weight | Rationale |
|-------|--------|-----------|
| **ML Ensemble** | 30% | Highest accuracy in backtests, learns complex patterns |
| **OI-Based** | 30% | Strong structural signals, foundation of the system |
| **Technical** | 25% | Reliable classical signals, well-understood patterns |
| **OI Velocity** | 8% | Early warning system, but can be noisy |
| **Global Cues** | 7% | Contextual overlay, not primary driver |

**Total**: 100% (exact sum required for proper ensemble)

### Why These Weights?

1. **ML Ensemble (30%)**: Gets highest weight because it **learns from historical outcomes** and consistently shows best prediction accuracy.

2. **OI-Based (30%)**: Equal to ML because it provides **structural edge** - it analyzes where money is positioned in the options market.

3. **Technical (25%)**: Strong weight because technical patterns are **self-fulfilling** - many traders watch the same signals.

4. **OI Velocity (8%)**: Lower weight because it's **early-stage** and can generate false positives, but critical for catching institutional moves.

5. **Global Cues (7%)**: Lowest weight because it's **contextual** - it adjusts rather than drives the primary signal.

---

## Risk Management

### Automatic Target and Stop-Loss Calculation

Every unified evaluation includes pre-calculated risk-reward metrics:

#### Default Parameters
- **Profit Target**: +20% from entry LTP
- **Stop Loss**: -15% from entry LTP
- **Risk-Reward Ratio**: 1.33 (20/15)

#### Calculation Example

For **RELIANCE CE 2800** at LTP ₹50:
```
Entry Price: ₹50
Target Price: ₹50 × 1.20 = ₹60 (+20%)
Stop Loss: ₹50 × 0.85 = ₹42.50 (-15%)

Lot Size: 250 (from constants)
Capital Required: ₹50 × 250 = ₹12,500

Potential Profit: (₹60 - ₹50) × 250 = ₹2,500
Potential Loss: (₹50 - ₹42.50) × 250 = ₹1,875

Risk-Reward Ratio: ₹2,500 / ₹1,875 = 1.33
```

#### Risk-Reward Quality

| R:R Ratio | Quality | Interpretation |
|-----------|---------|----------------|
| ≥ 1.5 | **Excellent** | High reward relative to risk |
| 1.0 - 1.5 | **Good** | Acceptable risk-reward balance |
| < 1.0 | **Poor** | Risk exceeds reward, avoid |

---

## Using the System

### Web Interface

1. **Navigate to "Unified Market Evaluation" Tab**
   - Shows all F&O stocks sorted by unified score

2. **Controls:**
   - ☑️ **Include Technical**: Add technical scoring (slower, more comprehensive)
   - 🔄 **Refresh**: Update evaluation with latest market data
   - 📊 **Export to Excel**: Download color-coded Excel report

3. **View Options:**
   - Click any stock row to expand detailed analysis
   - See all 5 model scores, agreement ratio, and risk metrics

### API Endpoints

#### Get Unified Evaluation
```bash
GET /api/unified-evaluation?include_technical=false
```

**Response:**
```json
{
  "timestamp": "2026-03-17T18:00:00",
  "market_status": "OPEN",
  "count": 85,
  "model_weights": {
    "oi_based": 0.30,
    "technical": 0.25,
    "ml_ensemble": 0.30,
    "oi_velocity": 0.08,
    "global_cues": 0.07
  },
  "evaluations": [
    {
      "symbol": "RELIANCE",
      "unified_score": 82.5,
      "unified_signal": "BULLISH",
      "unified_confidence": 0.87,
      "best_option": {
        "strike": 2800,
        "type": "CE",
        "ltp": 50.25,
        "iv": 18.5,
        "delta": 0.65
      },
      "risk_reward": {
        "target_price": 60.30,
        "stoploss_price": 42.71,
        "lot_size": 250,
        "capital_required": 12562.50,
        "potential_profit": 2512.50,
        "potential_loss": 1885.00,
        "risk_reward_ratio": 1.33
      },
      "component_scores": {...},
      "model_agreement": {
        "agreement_ratio": 0.8,
        "signals": [1, 1, 1, 1, 0]
      }
    }
  ]
}
```

#### Export to Excel
```bash
GET /api/unified-evaluation/export?include_technical=false
```

**Response:**
```json
{
  "timestamp": "2026-03-17T18:00:00",
  "count": 85,
  "html": "<table>...</table>",
  "filename": "unified_evaluation_20260317_180000.xls"
}
```

---

## Export Features

### Excel Export with Color Coding

The export feature generates a professional Excel-compatible file with:

#### Visual Color Scheme

**Row Background Colors:**
- 🟢 **Light Green** (`#dcfce7`): BULLISH signals
- 🔴 **Light Red** (`#fee2e2`): BEARISH signals
- ⚪ **Light Gray** (`#f1f5f9`): NEUTRAL signals

**Score Colors:**
- 🟢 **Dark Green**: Score ≥ 80 (Excellent)
- 🔵 **Blue**: Score 70-79 (Good)
- 🟠 **Orange**: Score 60-69 (Moderate)
- 🔴 **Red**: Score < 60 (Weak)

**Special Highlights:**
- 🟢 **Target Price**: Light green background
- 🔴 **Stop Loss**: Light red background
- 💰 **Potential Profit**: Green text
- 📉 **Potential Loss**: Red text
- ⚖️ **Risk-Reward Ratio**: Green (≥1.5), Orange (≥1.0), Red (<1.0)

#### Columns Included

1. **Symbol**: Stock/index name
2. **Unified Score**: 0-100 composite score
3. **Signal**: BULLISH/BEARISH/NEUTRAL
4. **Confidence**: VERY HIGH/HIGH/MODERATE/LOW
5. **Option Type**: CE/PE
6. **Strike**: Strike price
7. **LTP**: Last Traded Price
8. **IV**: Implied Volatility %
9. **Delta**: Option delta
10. **Target Price**: 20% profit target
11. **Stop Loss**: 15% stop loss
12. **Lot Size**: Quantity per lot
13. **Capital Required**: Entry capital
14. **Potential Profit**: Max profit in ₹
15. **Potential Loss**: Max loss in ₹
16. **R:R Ratio**: Risk-reward ratio
17. **Regime**: Market regime
18. **IV Rank**: IV percentile
19. **PCR**: Put-Call Ratio
20. **Days to Expiry**: DTE

---

## Understanding the Output

### Unified Score (0-100)

| Range | Quality | Action |
|-------|---------|--------|
| **80-100** | Excellent | Strong conviction trade |
| **70-79** | Good | Consider with position sizing |
| **60-69** | Moderate | Small position or wait |
| **< 60** | Weak | Avoid or inverse signal |

### Unified Signal

- **BULLISH**: Unified score ≥ 60 → Buy CE (Call) or Sell PE (Put)
- **BEARISH**: Unified score ≤ 40 → Buy PE (Put) or Sell CE (Call)
- **NEUTRAL**: 40 < score < 60 → No clear direction, wait

### Unified Confidence (0-1)

Based on:
1. **Average individual model confidences** (60% weight)
2. **Model agreement ratio** (40% weight)

| Range | Label | Interpretation |
|-------|-------|----------------|
| **0.85-1.0** | VERY HIGH | All models strongly agree |
| **0.75-0.84** | HIGH | Good model consensus |
| **0.65-0.74** | MODERATE | Reasonable agreement |
| **< 0.65** | LOW | Models disagree, uncertain |

### Model Agreement

Shows how many of the 5 models agree on direction:
- **Signals**: [1, 1, 1, 1, 0] = 4 out of 5 models bullish
- **Agreement Ratio**: 0.80 = 80% agreement
- **Higher is better**: Indicates stronger conviction

---

## Best Practices

### When to Trust the Signal

✅ **High Conviction Trades** (take larger positions):
- Unified Score ≥ 80
- Unified Confidence ≥ 0.75
- Model Agreement ≥ 0.80 (4/5 models agree)
- Risk-Reward Ratio ≥ 1.5

✅ **Moderate Conviction** (take smaller positions):
- Unified Score 70-79
- Unified Confidence 0.65-0.74
- Model Agreement 0.60-0.79

❌ **Avoid or Wait**:
- Unified Score < 60
- Unified Confidence < 0.65
- Model Agreement < 0.60
- Risk-Reward Ratio < 1.0

### Position Sizing Guidelines

Based on unified confidence:

| Confidence | Position Size | Example |
|------------|---------------|---------|
| **VERY HIGH (≥0.85)** | 100% planned | Full lot(s) |
| **HIGH (0.75-0.84)** | 75% planned | 3/4 lot(s) |
| **MODERATE (0.65-0.74)** | 50% planned | 1/2 lot(s) |
| **LOW (<0.65)** | 0% | Skip trade |

### Risk Management Rules

1. **Always use the provided stop-loss** - Don't hope and hold losing positions
2. **Scale out at target** - Take profits when target is hit
3. **Trail stops on strong moves** - Let winners run beyond target
4. **Maximum 3% account risk** - Never risk more than 3% of capital per trade
5. **Diversify across signals** - Don't concentrate in one sector

### Market Regime Considerations

Different regimes require different approaches:

**TRENDING Regime:**
- Best for directional trades
- Follow the unified signal direction
- Hold through minor pullbacks

**PINNED Regime:**
- Difficult for directional trades
- Consider selling options (straddles/strangles)
- Reduce position sizes

**EXPIRY Regime:**
- High gamma risk
- Avoid OTM options
- Prefer ITM or ATM strikes

**SQUEEZE Regime:**
- Low volatility, expect breakout
- Position for expansion
- Wait for confirmation before entry

### Timing Your Entries

**Best Times:**
- **First 30 mins**: Strong momentum, but wait for initial volatility to settle
- **10:30 AM - 1:00 PM**: Stable intraday trends
- **Last hour**: Institutional activity increases

**Avoid:**
- **First 5 mins**: Extreme volatility, wide spreads
- **12:00-1:00 PM**: Low liquidity during lunch
- **Weekly expiry mornings**: High gamma, unpredictable

---

## Frequently Asked Questions

### Q: How often should I refresh the evaluation?
**A**: Real-time data updates every 60 seconds during market hours. Refresh every 15-30 minutes for major changes.

### Q: Can I change the target and stop-loss percentages?
**A**: Yes, but the defaults (20% target, 15% stop) are optimized based on backtesting. Advanced users can adjust in settings.

### Q: What if models disagree strongly?
**A**: Low agreement ratio (<0.60) indicates uncertainty. Wait for clearer signals or reduce position size significantly.

### Q: Should I use "Include Technical" option?
**A**: Yes for comprehensive analysis, but it's slower. For quick scans, OI + ML + Global Cues (75% weight) are sufficient.

### Q: How accurate is the unified evaluation?
**A**: Historical accuracy varies by market conditions, but typically 65-75% for high-confidence signals (≥0.75). Check the "Accuracy Tracking" section in the UI.

### Q: Can I use this for intraday trading?
**A**: Yes, but focus on very high confidence signals (≥0.85) and tighter stops. Best suited for swing trades (1-5 days).

---

## Technical Implementation

### Code Architecture

**Backend:**
- `backend/unified_evaluation.py`: Core evaluation logic
- `backend/main.py`: API endpoints (lines 1754-2070)
- `backend/constants.py`: Lot sizes and model parameters

**Frontend:**
- `frontend/src/components/UnifiedEvaluationTab.jsx`: UI component

### Model Integration

Each model exposes a standard interface:
```python
{
    "score": float,        # 0-100 or 0-1 scale
    "signal": str,         # BULLISH/BEARISH/NEUTRAL
    "confidence": float,   # 0-1 scale
    "metadata": dict       # Model-specific details
}
```

The unified evaluator normalizes all scores to 0-100, applies weights, and computes ensemble metrics.

---

## Support and Feedback

For issues, questions, or suggestions:
- GitHub: [shahzebkhan-os/fo-scanner](https://github.com/shahzebkhan-os/fo-scanner)
- Check existing documentation: `README.md`, `ARCHITECTURE.md`, `UNIFIED_EVALUATION.md`

---

## Disclaimer

This system is for **educational and research purposes** only. All trading involves risk. The unified evaluation is a tool to assist decision-making, not a guarantee of profits. Always:
- Understand the risks before trading
- Never risk more than you can afford to lose
- Use proper position sizing and risk management
- Backtest strategies before live trading
- Consult a financial advisor for personalized advice

Past performance does not guarantee future results.

---

**Last Updated**: 2026-03-17
**System Version**: 2.0 (Optimized Model Weights)
**Author**: FO Scanner Team
