"""
backtest_pipeline.py — Minimum Viable Backtester

Replays pipeline execution across historical dates, matching outcomes from historical price data.
Allows testing of actual profitability for threshold changes (e.g. 40/100 confluence vs 3/5).
"""

import sys
import asyncio
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from statistics import mean

# Import simulate_trade from the existing backtest helper
from backtest import simulate_trade
from db import DB_PATH

def trading_days(start_date: str, end_date: str):
    """Yield all weekdays between start and end date (basic form of trading days)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    td = timedelta(days=1)
    
    current = start
    while current <= end:
        if current.weekday() < 5: # Monday is 0, Sunday is 6
            yield current.strftime("%Y-%m-%d")
        current += td

def run_pipeline_on_historical_data(date_str: str) -> list:
    """
    Mock/Stub: Load historical option chain data for this date and run `main.py -> run_pipeline`.
    For the minimum viable version, we pull previously logged scanner output for the given date.
    
    In a true EOD data replay, you would load EOD option chain data and call `fo_trades.run_pipeline` directly.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Fetch historical signals logged by the scanner over the day
    # Or ideally, from your EOD database
    query = """
        SELECT symbol, snapshot_time, signal, score, top_pick_type, top_pick_strike, top_pick_ltp, dte
        FROM market_snapshots
        WHERE snapshot_time LIKE ? 
          AND signal IN ('BULLISH', 'BEARISH')
          AND score >= 40
        ORDER BY snapshot_time ASC
    """
    rows = conn.execute(query, (f"{date_str}%",)).fetchall()
    conn.close()
    
    signals = []
    for r in rows:
        if r["top_pick_type"] and r["top_pick_strike"]:
            signals.append({
                'symbol': r['symbol'],
                'signal': r['signal'],
                'confluence_score': r['score'],
                'strategy': f"LONG_{r['top_pick_type']}",
                'suggested_entry': r['top_pick_strike'], # We use strike as the identifier for the option finding
                'opt_type': r['top_pick_type'],
                'dte': r['dte'] if r['dte'] else 5
            })
    return signals

async def backtest_pipeline(start_date: str, end_date: str):
    results = []
    print(f"Starting backtest from {start_date} to {end_date}...")
    
    for date in trading_days(start_date, end_date):
        print(f"\\n--- Processing date: {date} ---")
        # Replay pipeline on historical data
        signals = run_pipeline_on_historical_data(date)
        print(f"Found {len(signals)} passing signals.")
        
        for signal in signals:
            # Check what actually happened using the existing IndStocks historical helper
            outcome = await simulate_trade(
                symbol   = signal['symbol'],
                opt_type = signal['opt_type'],
                strike   = signal['suggested_entry'],
                entry_date= date,
                signal_score= signal['confluence_score'],
                take_profit_pct=40.0,
                stop_loss_pct=-20.0,
                hold_days=signal['dte']
            )
            
            if outcome:
                results.append({
                    'date':        date,
                    'symbol':      signal['symbol'],
                    'strategy':    signal['strategy'],
                    'confluence':  signal['confluence_score'],
                    'outcome_pct': outcome['pnl_pct'],
                    'correct':     1 if outcome['pnl_pct'] > 0 else 0
                })

    if not results:
        print("\\nNo results. Try a broader date range or verify historical DB.")
        return 0, 0

    # Key metrics
    hit_rate    = sum(r['correct'] for r in results) / len(results)
    avg_return  = mean(r['outcome_pct'] for r in results)
    
    print("\\n==================================")
    print("      BACKTEST PIPELINE RESULTS     ")
    print("==================================")
    print(f"Total Evaluated Trades : {len(results)}")
    print(f"Overall Hit Rate       : {hit_rate*100:.1f}%")
    print(f"Average Profit/Loss    : {avg_return:.2f}%")
    print("==================================")
    
    return hit_rate, avg_return

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python backtest_pipeline.py YYYY-MM-DD YYYY-MM-DD")
        sys.exit(1)
        
    start_d, end_d = sys.argv[1], sys.argv[2]
    asyncio.run(backtest_pipeline(start_d, end_d))
