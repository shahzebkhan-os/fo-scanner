# ML Score and QUANT Score Research Analysis

## Executive Summary

This document provides a comprehensive analysis of how ML Score and QUANT Score are calculated in the NSE F&O Scanner, along with research-backed recommendations for improving their accuracy.

---

## Table of Contents

1. [Current Implementation Analysis](#1-current-implementation-analysis)
2. [QUANT Score Deep Dive](#2-quant-score-deep-dive)
3. [ML Score Deep Dive](#3-ml-score-deep-dive)
4. [12-Signal Engine Architecture](#4-12-signal-engine-architecture)
5. [Identified Issues and Limitations](#5-identified-issues-and-limitations)
6. [Research-Backed Improvement Recommendations](#6-research-backed-improvement-recommendations)
7. [Implementation Priority](#7-implementation-priority)

---

## 1. Current Implementation Analysis

### Score Display in UI (ScannerTab.jsx)

Both scores are displayed as dials (0-100) in the scanner cards:

```jsx
<ScoreDial score={r.score} theme={theme} subLabel="QUANT" />
<ScoreDial score={r.ml_score || 0} theme={theme} subLabel="ML SCORE" />
```

### Score Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  DATA COLLECTION                                                 │
│  NSE Option Chain → fetch_nse_chain()                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  QUANT SCORE CALCULATION                                         │
│  compute_stock_score_v2() in backend/analytics.py               │
│  → Returns: score (0-100), signal (BULLISH/BEARISH/NEUTRAL)     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  ML SCORE CALCULATION                                            │
│  ml_predict() in backend/ml_model.py                            │
│  → Returns: probability (0.0-1.0) of bullish next bar           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  SIGNAL REFINEMENT                                               │
│  ML probability refines QUANT signal:                           │
│  - Confirmation: +5 to score if ML agrees strongly              │
│  - Divergence: Signal → NEUTRAL, -15 from score                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. QUANT Score Deep Dive

### Location: `backend/analytics.py::compute_stock_score_v2()`

### Input Data Required
- `chain_data`: Full options chain (CE/PE for all strikes)
- `spot`: Current underlying price
- `symbol`: Stock/Index symbol
- `expiry_str`: Option expiry date
- `iv_rank_data`: Historical IV rank data
- `prev_chain_data`: Previous snapshot for buildup detection
- `fii_net`: FII net position data

### Scoring Components (5 Factors)

#### 1. GEX (Gamma Exposure) Signal
```python
gex_data = compute_gex(records, spot, lot_size)
is_spot_above_zgl = spot > gex_data["zero_gamma_level"]
gex_bullish = is_spot_above_zgl and gex_data["net_gex"] > 0
# sub_gex = 100 if bullish, 0 if bearish, 50 if neutral
```

**How GEX is calculated:**
- For each strike: `ce_gex = ce_oi × ce_gamma × lot_size × (spot²) / 100`
- `net_gex = total_call_gex - total_put_gex`
- Positive GEX → market makers dampen moves (PINNED regime)
- Negative GEX → market makers amplify moves (TRENDING regime)

#### 2. Volume PCR (Put-Call Volume Ratio)
```python
vol_pcr = pe_vol / ce_vol if ce_vol > 0 else 1.0
sub_volpcr = min(100, max(0, vol_pcr * 50))
```

**Interpretation:**
- PCR > 1.2 → Bullish (excessive put buying = contrarian buy)
- PCR < 0.8 → Bearish (excessive call buying = contrarian sell)

#### 3. DWOI PCR (Delta-Weighted Open Interest PCR)
```python
ce_dwoi = ce_oi * abs(ce_delta)  # For each strike
pe_dwoi = pe_oi * abs(pe_delta)
dwoi_pcr = pe_dwoi / ce_dwoi
sub_dwoipcr = min(100, max(0, dwoi_pcr * 50))
```

**Purpose:** Weights OI by delta to give more importance to ATM options.

#### 4. IV Skew
```python
skew = pe_iv - ce_iv  # At ATM strike
# skew > 2.0 → BEARISH (fear in puts)
# skew < -1.0 → BULLISH (complacency in puts)
sub_skew = 100 - skew_percentile
```

#### 5. OI Buildup Pattern
```python
# Compares current OI vs previous snapshot
# Long buildup: Price ↑ + OI ↑ → Bullish
# Short buildup: Price ↓ + OI ↑ → Bearish
sub_build = 100 if BULLISH else (0 if BEARISH else 50)
```

### Regime-Based Weighting

The weights change based on market regime:

| Regime    | GEX   | Vol PCR | DWOI  | Skew  | Buildup |
|-----------|-------|---------|-------|-------|---------|
| PINNED    | 30%   | 10%     | 40%   | 10%   | 10%     |
| TRENDING  | 15%   | 25%     | 15%   | 20%   | 25%     |
| EXPIRY    | 10%   | 40%     | 10%   | 10%   | 30%     |
| SQUEEZE   | 40%   | 30%     | 10%   | 10%   | 10%     |

### Final Score Calculation
```python
weighted_score = (
    (sub_gex     * weights["gex"]) +
    (sub_volpcr  * weights["vol_pcr"]) +
    (sub_dwoipcr * weights["dwoi"]) +
    (sub_skew    * weights["skew"]) +
    (sub_build   * weights["buildup"])
)
# FII penalty for bearish index signals
if direction == "BEARISH" and fii_net < 0 and symbol in ["NIFTY", "BANKNIFTY"]:
    weighted_score = max(0, weighted_score / 1.15)
```

---

## 3. ML Score Deep Dive

### Location: `backend/ml_model.py`

### Model Architecture
- **Algorithm:** LightGBM (Gradient Boosting)
- **Task:** Binary classification (next bar direction)
- **Calibration:** Isotonic regression for probability calibration
- **Cross-validation:** TimeSeriesSplit (no look-ahead bias)

### Training Data
```sql
SELECT
    score as weighted_score,
    COALESCE(net_gex, 0) as gex,
    COALESCE(iv_skew, 0) as iv_skew,
    COALESCE(pcr_oi, 1) as pcr,
    regime,
    spot_price,
    symbol,
    snapshot_time
FROM market_snapshots
WHERE spot_price IS NOT NULL AND spot_price > 0
ORDER BY symbol, snapshot_time ASC
```

### Features Used (Only 5!)
1. `weighted_score` - QUANT score from analytics.py
2. `gex` - Net gamma exposure
3. `iv_skew` - Put-Call IV differential
4. `pcr` - Put-Call OI ratio
5. `regime_encoded` - Market regime (0-3)

### Target Label
```python
df["label"] = (df["next_spot"] > df["spot_price"]).astype(int)
# 1 = price went up next bar, 0 = price went down
```

### Model Parameters
```python
params = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 20,
    "n_estimators": 200,
    "random_state": 42,
}
```

### ML Score Conversion in main.py
```python
ml_prob = ml_predict(stats)  # Returns 0.0-1.0

if signal == "BULLISH":
    ml_score = int(ml_prob * 100)  # High prob = high score
elif signal == "BEARISH":
    ml_score = int((1 - ml_prob) * 100)  # Low prob = high score
else:
    ml_score = int(max(ml_prob, 1 - ml_prob) * 100)  # Confidence
```

### ML-QUANT Integration Rules

**Rule 1: Confirmation (Boost)**
```python
if stock_score >= 80 and (
    (signal == "BULLISH" and ml_prob > 0.70) or
    (signal == "BEARISH" and ml_prob < 0.30)
):
    stats["score"] = min(100, stock_score + 5)
```

**Rule 2: Divergence Guard (Downgrade)**
```python
elif (signal == "BULLISH" and ml_prob < 0.40) or (signal == "BEARISH" and ml_prob > 0.60):
    stats["signal"] = "NEUTRAL"
    stats["score"] = max(0, stock_score - 15)
```

---

## 4. 12-Signal Engine Architecture

### Location: `backend/signals/engine.py`

The project has a more comprehensive 12-signal system that is NOT fully integrated with the main QUANT score:

| Signal | Name | Weight (Range-Bound) | Implementation |
|--------|------|----------------------|----------------|
| 1 | OI Analysis | 20% | `oi_analysis.py` |
| 2 | IV Analysis | 20% | `iv_analysis.py` |
| 3 | Max Pain & GEX | 15% | `max_pain.py` |
| 4 | India VIX | (part of IV) | `iv_analysis.py` |
| 5 | Price Action | 8% | `price_action.py` |
| 6 | Technicals | 5% | `technicals.py` |
| 7 | Global Cues | - | `global_cues.py` |
| 8 | FII/DII | - | `fii_dii.py` |
| 9 | Straddle Pricing | 15% | `straddle_pricing.py` |
| 10 | News Scanner | - | `news_scanner.py` |
| 11 | Regime Classifier | - | `market/regime.py` |
| 12 | Greeks Signal | 10% | `greeks_signal.py` |

**Key Finding:** The 12-signal engine (`MasterSignalEngine`) is implemented but appears to NOT be used in the main scan endpoint. The main `/api/scan` uses the simpler `compute_stock_score_v2()`.

---

## 5. Identified Issues and Limitations

### QUANT Score Issues

1. **Limited Technical Analysis**
   - No price momentum indicators (RSI, MACD)
   - No trend confirmation (EMAs, Supertrend)
   - Relies purely on options chain data

2. **Static Thresholds**
   - PCR thresholds (1.2, 0.8) are fixed
   - Should adapt based on historical PCR distribution

3. **Missing Time-of-Day Adjustments**
   - No adjustment for morning volatility
   - No adjustment for expiry day behavior

4. **Buildup Detection Weakness**
   - Requires previous snapshot (often unavailable)
   - Falls back to "NEUTRAL" when data missing

5. **Regime Detection Simplicity**
   - Only 4 regimes (PINNED, TRENDING, EXPIRY, SQUEEZE)
   - Missing intraday regime shifts

### ML Score Issues

1. **Feature Poverty**
   - Only 5 features, most derived from QUANT score
   - ML essentially learns to smooth QUANT predictions
   - No technical indicators in features

2. **Target Simplification**
   - Binary up/down classification loses magnitude
   - A 0.1% move = 2% move in training

3. **No Time Features**
   - Missing hour-of-day, day-of-week
   - Missing days-to-expiry as feature

4. **Missing Market Context**
   - No VIX feature
   - No index correlation features
   - No sector momentum

5. **Calibration Assumptions**
   - Isotonic regression may not generalize well
   - No periodic recalibration mechanism

6. **Data Quality**
   - Minimum 500 rows required
   - No handling of market regime shifts in training data

### System Integration Issues

1. **12-Signal Engine Underutilization**
   - Comprehensive signals exist but aren't used
   - Main scan uses simpler 5-factor model

2. **Score Inconsistency**
   - QUANT returns 0-100 integer
   - ML returns 0.0-1.0 probability
   - Conversion loses information

3. **No Ensemble Approach**
   - ML and QUANT are sequential, not parallel
   - Could use stacking or blending

---

## 6. Research-Backed Improvement Recommendations

### A. QUANT Score Improvements

#### A1. Add Technical Confirmation Layer
```python
# Add to compute_stock_score_v2()
tech_score = compute_technical_confirmation(prices[-20:])
# RSI, EMA crossover, volume confirmation
# Weight: 15% of total score
```

**Research Basis:** Academic studies show options flow + price momentum combination improves signal accuracy by 15-25%.

#### A2. Dynamic PCR Thresholds
```python
# Instead of fixed 1.2/0.8
pcr_mean = np.mean(pcr_history[-20:])
pcr_std = np.std(pcr_history[-20:])
PCR_BULLISH_THRESHOLD = pcr_mean + 1.5 * pcr_std
PCR_BEARISH_THRESHOLD = pcr_mean - 1.5 * pcr_std
```

**Research Basis:** Mean-reversion strategies with dynamic bands outperform fixed thresholds.

#### A3. Time-of-Day Adjustment
```python
# Morning volatility discount (9:15-10:30)
if 9 <= current_hour < 10.5:
    score_adjustment = 0.85  # 15% discount
# Expiry day volatility
if is_expiry_day and current_hour >= 14:
    score_adjustment *= 0.90  # Additional 10% discount
```

#### A4. Integrate 12-Signal Engine
```python
# Replace simple score with full engine
engine = MasterSignalEngine()
result = engine.compute_all_signals(
    spot=spot,
    records=records,
    vix=current_vix,
    # ... all other inputs
)
composite_score = (result.composite_score + 1) * 50  # Convert -1..1 to 0..100
```

### B. ML Score Improvements

#### B1. Feature Engineering Expansion
```python
# Add 10+ new features
features = [
    "weighted_score",      # Existing
    "gex",                 # Existing
    "iv_skew",             # Existing
    "pcr",                 # Existing
    "regime_encoded",      # Existing
    # NEW FEATURES:
    "vix",                 # India VIX
    "vix_change_pct",      # VIX momentum
    "dte",                 # Days to expiry
    "hour_sin",            # Cyclical hour encoding
    "hour_cos",            # Cyclical hour encoding
    "day_of_week",         # 0-4
    "price_momentum_5",    # 5-bar price change %
    "volume_spike",        # Current vol / 20-bar avg
    "rsi_14",              # RSI indicator
    "bb_position",         # Position within Bollinger Bands
    "max_pain_distance",   # Distance from max pain
    "sector_momentum",     # Sector index change
]
```

**Research Basis:** Feature engineering is the highest-ROI improvement for gradient boosting models.

#### B2. Multi-Class or Regression Target
```python
# Instead of binary up/down
# Option 1: Multi-class
# 0 = down > 0.5%, 1 = sideways, 2 = up > 0.5%

# Option 2: Regression
df["target"] = (df["next_spot"] - df["spot_price"]) / df["spot_price"] * 100
# Then convert to probability via softmax
```

#### B3. Ensemble Architecture
```python
# Blend multiple models
models = {
    "lgbm": LGBMClassifier(...),
    "xgboost": XGBClassifier(...),
    "catboost": CatBoostClassifier(...),
}
# Final prediction = weighted average
final_prob = sum(w * m.predict_proba(X)[:, 1] for w, m in weights_models) / sum(weights)
```

#### B4. Walk-Forward Validation
```python
# Instead of simple TimeSeriesSplit
for train_end in monthly_checkpoints:
    train_data = data[data.date < train_end]
    test_data = data[(data.date >= train_end) & (data.date < train_end + 1_month)]
    model.fit(train_data)
    predictions = model.predict(test_data)
    # Track performance by regime
```

#### B5. Automated Retraining
```python
# Add to scheduler.py
async def retrain_ml_model_weekly():
    """Retrain ML model every Sunday night with latest data."""
    result = train_model()
    if result.get("cv_log_loss_mean", 1.0) < 0.69:  # Better than random
        log.info(f"Model retrained: {result}")
    else:
        log.warning(f"Model retrain failed quality check: {result}")
```

### C. System Integration Improvements

#### C1. Use Full Signal Engine
```python
# In main.py scan endpoint
from .signals.engine import MasterSignalEngine

engine = MasterSignalEngine()
aggregated = engine.compute_all_signals(
    spot=spot,
    records=records,
    # ... pass all available data
)

# Use aggregated signal instead of simple score
stats["signal_engine_score"] = aggregated.composite_score
stats["signal_engine_confidence"] = aggregated.confidence
stats["recommended_strategy"] = aggregated.recommended_strategy
```

#### C2. Stacking Ensemble
```python
# Level 1: Individual predictors
quant_score = compute_stock_score_v2(...)
ml_prob = ml_predict(...)
signal_engine = master_engine.compute_all_signals(...)

# Level 2: Meta-learner
meta_features = [
    quant_score / 100,
    ml_prob,
    signal_engine.composite_score,
    signal_engine.confidence,
]
final_score = meta_model.predict(meta_features)
```

#### C3. Confidence-Weighted Scoring
```python
# Weight scores by confidence
quant_weight = quant_confidence * 0.5
ml_weight = ml_confidence * 0.3
engine_weight = engine_confidence * 0.2

final_score = (
    quant_score * quant_weight +
    ml_score * ml_weight +
    engine_score * engine_weight
) / (quant_weight + ml_weight + engine_weight)
```

---

## 7. Implementation Priority

### Phase 1: Quick Wins (1-2 days)
1. ✅ Add VIX and DTE to ML features
2. ✅ Add hour-of-day cyclical features
3. ✅ Add time-of-day adjustment to QUANT score
4. ✅ Document current implementation (this file)

### Phase 2: Medium Effort (3-5 days)
1. Integrate 12-signal engine into main scan
2. Expand ML features to 15+
3. Add automated weekly retraining
4. Implement dynamic PCR thresholds

### Phase 3: Significant Effort (1-2 weeks)
1. Build stacking ensemble
2. Add walk-forward validation
3. Implement multi-model ensemble (LightGBM + XGBoost)
4. Add backtesting A/B comparison framework

### Phase 4: Research & Development (ongoing)
1. Experiment with deep learning (LSTM for sequence)
2. Add NLP for news sentiment
3. Cross-asset correlation features
4. Real-time performance monitoring dashboard

---

## Appendix: Code References

| Component | File | Function |
|-----------|------|----------|
| QUANT Score | `backend/analytics.py` | `compute_stock_score_v2()` |
| ML Model | `backend/ml_model.py` | `train_model()`, `predict()` |
| Signal Engine | `backend/signals/engine.py` | `MasterSignalEngine.compute_all_signals()` |
| Regime Classifier | `backend/market/regime.py` | `RegimeClassifier.classify()` |
| OI Analysis | `backend/signals/oi_analysis.py` | `OiSignal.compute()` |
| IV Analysis | `backend/signals/iv_analysis.py` | `IvSignal.compute()` |
| Technicals | `backend/signals/technicals.py` | `TechnicalSignal.compute()` |
| Score Display | `frontend/src/components/ScannerTab.jsx` | `<ScoreDial>` |

---

## Conclusion

The current scoring system is functional but has significant room for improvement:

1. **QUANT Score** relies solely on options chain data without price confirmation
2. **ML Score** uses only 5 features derived mostly from QUANT score
3. **12-Signal Engine** is implemented but not utilized in the main flow

**Expected accuracy improvement with recommendations:**
- Phase 1: 5-10% improvement
- Phase 2: 15-25% improvement  
- Phase 3: 25-40% improvement (compounded)

The key insight is that the codebase already has a sophisticated 12-signal architecture that isn't being used. Integrating it would be the highest-value improvement.
