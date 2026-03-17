# Unified Market Evaluation Feature

## Overview

The Unified Market Evaluation feature combines **all available scoring models** to provide the single best F&O (Futures & Options) suggestion for each stock with a comprehensive confidence score.

## Models Combined

The unified evaluation integrates 5 different models with weighted ensemble scoring:

| Model | Weight | Description |
|-------|--------|-------------|
| **OI-Based Scoring** | 35% | Quantitative model analyzing Open Interest, Greeks, IV, PCR, GEX, and regime detection |
| **Technical Indicators** | 20% | Classical TA using RSI, MACD, ADX, Stochastic, EMAs, Bollinger Bands, Volume, VWAP |
| **ML Ensemble** | 25% | Combined LightGBM (60%) + LSTM (40%) predictions |
| **OI Velocity** | 10% | Unusual Options Activity (UOA) detection via OI acceleration |
| **Global Cues** | 10% | Macro sentiment from global markets (SPX, NASDAQ, DXY, Crude, USD/INR, VIX) |

## How It Works

### 1. Score Normalization

All model scores are normalized to a 0-100 scale:

- **OI-Based**: Already 0-100
- **Technical**: Already 0-100
- **ML Ensemble**: Probability (0-1) converted to 0-100
- **OI Velocity**: Range (-1 to +1) mapped to 0-100
- **Global Cues**: Range (-1 to +1) mapped to 0-100

### 2. Weighted Ensemble

```python
unified_score = (
    oi_based * 0.35 +
    technical * 0.20 +
    ml_ensemble * 0.25 +
    oi_velocity * 0.10 +
    global_cues * 0.10
)
```

### 3. Signal Determination

- **BULLISH**: unified_score ≥ 60
- **BEARISH**: unified_score ≤ 40
- **NEUTRAL**: 40 < unified_score < 60

### 4. Confidence Calculation

Confidence is calculated based on:
- **Average confidence** of individual models (60% weight)
- **Model agreement ratio** (40% weight)

Higher confidence when all models agree on the same direction.

## API Endpoints

### GET /api/unified-evaluation

Returns unified market evaluation for all stocks.

**Query Parameters:**
- `include_technical` (bool, optional): Include technical scoring (slower). Default: `false`

**Response:**
```json
{
  "timestamp": "2026-03-17T17:39:21.089Z",
  "market_status": "OPEN",
  "count": 50,
  "evaluations": [
    {
      "symbol": "RELIANCE",
      "best_option": {
        "strike": 2800,
        "type": "CE",
        "ltp": 45.50,
        "iv": 18.5,
        "delta": 0.45,
        "option_score": 85
      },
      "unified_score": 78.5,
      "unified_signal": "BULLISH",
      "unified_confidence": 0.82,
      "component_scores": {
        "oi_based": {"score": 82, "signal": "BULLISH", "confidence": 0.75},
        "technical": {"score": 75, "signal": "BULLISH", "confidence": 0.68},
        "ml_ensemble": {"bullish_probability": 0.72, "lgb_prob": 0.70, "nn_prob": 0.75},
        "oi_velocity": {"score": 0.45, "uoa_detected": true},
        "global_cues": {"score": 0.35, "adjustment": 5}
      },
      "normalized_scores": {
        "oi_based": 82,
        "technical": 75,
        "ml_ensemble": 72,
        "oi_velocity": 72.5,
        "global_cues": 67.5
      },
      "model_agreement": {
        "signals": [1, 1, 1, 1, 1],
        "agreement_ratio": 1.0
      },
      "regime": "TRENDING",
      "iv_rank": 45.2,
      "pcr": 1.15,
      "spot_price": 2785.50,
      "days_to_expiry": 7,
      "signal_reasons": ["🔥 High Score", "🤖 AI Confirmed", "🎯 UOA Detected"]
    }
  ],
  "model_weights": {
    "oi_based": 0.35,
    "technical": 0.20,
    "ml_ensemble": 0.25,
    "oi_velocity": 0.10,
    "global_cues": 0.10
  },
  "description": "Unified evaluation combining OI-based, technical, ML, OI velocity, and global cues models"
}
```

### GET /api/unified-evaluation/accuracy

Tracks the accuracy of unified evaluation predictions.

**Query Parameters:**
- `min_unified_score` (float, optional): Minimum unified score threshold. Default: `70.0`
- `min_confidence` (float, optional): Minimum confidence threshold. Default: `0.65`
- `days_back` (int, optional): Number of days to look back. Default: `7`

**Response:**
```json
{
  "timestamp": "2026-03-17T17:39:21.089Z",
  "period_days": 7,
  "filters": {
    "min_unified_score": 70.0,
    "min_confidence": 0.65
  },
  "overall": {
    "total_predictions": 125,
    "correct": 85,
    "incorrect": 30,
    "pending": 10,
    "accuracy_pct": 73.91
  },
  "by_signal": {
    "BULLISH": {
      "total": 60,
      "correct": 45,
      "incorrect": 10,
      "accuracy": 81.82
    },
    "BEARISH": {
      "total": 40,
      "correct": 25,
      "incorrect": 12,
      "accuracy": 67.57
    },
    "NEUTRAL": {
      "total": 25,
      "correct": 15,
      "incorrect": 8,
      "accuracy": 65.22
    }
  },
  "recent_predictions": [...]
}
```

## Frontend UI

The **Market Eval** tab provides:

### 1. Model Weights Visualization
- Pie chart showing the weight distribution of each model

### 2. Accuracy Tracking
- Overall accuracy percentage
- Correct vs incorrect predictions
- Accuracy breakdown by signal type (BULLISH/BEARISH/NEUTRAL)

### 3. Top Opportunities List
- Sorted by unified_score (descending)
- Shows best F&O option for each stock
- Click to expand for detailed analysis

### 4. Detailed Stock Analysis (on click)
- Bar chart of normalized component scores
- Individual model details (score, signal, confidence)
- Model agreement visualization
- Best option specifications

## Usage Examples

### Basic Usage (without technical)
```bash
curl http://localhost:8000/api/unified-evaluation
```

### Include Technical Scoring (slower)
```bash
curl http://localhost:8000/api/unified-evaluation?include_technical=true
```

### Check Accuracy
```bash
curl http://localhost:8000/api/unified-evaluation/accuracy?min_unified_score=75&min_confidence=0.7&days_back=14
```

## Implementation Details

### Backend (`backend/unified_evaluation.py`)

**Class: `UnifiedEvaluation`**

Key methods:
- `compute_unified_score()`: Combines all model scores with weighted ensemble
- `select_best_fo_option()`: Selects the best F&O option from scan results
- `evaluate_market()`: Evaluates entire market and returns sorted results

### Frontend (`frontend/src/components/UnifiedEvaluationTab.jsx`)

Key features:
- Dark mode support
- Real-time data refresh
- Interactive stock detail expansion
- Visual charts for scores and weights

## Performance Considerations

- **Without Technical**: ~2-5 seconds for 50+ stocks
- **With Technical**: ~10-20 seconds (fetches historical price data via yfinance)
- Results are cached from the main scan endpoint
- Technical scoring is optional and disabled by default for faster response

## Model Agreement

The feature tracks how many models agree on the signal direction:

- **Agreement Ratio = 1.0**: All 5 models agree → Very high confidence
- **Agreement Ratio = 0.6**: 3 out of 5 models agree → Moderate confidence
- **Agreement Ratio = 0.4**: Mixed signals → Lower confidence

## Signal Interpretation

### Unified Score Ranges

| Score Range | Interpretation | Confidence Level |
|-------------|---------------|------------------|
| 80-100 | Very Strong Signal | VERY HIGH |
| 70-79 | Strong Signal | HIGH |
| 60-69 | Moderate Signal | MODERATE |
| 50-59 | Weak Signal | LOW |
| 40-49 | Very Weak Signal | VERY LOW |
| 0-39 | Opposite Direction | - |

## Future Enhancements

Potential improvements:
1. Dynamic weight adjustment based on recent accuracy
2. Per-symbol model performance tracking
3. Regime-specific weight optimization
4. Real-time paper trading based on unified evaluation
5. Historical backtest of unified model performance

## Testing

To verify the feature is working:

1. Start backend: `cd backend && uvicorn main:app --reload`
2. Navigate to: `http://localhost:8000/api/unified-evaluation`
3. Open frontend: `cd frontend && npm run dev`
4. Click on "Market Eval" tab
5. View unified evaluations and click on stocks for details

## Notes

- The unified evaluation uses existing scan data, so run a scan first for fresh results
- Accuracy tracking requires historical market_snapshots data
- Model weights can be adjusted in `unified_evaluation.py` (`WEIGHTS` dict)
- Technical scoring fetches data from yfinance, which may be slow or rate-limited
