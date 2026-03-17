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
from datetime import datetime, time as dtime, date
from zoneinfo import ZoneInfo

from . import db
from . import signals_legacy as Signals

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

# These are injected at startup from main.py
_fetch_nse_chain_fn   = None
_send_telegram_fn     = None
_is_market_open_fn    = None
_scan_all_symbols_fn  = None   # should return list of scan result dicts
_ml_train_fn          = None
_all_symbols_list     = []

def init_scheduler(
    fetch_chain_fn,
    send_telegram_fn,
    is_market_open_fn,
    scan_fn,
    train_fn,
    all_symbols: list,
):
    global _fetch_nse_chain_fn, _send_telegram_fn, _is_market_open_fn
    global _scan_all_symbols_fn, _ml_train_fn, _all_symbols_list
    _fetch_nse_chain_fn  = fetch_chain_fn
    _send_telegram_fn    = send_telegram_fn
    _is_market_open_fn   = is_market_open_fn
    _scan_all_symbols_fn = scan_fn
    _ml_train_fn         = train_fn
    _all_symbols_list    = all_symbols
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

async def pre_market_report_loop():
    """
    Sends a Telegram summary of top setups every weekday at 9:00 AM IST,
    before market opens. Scans all symbols and picks top 5 by score.
    """
    log.info("Pre-market report loop started.")
    _sent_today = None

    while True:
        try:
            now   = datetime.now(IST)
            today = now.date()

            # Weekdays only, between 8:55–9:10 AM, once per day
            is_weekday  = now.weekday() < 5
            is_report_window = dtime(8, 55) <= now.time() <= dtime(9, 10)

            if is_weekday and is_report_window and _sent_today != today:
                log.info("Generating pre-market report...")

                if _scan_all_symbols_fn:
                    results = await _scan_all_symbols_fn()
                    top5    = sorted(results, key=lambda x: x.get("score", 0), reverse=True)[:5]

                    if not top5:
                        await asyncio.sleep(600)
                        continue

                    lines = [
                        "📊 *PRE-MARKET REPORT*",
                        f"🗓 {today.strftime('%d %b %Y')} | Top 5 Setups\n",
                    ]
                    for i, r in enumerate(top5, 1):
                        sym    = r["symbol"]
                        sig    = r.get("signal", "NEUTRAL")
                        score  = r.get("score", 0)
                        pcr    = r.get("pcr", 0)
                        iv     = r.get("iv", 0)
                        picks  = r.get("top_picks", [])
                        pick_str = ", ".join(
                            f"{p['strike']} {p['type']} @ ₹{p['ltp']}"
                            for p in picks[:1]
                        ) if picks else "—"

                        emoji = "🟢" if sig == "BULLISH" else "🔴" if sig == "BEARISH" else "⚪"
                        lines.append(
                            f"{i}. {emoji} *{sym}* — Score: {score}\n"
                            f"   Signal: {sig} | PCR: {pcr} | IV: {iv}\n"
                            f"   Best Pick: {pick_str}"
                        )

                    # Sector summary
                    sector_map = Signals.build_sector_heatmap(results)
                    bull_sectors = [s for s, d in sector_map.items() if d["signal"] == "BULLISH"]
                    bear_sectors = [s for s, d in sector_map.items() if d["signal"] == "BEARISH"]
                    if bull_sectors:
                        lines.append(f"\n🟢 Bullish sectors: {', '.join(bull_sectors)}")
                    if bear_sectors:
                        lines.append(f"🔴 Bearish sectors: {', '.join(bear_sectors)}")

                    lines.append("\n_Market opens at 9:15 AM IST_")
                    msg = "\n".join(lines)

                    if _send_telegram_fn:
                        await _send_telegram_fn(msg)
                    _sent_today = today
                    log.info("Pre-market report sent.")

            await asyncio.sleep(120)   # check every 2 min

        except Exception as e:
            log.error(f"Pre-market report error: {e}")
            await asyncio.sleep(120)


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
    Background loop that triggers a full scan every 5 minutes.
    Since _internal_scan is now wired to _handle_auto_trade,
    this drives the background auto-paper-trading.
    """
    log.info("Auto Trade background loop started (5 min interval).")
    while True:
        try:
            if _is_market_open_fn and _is_market_open_fn():
                if _scan_all_symbols_fn:
                    log.info("Auto Trade: Running background automated scan...")
                    # This calls main._internal_scan() which now triggers trades
                    await _scan_all_symbols_fn()
                    log.info("Auto Trade: Background scan cycle completed.")
            
            await asyncio.sleep(300)  # 5 minutes
        except Exception as e:
            log.error(f"Auto trade loop error: {e}")
            await asyncio.sleep(300)


async def start_all():
    """Launch all background tasks. Call from FastAPI lifespan."""
    asyncio.create_task(oi_snapshot_loop())
    asyncio.create_task(iv_history_loop())
    asyncio.create_task(pre_market_report_loop())
    asyncio.create_task(bulk_deals_loop())
    asyncio.create_task(db_cleanup_loop())
    asyncio.create_task(auto_tpsl_loop())
    asyncio.create_task(accuracy_sampler_loop())
    asyncio.create_task(accuracy_price_updater_loop())
    asyncio.create_task(ml_retrain_loop())
    asyncio.create_task(auto_trade_loop())
    log.info("All scheduler tasks started (including Auto Trade Background Loop).")


