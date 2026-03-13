"""
LightGBM model trained on market_snapshots to predict next-bar direction.
Used to validate/calibrate the quantitative weighted_score from analytics.py.
Does NOT replace compute_stock_score_v2 — runs alongside it as a second opinion.
"""

import numpy as np
import sqlite3
import os
from pathlib import Path
from typing import Optional
import asyncio
import logging

log = logging.getLogger(__name__)

try:
    import lightgbm as lgb
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import log_loss
    import pandas as pd
    LGB_AVAILABLE = True
except ImportError:
    LGB_AVAILABLE = False

MODEL_PATH = Path(os.path.dirname(__file__)) / "models" / "lgbm_signal.txt"
CALIBRATOR_PATH = Path(os.path.dirname(__file__)) / "models" / "isotonic_calibrator.pkl"
MIN_ROWS_TO_TRAIN = 500  # Need at least 500 historical snapshots


def _load_training_data(db_path: str = None) -> tuple:
    """
    Load features from market_snapshots table.
    Labels: 1 if next_bar_close > current_close else 0.
    
    Features expanded from 5 to 13 for improved accuracy (Phase 2A):
    - Original 5: weighted_score, gex, iv_skew, pcr, regime_encoded
    - New market context: vix_norm, dte
    - New time features: hour_sin, hour_cos, day_of_week
    - New price context: price_momentum_5, volume_ratio, max_pain_distance
    """
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "scanner.db")
    
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")
    
    conn = sqlite3.connect(db_path)
    
    # Check if market_snapshots table exists
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_snapshots'")
    if not cursor.fetchone():
        conn.close()
        raise ValueError("market_snapshots table does not exist. Run historical backfill first.")
    
    # Expanded query with more features (Phase 2A)
    query = """
        SELECT
            score as weighted_score,
            COALESCE(net_gex, 0) as gex,
            COALESCE(iv_skew, 0) as iv_skew,
            COALESCE(pcr_oi, 1) as pcr,
            regime,
            spot_price,
            symbol,
            snapshot_time,
            COALESCE(vix, 15.0) as vix,
            COALESCE(dte, 7) as dte,
            COALESCE(max_pain, spot_price) as max_pain,
            COALESCE(volume_ratio, 1.0) as volume_ratio
        FROM market_snapshots
        WHERE spot_price IS NOT NULL AND spot_price > 0
        ORDER BY symbol, snapshot_time ASC
    """
    
    df = pd.read_sql(query, conn)
    conn.close()
    
    if df.empty:
        raise ValueError("No data found in market_snapshots table")
    
    # Create labels: 1 if next bar's spot > current spot, else 0
    # Group by symbol to compute next_spot and lag features correctly
    df['next_spot'] = df.groupby('symbol')['spot_price'].shift(-1)
    df['prev_spot'] = df.groupby('symbol')['spot_price'].shift(1)
    df['spot_5_ago'] = df.groupby('symbol')['spot_price'].shift(5)
    df = df.dropna(subset=["next_spot", "prev_spot"])

    df["label"] = (df["next_spot"] > df["spot_price"]).astype(int)
    df["regime_encoded"] = df["regime"].map({
        "PINNED": 0, "TRENDING": 1, "EXPIRY": 2, "SQUEEZE": 3
    }).fillna(1)  # Default to TRENDING
    
    # Engineered features (Phase 2A)
    ts = pd.to_datetime(df["snapshot_time"])
    hour = ts.dt.hour + ts.dt.minute / 60.0

    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)   # Cyclical — avoids 23→0 jump
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["day_of_week"] = ts.dt.dayofweek              # 0=Mon, 4=Fri
    df["price_momentum_5"] = ((df["spot_price"] - df["spot_5_ago"])
                              / df["spot_5_ago"].replace(0, np.nan) * 100).fillna(0)
    df["vix_norm"] = df["vix"] / 20.0                # Normalized around VIX=20
    df["max_pain_distance"] = ((df["spot_price"] - df["max_pain"])
                               / df["spot_price"].replace(0, np.nan) * 100).fillna(0)
    
    # Features list - expanded from 5 to 13
    FEATURES = [
        # Original 5 (keep all)
        "weighted_score", "gex", "iv_skew", "pcr", "regime_encoded",
        # New market context
        "vix_norm", "dte",
        # New time features (cyclical encoding — critical for ML)
        "hour_sin", "hour_cos", "day_of_week",
        # New price context
        "price_momentum_5", "volume_ratio", "max_pain_distance",
    ]
    # Only use available columns (graceful degradation for older databases)
    FEATURES = [f for f in FEATURES if f in df.columns]
    
    # Handle missing values
    for col in FEATURES:
        df[col] = df[col].fillna(0)
    
    X = df[FEATURES].values.astype(np.float64)
    y = df["label"].values.astype(np.int32)
    
    return X, y, FEATURES


def train_model(db_path: str = None) -> dict:
    """Train LightGBM on market_snapshots. Returns training metrics."""
    if not LGB_AVAILABLE:
        return {"error": "lightgbm not installed. Run: pip install lightgbm scikit-learn pandas"}
    
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "scanner.db")
    
    try:
        X, y, feature_names = _load_training_data(db_path)
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}
    
    if len(X) < MIN_ROWS_TO_TRAIN:
        return {"error": f"Need {MIN_ROWS_TO_TRAIN} snapshots, have {len(X)}. Run more historical backfill first."}
    
    # Time-series cross validation (no future leakage)
    n_splits = min(5, len(X) // 100)  # Ensure enough data per fold
    if n_splits < 2:
        n_splits = 2
    
    tscv = TimeSeriesSplit(n_splits=n_splits)
    val_losses = []
    
    params = {
        "objective":           "binary",
        "metric":              "binary_logloss",
        "learning_rate":       0.03,    # Reduced from 0.05 — more robust on small data
        "num_leaves":          15,      # Reduced from 31 — prevents overfitting
        "min_child_samples":   30,      # Increased from 20 — requires more data per leaf
        "n_estimators":        500,     # More trees to compensate for lower LR
        "feature_fraction":    0.8,     # Random feature subsampling per tree
        "bagging_fraction":    0.8,     # Row subsampling
        "bagging_freq":        5,
        "lambda_l1":           0.1,     # L1 regularization
        "lambda_l2":           0.1,     # L2 regularization
        "random_state":        42,
        "verbose":             -1,
    }
    
    for train_idx, val_idx in tscv.split(X):
        model = lgb.LGBMClassifier(**params)
        model.fit(
            X[train_idx], y[train_idx],
            eval_set=[(X[val_idx], y[val_idx])],
            callbacks=[lgb.early_stopping(20, verbose=False)]
        )
        preds = model.predict_proba(X[val_idx])[:, 1]
        val_losses.append(log_loss(y[val_idx], preds))
    
    # Final model on all data
    final_model = lgb.LGBMClassifier(**params)
    final_model.fit(X, y)
    
    # Isotonic calibration
    raw_probs = final_model.predict_proba(X)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_probs, y)
    
    # Save model
    MODEL_PATH.parent.mkdir(exist_ok=True)
    final_model.booster_.save_model(str(MODEL_PATH))
    
    import pickle
    with open(CALIBRATOR_PATH, "wb") as f:
        pickle.dump(calibrator, f)
    
    importances = dict(zip(feature_names, map(float, final_model.feature_importances_)))
    return {
        "cv_log_loss_mean": round(float(np.mean(val_losses)), 4),
        "cv_log_loss_std": round(float(np.std(val_losses)), 4),
        "feature_importances": importances,
        "training_rows": len(X),
        "model_saved": str(MODEL_PATH),
    }


def predict(features: dict) -> Optional[float]:
    """
    Returns calibrated probability (0-1) of bullish next bar.
    Returns None if model not trained yet.
    
    Now supports expanded feature set (Phase 2A).
    Falls back gracefully when new features aren't available.
    """
    if not LGB_AVAILABLE or not MODEL_PATH.exists():
        return None
    
    try:
        import lightgbm as lgb
        import pickle
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        model = lgb.Booster(model_file=str(MODEL_PATH))
        
        if not CALIBRATOR_PATH.exists():
            return None
            
        with open(CALIBRATOR_PATH, "rb") as f:
            calibrator = pickle.load(f)
        
        regime_map = {"PINNED": 0, "TRENDING": 1, "EXPIRY": 2, "SQUEEZE": 3}
        
        # Extract features with fallback to metrics sub-dict
        metrics = features.get("metrics", {})
        
        # Get current time for hour features
        IST = ZoneInfo("Asia/Kolkata")
        now = datetime.now(IST)
        hour = now.hour + now.minute / 60.0
        
        # Expanded feature extraction (Phase 2A)
        # Build feature vector - order must match training
        feature_values = [
            # Original 5
            float(features.get("weighted_score", features.get("score", 0))),
            float(features.get("gex", metrics.get("gex", 0))),
            float(features.get("iv_skew", metrics.get("iv_skew", 0))),
            float(features.get("pcr", metrics.get("pcr", features.get("pcr_oi", 1)))),
            float(regime_map.get(features.get("regime", "TRENDING"), 1)),
            # New market context
            float(features.get("vix", 15.0)) / 20.0,  # vix_norm
            float(features.get("dte", features.get("days_to_expiry", 7))),
            # New time features (cyclical encoding)
            np.sin(2 * np.pi * hour / 24),  # hour_sin
            np.cos(2 * np.pi * hour / 24),  # hour_cos
            float(now.weekday()),  # day_of_week
            # New price context (default to 0 if not available)
            float(features.get("price_momentum_5", 0)),
            float(features.get("volume_ratio", 1.0)),
            float(features.get("max_pain_distance", 0)),
        ]
        
        X = np.array([feature_values])
        
        # Handle case where model has different feature count (fallback to original 5)
        expected_features = model.num_feature()
        if X.shape[1] != expected_features:
            # Fall back to original 5 features for older models
            X = np.array([[
                float(features.get("weighted_score", features.get("score", 0))),
                float(features.get("gex", metrics.get("gex", 0))),
                float(features.get("iv_skew", metrics.get("iv_skew", 0))),
                float(features.get("pcr", metrics.get("pcr", features.get("pcr_oi", 1)))),
                float(regime_map.get(features.get("regime", "TRENDING"), 1)),
            ]])
        
        raw_prob = model.predict(X)[0]
        calibrated_prob = calibrator.predict([raw_prob])[0]
        return round(float(calibrated_prob), 4)
    except Exception as e:
        log.warning(f"ML prediction failed: {e}")
        return None


def predict_ensemble(features: dict, quant_score: float, engine_score: float = None) -> dict:
    """
    Blends QUANT score, ML probability, and 12-signal engine score.
    Weights are dynamic — ML only contributes when it's confident (far from 0.5).

    Returns full breakdown for display and logging.
    
    Phase 3A: Confidence-weighted stacking ensemble.
    """
    ml_prob = predict(features)   # Existing function; returns None if not trained

    # ML confidence = how far from random (0.5) the prediction is
    ml_conf = abs(ml_prob - 0.5) * 2 if ml_prob is not None else 0.0

    # Directional ML score 0-100 (same logic as current main.py conversion)
    signal = features.get("signal", "NEUTRAL")
    if signal == "BULLISH":
        ml_score_100 = int((ml_prob or 0.5) * 100)
    elif signal == "BEARISH":
        ml_score_100 = int((1 - (ml_prob or 0.5)) * 100)
    else:
        ml_score_100 = int(max(ml_prob or 0.5, 1 - (ml_prob or 0.5)) * 100)

    # Allocate weights — ML weight scales with its confidence
    quant_w  = 0.50
    ml_w     = 0.30 * ml_conf
    engine_w = 0.20 if engine_score is not None else 0.0
    total_w  = quant_w + ml_w + engine_w or 1.0

    blend = {
        "quant":  quant_w  / total_w,
        "ml":     ml_w     / total_w,
        "engine": engine_w / total_w,
    }

    final = (
        quant_score  * blend["quant"] +
        ml_score_100 * blend["ml"]   +
        (engine_score or 0) * blend["engine"]
    )

    return {
        "final_score":   round(min(100, max(0, final))),
        "ml_prob":       round(ml_prob, 4) if ml_prob is not None else None,
        "ml_score":      ml_score_100,
        "quant_score":   int(quant_score),
        "engine_score":  int(engine_score) if engine_score is not None else None,
        "blend_weights": {k: round(v, 3) for k, v in blend.items()},
        "confidence":    round((ml_conf * 0.5 + min(1.0, quant_score / 100) * 0.5), 3),
    }


def get_model_status() -> dict:
    """Check if model is trained and return status."""
    trained = MODEL_PATH.exists() and CALIBRATOR_PATH.exists()
    return {
        "trained": trained,
        "model_path": str(MODEL_PATH) if trained else None,
        "lgb_available": LGB_AVAILABLE,
    }
