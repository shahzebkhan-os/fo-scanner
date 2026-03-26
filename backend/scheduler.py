"""
scheduler.py — Background Task Scheduler v4.1
Tasks:
  1. OI Snapshot      — every 15 min during market hours
  2. IV History Save  — once daily at 15:35
  3. Pre-Market Report — every weekday at 9:00 AM IST via Telegram
  4. Bulk Deals Fetch — every weekday at 16:00 IST
  5. DB Cleanup       — every Sunday midnight
  7. Accuracy Sampler — every 10 min + auto CSV export
  8. Accuracy Price Updater — every 5 min
"""

import asyncio
import logging
import os
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
import yfinance as yf
import pandas as pd

from . import db
from . import signals_legacy as Signals

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

# These are injected at startup from main.py
_fetch_nse_chain_fn   = None
_send_telegram_fn     = None
_send_telegram_document_fn = None
_is_market_open_fn    = None
_scan_all_symbols_fn  = None   # should return list of scan result dicts
_scan_symbol_fn       = None   # should return stats for one symbol
_ml_train_fn          = None
_all_symbols_list     = []

def init_scheduler(
    fetch_chain_fn,
    send_telegram_fn,
    is_market_open_fn,
    scan_fn,
    train_fn,
    all_symbols: list,
    scan_symbol_fn = None,
    send_telegram_doc_fn = None,
):
    global _fetch_nse_chain_fn, _send_telegram_fn, _is_market_open_fn
    global _scan_all_symbols_fn, _ml_train_fn, _all_symbols_list, _scan_symbol_fn
    global _send_telegram_document_fn
    _fetch_nse_chain_fn  = fetch_chain_fn
    _send_telegram_fn    = send_telegram_fn
    _send_telegram_document_fn = send_telegram_doc_fn
    _is_market_open_fn   = is_market_open_fn
    _scan_all_symbols_fn = scan_fn
    _ml_train_fn         = train_fn
    _all_symbols_list    = all_symbols
    _scan_symbol_fn      = scan_symbol_fn
    log.info("Scheduler initialised.")


# ══════════════════════════════════════════════════════════════════════════════
# Task 1: OI Snapshot (every 15 min)
# ══════════════════════════════════════════════════════════════════════════════

async def oi_snapshot_loop():
    """Takes a full chain snapshot for all symbols every 15 minutes."""
    log.info("OI Snapshot loop started.")
    while True:
        try:
            if _is_market_open_fn and _is_market_open_fn():
                log.info("Taking OI snapshot...")
                sem = asyncio.Semaphore(4)

                async def snap(symbol):
                    async with sem:
                        try:
                            chain = await _fetch_nse_chain_fn(symbol)
                            records  = chain.get("records", {}).get("data", [])
                            expiries = chain.get("records", {}).get("expiryDates", [])
                            expiry   = expiries[0] if expiries else ""
                            if records:
                                db.save_oi_snapshot(symbol, expiry, records)
                        except Exception as e:
                            log.warning(f"OI snapshot failed for {symbol}: {e}")

                await asyncio.gather(*[snap(s) for s in _all_symbols_list])
                log.info(f"OI snapshot done ({len(_all_symbols_list)} symbols)")

            await asyncio.sleep(900)   # 15 minutes

        except Exception as e:
            log.error(f"OI snapshot loop error: {e}")
            await asyncio.sleep(900)


# ══════════════════════════════════════════════════════════════════════════════
# Task 2: IV History (once daily at market close)
# ══════════════════════════════════════════════════════════════════════════════

async def iv_history_loop():
    """Saves end-of-day ATM IV for each symbol once daily."""
    log.info("IV history loop started.")
    _saved_today = None

    while True:
        try:
            now   = datetime.now(IST)
            today = now.date()

            # Run at 15:35, once per day
            if now.time() >= dtime(15, 35) and _saved_today != today:
                log.info("Saving end-of-day IV history...")
                sem = asyncio.Semaphore(4)

                async def save_iv(symbol):
                    async with sem:
                        try:
                            chain  = await _fetch_nse_chain_fn(symbol)
                            recs   = chain.get("records", {}).get("data", [])
                            spot   = chain.get("records", {}).get("underlyingValue", 0)
                            if not recs or not spot:
                                return

                            from .analytics import nearest_atm, get_strike_interval
                            atm    = nearest_atm(spot, symbol)
                            band   = get_strike_interval(symbol) * 3
                            iv_sum = count = 0

                            for row in recs:
                                if abs(row.get("strikePrice", 0) - atm) <= band:
                                    for side in ["CE", "PE"]:
                                        iv = (row.get(side) or {}).get("impliedVolatility", 0)
                                        if iv and iv > 0:
                                            iv_sum += iv
                                            count  += 1

                            if count > 0:
                                db.save_daily_iv(symbol, iv_sum / count)

                        except Exception as e:
                            log.warning(f"IV save failed for {symbol}: {e}")

                await asyncio.gather(*[save_iv(s) for s in _all_symbols_list])
                _saved_today = today
                log.info("IV history saved.")

            await asyncio.sleep(300)   # check every 5 min

        except Exception as e:
            log.error(f"IV history loop error: {e}")
            await asyncio.sleep(300)


# ══════════════════════════════════════════════════════════════════════════════
# Task 3: Pre-Market Report (9:00 AM weekdays)
# ══════════════════════════════════════════════════════════════════════════════




# ══════════════════════════════════════════════════════════════════════════════
# Task 4: Bulk Deals Fetch (16:00 daily)
# ══════════════════════════════════════════════════════════════════════════════

async def bulk_deals_loop():
    """Fetches NSE bulk/block deals once daily after market close."""
    log.info("Bulk deals loop started.")
    _fetched_today = None

    while True:
        try:
            now   = datetime.now(IST)
            today = now.date()

            if now.weekday() < 5 and now.time() >= dtime(16, 0) and _fetched_today != today:
                log.info("Fetching bulk/block deals...")
                deals = await Signals.fetch_bulk_deals()
                _fetched_today = today
                log.info(f"Bulk deals: {len(deals)} records saved.")

            await asyncio.sleep(1800)   # check every 30 min

        except Exception as e:
            log.error(f"Bulk deals loop error: {e}")
            await asyncio.sleep(1800)


# ══════════════════════════════════════════════════════════════════════════════
# Task 5: DB Cleanup (weekly)
# ══════════════════════════════════════════════════════════════════════════════

async def db_cleanup_loop():
    """Prunes old OI history and notifications once a week."""
    log.info("DB cleanup loop started.")
    while True:
        try:
            now = datetime.now(IST)
            # Run on Sunday between 00:00–01:00
            if now.weekday() == 6 and now.time() < dtime(1, 0):
                log.info("Running DB cleanup...")
                import sqlite3, os
                db_path = os.path.join(os.path.dirname(__file__), "scanner.db")
                with sqlite3.connect(db_path) as conn:
                    # Keep 30 days of OI history
                    conn.execute("DELETE FROM oi_history WHERE snap_date < date('now', '-30 days')")
                    # Keep 365 days of IV history
                    conn.execute("DELETE FROM iv_history WHERE snap_date < date('now', '-365 days')")
                    conn.execute("VACUUM")

                db.cleanup_old_notifications(days=14)
                log.info("DB cleanup done.")

            await asyncio.sleep(3600)   # check every hour

        except Exception as e:
            log.error(f"DB cleanup error: {e}")
            await asyncio.sleep(3600)


# ══════════════════════════════════════════════════════════════════════════════
# Task 6: Auto TP/SL Monitor (every 5 min during market hours)
# ══════════════════════════════════════════════════════════════════════════════

# Configurable TP/SL percentages
AUTO_TP_PCT =  25.0   # Take profit at +25%
AUTO_SL_PCT = -15.0   # Stop loss at -15%

async def auto_tpsl_loop():
    """
    Monitors open paper trades and auto-exits based on TP/SL rules.
    Runs every 5 minutes during market hours.
    """
    log.info("Auto TP/SL monitor loop started.")

    while True:
        try:
            if _is_market_open_fn and _is_market_open_fn():
                open_trades = db.get_open_trades()
                if open_trades:
                    # Group trades by symbol to batch LTP fetches
                    symbols = list({t["symbol"] for t in open_trades})

                    # Fetch current LTPs for trade symbols
                    ltp_map = {}
                    if _fetch_nse_chain_fn:
                        sem = asyncio.Semaphore(3)
                        async def fetch_ltp(sym):
                            async with sem:
                                try:
                                    chain = await _fetch_nse_chain_fn(sym)
                                    records = chain.get("records", {}).get("data", [])
                                    spot = chain.get("records", {}).get("underlyingValue", 0)
                                    ltp_map[sym] = {"spot": spot, "records": records}
                                except Exception as e:
                                    log.warning(f"TP/SL LTP fetch failed for {sym}: {e}")

                        await asyncio.gather(*[fetch_ltp(s) for s in symbols])

                    now = datetime.now(IST)
                    eod_squareoff = now.time() >= dtime(15, 15)

                    for trade in open_trades:
                        sym = trade["symbol"]
                        if sym not in ltp_map:
                            continue

                        chain_data = ltp_map[sym]
                        # Find current LTP for this specific strike/type
                        current_ltp = None
                        for rec in chain_data.get("records", []):
                            if rec.get("strikePrice") == trade["strike"]:
                                side_data = rec.get(trade["type"], {}) or {}
                                ltp = side_data.get("lastPrice", 0)
                                if ltp and ltp > 0:
                                    current_ltp = ltp
                                    break

                        if current_ltp is None:
                            continue

                        entry = trade["entry_price"]
                        if entry <= 0:
                            continue

                        pnl_pct = (current_ltp - entry) / entry * 100

                        # Update current price in DB
                        db.update_trade(trade["id"], current_ltp)

                        # TP/SL logic
                        if pnl_pct >= AUTO_TP_PCT:
                            reason = f"Auto TP +{AUTO_TP_PCT:.0f}% (P&L: {pnl_pct:+.1f}%)"
                            db.update_trade(trade["id"], current_ltp, exit_flag=True, reason=reason)
                            log.info(f"  ✅ TP hit: {sym} {trade['type']} {trade['strike']} @ ₹{current_ltp} ({pnl_pct:+.1f}%)")

                        elif pnl_pct <= AUTO_SL_PCT:
                            reason = f"Auto SL {AUTO_SL_PCT:.0f}% (P&L: {pnl_pct:+.1f}%)"
                            db.update_trade(trade["id"], current_ltp, exit_flag=True, reason=reason)
                            log.info(f"  ❌ SL hit: {sym} {trade['type']} {trade['strike']} @ ₹{current_ltp} ({pnl_pct:+.1f}%)")

                        elif eod_squareoff:
                            reason = f"EOD Square-off (P&L: {pnl_pct:+.1f}%)"
                            db.update_trade(trade["id"], current_ltp, exit_flag=True, reason=reason)
                            log.info(f"  🔲 EOD exit: {sym} {trade['type']} {trade['strike']} @ ₹{current_ltp} ({pnl_pct:+.1f}%)")

                    log.info(f"TP/SL check done — {len(open_trades)} open trades monitored")

            await asyncio.sleep(300)   # Check every 5 minutes

        except Exception as e:
            log.error(f"Auto TP/SL loop error: {e}")
            await asyncio.sleep(300)


# ══════════════════════════════════════════════════════════════════════════════
# Task 7: Trade Tracker - Sampler (every 15 min)
# ══════════════════════════════════════════════════════════════════════════════

async def accuracy_sampler_loop():
    """Takes a snapshot of directional suggested trades every 15 minutes."""
    log.info("Trade tracker sampler loop started (15 min interval).")
    from .constants import LOT_SIZES
    while True:
        try:
            if _is_market_open_fn and _is_market_open_fn():
                if _scan_all_symbols_fn:
                    log.info("Trade Tracker: Sampling suggested trades...")
                    results = await _scan_all_symbols_fn()
                    # Only track directional signals with meaningful scores
                    suggested_trades = [
                        r for r in results
                        if r.get("signal") in ("BULLISH", "BEARISH")
                        and r.get("score", 0) >= 60
                        and len(r.get("top_picks", [])) > 0
                    ]

                    if suggested_trades:
                        # Build trade list first, create snapshot only if we have trades
                        pending = []
                        for r in suggested_trades:
                            sig = r["signal"]
                            picks = r.get("top_picks", [])
                            ls = LOT_SIZES.get(r["symbol"], 1)
                            # Only save picks matching signal direction
                            for p in picks:
                                if (sig == "BULLISH" and p["type"] == "CE") or (sig == "BEARISH" and p["type"] == "PE"):
                                    pending.append((r, p, ls))

                        if pending:
                            sid = db.create_accuracy_snapshot()
                            count = 0
                            for r, p, ls in pending:
                                tid = db.add_accuracy_trade(
                                    sid, r["symbol"], p["type"], p["strike"],
                                    p["ltp"], r["score"], r["ltp"], 
                                    lot_size=ls,
                                    ml_prob=r.get("ml_bullish_probability"),
                                    signal=r.get("signal", "NEUTRAL"),
                                    iv_rank=r.get("iv_rank"),
                                    regime=r.get("regime"),
                                    max_pain=r.get("max_pain"),
                                    days_to_expiry=r.get("days_to_expiry"),
                                    pcr=r.get("pcr"),
                                    iv=r.get("iv"),
                                    vol_spike=r.get("vol_spike"),
                                    ml_score=r.get("ml_score")
                                )
                                if tid:
                                    db.update_accuracy_trade_price(tid, p["ltp"])
                                count += 1
                            log.info(f"Trade Tracker: Created snapshot {sid} with {count} directional trades.")
                        else:
                            log.info("Trade Tracker: No directional trades to save this cycle.")

            await asyncio.sleep(900)  # 15 minutes
        except Exception as e:
            log.error(f"Trade tracker sampler loop error: {e}")
            await asyncio.sleep(600)

# ══════════════════════════════════════════════════════════════════════════════
# Task 8: Trade Tracker - Price Updater (every 5 min)
# ══════════════════════════════════════════════════════════════════════════════

async def accuracy_price_updater_loop():
    """Updates current prices for all active trades every 5 minutes."""
    log.info("Trade tracker price updater loop started (5 min interval).")
    while True:
        try:
            if _is_market_open_fn and _is_market_open_fn():
                active_trades = db.get_active_accuracy_trades()
                if active_trades:
                    symbols = list({t["symbol"] for t in active_trades})
                    log.info(f"Trade Tracker: Updating prices for {len(symbols)} symbols...")

                    sem = asyncio.Semaphore(3)
                    async def update_sym(sym):
                        async with sem:
                            try:
                                chain = await _fetch_nse_chain_fn(sym)
                                data = chain.get("records", {}).get("data", [])
                                # Map strike+type to LTP
                                prices = {}
                                for row in data:
                                    strike = row.get("strikePrice")
                                    for side in ["CE", "PE"]:
                                        ltp = row.get(side, {}).get("lastPrice", 0)
                                        if ltp: prices[(strike, side)] = ltp

                                # Update all trades for this symbol
                                for t in active_trades:
                                    if t["symbol"] == sym:
                                        key = (t["strike"], t["type"])
                                        if key in prices:
                                            db.update_accuracy_trade_price(t["id"], prices[key])
                            except Exception as e:
                                log.warning(f"Trade tracker price update failed for {sym}: {e}")

                    await asyncio.gather(*[update_sym(s) for s in symbols])
                    log.info("Trade Tracker: Price updates completed.")

            await asyncio.sleep(300)  # 5 minutes
        except Exception as e:
            log.error(f"Trade tracker price updater loop error: {e}")
            await asyncio.sleep(300)


# ══════════════════════════════════════════════════════════════════════════════
# Start all tasks
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# Task 8.5: Technical Score Momentum Snapshot (every 15 min)
# ══════════════════════════════════════════════════════════════════════════════

async def technical_snapshot_loop():
    """Fetches 5m yfinance data for all symbols, saves scores to DB, and alerts Telegram."""
    log.info("Technical snapshot loop started (5 min interval).")
    while True:
        try:
            market_open = _is_market_open_fn() if _is_market_open_fn else True
            log.info(f"Technical snapshot check: Market Open = {market_open}")
            if market_open:
                log.info("Taking technical score snapshot... (5-min interval)")
                
                def _fetch_and_score():
                    from .scoring_technical import compute_technical_score
                    from .constants import YFINANCE_TICKER_MAP
                    
                    symbols = _all_symbols_list
                    tickers = [YFINANCE_TICKER_MAP.get(s, f"{s}.NS") for s in symbols]
                    log.info(f"📊 Starting Technical Snapshot fetch for {len(tickers)} symbols...")
                    
                    df = yf.download(tickers, period="5d", interval="5m", progress=False, threads=True)
                    log.info(f"yf.download returned df of shape: {df.shape if df is not None else 'None'}")
                    if df is None or df.empty or len(df.columns) == 0:
                        log.warning("yf.download returned empty or invalid dataframe.")
                        return []
                        
                    if not isinstance(df.index, pd.DatetimeIndex):
                         df.index = pd.to_datetime(df.index)
                    
                    records = []
                    
                    def _extract(data_df, tick):
                        try:
                            # Robust extraction for MultiIndex [Metric, Ticker] or [Ticker, Metric]
                            if isinstance(data_df.columns, pd.MultiIndex):
                                # Level 0 is Metric (Close, High, etc) and Level 1 is Ticker
                                if tick in data_df.columns.get_level_values(1):
                                    c = data_df["Close"][tick].dropna().tolist()
                                    h = data_df["High"][tick].dropna().tolist()
                                    l = data_df["Low"][tick].dropna().tolist()
                                    v = data_df["Volume"][tick].dropna().tolist()
                                # Level 0 is Ticker and Level 1 is Metric
                                elif tick in data_df.columns.get_level_values(0):
                                    c = data_df[tick]["Close"].dropna().tolist()
                                    h = data_df[tick]["High"].dropna().tolist()
                                    l = data_df[tick]["Low"].dropna().tolist()
                                    v = data_df[tick]["Volume"].dropna().tolist()
                                else:
                                    return [], [], [], []
                            else:
                                c = data_df["Close"].dropna().tolist()
                                h = data_df["High"].dropna().tolist()
                                l = data_df["Low"].dropna().tolist()
                                v = data_df["Volume"].dropna().tolist()
                            
                            def _flatten(lst):
                                if lst and hasattr(lst[0], "__len__") and not isinstance(lst[0], str):
                                    return [x[0] if len(x)>0 else x for x in lst]
                                return lst
                                
                            return _flatten(c), _flatten(h), _flatten(l), _flatten(v)
                        except Exception:
                            return [], [], [], []
                            
                    # Resample per ticker for accuracy
                    for sym, tick in zip(symbols, tickers):
                        try:
                            c5, h5, l5, v5 = _extract(df, tick)
                            if len(c5) < 10: continue
                            
                            # Extract the corresponding timestamps for this ticker's data
                            # (In case some tickers have missing bars, though yf.download aligns them)
                            ticker_index = df.index[-len(c5):]
                            temp_df = pd.DataFrame({'Close': c5, 'High': h5, 'Low': l5, 'Volume': v5}, index=ticker_index)
                            
                            df_15m = temp_df.resample('15min').agg({'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
                            df_30m = temp_df.resample('30min').agg({'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

                            c15, h15, l15, v15 = df_15m['Close'].tolist(), df_15m['High'].tolist(), df_15m['Low'].tolist(), df_15m['Volume'].tolist()
                            if len(c15) > 10:
                                res15 = compute_technical_score(c15, h15, l15, v15)
                                res15_dict = res15.to_dict()
                                records.append({
                                    "symbol": sym,
                                    "timeframe": "15m",
                                    "score": res15_dict.get("score", 0),
                                    "direction": res15_dict.get("direction", "NEUTRAL"),
                                    "confidence": res15_dict.get("confidence", 0),
                                    "direction_strength": res15_dict.get("direction_strength", "UNKNOWN"),
                                    "adx": res15_dict.get("indicators", {}).get("adx", {}).get("adx", 0)
                                })

                            c30, h30, l30, v30 = df_30m['Close'].tolist(), df_30m['High'].tolist(), df_30m['Low'].tolist(), df_30m['Volume'].tolist()
                            if len(c30) > 10:
                                res30 = compute_technical_score(c30, h30, l30, v30)
                                res30_dict = res30.to_dict()
                                records.append({
                                    "symbol": sym,
                                    "timeframe": "30m",
                                    "score": res30_dict.get("score", 0),
                                    "direction": res30_dict.get("direction", "NEUTRAL"),
                                    "confidence": res30_dict.get("confidence", 0),
                                    "direction_strength": res30_dict.get("direction_strength", "UNKNOWN"),
                                    "adx": res30_dict.get("indicators", {}).get("adx", {}).get("adx", 0)
                                })
                        except Exception as e:
                            log.debug(f"Technical score failed for {sym}: {e}")
                    return records

                records = await asyncio.to_thread(_fetch_and_score)
                if records:
                    db.save_technical_score_snapshots(records)
                    log.info(f"Saved {len(records)} tech snapshots to database.")
                    
                    # ── Technical Auto-Trading Trigger (Score >= 70) ──
                    rel = [r for r in records if r["timeframe"] == "15m"]
                    # Previous periodic highlight alerts are intentionally removed.
                    # Notifications are now sent only for good-entry executions.

                    # Process all 15m records, not just the top 5
                    # Enhanced with ADX and direction strength filters for higher accuracy
                    tech_70_plus = [r for r in rel if r["score"] >= 70]
                    if tech_70_plus:
                        log.info(f"Checking auto-trade for {len(tech_70_plus)} symbols with score >= 70")
                        for r in tech_70_plus:
                            try:
                                # Apply quality filters for auto-trading:
                                # 1. ADX >= 25 (trending market only)
                                # 2. Direction strength must be STRONG (not WEAK)
                                adx_val = r.get("adx", 0)
                                direction_strength = r.get("direction_strength", "UNKNOWN")

                                if adx_val < 25:
                                    log.info(f"Skipping {r['symbol']} auto-trade: ADX {adx_val:.1f} < 25 (ranging market)")
                                    continue

                                if direction_strength != "STRONG":
                                    log.info(f"Skipping {r['symbol']} auto-trade: Direction strength is {direction_strength} (need STRONG)")
                                    continue

                                # Always get fresh full stats for trade execution
                                if _scan_symbol_fn:
                                    full = await _scan_symbol_fn(r["symbol"])
                                    if full and "top_picks" in full:
                                        # Find pick matching direction
                                        target_type = "CE" if r["direction"] == "BULLISH" else "PE"
                                        picks = [p for p in full["top_picks"] if p["type"] == target_type]
                                        if picks:
                                            p = picks[0]
                                            created = db.add_trade(
                                                symbol=r["symbol"],
                                                opt_type=p["type"],
                                                strike=p["strike"],
                                                entry_price=p["ltp"],
                                                reason=f"Auto: Technical Score {r['score']}% ({r['direction']}/{direction_strength}, ADX {adx_val:.0f})",
                                                entry_score=r["score"]
                                            )
                                            if created:
                                                log.info(f"✓ Auto-trade executed: {r['symbol']} {target_type} (Score {r['score']}%, {direction_strength}, ADX {adx_val:.0f})")
                                                if _send_telegram_fn:
                                                    uid = f"technical-entry-{r['symbol']}-{p['type']}-{p['strike']}-{r['score']}-{datetime.now(IST).date().isoformat()}"
                                                    if not db.is_notified(uid):
                                                        db.mark_notified(uid)
                                                        await _send_telegram_fn(
                                                            "\n".join([
                                                                f"🎯 *Good Entry Found*: *{r['symbol']}*",
                                                                f"Direction: *{r['direction']}* ({direction_strength})",
                                                                f"Technical Score: *{r['score']}* | Confidence: *{round(r.get('confidence', 0) * 100, 1)}%*",
                                                                f"Best Pick: *{p['strike']} {p['type']}* @ ₹{round(p['ltp'], 2)}",
                                                                f"ADX: *{round(adx_val, 1)}*",
                                                            ])
                                                        )
                            except Exception as te:
                                log.error(f"Auto-trade trigger failed for {r['symbol']}: {te}")

                else:
                    log.warning("No technical score records generated.")
                    
            await asyncio.sleep(300)  # 5 min
            
        except Exception as e:
            log.error(f"Technical snapshot loop error: {e}")
            await asyncio.sleep(300)


# ══════════════════════════════════════════════════════════════════════════════
# Task 9: ML Model Retraining (daily at 15:45)
# ══════════════════════════════════════════════════════════════════════════════

async def ml_retrain_loop():
    """Retrains the LightGBM + Neural Network models once daily after market close."""
    log.info("ML retrain loop started.")
    _trained_today = None

    while True:
        try:
            now   = datetime.now(IST)
            today = now.date()

            # Run at 15:45, once per day
            if now.time() >= dtime(15, 45) and _trained_today != today:
                log.info("Starting daily ML model retraining (LightGBM + Neural Network)...")
                if _ml_train_fn:
                    res = await asyncio.to_thread(_ml_train_fn)
                    if "error" in res:
                        log.error(f"ML retraining failed: {res['error']}")
                    else:
                        log.info(f"ML retraining done: LGB Loss {res.get('cv_log_loss_mean')}, Rows {res.get('training_rows')}")
                        nn = res.get("nn", {})
                        if nn.get("nn_cv_log_loss_mean"):
                            log.info(f"NN retraining done: Loss {nn['nn_cv_log_loss_mean']}, Sequences {nn.get('nn_training_sequences')}")
                        elif nn.get("error"):
                            log.warning(f"NN retraining skipped: {nn['error']}")
                        _trained_today = today

            await asyncio.sleep(600)   # check every 10 min

        except Exception as e:
            log.error(f"ML retrain loop error: {e}")
            await asyncio.sleep(600)


async def auto_trade_loop():
    """
    Background loop that triggers a full scan every 15 minutes.
    Since _internal_scan is now wired to _handle_auto_trade,
    this drives the background auto-paper-trading.
    """
    log.info("Auto Trade background loop started (15 min interval).")
    while True:
        try:
            if _is_market_open_fn and _is_market_open_fn():
                if _scan_all_symbols_fn:
                    log.info("Auto Trade: Running background automated scan...")
                    # This calls main._internal_scan() which now triggers trades
                    await _scan_all_symbols_fn()
                    log.info("Auto Trade: Background scan cycle completed.")
            
            await asyncio.sleep(900)  # 15 minutes
        except Exception as e:
            log.error(f"Auto trade loop error: {e}")
            await asyncio.sleep(900)


async def technical_report_loop():
    """Generates a CSV report for all popular symbols every 15 minutes."""
    log.info("Technical Report CSV loop started.")
    import io
    import csv
    from .constants import POPULAR_SYMBOLS

    while True:
        try:
            if _is_market_open_fn and _is_market_open_fn():
                if _scan_symbol_fn and _send_telegram_document_fn:
                    log.info("Generating Technical Score CSV Report...")
                    
                    rows = []
                    for sym in POPULAR_SYMBOLS:
                        try:
                            stats = await _scan_symbol_fn(sym)
                            if stats:
                                ts = stats.get("technical_score", {})
                                picks = stats.get("top_picks", [])
                                best_pick = picks[0] if picks else {}
                                
                                rows.append([
                                    sym,
                                    ts.get("score", ""),
                                    ts.get("direction", ""),
                                    f"{ts.get('confidence', 0)*100:.1f}%",
                                    best_pick.get("strike", ""),
                                    best_pick.get("type", ""),
                                    best_pick.get("ltp", "")
                                ])
                        except Exception as e:
                            log.warning(f"Failed to fetch report stats for {sym}: {e}")
                    
                    if rows:
                        headers = ["Symbol", "Score", "Direction", "Confidence", "Best Strike", "Type", "LTP"]
                        buffer = io.StringIO()
                        writer = csv.writer(buffer)
                        writer.writerow(headers)
                        writer.writerows(rows)
                        
                        csv_content = buffer.getvalue()
                        filename = f"technical_report_{datetime.now(IST).strftime('%H%M')}.csv"
                        caption = "📊 *Technical Score Report (All Popular Symbols)*\nFull coverage attached."
                        
                        await _send_telegram_document_fn(filename, csv_content, caption)
                        log.info("Technical Report CSV dispatched.")

            await asyncio.sleep(900)  # 15 minutes
        except Exception as e:
            log.error(f"Technical report loop error: {e}")
            await asyncio.sleep(900)


async def start_all():
    """Launch all background tasks. Call from FastAPI lifespan."""
    # ── Disabled: Scanner / Market Eval / Suggestions / F&O Trade tabs off ──
    # asyncio.create_task(oi_snapshot_loop())       # Scanner/Market Eval
    # asyncio.create_task(iv_history_loop())         # Scanner/Market Eval

    # asyncio.create_task(bulk_deals_loop())         # Scanner
    # asyncio.create_task(auto_trade_loop())         # F&O Trade
    asyncio.create_task(db_cleanup_loop())
    asyncio.create_task(technical_snapshot_loop())
    asyncio.create_task(ml_retrain_loop())
    log.info("Scheduler started (Technical Snapshot + Cleanup + ML Retrain active).")
