"""
LightGBM + LSTM Neural Network ensemble for next-bar direction prediction.

LightGBM captures point-in-time feature interactions while the LSTM neural
network processes historical sequences to detect temporal patterns.  When both
models are trained the final probability is a weighted blend:

    P = 0.60 × LightGBM + 0.40 × NeuralNetwork

If only one model is available the other's weight is redistributed so the
prediction still works.
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

from .nn_model import train_nn, predict_nn, get_nn_status, TORCH_AVAILABLE

MODEL_PATH = Path(os.path.dirname(__file__)) / "models" / "lgbm_signal.txt"
CALIBRATOR_PATH = Path(os.path.dirname(__file__)) / "models" / "isotonic_calibrator.pkl"
MIN_ROWS_TO_TRAIN = 500  # Need at least 500 historical snapshots

# Ensemble blend weights
LGB_WEIGHT = 0.60
NN_WEIGHT = 0.40


def _load_training_data(db_path: str = None) -> tuple:
    """
    Load features from market_snapshots table.
    Labels: 1 if next_bar_close > current_close else 0.
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
    
    query = """
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
    """
    
    df = pd.read_sql(query, conn)
    conn.close()
    
    if df.empty:
        raise ValueError("No data found in market_snapshots table")
    
    # Create labels: 1 if next bar's spot > current spot, else 0
    # Group by symbol to compute next_spot correctly
    df['next_spot'] = df.groupby('symbol')['spot_price'].shift(-1)
    df = df.dropna(subset=["next_spot"])
    
    df["label"] = (df["next_spot"] > df["spot_price"]).astype(int)
    df["regime_encoded"] = df["regime"].map({
        "PINNED": 0, "TRENDING": 1, "EXPIRY": 2, "SQUEEZE": 3
    }).fillna(1)  # Default to TRENDING
    
    features = ["weighted_score", "gex", "iv_skew", "pcr", "regime_encoded"]
    
    # Add OI velocity / UOA features if present in the data
    extra = ["oi_velocity_score", "uoa_detected"]
    features = features + [f for f in extra if f in df.columns and f not in features]

    # Handle missing values
    for col in features:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    
    X = df[features].values.astype(np.float64)
    y = df["label"].values.astype(np.int32)
    
    return X, y, features


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
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_child_samples": 20,
        "n_estimators": 200,
        "random_state": 42,
        "verbose": -1,
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
    result = {
        "cv_log_loss_mean": round(float(np.mean(val_losses)), 4),
        "cv_log_loss_std": round(float(np.std(val_losses)), 4),
        "feature_importances": importances,
        "training_rows": len(X),
        "model_saved": str(MODEL_PATH),
    }

    # ── Also train the LSTM neural network ────────────────────────────────
    nn_result = train_nn(db_path)
    if "error" in nn_result:
        log.warning(f"NN training skipped: {nn_result['error']}")
    else:
        log.info(f"NN training done: loss={nn_result.get('nn_cv_log_loss_mean')}")
    result["nn"] = nn_result

    return result


def _predict_lgb(features: dict) -> Optional[float]:
    """LightGBM point-in-time prediction (calibrated)."""
    if not LGB_AVAILABLE or not MODEL_PATH.exists() or not CALIBRATOR_PATH.exists():
        return None

    try:
        import lightgbm as lgb
        import pickle

        model = lgb.Booster(model_file=str(MODEL_PATH))

        with open(CALIBRATOR_PATH, "rb") as f:
            calibrator = pickle.load(f)

        regime_map = {"PINNED": 0, "TRENDING": 1, "EXPIRY": 2, "SQUEEZE": 3}
        metrics = features.get("metrics", {})

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
        log.warning(f"LGB prediction failed: {e}")
        return None


def predict(features: dict, symbol: str = None) -> Optional[float]:
    """Ensemble prediction blending LightGBM and LSTM neural network.

    Returns calibrated probability (0-1) of bullish next bar.
    Returns None if no model is trained.

    Blend weights (when both models available):
        LightGBM  60 %  — strong on feature interactions
        LSTM NN   40 %  — captures temporal / sequential patterns
    """
    lgb_prob = _predict_lgb(features)

    # Neural network needs the symbol to fetch historical sequence
    nn_prob = None
    if symbol:
        nn_prob = predict_nn(symbol, features)

    # Ensemble blending
    if lgb_prob is not None and nn_prob is not None:
        blended = LGB_WEIGHT * lgb_prob + NN_WEIGHT * nn_prob
        return round(float(blended), 4)
    elif lgb_prob is not None:
        return lgb_prob
    elif nn_prob is not None:
        return nn_prob
    return None


def get_model_status() -> dict:
    """Check if models are trained and return status."""
    lgb_trained = MODEL_PATH.exists() and CALIBRATOR_PATH.exists()
    nn_status = get_nn_status()
    return {
        "trained": lgb_trained or nn_status["nn_trained"],
        "lgb_trained": lgb_trained,
        "model_path": str(MODEL_PATH) if lgb_trained else None,
        "lgb_available": LGB_AVAILABLE,
        **nn_status,
    }
