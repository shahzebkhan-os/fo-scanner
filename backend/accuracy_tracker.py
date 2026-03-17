"""
Accuracy Tracker - Real-time and Historical Model Accuracy Monitoring

This module tracks the accuracy of prediction models (LightGBM + LSTM ensemble)
throughout market hours and allows historical analysis with configurable settings.

Features:
- Real-time accuracy tracking during market hours
- Historical accuracy analysis with date range support
- Detailed visual representation of prediction performance
- Configurable settings for retesting accuracy
- Stores all important prediction metadata for analysis
"""

import sqlite3
import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from pathlib import Path
import json

log = logging.getLogger(__name__)

try:
    import pandas as pd
    import numpy as np
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class AccuracyTracker:
    """
    Tracks and analyzes model prediction accuracy in real-time and historically.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "scanner.db")
        self.db_path = db_path
        self.config_path = Path(os.path.dirname(__file__)) / "accuracy_config.json"
        self.default_config = {
            "min_score_threshold": 70,
            "min_confidence_threshold": 0.50,
            "min_ml_probability": 0.55,
            "profit_target_pct": 20.0,
            "stop_loss_pct": 20.0,
            "tracking_interval_seconds": 300,  # 5 minutes
            "track_during_market_hours": True,
            "market_start_hour": 9,
            "market_start_minute": 15,
            "market_end_hour": 15,
            "market_end_minute": 30,
        }
        self._ensure_tracking_tables()

    def _ensure_tracking_tables(self):
        """Create additional tables for detailed accuracy tracking if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Accuracy runs table - stores metadata about each accuracy tracking session
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accuracy_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT,
                run_type TEXT NOT NULL,  -- 'LIVE' or 'HISTORICAL'
                date_range_start TEXT,
                date_range_end TEXT,
                total_predictions INTEGER DEFAULT 0,
                correct_predictions INTEGER DEFAULT 0,
                accuracy_pct REAL DEFAULT 0,
                total_profit REAL DEFAULT 0,
                total_loss REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                avg_profit_per_trade REAL DEFAULT 0,
                config_json TEXT,  -- Store configuration used for this run
                status TEXT DEFAULT 'RUNNING'  -- RUNNING, COMPLETED, FAILED
            )
        """)

        # Detailed prediction outcomes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accuracy_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES accuracy_runs(id) ON DELETE CASCADE,
                symbol TEXT NOT NULL,
                prediction_time TEXT NOT NULL,
                signal TEXT NOT NULL,
                score INTEGER NOT NULL,
                confidence REAL NOT NULL,
                ml_probability REAL,
                lgb_probability REAL,
                nn_probability REAL,
                regime TEXT,
                spot_price REAL,

                -- Option details
                option_type TEXT,
                strike REAL,
                entry_price REAL,

                -- Outcome tracking
                exit_price REAL,
                exit_time TEXT,
                pnl_pct REAL,
                pnl_absolute REAL,
                outcome TEXT,  -- WIN, LOSS, NEUTRAL, PENDING

                -- Additional context
                iv_rank REAL,
                pcr REAL,
                max_pain REAL,
                days_to_expiry INTEGER,
                gex REAL,
                iv_skew REAL
            )
        """)

        # Price updates table for tracking option prices over time
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accuracy_price_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id INTEGER NOT NULL REFERENCES accuracy_predictions(id) ON DELETE CASCADE,
                price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                spot_price REAL
            )
        """)

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accuracy_runs_date ON accuracy_runs(start_time, end_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accuracy_predictions_run ON accuracy_predictions(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accuracy_predictions_symbol ON accuracy_predictions(symbol, prediction_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accuracy_predictions_outcome ON accuracy_predictions(outcome)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accuracy_price_updates_pred ON accuracy_price_updates(prediction_id)")

        conn.commit()
        conn.close()

    def load_config(self) -> dict:
        """Load accuracy tracking configuration."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults to handle new config keys
                    return {**self.default_config, **loaded_config}
            except Exception as e:
                log.warning(f"Failed to load config: {e}, using defaults")
        return self.default_config.copy()

    def save_config(self, config: dict):
        """Save accuracy tracking configuration."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            log.info("Accuracy tracking config saved")
        except Exception as e:
            log.error(f"Failed to save config: {e}")

    def start_accuracy_run(self, run_type: str = "LIVE", date_range: Tuple[str, str] = None, config: dict = None) -> int:
        """
        Start a new accuracy tracking run.

        Args:
            run_type: 'LIVE' for real-time tracking, 'HISTORICAL' for backtesting
            date_range: Tuple of (start_date, end_date) for historical runs
            config: Configuration dict to use for this run

        Returns:
            run_id: ID of the created accuracy run
        """
        if config is None:
            config = self.load_config()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        start_time = datetime.now().isoformat()
        date_range_start = date_range[0] if date_range else None
        date_range_end = date_range[1] if date_range else None

        cursor.execute("""
            INSERT INTO accuracy_runs (
                start_time, run_type, date_range_start, date_range_end, config_json, status
            ) VALUES (?, ?, ?, ?, ?, 'RUNNING')
        """, (start_time, run_type, date_range_start, date_range_end, json.dumps(config)))

        run_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log.info(f"Started accuracy run {run_id} ({run_type})")
        return run_id

    def record_prediction(self, run_id: int, symbol: str, scan_result: dict, top_pick: dict = None) -> int:
        """
        Record a prediction for accuracy tracking.

        Args:
            run_id: ID of the accuracy run
            symbol: Stock symbol
            scan_result: Full scan result dict containing score, signal, ML predictions, etc.
            top_pick: Top option pick from suggestions

        Returns:
            prediction_id: ID of the recorded prediction
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Extract ML model probabilities
        ml_prob = scan_result.get("ml_probability")
        lgb_prob = scan_result.get("ml", {}).get("lgb_probability") if isinstance(scan_result.get("ml"), dict) else None
        nn_prob = scan_result.get("ml", {}).get("nn_probability") if isinstance(scan_result.get("ml"), dict) else None

        # Option details from top pick
        option_type = top_pick.get("type") if top_pick else None
        strike = top_pick.get("strike") if top_pick else None
        entry_price = top_pick.get("ltp") if top_pick else None

        cursor.execute("""
            INSERT INTO accuracy_predictions (
                run_id, symbol, prediction_time, signal, score, confidence,
                ml_probability, lgb_probability, nn_probability, regime, spot_price,
                option_type, strike, entry_price, outcome,
                iv_rank, pcr, max_pain, days_to_expiry, gex, iv_skew
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?)
        """, (
            run_id, symbol, datetime.now().isoformat(),
            scan_result.get("signal", "NEUTRAL"),
            scan_result.get("score", 0),
            scan_result.get("confidence", 0),
            ml_prob, lgb_prob, nn_prob,
            scan_result.get("regime", "NEUTRAL"),
            scan_result.get("spot_price", 0),
            option_type, strike, entry_price,
            scan_result.get("iv_rank", 0),
            scan_result.get("pcr", 1.0),
            scan_result.get("max_pain", 0),
            scan_result.get("days_to_expiry", 0),
            scan_result.get("gex", 0),
            scan_result.get("iv_skew", 0)
        ))

        prediction_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return prediction_id

    def update_prediction_price(self, prediction_id: int, current_price: float, spot_price: float = None):
        """Update the current price for a pending prediction."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Record price update
        cursor.execute("""
            INSERT INTO accuracy_price_updates (prediction_id, price, timestamp, spot_price)
            VALUES (?, ?, ?, ?)
        """, (prediction_id, current_price, datetime.now().isoformat(), spot_price))

        conn.commit()
        conn.close()

    def evaluate_prediction(self, prediction_id: int, current_price: float, config: dict = None) -> Optional[str]:
        """
        Evaluate if a prediction has hit profit target or stop loss.

        Args:
            prediction_id: ID of the prediction to evaluate
            current_price: Current option price
            config: Configuration with profit/loss thresholds

        Returns:
            outcome: 'WIN', 'LOSS', or None if still pending
        """
        if config is None:
            config = self.load_config()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get prediction details
        cursor.execute("""
            SELECT entry_price, signal FROM accuracy_predictions WHERE id = ?
        """, (prediction_id,))
        row = cursor.fetchone()

        if not row or not row[0]:
            conn.close()
            return None

        entry_price = row[0]
        signal = row[1]

        # Calculate P&L percentage
        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        # For bearish signals, invert the P&L (profit when price goes down)
        if signal == "BEARISH":
            pnl_pct = -pnl_pct

        profit_target = config.get("profit_target_pct", 20.0)
        stop_loss = config.get("stop_loss_pct", 20.0)

        outcome = None
        if pnl_pct >= profit_target:
            outcome = "WIN"
        elif pnl_pct <= -stop_loss:
            outcome = "LOSS"

        if outcome:
            # Update prediction with outcome
            cursor.execute("""
                UPDATE accuracy_predictions
                SET exit_price = ?, exit_time = ?, pnl_pct = ?, outcome = ?
                WHERE id = ?
            """, (current_price, datetime.now().isoformat(), pnl_pct, outcome, prediction_id))
            conn.commit()
            log.info(f"Prediction {prediction_id} outcome: {outcome} (P&L: {pnl_pct:.2f}%)")

        conn.close()
        return outcome

    def finalize_accuracy_run(self, run_id: int):
        """Calculate final statistics and mark run as completed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all predictions for this run
        cursor.execute("""
            SELECT outcome, pnl_pct FROM accuracy_predictions WHERE run_id = ?
        """, (run_id,))

        predictions = cursor.fetchall()
        if not predictions:
            conn.close()
            return

        total_predictions = len(predictions)
        wins = sum(1 for p in predictions if p[0] == "WIN")
        losses = sum(1 for p in predictions if p[0] == "LOSS")
        pending = sum(1 for p in predictions if p[0] == "PENDING")

        # Calculate metrics
        completed = wins + losses
        accuracy_pct = (wins / completed * 100) if completed > 0 else 0
        win_rate = (wins / completed) if completed > 0 else 0

        # Calculate P&L
        total_profit = sum(p[1] for p in predictions if p[0] == "WIN" and p[1] is not None)
        total_loss = sum(abs(p[1]) for p in predictions if p[0] == "LOSS" and p[1] is not None)
        avg_profit = (total_profit - total_loss) / completed if completed > 0 else 0

        # Update run statistics
        cursor.execute("""
            UPDATE accuracy_runs
            SET end_time = ?,
                total_predictions = ?,
                correct_predictions = ?,
                accuracy_pct = ?,
                total_profit = ?,
                total_loss = ?,
                win_rate = ?,
                avg_profit_per_trade = ?,
                status = ?
            WHERE id = ?
        """, (
            datetime.now().isoformat(),
            total_predictions,
            wins,
            accuracy_pct,
            total_profit,
            total_loss,
            win_rate,
            avg_profit,
            'COMPLETED' if pending == 0 else 'RUNNING',
            run_id
        ))

        conn.commit()
        conn.close()

        log.info(f"Accuracy run {run_id}: {wins}/{completed} wins ({accuracy_pct:.2f}%), Avg P&L: {avg_profit:.2f}%")

    def get_run_summary(self, run_id: int) -> Optional[dict]:
        """Get detailed summary of an accuracy run."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get run details
        cursor.execute("SELECT * FROM accuracy_runs WHERE id = ?", (run_id,))
        run = cursor.fetchone()

        if not run:
            conn.close()
            return None

        # Get all predictions
        cursor.execute("""
            SELECT * FROM accuracy_predictions WHERE run_id = ?
            ORDER BY prediction_time DESC
        """, (run_id,))
        predictions = [dict(row) for row in cursor.fetchall()]

        conn.close()

        # Calculate additional statistics
        by_outcome = defaultdict(list)
        by_symbol = defaultdict(lambda: {"predictions": 0, "wins": 0, "losses": 0, "avg_pnl": 0})
        by_signal = defaultdict(lambda: {"predictions": 0, "wins": 0, "losses": 0})
        by_regime = defaultdict(lambda: {"predictions": 0, "wins": 0, "losses": 0})

        for pred in predictions:
            outcome = pred["outcome"]
            symbol = pred["symbol"]
            signal = pred["signal"]
            regime = pred["regime"]

            by_outcome[outcome].append(pred)

            by_symbol[symbol]["predictions"] += 1
            if outcome == "WIN":
                by_symbol[symbol]["wins"] += 1
            elif outcome == "LOSS":
                by_symbol[symbol]["losses"] += 1
            if pred["pnl_pct"]:
                by_symbol[symbol]["avg_pnl"] += pred["pnl_pct"]

            by_signal[signal]["predictions"] += 1
            if outcome == "WIN":
                by_signal[signal]["wins"] += 1
            elif outcome == "LOSS":
                by_signal[signal]["losses"] += 1

            by_regime[regime]["predictions"] += 1
            if outcome == "WIN":
                by_regime[regime]["wins"] += 1
            elif outcome == "LOSS":
                by_regime[regime]["losses"] += 1

        # Calculate averages
        for symbol_stats in by_symbol.values():
            if symbol_stats["predictions"] > 0:
                symbol_stats["avg_pnl"] /= symbol_stats["predictions"]
                symbol_stats["win_rate"] = symbol_stats["wins"] / (symbol_stats["wins"] + symbol_stats["losses"]) if (symbol_stats["wins"] + symbol_stats["losses"]) > 0 else 0

        for signal_stats in by_signal.values():
            signal_stats["win_rate"] = signal_stats["wins"] / (signal_stats["wins"] + signal_stats["losses"]) if (signal_stats["wins"] + signal_stats["losses"]) > 0 else 0

        for regime_stats in by_regime.values():
            regime_stats["win_rate"] = regime_stats["wins"] / (regime_stats["wins"] + regime_stats["losses"]) if (regime_stats["wins"] + regime_stats["losses"]) > 0 else 0

        return {
            "run": dict(run),
            "predictions": predictions,
            "stats": {
                "by_outcome": dict(by_outcome),
                "by_symbol": dict(by_symbol),
                "by_signal": dict(by_signal),
                "by_regime": dict(by_regime)
            }
        }

    def get_all_runs(self, limit: int = 50) -> List[dict]:
        """Get list of all accuracy runs."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM accuracy_runs
            ORDER BY start_time DESC
            LIMIT ?
        """, (limit,))

        runs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return runs

    def run_historical_accuracy_test(self, start_date: str, end_date: str, config: dict = None) -> dict:
        """
        Run accuracy test on historical market_snapshots data.

        Args:
            start_date: Start date in 'YYYY-MM-DD' format
            end_date: End date in 'YYYY-MM-DD' format
            config: Configuration dict with thresholds

        Returns:
            dict with run_id and summary statistics
        """
        if config is None:
            config = self.load_config()

        # Start accuracy run
        run_id = self.start_accuracy_run(
            run_type="HISTORICAL",
            date_range=(start_date, end_date),
            config=config
        )

        try:
            conn = sqlite3.connect(self.db_path)

            # Query historical snapshots
            query = """
                SELECT
                    symbol, snapshot_time, signal, score, confidence, regime, spot_price,
                    top_pick_type, top_pick_strike, top_pick_ltp, pick_pnl_pct_next,
                    iv_rank, pcr_oi as pcr, max_pain_strike as max_pain,
                    dte, net_gex as gex, iv_skew, trade_result
                FROM market_snapshots
                WHERE snapshot_time >= ? AND snapshot_time <= ?
                    AND score >= ?
                    AND confidence >= ?
                    AND signal != 'NEUTRAL'
                    AND top_pick_ltp IS NOT NULL
                    AND top_pick_ltp > 0
                ORDER BY snapshot_time ASC
            """

            params = (
                f"{start_date} 00:00:00",
                f"{end_date} 23:59:59",
                config.get("min_score_threshold", 70),
                config.get("min_confidence_threshold", 0.5)
            )

            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            log.info(f"Running historical accuracy test on {len(rows)} snapshots from {start_date} to {end_date}")

            for row in rows:
                symbol = row[0]

                # Create scan result dict
                scan_result = {
                    "signal": row[2],
                    "score": row[3],
                    "confidence": row[4],
                    "regime": row[5],
                    "spot_price": row[6],
                    "iv_rank": row[11],
                    "pcr": row[12],
                    "max_pain": row[13],
                    "days_to_expiry": row[14],
                    "gex": row[15],
                    "iv_skew": row[16]
                }

                # Top pick details
                top_pick = {
                    "type": row[7],
                    "strike": row[8],
                    "ltp": row[9]
                }

                # Record prediction
                prediction_id = self.record_prediction(run_id, symbol, scan_result, top_pick)

                # Evaluate based on next-bar P&L
                pnl_pct_next = row[10]
                if pnl_pct_next is not None:
                    # Calculate exit price based on P&L
                    entry_price = row[9]
                    exit_price = entry_price * (1 + pnl_pct_next / 100)

                    # Update with final outcome
                    outcome = self.evaluate_prediction(prediction_id, exit_price, config)

                    # If not determined by evaluate_prediction, use trade_result if available
                    if not outcome and row[17]:
                        outcome = row[17]
                        conn_update = sqlite3.connect(self.db_path)
                        cursor_update = conn_update.cursor()
                        cursor_update.execute("""
                            UPDATE accuracy_predictions
                            SET exit_price = ?, pnl_pct = ?, outcome = ?
                            WHERE id = ?
                        """, (exit_price, pnl_pct_next, outcome, prediction_id))
                        conn_update.commit()
                        conn_update.close()

            conn.close()

            # Finalize the run
            self.finalize_accuracy_run(run_id)

            # Get summary
            summary = self.get_run_summary(run_id)

            return {
                "success": True,
                "run_id": run_id,
                "summary": summary
            }

        except Exception as e:
            log.error(f"Historical accuracy test failed: {e}")

            # Mark run as failed
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE accuracy_runs SET status = 'FAILED', end_time = ? WHERE id = ?
            """, (datetime.now().isoformat(), run_id))
            conn.commit()
            conn.close()

            return {
                "success": False,
                "error": str(e),
                "run_id": run_id
            }

    def get_visualization_data(self, run_id: int) -> dict:
        """
        Get data formatted for visualization charts.

        Returns data for:
        - Win rate over time
        - P&L distribution
        - Accuracy by symbol, signal, regime
        - Prediction timeline
        """
        summary = self.get_run_summary(run_id)
        if not summary:
            return {}

        predictions = summary["predictions"]

        # Timeline data (cumulative accuracy over time)
        timeline = []
        cumulative_wins = 0
        cumulative_total = 0
        cumulative_pnl = 0

        for pred in sorted(predictions, key=lambda x: x["prediction_time"]):
            if pred["outcome"] in ["WIN", "LOSS"]:
                cumulative_total += 1
                if pred["outcome"] == "WIN":
                    cumulative_wins += 1
                if pred["pnl_pct"]:
                    cumulative_pnl += pred["pnl_pct"]

                timeline.append({
                    "time": pred["prediction_time"],
                    "accuracy": (cumulative_wins / cumulative_total * 100) if cumulative_total > 0 else 0,
                    "win_count": cumulative_wins,
                    "total_count": cumulative_total,
                    "cumulative_pnl": cumulative_pnl
                })

        # P&L distribution
        pnl_distribution = {
            "bins": [],
            "counts": []
        }

        pnl_values = [p["pnl_pct"] for p in predictions if p["pnl_pct"] is not None]
        if pnl_values and PANDAS_AVAILABLE:
            hist, bins = np.histogram(pnl_values, bins=20)
            pnl_distribution["bins"] = [f"{bins[i]:.1f} to {bins[i+1]:.1f}" for i in range(len(bins)-1)]
            pnl_distribution["counts"] = hist.tolist()

        # Accuracy by score ranges
        score_accuracy = defaultdict(lambda: {"total": 0, "wins": 0})
        for pred in predictions:
            if pred["outcome"] in ["WIN", "LOSS"]:
                score_range = (pred["score"] // 10) * 10
                score_accuracy[score_range]["total"] += 1
                if pred["outcome"] == "WIN":
                    score_accuracy[score_range]["wins"] += 1

        score_accuracy_chart = {
            "ranges": [f"{k}-{k+9}" for k in sorted(score_accuracy.keys())],
            "accuracy": [
                (score_accuracy[k]["wins"] / score_accuracy[k]["total"] * 100) if score_accuracy[k]["total"] > 0 else 0
                for k in sorted(score_accuracy.keys())
            ],
            "counts": [score_accuracy[k]["total"] for k in sorted(score_accuracy.keys())]
        }

        return {
            "timeline": timeline,
            "pnl_distribution": pnl_distribution,
            "score_accuracy": score_accuracy_chart,
            "by_symbol": summary["stats"]["by_symbol"],
            "by_signal": summary["stats"]["by_signal"],
            "by_regime": summary["stats"]["by_regime"]
        }


# Global instance for easy access
_tracker_instance = None

def get_accuracy_tracker() -> AccuracyTracker:
    """Get or create the global accuracy tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = AccuracyTracker()
    return _tracker_instance
