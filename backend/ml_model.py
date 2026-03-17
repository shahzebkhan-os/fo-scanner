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
import warnings

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

try:
    from .nn_model import train_nn, predict_nn, get_nn_status, TORCH_AVAILABLE
except ImportError:
    from nn_model import train_nn, predict_nn, get_nn_status, TORCH_AVAILABLE

MODEL_PATH = Path(os.path.dirname(__file__)) / "models" / "lgbm_signal.txt"
CALIBRATOR_PATH = Path(os.path.dirname(__file__)) / "models" / "isotonic_calibrator.pkl"
FEATURE_META_PATH = Path(os.path.dirname(__file__)) / "models" / "lgbm_features.pkl"
MIN_ROWS_TO_TRAIN = 500  # Need at least 500 historical snapshots

# Ensemble blend weights
LGB_WEIGHT = 0.60
NN_WEIGHT = 0.40
assert abs(LGB_WEIGHT + NN_WEIGHT - 1.0) < 1e-9, "Ensemble weights must sum to 1.0"

# ── Feature definition ────────────────────────────────────────────────────────
# Ordered list of features for LightGBM training and inference.
# ORDER MATTERS — must be identical between _load_training_data and _predict_lgb.
# Backward-compatible: if a saved model has fewer features, FEATURE_META_PATH
# records the exact list used during training and _predict_lgb uses that list.
FEATURE_NAMES = [
    "weighted_score",      # composite quant score (0–100)
    "gex",                 # net gamma exposure
    "iv_skew",             # PE IV − CE IV
    "pcr",                 # put/call ratio by open interest
    "pcr_vol",             # put/call ratio by volume
    "regime_encoded",      # 0=PINNED, 1=TRENDING, 2=EXPIRY, 3=SQUEEZE, 4=NEUTRAL
    "oi_velocity_score",   # OI change velocity (−1 to +1)
    "pcr_velocity",        # rate of change of PCR across recent snapshots
    "rsi_14",              # 14-period RSI of spot price
    "sma_20",              # 20-period simple moving average
    "ema_9",               # 9-period exponential moving average
    "bb_upper_dist",       # distance of price from upper Bollinger band
    "bb_lower_dist",       # distance of price from lower Bollinger band
    "uoa_detected",        # unusual options activity flag (0/1)
    "dte",                 # days to nearest expiry (clipped at 90)
    "iv_rank",             # IV rank (0–100 percentile over lookback)
    "avg_iv",              # average ATM IV ((CE IV + PE IV) / 2)
    "max_pain_dist_pct",   # |spot − max_pain| / spot × 100
]

_REGIME_MAP = {"PINNED": 0, "TRENDING": 1, "EXPIRY": 2, "SQUEEZE": 3, "NEUTRAL": 4}


def _get_feature_value(feature_name: str, features: dict) -> float:
    """Extract a named feature from a scan stats / features dict with sensible fallbacks.

    ``features`` is whatever dict is passed to ``predict()`` — typically the
    output of ``compute_stock_score_v2`` potentially enriched with a
    ``spot_price`` key by the scan loop.
    """
    m = features.get("metrics", {}) or {}

    if feature_name == "weighted_score":
        return float(features.get("weighted_score", features.get("score", 0)))
    if feature_name == "gex":
        return float(features.get("gex", features.get("net_gex", m.get("gex", 0))))
    if feature_name == "iv_skew":
        return float(features.get("iv_skew", m.get("iv_skew", 0)))
    if feature_name == "pcr":
        return float(features.get("pcr", features.get("pcr_oi", 1.0)))
    if feature_name == "pcr_vol":
        return float(features.get("pcr_vol", m.get("vol_pcr", 1.0)))
    if feature_name == "regime_encoded":
        return float(_REGIME_MAP.get(features.get("regime", "TRENDING"), 1))
    if feature_name == "oi_velocity_score":
        return float(features.get("oi_velocity_score", m.get("oi_velocity_score", 0)))
    if feature_name == "pcr_velocity":
        return float(features.get("pcr_velocity", m.get("pcr_velocity", 0)))
    if feature_name == "rsi_14":
        return float(features.get("rsi_14", m.get("rsi_14", 50.0)))
    if feature_name == "sma_20":
        return float(features.get("sma_20", m.get("sma_20", features.get("spot_price", 0))))
    if feature_name == "ema_9":
        return float(features.get("ema_9", m.get("ema_9", features.get("spot_price", 0))))
    if feature_name == "bb_upper_dist":
        return float(features.get("bb_upper_dist", m.get("bb_upper_dist", 0)))
    if feature_name == "bb_lower_dist":
        return float(features.get("bb_lower_dist", m.get("bb_lower_dist", 0)))
    if feature_name == "uoa_detected":
        return float(features.get("uoa_detected", m.get("uoa_detected", 0)))
    if feature_name == "dte":
        raw = float(features.get("dte", features.get("days_to_expiry", m.get("dte", 5))))
        return min(raw, 90.0)
    if feature_name == "iv_rank":
        return float(features.get("iv_rank", m.get("iv_rank", 50.0)))
    if feature_name == "avg_iv":
        if "avg_iv" in features:
            return float(features["avg_iv"])
        if "iv" in features:
            return float(features["iv"])
        ce = float(features.get("atm_ce_iv", 0))
        pe = float(features.get("atm_pe_iv", 0))
        return (ce + pe) / 2.0
    if feature_name == "max_pain_dist_pct":
        spot = float(features.get("spot_price", 1) or 1)
        mp = float(features.get("max_pain", features.get("max_pain_strike", spot)) or spot)
        return abs(spot - mp) / max(spot, 1) * 100
    return 0.0


def _load_training_data(db_path: str = None) -> tuple:
    """Load features and labels from market_snapshots.

    Label priority:
      1. ``trade_result`` = 'WIN'  → 1  (option gained ≥ 20 %)
      2. ``trade_result`` = 'LOSS' → 0  (option lost ≥ 20 %)
      3. Fallback: next-bar spot price direction (1 if up, 0 if down)

    Using actual trade outcomes as the primary label gives a more direct
    signal about the profitability of the F&O strategy than raw spot direction.
    """
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "scanner.db")

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    conn = sqlite3.connect(db_path)

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_snapshots'")
    if not cursor.fetchone():
        conn.close()
        raise ValueError("market_snapshots table does not exist. Run historical backfill first.")

    query = """
        SELECT
            COALESCE(score, 0)                                              AS weighted_score,
            COALESCE(net_gex, 0)                                            AS gex,
            COALESCE(iv_skew, 0)                                            AS iv_skew,
            COALESCE(pcr_oi, 1)                                             AS pcr,
            COALESCE(pcr_vol, 1)                                            AS pcr_vol,
            COALESCE(oi_velocity_score, 0)                                  AS oi_velocity_score,
            COALESCE(uoa_detected, 0)                                       AS uoa_detected,
            MIN(COALESCE(dte, 5), 90)                                       AS dte,
            COALESCE(iv_rank, 50)                                           AS iv_rank,
            COALESCE((atm_ce_iv + atm_pe_iv) / 2.0, 0)                     AS avg_iv,
            CASE WHEN spot_price > 0
                 THEN ABS(spot_price - COALESCE(max_pain_strike, spot_price)) / spot_price * 100
                 ELSE 0 END                                                 AS max_pain_dist_pct,
            regime,
            spot_price,
            COALESCE(trade_result, '')                                      AS trade_result,
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

    # Ensure ordering per symbol for rolling calculations
    df["snapshot_time"] = pd.to_datetime(df["snapshot_time"])
    df = df.sort_values(["symbol", "snapshot_time"])

    # ── Price-action technicals & PCR velocity ─────────────────────────────
    df["pcr_velocity"] = 0.0
    df["rsi_14"] = 50.0
    df["sma_20"] = df["spot_price"]
    df["ema_9"] = df["spot_price"]
    df["bb_upper_dist"] = 0.0
    df["bb_lower_dist"] = 0.0

    for sym, group in df.groupby("symbol"):
        idx = group.index
        prices = group["spot_price"].astype(float)
        pcr_series = group["pcr"].astype(float)

        delta = prices.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        roll_up = gain.ewm(alpha=1 / 14, adjust=False).mean()
        roll_down = loss.ewm(alpha=1 / 14, adjust=False).mean()
        rs = roll_up / roll_down.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        sma20 = prices.rolling(window=20, min_periods=1).mean()
        ema9 = prices.ewm(span=9, adjust=False).mean()
        rolling_std = prices.rolling(window=20, min_periods=1).std()
        upper_band = sma20 + 2 * rolling_std
        lower_band = sma20 - 2 * rolling_std

        upper_dist = (prices - upper_band) / prices.replace(0, np.nan)
        lower_dist = (prices - lower_band) / prices.replace(0, np.nan)

        pcr_vel = pcr_series.rolling(window=5, min_periods=2).apply(
            lambda x: (x[-1] - x[0]) / max(len(x) - 1, 1), raw=True
        )

        df.loc[idx, "rsi_14"] = rsi.fillna(50.0)
        df.loc[idx, "sma_20"] = sma20.ffill().bfill()
        df.loc[idx, "ema_9"] = ema9.ffill().bfill()
        df.loc[idx, "bb_upper_dist"] = upper_dist.replace([np.inf, -np.inf], 0).fillna(0)
        df.loc[idx, "bb_lower_dist"] = lower_dist.replace([np.inf, -np.inf], 0).fillna(0)
        df.loc[idx, "pcr_velocity"] = pcr_vel.replace([np.inf, -np.inf], 0).fillna(0)

    # ── Label construction ────────────────────────────────────────────────
    # Primary: use trade_result when available (direct profitability signal).
    df = df.assign(label=np.nan)
    df.loc[df["trade_result"] == "WIN", "label"] = 1.0
    df.loc[df["trade_result"] == "LOSS", "label"] = 0.0

    # Fallback: next-bar spot direction for rows without a clear trade result.
    df = df.assign(next_spot=df.groupby("symbol")["spot_price"].shift(-1))
    spot_label = (df["next_spot"] > df["spot_price"]).astype(float)
    fallback_mask = df["label"].isna() & df["next_spot"].notna()
    df.loc[fallback_mask, "label"] = spot_label[fallback_mask]

    df = df.dropna(subset=["label"])
    df.loc[:, "label"] = df["label"].astype(np.int32)

    # ── Regime encoding ────────────────────────────────────────────────────
    df["regime_encoded"] = (
        df["regime"]
        .map(_REGIME_MAP)
        .fillna(1)  # default to TRENDING
        .astype(float)
    )

    # Fill any remaining NaN feature values with safe defaults
    spot_median = float(df["spot_price"].median()) if not df["spot_price"].dropna().empty else 0.0

    for col in FEATURE_NAMES:
        if col in df.columns:
            if col in ("pcr", "pcr_vol"):
                default = 1.0
            elif col == "iv_rank":
                default = 50.0
            elif col == "rsi_14":
                default = 50.0
            elif col in ("sma_20", "ema_9"):
                default = spot_median
            else:
                default = 0.0
            df[col] = df[col].fillna(default)

    X = df[FEATURE_NAMES].values.astype(np.float64)
    y = df["label"].values.astype(np.int32)

    win_pct = round(float(y.mean()) * 100, 1)
    log.info(f"Training data: {len(X)} rows | label=1 (bullish/WIN): {win_pct}%")

    return X, y, FEATURE_NAMES


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

    print(f"Training LightGBM on {len(X)} snapshots with {X.shape[1]} features...")

    # Time-series cross validation (no future leakage)
    n_splits = min(5, len(X) // 100)
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
        "n_estimators": 300,
        # Regularisation — reduces over-fitting on smaller datasets
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        # Balance WIN vs LOSS classes automatically
        "class_weight": "balanced",
        "random_state": 42,
        "verbose": -1,
    }

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        print(f"  LightGBM Fold {fold + 1}/{n_splits}: train={len(train_idx)}, val={len(val_idx)}")
        model = lgb.LGBMClassifier(**params)
        model.fit(
            X[train_idx], y[train_idx],
            eval_set=[(X[val_idx], y[val_idx])],
            callbacks=[lgb.early_stopping(30, verbose=False)],
        )
        preds = model.predict_proba(X[val_idx])[:, 1]
        loss = log_loss(y[val_idx], preds)
        print(f"    Fold {fold + 1} LogLoss: {loss:.4f}")
        val_losses.append(loss)

    # Final model on all data
    log.info("Training final LightGBM model on all data...")
    print("Training final LightGBM model on all data...")
    final_model = lgb.LGBMClassifier(**params)
    final_model.fit(X, y)

    # Isotonic calibration
    log.info("Calibrating probabilities...")
    print("Calibrating probabilities...")
    raw_probs = final_model.predict_proba(X)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_probs, y)

    # Save model and feature metadata
    MODEL_PATH.parent.mkdir(exist_ok=True)
    final_model.booster_.save_model(str(MODEL_PATH))

    import pickle
    with open(CALIBRATOR_PATH, "wb") as f:
        pickle.dump(calibrator, f)
    # Persist which features (and their order) this model was trained on so
    # _predict_lgb can reconstruct the exact same vector at inference time.
    with open(FEATURE_META_PATH, "wb") as f:
        pickle.dump({"features": feature_names}, f)

    importances = dict(zip(feature_names, map(float, final_model.feature_importances_)))
    result = {
        "cv_log_loss_mean": round(float(np.mean(val_losses)), 4),
        "cv_log_loss_std": round(float(np.std(val_losses)), 4),
        "feature_importances": importances,
        "training_rows": len(X),
        "features_used": feature_names,
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
    """LightGBM point-in-time prediction (calibrated).

    Loads the saved feature list from FEATURE_META_PATH so that predictions
    always use the same feature order and set that was used during training.
    Falls back to the legacy 5-feature set if the metadata file is missing
    (i.e. for models trained before this version).
    """
    if not LGB_AVAILABLE or not MODEL_PATH.exists() or not CALIBRATOR_PATH.exists():
        return None

    try:
        import lightgbm as lgb
        import pickle

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            with open(CALIBRATOR_PATH, "rb") as f:
                calibrator = pickle.load(f)

        model = lgb.Booster(model_file=str(MODEL_PATH))

        # Determine which features the saved model expects
        if FEATURE_META_PATH.exists():
            with open(FEATURE_META_PATH, "rb") as f:
                meta = pickle.load(f)
            feature_names = meta["features"]
        else:
            # Legacy fallback for models trained before feature-metadata was saved
            feature_names = ["weighted_score", "gex", "iv_skew", "pcr", "regime_encoded"]

        feat_vals = [_get_feature_value(fn, features) for fn in feature_names]
        X = np.array([feat_vals])

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


def get_model_details(db_path: str = None) -> dict:
    """Return comprehensive model details for the ML visualization tab."""
    import pickle

    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "scanner.db")

    status = get_model_status()
    details = {**status}

    # Ensemble configuration
    details["ensemble"] = {
        "lgb_weight": LGB_WEIGHT,
        "nn_weight": NN_WEIGHT,
        "description": f"P = {LGB_WEIGHT:.0%} × LightGBM + {NN_WEIGHT:.0%} × NeuralNetwork",
    }

    # LightGBM model details
    lgb_details = {
        "available": LGB_AVAILABLE,
        "trained": status.get("lgb_trained", False),
        "model_type": "LightGBM Gradient Boosted Trees",
        "features": FEATURE_NAMES,
        "hyperparameters": {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 20,
            "n_estimators": 300,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "class_weight": "balanced",
        },
        "calibration": "Isotonic Regression",
        "feature_importances": None,
    }

    # Try to load feature importances from saved model
    if LGB_AVAILABLE and MODEL_PATH.exists():
        try:
            model = lgb.Booster(model_file=str(MODEL_PATH))
            feat_names = model.feature_name()
            feat_imp = model.feature_importance(importance_type="gain")
            total = sum(feat_imp) if sum(feat_imp) > 0 else 1
            # Use saved feature names if available; otherwise fall back to FEATURE_NAMES
            if feat_names and feat_names[0].startswith("Column_"):
                if FEATURE_META_PATH.exists():
                    try:
                        import pickle as _pkl
                        with open(FEATURE_META_PATH, "rb") as _f:
                            _meta = _pkl.load(_f)
                        feat_names = _meta["features"][: len(feat_names)]
                    except Exception:
                        feat_names = FEATURE_NAMES[: len(feat_names)]
                else:
                    feat_names = FEATURE_NAMES[: len(feat_names)]
            lgb_details["feature_importances"] = {
                name: round(float(imp / total * 100), 2) for name, imp in zip(feat_names, feat_imp)
            }
            lgb_details["num_trees"] = model.num_trees()
        except Exception as e:
            log.warning(f"Could not load LGB feature importances: {e}")

    details["lgb"] = lgb_details

    # Neural Network model details
    try:
        from .nn_model import NN_MODEL_PATH, NN_META_PATH, SEQ_LEN, FEATURES as NN_FEATURES, TORCH_AVAILABLE as NN_AVAILABLE
    except ImportError:
        from nn_model import NN_MODEL_PATH, NN_META_PATH, SEQ_LEN, FEATURES as NN_FEATURES, TORCH_AVAILABLE as NN_AVAILABLE

    nn_details = {
        "available": NN_AVAILABLE,
        "trained": status.get("nn_trained", False),
        "model_type": "LSTM (Long Short-Term Memory) Neural Network",
        "architecture": {
            "type": "2-Layer LSTM + MLP Head",
            "hidden_size": 64,
            "num_layers": 2,
            "dropout": 0.3,
            "mlp_hidden": 32,
            "activation": "ReLU → Sigmoid",
            "output": "P(bullish) ∈ [0, 1]",
        },
        "features": list(NN_FEATURES),
        "sequence_length": SEQ_LEN,
        "hyperparameters": {
            "epochs": 30,
            "batch_size": 64,
            "learning_rate": 0.001,
            "weight_decay": 1e-5,
            "early_stopping_patience": 5,
            "gradient_clipping": 1.0,
        },
    }

    # Load NN metadata if available
    if NN_META_PATH.exists():
        try:
            with open(NN_META_PATH, "rb") as f:
                meta = pickle.load(f)
            nn_details["input_size"] = meta.get("input_size")
            nn_details["saved_features"] = meta.get("features")
        except Exception:
            pass

    details["nn"] = nn_details

    # Training data statistics
    data_stats = {"available": False}
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_snapshots'")
            if cursor.fetchone():
                cursor.execute("SELECT COUNT(*) FROM market_snapshots WHERE spot_price IS NOT NULL AND spot_price > 0")
                total_rows = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(DISTINCT symbol) FROM market_snapshots WHERE spot_price IS NOT NULL AND spot_price > 0")
                unique_symbols = cursor.fetchone()[0]
                cursor.execute("SELECT MIN(snapshot_time), MAX(snapshot_time) FROM market_snapshots WHERE spot_price IS NOT NULL AND spot_price > 0")
                row = cursor.fetchone()
                min_time, max_time = row if row else (None, None)
                cursor.execute(
                    "SELECT regime, COUNT(*) FROM market_snapshots WHERE spot_price IS NOT NULL AND spot_price > 0 GROUP BY regime"
                )
                regime_dist = {r: c for r, c in cursor.fetchall()}
                data_stats = {
                    "available": True,
                    "total_rows": total_rows,
                    "unique_symbols": unique_symbols,
                    "min_rows_required": MIN_ROWS_TO_TRAIN,
                    "ready_to_train": total_rows >= MIN_ROWS_TO_TRAIN,
                    "date_range": {"from": min_time, "to": max_time},
                    "regime_distribution": regime_dist,
                }
            conn.close()
        except Exception as e:
            log.warning(f"Could not load training data stats: {e}")

    details["training_data"] = data_stats

    # Schedule info
    details["schedule"] = {
        "auto_retrain": "Daily at 15:45 IST (after market close)",
        "manual_train": "POST /api/ml/train",
        "min_rows": MIN_ROWS_TO_TRAIN,
    }

    return details


def get_symbol_predictions(db_path: str = None) -> list:
    """Return per-symbol ML prediction breakdown (LGB vs NN) for recently scanned symbols."""
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "scanner.db")

    if not os.path.exists(db_path):
        return []

    results = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_snapshots'")
        if not cursor.fetchone():
            conn.close()
            return []

        # Get the latest snapshot per symbol with expanded feature columns
        cursor.execute("""
            SELECT symbol, score, COALESCE(net_gex, 0), COALESCE(iv_skew, 0),
                   COALESCE(pcr_oi, 1), COALESCE(pcr_vol, 1),
                   COALESCE(oi_velocity_score, 0), COALESCE(uoa_detected, 0),
                   MIN(COALESCE(dte, 5), 90),
                   COALESCE(iv_rank, 50),
                   COALESCE((atm_ce_iv + atm_pe_iv) / 2.0, 0),
                   CASE WHEN spot_price > 0
                        THEN ABS(spot_price - COALESCE(max_pain_strike, spot_price)) / spot_price * 100
                        ELSE 0 END,
                   regime, spot_price
            FROM market_snapshots
            WHERE snapshot_time = (
                SELECT MAX(snapshot_time) FROM market_snapshots AS ms2
                WHERE ms2.symbol = market_snapshots.symbol
                  AND ms2.spot_price IS NOT NULL AND ms2.spot_price > 0
            )
            ORDER BY score DESC
            LIMIT 30
        """)
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            (symbol, score, gex, iv_skew, pcr, pcr_vol, oi_vel, uoa,
             dte, iv_rank, avg_iv, mp_dist, regime, spot) = row
            features = {
                "weighted_score": float(score or 0),
                "gex": float(gex or 0),
                "iv_skew": float(iv_skew or 0),
                "pcr": float(pcr or 1),
                "pcr_vol": float(pcr_vol or 1),
                "oi_velocity_score": float(oi_vel or 0),
                "uoa_detected": float(uoa or 0),
                "dte": float(dte or 5),
                "iv_rank": float(iv_rank or 50),
                "avg_iv": float(avg_iv or 0),
                "max_pain_dist_pct": float(mp_dist or 0),
                "regime": regime or "TRENDING",
                "score": float(score or 0),
                "spot_price": float(spot or 1),
            }

            lgb_prob = _predict_lgb(features)
            nn_prob = predict_nn(symbol, features, db_path)

            ensemble_prob = None
            if lgb_prob is not None and nn_prob is not None:
                ensemble_prob = round(LGB_WEIGHT * lgb_prob + NN_WEIGHT * nn_prob, 4)
            elif lgb_prob is not None:
                ensemble_prob = lgb_prob
            elif nn_prob is not None:
                ensemble_prob = nn_prob

            results.append({
                "symbol": symbol,
                "spot_price": float(spot or 0),
                "regime": regime or "TRENDING",
                "quant_score": float(score or 0),
                "lgb_probability": lgb_prob,
                "nn_probability": nn_prob,
                "ensemble_probability": ensemble_prob,
                "signal": "BULLISH" if ensemble_prob and ensemble_prob > 0.55 else "BEARISH" if ensemble_prob and ensemble_prob < 0.45 else "NEUTRAL",
            })
    except Exception as e:
        log.warning(f"Could not generate symbol predictions: {e}")

    return results

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    print("==================================================")
    print("    Training ML Models (LightGBM + LSTM)          ")
    print("==================================================")
    print("Starting ML pipeline...")
    res = train_model()
    if "error" in res:
        print(f"❌ Error: {res['error']}")
    else:
        print("\n✅ Training Complete!")
        print(f"🌲 LightGBM CV Loss: {res.get('cv_log_loss_mean')} (±{res.get('cv_log_loss_std')})")
        if "nn" in res and not res["nn"].get("error"):
            print(f"🧬 LSTM NN CV Loss: {res['nn'].get('nn_cv_log_loss_mean')} (±{res['nn'].get('nn_cv_log_loss_std')})")
        print("Models saved successfully.")
