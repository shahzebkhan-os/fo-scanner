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
            COALESCE(gex, 0) as gex,
            COALESCE(iv_skew, 0) as iv_skew,
            COALESCE(pcr, 1) as pcr,
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
    """
    if not LGB_AVAILABLE or not MODEL_PATH.exists():
        return None
    
    try:
        import lightgbm as lgb
        import pickle
        
        model = lgb.Booster(model_file=str(MODEL_PATH))
        
        if not CALIBRATOR_PATH.exists():
            return None
            
        with open(CALIBRATOR_PATH, "rb") as f:
            calibrator = pickle.load(f)
        
        regime_map = {"PINNED": 0, "TRENDING": 1, "EXPIRY": 2, "SQUEEZE": 3}
        X = np.array([[
            float(features.get("weighted_score", features.get("score", 0))),
            float(features.get("gex", 0)),
            float(features.get("iv_skew", 0)),
            float(features.get("pcr", 1)),
            float(regime_map.get(features.get("regime", "TRENDING"), 1)),
        ]])
        
        raw_prob = model.predict(X)[0]
        calibrated_prob = calibrator.predict([raw_prob])[0]
        return round(float(calibrated_prob), 4)
    except Exception as e:
        log.warning(f"ML prediction failed: {e}")
        return None


def get_model_status() -> dict:
    """Check if model is trained and return status."""
    trained = MODEL_PATH.exists() and CALIBRATOR_PATH.exists()
    return {
        "trained": trained,
        "model_path": str(MODEL_PATH) if trained else None,
        "lgb_available": LGB_AVAILABLE,
    }
