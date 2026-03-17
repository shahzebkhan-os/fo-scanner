"""
LSTM Neural Network for processing historical market data sequences.

Complements the LightGBM model by capturing temporal patterns in the
market_snapshots history that a point-in-time classifier misses.
When both models are trained the ensemble blends their outputs to produce
a more robust bullish-probability estimate.
"""

import numpy as np
import sqlite3
import os
os.environ["OMP_NUM_THREADS"] = "1"
import pickle
import logging
import warnings
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    import pandas as pd
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import log_loss

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

NN_MODEL_PATH = Path(os.path.dirname(__file__)) / "models" / "nn_lstm.pt"
NN_SCALER_PATH = Path(os.path.dirname(__file__)) / "models" / "nn_scaler.pkl"
NN_META_PATH = Path(os.path.dirname(__file__)) / "models" / "nn_meta.pkl"

SEQ_LEN = 10  # sliding-window length (number of past bars per sample)
# Feature list for the LSTM — must match FEATURE_NAMES in ml_model.py exactly
# so that the two models see the same input representation.
FEATURES = [
    "weighted_score",    # composite quant score (0–100)
    "gex",               # net gamma exposure
    "iv_skew",           # PE IV − CE IV
    "pcr",               # put/call ratio by open interest
    "pcr_vol",           # put/call ratio by volume
    "regime_encoded",    # 0=PINNED, 1=TRENDING, 2=EXPIRY, 3=SQUEEZE, 4=NEUTRAL
    "oi_velocity_score", # OI change velocity
    "pcr_velocity",      # rate of change of PCR across recent snapshots
    "rsi_14",            # 14-period RSI of spot price
    "sma_20",            # 20-period SMA
    "ema_9",             # 9-period EMA
    "bb_upper_dist",     # distance of price from upper Bollinger band
    "bb_lower_dist",     # distance of price from lower Bollinger band
    "uoa_detected",      # unusual options activity flag (0/1)
    "dte",               # days to expiry (clipped at 90)
    "iv_rank",           # IV rank (0–100 percentile)
    "avg_iv",            # average ATM IV ((CE IV + PE IV) / 2)
    "max_pain_dist_pct", # |spot − max_pain| / spot × 100
]
MIN_ROWS_TO_TRAIN = 500
RANDOM_BASELINE_LOSS = 0.693  # ln(2) — log-loss of a coin-flip classifier


# ── Model architecture ────────────────────────────────────────────────────────


if TORCH_AVAILABLE:

    class LSTMPredictor(nn.Module):
        """Two-layer LSTM followed by a small MLP head → P(bullish)."""

        def __init__(self, input_size: int, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.3):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size,
                hidden_size,
                num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0,
            )
            self.dropout = nn.Dropout(dropout)
            self.fc1 = nn.Linear(hidden_size, 32)
            self.relu = nn.ReLU()
            self.fc2 = nn.Linear(32, 1)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            lstm_out, _ = self.lstm(x)
            last_hidden = lstm_out[:, -1, :]  # only the final time-step
            x = self.dropout(last_hidden)
            x = self.relu(self.fc1(x))
            x = torch.sigmoid(self.fc2(x))
            return x.squeeze(-1)

else:
    LSTMPredictor = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_sequences(values: np.ndarray, labels: np.ndarray, seq_len: int = SEQ_LEN):
    """Sliding window over a *single* symbol's sorted feature matrix."""
    X_seqs, y_labels = [], []
    for i in range(len(values) - seq_len):
        X_seqs.append(values[i : i + seq_len])
        y_labels.append(labels[i + seq_len - 1])
    return X_seqs, y_labels


def _load_sequence_data(db_path: str = None):
    """Load market_snapshots → (X_seq, y, feature_names, scaler).

    Returns numpy arrays ready for PyTorch:
        X_seq : (N, SEQ_LEN, n_features) float32
        y     : (N,) int32
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

    df["snapshot_time"] = pd.to_datetime(df["snapshot_time"])
    df = df.sort_values(["symbol", "snapshot_time"])

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

    # ── Label construction (mirrors ml_model.py) ──────────────────────────
    df = df.assign(label=np.nan)
    df.loc[df["trade_result"] == "WIN", "label"] = 1.0
    df.loc[df["trade_result"] == "LOSS", "label"] = 0.0

    df = df.assign(next_spot=df.groupby("symbol")["spot_price"].shift(-1))
    spot_label = (df["next_spot"] > df["spot_price"]).astype(float)
    fallback_mask = df["label"].isna() & df["next_spot"].notna()
    df.loc[fallback_mask, "label"] = spot_label[fallback_mask]
    df = df.dropna(subset=["label"])
    df.loc[:, "label"] = df["label"].astype(np.int32)

    df["regime_encoded"] = (
        df["regime"]
        .map({"PINNED": 0, "TRENDING": 1, "EXPIRY": 2, "SQUEEZE": 3, "NEUTRAL": 4})
        .fillna(1)
        .astype(float)
    )

    for col in FEATURES:
        if col in df.columns:
            if col in ("pcr", "pcr_vol"):
                default = 1.0
            elif col == "iv_rank":
                default = 50.0
            elif col == "rsi_14":
                default = 50.0
            elif col in ("sma_20", "ema_9"):
                default = float(df["spot_price"].median()) if not df["spot_price"].dropna().empty else 0.0
            else:
                default = 0.0
            df[col] = df[col].fillna(default)

    # Fit scaler on all rows
    scaler = StandardScaler()
    df[FEATURES] = scaler.fit_transform(df[FEATURES].values)

    # Build sliding-window sequences per symbol
    all_X, all_y = [], []
    for _symbol, group in df.groupby("symbol"):
        if len(group) < SEQ_LEN + 1:
            continue
        vals = group[FEATURES].values.astype(np.float32)
        labs = group["label"].values.astype(np.int32)
        xs, ys = _create_sequences(vals, labs, SEQ_LEN)
        all_X.extend(xs)
        all_y.extend(ys)

    if not all_X:
        raise ValueError("Not enough sequential data to create training sequences")

    X_seq = np.array(all_X, dtype=np.float32)
    y_arr = np.array(all_y, dtype=np.int32)
    return X_seq, y_arr, FEATURES, scaler


# ── Training ──────────────────────────────────────────────────────────────────


def train_nn(db_path: str = None) -> dict:
    """Train the LSTM neural network on historical sequences.

    Returns a metrics dict compatible with the LightGBM train_model() format.
    """
    if not TORCH_AVAILABLE:
        return {"error": "torch not installed. Run: pip install torch"}

    print("Starting LSTM Neural Network training pipeline...")
    try:
        print("Loading sequence data for NN...")
        X_seq, y, feature_names, scaler = _load_sequence_data(db_path)
        print(f"Loaded {len(X_seq)} sequences successfully.")
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}

    if len(X_seq) < MIN_ROWS_TO_TRAIN:
        return {"error": f"Need {MIN_ROWS_TO_TRAIN} sequences, have {len(X_seq)}. Run more historical backfill first."}

    device = torch.device("cpu")  # keep it simple; GPU optional

    # Time-series split for validation
    n_splits = min(5, len(X_seq) // 100)
    if n_splits < 2:
        n_splits = 2
    tscv = TimeSeriesSplit(n_splits=n_splits)
    val_losses = []

    # Hyperparameters
    epochs = 30
    batch_size = 64
    lr = 1e-3
    input_size = X_seq.shape[2]

    print(f"Starting time-series cross-validation ({n_splits} splits)...")
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X_seq)):
        print(f"  Fold {fold + 1}/{n_splits}: train={len(train_idx)}, val={len(val_idx)}")
        print("    Initializing LSTMPredictor...")
        model = LSTMPredictor(input_size=input_size).to(device)
        print("    LSTMPredictor initialized. Creating optimizer...")
        optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
        criterion = nn.BCELoss()

        X_train_t = torch.tensor(X_seq[train_idx], dtype=torch.float32)
        y_train_t = torch.tensor(y[train_idx], dtype=torch.float32)
        X_val_t = torch.tensor(X_seq[val_idx], dtype=torch.float32)
        y_val_t = torch.tensor(y[val_idx], dtype=torch.float32)

        # Simple memory batching (no DataLoader)
        indices = np.arange(len(X_train_t))
        
        best_val_loss = float("inf")
        patience, wait = 5, 0

        for _epoch in range(epochs):
            print(f"    Epoch {_epoch + 1}/{epochs}...")
            model.train()
            # Shuffle manually
            np.random.shuffle(indices)
            
            for start_idx in range(0, len(indices), batch_size):
                batch_idx = indices[start_idx:start_idx + batch_size]
                xb = X_train_t[batch_idx].to(device)
                yb = y_train_t[batch_idx].to(device)
                
                optimizer.zero_grad()
                pred = model(xb)
                loss = criterion(pred, yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()

            # Validation
            model.eval()
            with torch.no_grad():
                val_pred = model(X_val_t.to(device)).cpu().numpy()
            val_pred = np.clip(val_pred, 1e-7, 1 - 1e-7)
            vl = float(log_loss(y[val_idx], val_pred))
            if vl < best_val_loss:
                best_val_loss = vl
                wait = 0
            else:
                wait += 1
                if wait >= patience:
                    break

        val_losses.append(best_val_loss)

    mean_loss = float(np.mean(val_losses))

    # Only save if better than random (log_loss < ln(2))
    if mean_loss >= RANDOM_BASELINE_LOSS:
        return {
            "error": f"NN cv_log_loss {mean_loss:.4f} ≥ {RANDOM_BASELINE_LOSS} (random baseline). Model not saved.",
            "cv_log_loss_mean": round(mean_loss, 4),
        }

    # Train final model on all data
    print(f"Training final LSTM model on all {len(X_seq)} sequences...")
    print("  Initializing final LSTMPredictor...")
    final_model = LSTMPredictor(input_size=input_size).to(device)
    print("  Final LSTMPredictor initialized.")
    optimizer = torch.optim.Adam(final_model.parameters(), lr=lr, weight_decay=1e-5)
    criterion = nn.BCELoss()
    X_all_t = torch.tensor(X_seq, dtype=torch.float32)
    y_all_t = torch.tensor(y, dtype=torch.float32)
    all_indices = np.arange(len(X_all_t))

    for _epoch in range(epochs):
        final_model.train()
        np.random.shuffle(all_indices)
        for start_idx in range(0, len(all_indices), batch_size):
            batch_idx = all_indices[start_idx:start_idx + batch_size]
            xb = X_all_t[batch_idx].to(device)
            yb = y_all_t[batch_idx].to(device)
            
            optimizer.zero_grad()
            pred = final_model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(final_model.parameters(), 1.0)
            optimizer.step()

    # Save model, scaler and metadata
    NN_MODEL_PATH.parent.mkdir(exist_ok=True)
    torch.save(final_model.state_dict(), str(NN_MODEL_PATH))

    with open(NN_SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    meta = {"input_size": input_size, "seq_len": SEQ_LEN, "features": feature_names}
    with open(NN_META_PATH, "wb") as f:
        pickle.dump(meta, f)

    log.info(f"NN model saved: loss={mean_loss:.4f}, sequences={len(X_seq)}")
    print(f"LSTM NN saved successfully! Loss: {mean_loss:.4f}")

    return {
        "nn_cv_log_loss_mean": round(mean_loss, 4),
        "nn_cv_log_loss_std": round(float(np.std(val_losses)), 4),
        "nn_training_sequences": len(X_seq),
        "nn_model_saved": str(NN_MODEL_PATH),
    }


# ── Prediction ────────────────────────────────────────────────────────────────

_cached_model = None
_cached_meta = None
_cached_scaler = None

def predict_nn(symbol: str, current_features: dict, db_path: str = None) -> Optional[float]:
    """Return P(bullish) from the LSTM model using recent historical bars."""
    global _cached_model, _cached_meta, _cached_scaler

    if not TORCH_AVAILABLE or not NN_MODEL_PATH.exists() or not NN_SCALER_PATH.exists() or not NN_META_PATH.exists():
        return None

    try:
        # Load model and meta into memory if not already cached
        if _cached_model is None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=UserWarning)
                with open(NN_META_PATH, "rb") as f:
                    _cached_meta = pickle.load(f)
                with open(NN_SCALER_PATH, "rb") as f:
                    _cached_scaler = pickle.load(f)
            
            _cached_model = LSTMPredictor(input_size=_cached_meta["input_size"])
            _cached_model.load_state_dict(torch.load(str(NN_MODEL_PATH), map_location="cpu", weights_only=True))
            _cached_model.eval()

        meta = _cached_meta
        scaler = _cached_scaler
        model = _cached_model

        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "scanner.db")
        if not os.path.exists(db_path):
            return None

        features_list = meta["features"]
        seq_len = meta["seq_len"]

        # Fetch recent snapshots using the same feature columns as training
        conn = sqlite3.connect(db_path)
        query = f"""
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
                snapshot_time
            FROM market_snapshots
            WHERE symbol = ? AND spot_price IS NOT NULL AND spot_price > 0
            ORDER BY snapshot_time DESC
            LIMIT ?
        """
        rows = conn.execute(query, (symbol, seq_len)).fetchall()
        conn.close()

        if len(rows) < seq_len - 1:
            return None  # need at least seq_len-1 historical bars + 1 live bar

        _rmap = {"PINNED": 0, "TRENDING": 1, "EXPIRY": 2, "SQUEEZE": 3, "NEUTRAL": 4}

        df_hist = pd.DataFrame(rows, columns=[
            "weighted_score", "gex", "iv_skew", "pcr", "pcr_vol", "oi_velocity_score",
            "uoa_detected", "dte", "iv_rank", "avg_iv", "max_pain_dist_pct", "regime",
            "spot_price", "snapshot_time",
        ])
        df_hist["snapshot_time"] = pd.to_datetime(df_hist["snapshot_time"])
        df_hist = df_hist.sort_values("snapshot_time")

        prices = df_hist["spot_price"].astype(float)
        pcr_series = df_hist["pcr"].astype(float)

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

        df_hist["rsi_14"] = rsi.fillna(50.0)
        df_hist["sma_20"] = sma20.ffill().bfill()
        df_hist["ema_9"] = ema9.ffill().bfill()
        df_hist["bb_upper_dist"] = upper_dist.replace([np.inf, -np.inf], 0).fillna(0)
        df_hist["bb_lower_dist"] = lower_dist.replace([np.inf, -np.inf], 0).fillna(0)
        df_hist["pcr_velocity"] = pcr_vel.replace([np.inf, -np.inf], 0).fillna(0)

        df_hist = df_hist.tail(seq_len)

        # Build historical feature matrix (oldest → newest) matching `features_list`.
        hist = []
        for _, row in df_hist.iterrows():
            reg = row["regime"]
            hist.append([
                float(row["weighted_score"] or 0), float(row["gex"] or 0), float(row["iv_skew"] or 0),
                float(row["pcr"] or 1), float(row["pcr_vol"] or 1),
                float(_rmap.get(reg, 1)),
                float(row["oi_velocity_score"] or 0),
                float(row["pcr_velocity"] or 0),
                float(row["rsi_14"] or 50),
                float(row["sma_20"] or row["spot_price"] or 0),
                float(row["ema_9"] or row["spot_price"] or 0),
                float(row["bb_upper_dist"] or 0),
                float(row["bb_lower_dist"] or 0),
                float(row["uoa_detected"] or 0),
                float(row["dte"] or 5), float(row["iv_rank"] or 50),
                float(row["avg_iv"] or 0), float(row["max_pain_dist_pct"] or 0),
            ])

        # Append current live bar using the same feature order
        try:
            from .ml_model import _get_feature_value
        except ImportError:
            from ml_model import _get_feature_value
        live_bar = [_get_feature_value(fn, current_features) for fn in features_list]
        hist.append(live_bar)

        # If saved model has fewer features (legacy), trim to match
        n_expected = meta["input_size"]
        hist = [[row[i] for i in range(min(len(row), n_expected))] for row in hist]

        # Use the last seq_len bars
        seq = hist[-seq_len:]
        if len(seq) < seq_len:
            return None

        arr = np.array(seq, dtype=np.float64)
        arr = scaler.transform(arr).astype(np.float32)

        # Run through LSTM using the already-loaded cached model
        with torch.no_grad():
            x_t = torch.tensor(arr, dtype=torch.float32).unsqueeze(0)  # (1, seq_len, features)
            prob = model(x_t).item()

        return round(float(np.clip(prob, 0.0, 1.0)), 4)

    except Exception as e:
        log.warning(f"NN prediction failed for {symbol}: {e}")
        return None


def get_nn_status() -> dict:
    """Return current neural network model status."""
    trained = NN_MODEL_PATH.exists() and NN_SCALER_PATH.exists() and NN_META_PATH.exists()
    return {
        "nn_trained": trained,
        "nn_model_path": str(NN_MODEL_PATH) if trained else None,
        "torch_available": TORCH_AVAILABLE,
    }
