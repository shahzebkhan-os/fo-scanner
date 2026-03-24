"""
Technical Score Backtesting System

Dedicated backtesting framework to validate and measure accuracy of technical
scoring signals. Tracks performance by direction, strength, regime, and timeframe.

Features:
- Walk-forward backtesting on historical data
- Performance metrics by signal type and market regime
- Indicator contribution analysis (which indicators drive wins/losses)
- Time-based performance analysis (intraday decay, best times to trade)
- Statistical significance testing
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import json

log = logging.getLogger(__name__)

try:
    import pandas as pd
    import numpy as np
    import yfinance as yf
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False
    log.warning("pandas/numpy/yfinance not available - technical backtesting disabled")


@dataclass
class BacktestTrade:
    """Individual trade result from backtest."""
    symbol: str
    entry_time: datetime
    exit_time: datetime
    direction: str  # BULLISH/BEARISH
    direction_strength: str  # STRONG/WEAK
    score: int
    confidence: float
    timeframe: str  # 5m/15m/30m
    regime: str  # TRENDING/RANGING

    entry_price: float
    exit_price: float
    pnl_pct: float
    outcome: str  # WIN/LOSS

    # Indicator values at entry
    indicators: Dict[str, dict]

    # Additional context
    adx_at_entry: float
    directional_edge: float
    agreement_pct: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d['entry_time'] = self.entry_time.isoformat()
        d['exit_time'] = self.exit_time.isoformat()
        return d


@dataclass
class BacktestMetrics:
    """Aggregate metrics from backtest run."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    total_profit_pct: float
    total_loss_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float

    max_consecutive_wins: int
    max_consecutive_losses: int

    # By direction
    bullish_trades: int
    bullish_wins: int
    bullish_win_rate: float

    bearish_trades: int
    bearish_wins: int
    bearish_win_rate: float

    # By strength
    strong_trades: int
    strong_wins: int
    strong_win_rate: float

    weak_trades: int
    weak_wins: int
    weak_win_rate: float

    # By regime
    trending_trades: int
    trending_wins: int
    trending_win_rate: float

    ranging_trades: int
    ranging_wins: int
    ranging_win_rate: float

    # Statistical significance
    z_score: Optional[float] = None
    p_value: Optional[float] = None
    is_significant: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class TechnicalBacktester:
    """
    Backtests technical scoring signals against historical price data.

    Strategy:
    - Entry: When technical score meets threshold with direction != NEUTRAL
    - Exit: After holding period (default 1 day) or when direction flips
    - Track performance by multiple dimensions (direction, strength, regime)
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent / "scanner.db"
        self.db_path = str(db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables for technical backtest results."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Backtest runs
        c.execute("""
            CREATE TABLE IF NOT EXISTS technical_backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                symbols TEXT NOT NULL,  -- JSON array
                timeframe TEXT NOT NULL,
                min_score_threshold INTEGER,
                min_confidence REAL,
                holding_period_minutes INTEGER,
                total_trades INTEGER,
                win_rate REAL,
                profit_factor REAL,
                metrics_json TEXT,  -- Full BacktestMetrics
                config_json TEXT
            )
        """)

        # Individual trades
        c.execute("""
            CREATE TABLE IF NOT EXISTS technical_backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES technical_backtest_runs(id),
                symbol TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT NOT NULL,
                direction TEXT NOT NULL,
                direction_strength TEXT NOT NULL,
                score INTEGER NOT NULL,
                confidence REAL NOT NULL,
                timeframe TEXT NOT NULL,
                regime TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                pnl_pct REAL NOT NULL,
                outcome TEXT NOT NULL,
                adx_at_entry REAL,
                directional_edge REAL,
                agreement_pct REAL,
                indicators_json TEXT
            )
        """)

        # Indicator performance tracking
        c.execute("""
            CREATE TABLE IF NOT EXISTS technical_indicator_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL REFERENCES technical_backtest_runs(id),
                indicator_name TEXT NOT NULL,
                total_contribution INTEGER,  -- How many trades this indicator contributed to
                winning_contribution INTEGER,
                losing_contribution INTEGER,
                avg_score_on_wins REAL,
                avg_score_on_losses REAL,
                win_rate REAL,
                UNIQUE(run_id, indicator_name)
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_tech_bt_runs_date ON technical_backtest_runs(start_date, end_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tech_bt_trades_run ON technical_backtest_trades(run_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tech_bt_trades_symbol ON technical_backtest_trades(symbol, entry_time)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_tech_bt_trades_outcome ON technical_backtest_trades(outcome, direction)")

        conn.commit()
        conn.close()

    def run_backtest(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        timeframe: str = "15m",
        min_score_threshold: int = 70,
        min_confidence: float = 0.65,
        holding_period_minutes: int = 1440,  # 1 day default
        exit_on_direction_flip: bool = True
    ) -> Tuple[BacktestMetrics, List[BacktestTrade]]:
        """
        Run backtest on historical data.

        Args:
            symbols: List of symbols to test
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            timeframe: Bar interval (5m/15m/30m)
            min_score_threshold: Minimum score to enter trade
            min_confidence: Minimum confidence to enter trade
            holding_period_minutes: How long to hold position
            exit_on_direction_flip: Exit early if direction changes

        Returns:
            (metrics, trades) tuple
        """
        if not DEPS_AVAILABLE:
            log.error("Cannot run backtest - dependencies not available")
            return None, []

        from backend.scoring_technical import compute_technical_score

        all_trades = []

        for symbol in symbols:
            log.info(f"Backtesting {symbol} from {start_date} to {end_date}")

            # Download historical data
            ticker_map = self._get_ticker_map()
            yf_symbol = ticker_map.get(symbol, f"{symbol}.NS")

            try:
                df = yf.download(
                    yf_symbol,
                    start=start_date,
                    end=end_date,
                    interval=timeframe,
                    progress=False
                )

                if df.empty or len(df) < 60:
                    log.warning(f"Insufficient data for {symbol}")
                    continue

            except Exception as e:
                log.error(f"Error downloading {symbol}: {e}")
                continue

            # Prepare price arrays
            closes = df['Close'].values.tolist()
            highs = df['High'].values.tolist()
            lows = df['Low'].values.tolist()
            volumes = df['Volume'].values.tolist()
            timestamps = df.index.tolist()

            # Simulate trading
            position = None  # Current open position
            i = 60  # Start after warmup

            while i < len(closes):
                # Check if we should exit existing position
                if position is not None:
                    time_in_position = (timestamps[i] - position['entry_time']).total_seconds() / 60

                    should_exit = False
                    exit_reason = None

                    # Time-based exit
                    if time_in_position >= holding_period_minutes:
                        should_exit = True
                        exit_reason = "holding_period"

                    # Direction flip exit
                    if exit_on_direction_flip and i >= position['entry_idx'] + 3:
                        # Recompute score at current bar
                        current_result = compute_technical_score(
                            closes[:i+1],
                            highs[:i+1],
                            lows[:i+1],
                            volumes[:i+1]
                        )

                        if current_result.direction != position['direction'] and current_result.direction != "NEUTRAL":
                            should_exit = True
                            exit_reason = "direction_flip"

                    if should_exit:
                        # Close position
                        exit_price = closes[i]
                        pnl_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100

                        # Adjust PnL sign based on direction
                        if position['direction'] == "BEARISH":
                            pnl_pct = -pnl_pct

                        outcome = "WIN" if pnl_pct > 0 else "LOSS"

                        trade = BacktestTrade(
                            symbol=symbol,
                            entry_time=position['entry_time'],
                            exit_time=timestamps[i],
                            direction=position['direction'],
                            direction_strength=position['direction_strength'],
                            score=position['score'],
                            confidence=position['confidence'],
                            timeframe=timeframe,
                            regime=position['regime'],
                            entry_price=position['entry_price'],
                            exit_price=exit_price,
                            pnl_pct=round(pnl_pct, 2),
                            outcome=outcome,
                            indicators=position['indicators'],
                            adx_at_entry=position['adx_at_entry'],
                            directional_edge=position['directional_edge'],
                            agreement_pct=position['agreement_pct']
                        )

                        all_trades.append(trade)
                        position = None

                # Check if we should enter new position
                if position is None:
                    result = compute_technical_score(
                        closes[:i+1],
                        highs[:i+1],
                        lows[:i+1],
                        volumes[:i+1]
                    )

                    # Entry conditions
                    if (result.direction in ["BULLISH", "BEARISH"] and
                        result.score >= min_score_threshold and
                        result.confidence >= min_confidence):

                        # Determine regime
                        adx_val = result.indicators.get('adx', {}).get('adx', 0)
                        regime = "TRENDING" if adx_val >= 25 else "RANGING"

                        position = {
                            'entry_idx': i,
                            'entry_time': timestamps[i],
                            'entry_price': closes[i],
                            'direction': result.direction,
                            'direction_strength': result.direction_strength,
                            'score': result.score,
                            'confidence': result.confidence,
                            'regime': regime,
                            'adx_at_entry': adx_val,
                            'directional_edge': result.directional_edge,
                            'agreement_pct': result.agreement_pct,
                            'indicators': result.indicators
                        }

                i += 1

            # Close any remaining position at end
            if position is not None:
                exit_price = closes[-1]
                pnl_pct = ((exit_price - position['entry_price']) / position['entry_price']) * 100

                if position['direction'] == "BEARISH":
                    pnl_pct = -pnl_pct

                outcome = "WIN" if pnl_pct > 0 else "LOSS"

                trade = BacktestTrade(
                    symbol=symbol,
                    entry_time=position['entry_time'],
                    exit_time=timestamps[-1],
                    direction=position['direction'],
                    direction_strength=position['direction_strength'],
                    score=position['score'],
                    confidence=position['confidence'],
                    timeframe=timeframe,
                    regime=position['regime'],
                    entry_price=position['entry_price'],
                    exit_price=exit_price,
                    pnl_pct=round(pnl_pct, 2),
                    outcome=outcome,
                    indicators=position['indicators'],
                    adx_at_entry=position['adx_at_entry'],
                    directional_edge=position['directional_edge'],
                    agreement_pct=position['agreement_pct']
                )

                all_trades.append(trade)

        # Calculate metrics
        metrics = self._calculate_metrics(all_trades)

        # Save to database
        self._save_backtest_run(
            start_date, end_date, symbols, timeframe,
            min_score_threshold, min_confidence, holding_period_minutes,
            metrics, all_trades
        )

        return metrics, all_trades

    def _calculate_metrics(self, trades: List[BacktestTrade]) -> BacktestMetrics:
        """Calculate aggregate metrics from trades."""
        if not trades:
            return BacktestMetrics(
                total_trades=0, winning_trades=0, losing_trades=0, win_rate=0,
                total_profit_pct=0, total_loss_pct=0, avg_win_pct=0, avg_loss_pct=0,
                profit_factor=0, max_consecutive_wins=0, max_consecutive_losses=0,
                bullish_trades=0, bullish_wins=0, bullish_win_rate=0,
                bearish_trades=0, bearish_wins=0, bearish_win_rate=0,
                strong_trades=0, strong_wins=0, strong_win_rate=0,
                weak_trades=0, weak_wins=0, weak_win_rate=0,
                trending_trades=0, trending_wins=0, trending_win_rate=0,
                ranging_trades=0, ranging_wins=0, ranging_win_rate=0
            )

        total_trades = len(trades)
        wins = [t for t in trades if t.outcome == "WIN"]
        losses = [t for t in trades if t.outcome == "LOSS"]

        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        total_profit_pct = sum(t.pnl_pct for t in wins)
        total_loss_pct = abs(sum(t.pnl_pct for t in losses))
        avg_win_pct = total_profit_pct / winning_trades if winning_trades > 0 else 0
        avg_loss_pct = total_loss_pct / losing_trades if losing_trades > 0 else 0
        profit_factor = total_profit_pct / total_loss_pct if total_loss_pct > 0 else 0

        # Consecutive wins/losses
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0

        for t in trades:
            if t.outcome == "WIN":
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)

        # By direction
        bullish_trades = [t for t in trades if t.direction == "BULLISH"]
        bullish_wins = [t for t in bullish_trades if t.outcome == "WIN"]
        bullish_win_rate = len(bullish_wins) / len(bullish_trades) if bullish_trades else 0

        bearish_trades = [t for t in trades if t.direction == "BEARISH"]
        bearish_wins = [t for t in bearish_trades if t.outcome == "WIN"]
        bearish_win_rate = len(bearish_wins) / len(bearish_trades) if bearish_trades else 0

        # By strength
        strong_trades = [t for t in trades if t.direction_strength == "STRONG"]
        strong_wins = [t for t in strong_trades if t.outcome == "WIN"]
        strong_win_rate = len(strong_wins) / len(strong_trades) if strong_trades else 0

        weak_trades = [t for t in trades if t.direction_strength == "WEAK"]
        weak_wins = [t for t in weak_trades if t.outcome == "WIN"]
        weak_win_rate = len(weak_wins) / len(weak_trades) if weak_trades else 0

        # By regime
        trending_trades = [t for t in trades if t.regime == "TRENDING"]
        trending_wins = [t for t in trending_trades if t.outcome == "WIN"]
        trending_win_rate = len(trending_wins) / len(trending_trades) if trending_trades else 0

        ranging_trades = [t for t in trades if t.regime == "RANGING"]
        ranging_wins = [t for t in ranging_trades if t.outcome == "WIN"]
        ranging_win_rate = len(ranging_wins) / len(ranging_trades) if ranging_trades else 0

        # Statistical significance (Z-test)
        z_score = None
        p_value = None
        is_significant = False

        if total_trades >= 30:
            # Null hypothesis: win_rate = 0.5 (random)
            p0 = 0.5
            z_score = (win_rate - p0) / np.sqrt(p0 * (1 - p0) / total_trades)
            # Two-tailed p-value
            from scipy import stats
            p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))
            is_significant = p_value < 0.05

        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=round(win_rate, 4),
            total_profit_pct=round(total_profit_pct, 2),
            total_loss_pct=round(total_loss_pct, 2),
            avg_win_pct=round(avg_win_pct, 2),
            avg_loss_pct=round(avg_loss_pct, 2),
            profit_factor=round(profit_factor, 2),
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            bullish_trades=len(bullish_trades),
            bullish_wins=len(bullish_wins),
            bullish_win_rate=round(bullish_win_rate, 4),
            bearish_trades=len(bearish_trades),
            bearish_wins=len(bearish_wins),
            bearish_win_rate=round(bearish_win_rate, 4),
            strong_trades=len(strong_trades),
            strong_wins=len(strong_wins),
            strong_win_rate=round(strong_win_rate, 4),
            weak_trades=len(weak_trades),
            weak_wins=len(weak_wins),
            weak_win_rate=round(weak_win_rate, 4),
            trending_trades=len(trending_trades),
            trending_wins=len(trending_wins),
            trending_win_rate=round(trending_win_rate, 4),
            ranging_trades=len(ranging_trades),
            ranging_wins=len(ranging_wins),
            ranging_win_rate=round(ranging_win_rate, 4),
            z_score=round(z_score, 2) if z_score is not None else None,
            p_value=round(p_value, 4) if p_value is not None else None,
            is_significant=is_significant
        )

    def _save_backtest_run(
        self,
        start_date: str,
        end_date: str,
        symbols: List[str],
        timeframe: str,
        min_score_threshold: int,
        min_confidence: float,
        holding_period_minutes: int,
        metrics: BacktestMetrics,
        trades: List[BacktestTrade]
    ):
        """Save backtest run and trades to database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Save run
        c.execute("""
            INSERT INTO technical_backtest_runs (
                run_time, start_date, end_date, symbols, timeframe,
                min_score_threshold, min_confidence, holding_period_minutes,
                total_trades, win_rate, profit_factor, metrics_json, config_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            start_date,
            end_date,
            json.dumps(symbols),
            timeframe,
            min_score_threshold,
            min_confidence,
            holding_period_minutes,
            metrics.total_trades,
            metrics.win_rate,
            metrics.profit_factor,
            json.dumps(metrics.to_dict()),
            json.dumps({
                'min_score_threshold': min_score_threshold,
                'min_confidence': min_confidence,
                'holding_period_minutes': holding_period_minutes
            })
        ))

        run_id = c.lastrowid

        # Save trades
        for trade in trades:
            c.execute("""
                INSERT INTO technical_backtest_trades (
                    run_id, symbol, entry_time, exit_time, direction, direction_strength,
                    score, confidence, timeframe, regime, entry_price, exit_price,
                    pnl_pct, outcome, adx_at_entry, directional_edge, agreement_pct,
                    indicators_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                trade.symbol,
                trade.entry_time.isoformat(),
                trade.exit_time.isoformat(),
                trade.direction,
                trade.direction_strength,
                trade.score,
                trade.confidence,
                trade.timeframe,
                trade.regime,
                trade.entry_price,
                trade.exit_price,
                trade.pnl_pct,
                trade.outcome,
                trade.adx_at_entry,
                trade.directional_edge,
                trade.agreement_pct,
                json.dumps(trade.indicators)
            ))

        conn.commit()
        conn.close()

        log.info(f"Saved backtest run {run_id} with {len(trades)} trades")

    def get_backtest_runs(self, limit: int = 10) -> List[dict]:
        """Get recent backtest runs."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        rows = c.execute("""
            SELECT id, run_time, start_date, end_date, symbols, timeframe,
                   total_trades, win_rate, profit_factor, metrics_json
            FROM technical_backtest_runs
            ORDER BY run_time DESC
            LIMIT ?
        """, (limit,)).fetchall()

        conn.close()

        runs = []
        for row in rows:
            runs.append({
                'id': row[0],
                'run_time': row[1],
                'start_date': row[2],
                'end_date': row[3],
                'symbols': json.loads(row[4]),
                'timeframe': row[5],
                'total_trades': row[6],
                'win_rate': row[7],
                'profit_factor': row[8],
                'metrics': json.loads(row[9])
            })

        return runs

    def get_backtest_trades(self, run_id: int) -> List[dict]:
        """Get trades for a specific backtest run."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        rows = c.execute("""
            SELECT symbol, entry_time, exit_time, direction, direction_strength,
                   score, confidence, timeframe, regime, entry_price, exit_price,
                   pnl_pct, outcome, adx_at_entry, directional_edge, agreement_pct
            FROM technical_backtest_trades
            WHERE run_id = ?
            ORDER BY entry_time
        """, (run_id,)).fetchall()

        conn.close()

        trades = []
        for row in rows:
            trades.append({
                'symbol': row[0],
                'entry_time': row[1],
                'exit_time': row[2],
                'direction': row[3],
                'direction_strength': row[4],
                'score': row[5],
                'confidence': row[6],
                'timeframe': row[7],
                'regime': row[8],
                'entry_price': row[9],
                'exit_price': row[10],
                'pnl_pct': row[11],
                'outcome': row[12],
                'adx_at_entry': row[13],
                'directional_edge': row[14],
                'agreement_pct': row[15]
            })

        return trades

    def _get_ticker_map(self) -> Dict[str, str]:
        """Get NSE to yfinance ticker mapping."""
        try:
            from backend.constants import YFINANCE_TICKER_MAP
            return YFINANCE_TICKER_MAP
        except:
            return {}
