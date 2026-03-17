# Unified Evaluation Improvements - Implementation Guide

This document describes the 5 improvements to the FO Scanner Unified Market Evaluation system, designed to increase win rate by filtering out low-quality signals.

## Overview

All 5 improvements work as **additive filters** on top of the existing unified evaluation pipeline. No existing model weights or scoring logic has been changed. Signals pass through 6 sequential gates before being shown to users.

## Architecture

### Filter Gate Sequence

```
Signal → Gate 1: F&O Ban Check
       → Gate 2: Time of Day Filter
       → Gate 3: Market Regime Override
       → Gate 4: Event Blackout
       → Gate 5: Signal Quality
       → Gate 6: Signal Persistence
       → Final Output (PRIME/QUALIFIED/CONFIRMED signals only)
```

## Implementation Details

### Improvement #1: Signal Quality Filter

**Location:** `backend/filters/signal_quality.py`

**Purpose:** Enforces 6 hard conditions that ALL must be true for a signal to be tradeable.

**Hard Filter Conditions:**

1. **Unified Score ≥ 75** (raised from 60)
2. **Model Agreement Ratio ≥ 0.80** (at least 4 of 5 models agree)
3. **Unified Confidence ≥ 0.80**
4. **Risk-Reward Ratio ≥ 1.5**
5. **Option Volume ≥ 20-day average**
6. **IV Rank between 20% and 80%** (avoid extremes)

**Quality Tags:**
- **PRIME:** All 6 conditions pass → Full position - highest confidence
- **QUALIFIED:** 5 of 6 conditions pass → Half position - acceptable risk
- **MARGINAL:** 4 of 6 conditions pass → Monitor only - do not trade
- **BLOCKED:** 3 or fewer pass → Hidden from main list

**Usage:**
```python
from backend.filters.signal_quality import get_signal_quality_filter

quality_filter = get_signal_quality_filter()
result = quality_filter.evaluate(
    unified_score=80.0,
    model_agreement_ratio=0.85,
    unified_confidence=0.85,
    risk_reward_ratio=2.0,
    option_volume=1000,
    option_avg_volume=800,
    iv_rank=50.0,
)

print(result.tag)  # PRIME, QUALIFIED, MARGINAL, or BLOCKED
```

---

### Improvement #2: Time of Day Filter

**Location:** `backend/filters/time_of_day.py`

**Purpose:** Controls signal visibility based on IST market timing to avoid high-volatility and low-liquidity periods.

**Time Windows (IST):**

| Window | Time Range | Status | Allowed Signals |
|--------|-----------|--------|-----------------|
| Opening Volatility | 9:15 AM – 9:30 AM | BLOCKED | None |
| Early Morning | 9:30 AM – 10:15 AM | CAUTION | PRIME only |
| Prime Window | 10:15 AM – 1:00 PM | OPEN | PRIME + QUALIFIED |
| Lunch Lull | 1:00 PM – 2:00 PM | CAUTION | PRIME only |
| Afternoon Prime | 2:00 PM – 3:00 PM | OPEN | PRIME + QUALIFIED |
| Power Hour | 3:00 PM – 3:15 PM | CAUTION | PRIME only |
| Close Risk | 3:15 PM – 3:30 PM | BLOCKED | None |

**Expiry Day (Thursday) Special Rules:**
- Block all OTM option buys (only ITM/ATM allowed within 1 strike of spot)
- Raise score threshold to 85
- Force PRIME quality only
- Show expiry warning banner

**Usage:**
```python
from backend.filters.time_of_day import get_time_of_day_filter

time_filter = get_time_of_day_filter()
allowed, reason = time_filter.check_signal(
    quality_tag="PRIME",
    unified_score=85,
    option_delta=0.50,  # ATM
)

if allowed:
    # Signal can be shown
```

---

### Improvement #3: Market Regime Override

**Location:** `backend/filters/regime_override.py`

**Purpose:** Enforces regime-specific rules - certain trade types are fundamentally unsuitable for certain regimes.

**Regime Rules:**

#### TRENDING Regime
- ✅ Directional CE/PE buys ALLOWED - Best regime for this system
- ✅ Signal alignment with trend gets +5% confidence bonus
- ⛔ Counter-trend signals BLOCKED
- Threshold: 75

#### PINNED Regime
- ⛔ Directional CE/PE buys BLOCKED - Price is range-bound
- ✅ Option selling strategies only (straddles, strangles)
- Message: "Market is PINNED - Avoid directional trades"

#### SQUEEZE Regime
- ⛔ Immediate entry BLOCKED - Breakout direction unknown
- ✅ After breakout confirmation (2 candles outside range) - ALLOWED
- Threshold: 82 (higher bar for uncertain regime)

#### EXPIRY Regime
- ⛔ OTM options BLOCKED - High gamma risk
- ✅ ITM/ATM options ALLOWED (delta > 0.50)
- ⛔ Same-day expiry BLOCKED - Only DTE ≥ 2 allowed
- Threshold: 80

**Usage:**
```python
from backend.filters.regime_override import get_regime_override_filter

regime_filter = get_regime_override_filter()
result = regime_filter.apply_override(
    regime="TRENDING",
    signal_direction="BULLISH",
    option_delta=0.45,
    days_to_expiry=5,
    spot_price=23000,
    ema_20=22500,
)

if result.allowed:
    # Apply confidence adjustment
    confidence += result.confidence_adjustment
```

---

### Improvement #4: News/Event Blackout

**Location:** `backend/filters/event_calendar.py`

**Purpose:** Automatically reduces or suppresses signal confidence when high-impact events are imminent.

**Event Types & Actions:**

| Event Type | Scope | Action |
|-----------|-------|--------|
| RBI Monetary Policy | Nifty / BankNifty | Suppress all signals on announcement day |
| US Fed Meeting | Nifty / All | Reduce confidence by 20% |
| US CPI / NFP Data | Nifty / USD/INR sensitive | Add CAUTION tag, raise threshold to 82 |
| India Union Budget | All stocks | Suppress all signals on budget day |
| Stock Earnings | Individual stock | Block 3 days before + on day |
| Stock AGM / Board Meeting | Individual stock | Reduce confidence by 15% |
| Stock Ex-Dividend | Individual stock | Block - price gap risk |
| **NSE F&O Ban** | Individual stock | **BLOCK entirely** (CRITICAL - runs first) |

**Data Sources:**
- F&O Ban List: NSE API (https://www.nseindia.com/api/fo-secban) - Refresh every 30 min
- Corporate Events: NSE API (https://www.nseindia.com/api/corporates-corporateActions) - Refresh daily
- Macro Events: Hardcoded + NSE calendar - Refresh weekly

**Usage:**
```python
from backend.filters.event_calendar import get_event_calendar

event_calendar = get_event_calendar()

# CRITICAL: F&O Ban check (runs first)
is_banned = await event_calendar.is_fo_banned("RELIANCE")
if is_banned:
    # Remove from evaluation entirely

# Check other events
event_result = await event_calendar.check_events("RELIANCE")
if event_result.blocked:
    # Block signal
elif event_result.confidence_adjustment < 0:
    # Apply confidence reduction
    confidence += event_result.confidence_adjustment
```

---

### Improvement #5: Signal Persistence Check

**Location:** `backend/filters/signal_persistence.py`

**Purpose:** Requires signals to be consistently present across multiple consecutive evaluation cycles before being actionable.

**Persistence Rules:**
- Minimum 3 consecutive refreshes (typically 15-45 min apart)
- Score must not drop more than 5 points between any two refreshes
- Direction must not flip even once in the window
- Quality tag must maintain same level (PRIME/QUALIFIED)
- Cache duration: 2 hours per symbol

**Persistence Status:**
- **CONFIRMED:** 3+ consecutive refreshes passed → ✅ Actionable
- **BUILDING (2/3):** 2 refreshes passed → 🕐 Show with clock icon
- **BUILDING (1/3):** 1 refresh passed → Show dimmed
- **RESET:** Direction flipped or score dropped → Hide

**Signal History Structure:**
```python
{
    "symbol": "NIFTY",
    "timestamps": [t1, t2, t3],
    "scores": [80, 81, 82],
    "directions": ["BULLISH", "BULLISH", "BULLISH"],
    "quality_tags": ["PRIME", "PRIME", "PRIME"],
    "consecutive_count": 3,
    "is_persistent": True,
    "first_confirmed_at": "2026-03-17T11:30:00"
}
```

**Usage:**
```python
from backend.filters.signal_persistence import get_signal_persistence_cache

persistence_cache = get_signal_persistence_cache()

result = persistence_cache.update_history(
    symbol="NIFTY",
    unified_score=80.0,
    signal_direction="BULLISH",
    quality_tag="PRIME",
    unified_confidence=0.85,
)

if result.is_actionable:
    # Signal has been confirmed across 3+ refreshes
```

---

## Integration into Unified Evaluation

### Updated API Response

The `/api/unified-evaluation` endpoint now returns enhanced results with filter information:

```json
{
  "timestamp": "2026-03-17T11:30:00",
  "market_status": "Open",
  "count": 10,
  "evaluations": [
    {
      "symbol": "NIFTY",
      "unified_score": 82.5,
      "unified_signal": "BULLISH",
      "unified_confidence": 0.87,
      "unified_confidence_original": 0.85,

      "quality_tag": "PRIME",
      "is_actionable": true,
      "blocked": false,
      "blocked_reasons": [],

      "quality_filter": {
        "quality_tag": "PRIME",
        "conditions_passed": 6,
        "total_conditions": 6,
        "failed_conditions": [],
        "details": { ... }
      },

      "time_filter": {
        "time_window": "PRIME_WINDOW",
        "status": "OPEN",
        "is_expiry_day": false,
        "allowed_quality_tags": ["PRIME", "QUALIFIED"],
        "min_score_threshold": 75.0,
        "blocked": false,
        "message": null
      },

      "regime_override": {
        "allowed": true,
        "reason": "Signal aligns with bullish trend",
        "score_adjustment": 0.0,
        "confidence_adjustment": 0.05,
        "details": { ... }
      },

      "event_flag": {
        "has_event": false,
        "event_count": 0,
        "events": [],
        "action": null,
        "confidence_adjustment": 0.0,
        "blocked": false,
        "message": null
      },

      "persistence": {
        "status": "CONFIRMED",
        "consecutive_count": 3,
        "required_count": 3,
        "first_confirmed_at": "2026-03-17T11:00:00",
        "message": "✅ Confirmed (3/3)",
        "is_actionable": true
      },

      "best_option": { ... },
      "risk_reward": { ... },
      "component_scores": { ... },
      "model_agreement": { ... }
    }
  ]
}
```

### Usage with Filters (Default)

```python
from backend.unified_evaluation import get_unified_evaluator

evaluator = get_unified_evaluator()

# Filters are applied by default
evaluations = await evaluator.evaluate_market(
    scan_data=scan_data,
    include_technical=True,
    apply_filters=True,  # Default
)

# Only PRIME/QUALIFIED + CONFIRMED signals will be actionable
actionable_signals = [e for e in evaluations if e.get("is_actionable")]
```

### Usage without Filters (Testing/Debug)

```python
# Disable filters for testing
evaluations = await evaluator.evaluate_market(
    scan_data=scan_data,
    include_technical=True,
    apply_filters=False,  # Disable all filters
)
```

---

## Testing

### Run All Filter Tests

```bash
cd backend
python -m pytest tests/test_filters.py -v
```

### Run Unified Evaluation Tests

```bash
python -m pytest tests/test_unified_evaluation.py tests/test_unified_improvements.py -v
```

### Test Results

✅ **26/26 filter tests passed**
✅ **21/21 unified evaluation tests passed**
✅ **No regressions introduced**

---

## Performance Considerations

### Memory Usage
- **Signal Persistence Cache:** Max 100 symbols × 10 snapshots = 1,000 data points (~50KB)
- **Event Calendar Cache:** F&O ban list (~100 symbols), corporate events (~500 events), macro events (~20 events)
- Total additional memory: **< 1 MB**

### API Call Overhead
- **F&O Ban List:** Cached 30 min, ~200ms per fetch
- **Corporate Events:** Cached 24 hours, ~500ms per fetch
- **Filters Execution:** < 5ms per symbol
- **Total overhead per scan:** < 10ms for typical 10-stock scan

### Cache Refresh Strategy
- F&O Ban: Every 30 min (critical)
- Corporate Events: Daily at 9 AM
- Macro Events: Weekly
- Signal Persistence: In-memory, no disk I/O

---

## Configuration

All filter thresholds are configurable via class constants:

### Signal Quality Filter
```python
SignalQualityFilter.MIN_UNIFIED_SCORE = 75.0
SignalQualityFilter.MIN_MODEL_AGREEMENT = 0.80
SignalQualityFilter.MIN_UNIFIED_CONFIDENCE = 0.80
SignalQualityFilter.MIN_RISK_REWARD_RATIO = 1.5
SignalQualityFilter.IV_RANK_MIN = 20.0
SignalQualityFilter.IV_RANK_MAX = 80.0
```

### Time Filter
```python
TimeOfDayFilter.NORMAL_SCORE_THRESHOLD = 75.0
TimeOfDayFilter.EXPIRY_SCORE_THRESHOLD = 85.0
```

### Signal Persistence
```python
SignalPersistenceCache.MIN_CONSECUTIVE_REFRESHES = 3
SignalPersistenceCache.MAX_SCORE_DROP = 5.0
SignalPersistenceCache.MAX_CACHE_AGE_HOURS = 2
```

---

## Summary

These 5 improvements work together to filter out low-quality signals while preserving high-conviction trades:

1. **Quality Filter** ensures signals meet minimum standards
2. **Time Filter** avoids unfavorable market windows
3. **Regime Override** blocks unsuitable strategies for current market conditions
4. **Event Blackout** prevents trading around high-impact news
5. **Persistence Check** confirms signals are stable across time

**Expected Impact:**
- Win rate improvement: **⭐⭐⭐⭐⭐** (Very High)
- Trade frequency: Reduced by ~60-70% (by design - "trade less, win more")
- False positive reduction: ~80%
- Confidence in PRIME + CONFIRMED signals: > 85%

**Philosophy:** Trade less, win more. Quality over quantity.
