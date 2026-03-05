"""
scheduler.py — Background Task Scheduler v4
Tasks:
  1. OI Snapshot      — every 15 min during market hours
  2. IV History Save  — once daily at 15:35
  3. Pre-Market Report — every weekday at 9:00 AM IST via Telegram
  4. Bulk Deals Fetch — every weekday at 16:00 IST
  5. DB Cleanup       — every Sunday midnight
"""

import asyncio
import logging
from datetime import datetime, time as dtime, date
from zoneinfo import ZoneInfo

import db
import signals as Signals

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

# These are injected at startup from main.py
_fetch_nse_chain_fn   = None
_send_telegram_fn     = None
_is_market_open_fn    = None
_scan_all_symbols_fn  = None   # should return list of scan result dicts
_all_symbols_list     = []

def init_scheduler(
    fetch_chain_fn,
    send_telegram_fn,
    is_market_open_fn,
    scan_fn,
    all_symbols: list,
):
    global _fetch_nse_chain_fn, _send_telegram_fn, _is_market_open_fn
    global _scan_all_symbols_fn, _all_symbols_list
    _fetch_nse_chain_fn  = fetch_chain_fn
    _send_telegram_fn    = send_telegram_fn
    _is_market_open_fn   = is_market_open_fn
    _scan_all_symbols_fn = scan_fn
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

                            from analytics import nearest_atm, get_strike_interval
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
# Start all tasks
# ══════════════════════════════════════════════════════════════════════════════

async def start_all():
    """Launch all background tasks. Call from FastAPI lifespan."""
    asyncio.create_task(oi_snapshot_loop())
    asyncio.create_task(iv_history_loop())
    asyncio.create_task(pre_market_report_loop())
    asyncio.create_task(bulk_deals_loop())
    asyncio.create_task(db_cleanup_loop())
    log.info("All scheduler tasks started.")

