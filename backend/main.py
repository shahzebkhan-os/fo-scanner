"""
NSE F&O Option Chain Scanner — Backend v3 (Akamai fix)
"""

import os, time, asyncio, logging, random
from typing import Optional, List
from datetime import datetime, time as dtime
import json
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import io, csv
from . import db
from pydantic import BaseModel, Field
from . import analytics as Analytics
from . import signals_legacy as Signals
from . import scheduler as Scheduler
from .analytics import (
    compute_stock_score_v2 as compute_stock_score, score_option_v2 as score_option, black_scholes_greeks, days_to_expiry,
    STRIKE_INTERVALS
)
from .constants import LOT_SIZES, INDEX_SYMBOLS, FO_STOCKS
from .data_source import fetch_indstocks_ltp
from .signals_legacy import (
    SECTORS,
    SYMBOL_SECTOR,
    detect_uoa,
    screen_straddle,
    build_sector_heatmap,
    get_sector,
    get_pcr_history,
)

from .signals.fii_dii import FiiDiiSignal
from .signals.straddle_pricing import StraddleSignal
from .cache import cache
from .ml_model import predict as ml_predict, train_model as ml_train_model, get_model_status as ml_get_status, get_model_details as ml_get_details, get_symbol_predictions as ml_get_predictions
from .historical_loader import get_backfill_progress, run_backfill_with_progress, reset_backfill_progress
from .suggestions import generate_suggestions
from . import market_external
from .signals.global_cues import GlobalCuesSignal
from .scoring_technical import compute_technical_score
from .unified_evaluation import get_unified_evaluator
from .constants import FO_STOCKS, INDEX_SYMBOLS, LOT_SIZES, SLUG_MAP, YFINANCE_TICKER_MAP
from .technical_backtest import TechnicalBacktester

# Module-level GlobalCuesSignal singleton (stateless, safe to share)
_global_cues_signal = GlobalCuesSignal()

# IST timezone used throughout the module
IST = ZoneInfo("Asia/Kolkata")


def _apply_global_cues_adjustment(stats: dict, gc_result, signal: str) -> dict:
    """
    Apply global cues score adjustment to a stock's scan stats in-place.

    Boosts score when signal direction aligns with global sentiment,
    penalises when they strongly diverge. Maximum adjustment ±10 pts
    (already modulated by time_multiplier inside gc_result.score).
    """
    gc_score = gc_result.score  # -1.0 to +1.0 (time-decayed)
    gc_adjustment = 0
    if abs(gc_score) >= 0.1:
        MAX_ADJ = 10
        if (signal == "BULLISH" and gc_score > 0) or (signal == "BEARISH" and gc_score < 0):
            gc_adjustment = int(abs(gc_score) * MAX_ADJ)
        elif (signal == "BULLISH" and gc_score < -0.3) or (signal == "BEARISH" and gc_score > 0.3):
            gc_adjustment = -int(abs(gc_score) * MAX_ADJ // 2)
        stats["score"] = max(0, min(100, stats.get("score", 0) + gc_adjustment))
        reasons = stats.get("signal_reasons", [])
        if gc_adjustment >= 4:
            reasons.append(f"🌐 Global Cues Positive ({gc_score:+.2f})")
        elif gc_adjustment <= -4:
            reasons.append(f"🌐 Global Cues Negative ({gc_score:+.2f})")
        stats["signal_reasons"] = reasons
    stats["global_cues_score"] = round(gc_score, 3)
    stats["global_cues_adjustment"] = gc_adjustment
    return stats


def _compute_global_cues(ext_data: dict):
    """
    Compute GlobalCuesSignal from fetched external market data.

    Note: gift_nifty is passed as 0 because GIFT Nifty real-time data is
    unavailable via Yahoo Finance during Indian market hours.  The other
    four factors (US markets, DXY, Crude, USD/INR) still drive the signal.
    """
    return _global_cues_signal.compute(
        gift_nifty=0,
        nifty_prev_close=ext_data.get("nifty_prev_close", 0),
        spx_change_pct=ext_data.get("spx_change_pct", 0),
        nasdaq_change_pct=ext_data.get("nasdaq_change_pct", 0),
        dxy=ext_data.get("dxy", 0),
        dxy_prev=ext_data.get("dxy_prev", 0),
        crude_oil=ext_data.get("crude_oil", 0),
        crude_prev=ext_data.get("crude_prev", 0),
        usdinr=ext_data.get("usdinr", 0),
        usdinr_prev=ext_data.get("usdinr_prev", 0),
        current_time=datetime.now(IST),
    )


# ── Deduplication sets (in-memory, keyed by date so they reset daily) ────────
# Bug 6 fix: tracks which trades have already been entered today
# Bug 5 fix: separate sets for trades vs alerts so thresholds are independent
_traded_today: set  = set()   # "SYMBOL-TYPE-STRIKE-DATE"
# notified_signals moved to db.notifications for persistence
_daily_trade_count: int = 0
_sector_trade_count: dict = {}  # {sector: count}

# Auto paper trading caps (None => unlimited)
MAX_DAILY_AUTO_TRADES = None
MAX_SECTOR_TRADES     = None

SUGGESTION_SCAN_LIMIT = len(INDEX_SYMBOLS) + len(FO_STOCKS)

def _reset_daily_sets():
    """Called at the start of each new trading day."""
    global _traded_today, _daily_trade_count, _sector_trade_count
    _traded_today.clear()
    _daily_trade_count = 0
    _sector_trade_count = {}

_last_reset_date = None

def _maybe_reset_daily():
    global _last_reset_date
    today = datetime.now(IST).date()
    if _last_reset_date != today:
        _last_reset_date = today
        _reset_daily_sets()


def _timestamp_suffix() -> str:
    """Consistent timestamp suffix for generated filenames (IST timezone)."""
    return datetime.now(IST).strftime("%Y%m%d_%H%M%S")


import httpx, uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from dotenv import load_dotenv

load_dotenv()

# Secure token logic: fallback to empty instead of hardcoding production secrets
INDSTOCKS_TOKEN = os.getenv("INDSTOCKS_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

INDSTOCKS_BASE  = "https://api.indstocks.com/v1"
NSE_BASE        = "https://www.nseindia.com"

# Telegram alerts are deduplicated via db.is_signal_notified / mark_signal_notified
# Auto-trade thresholds are adjustable via environment or API
AUTO_SCORE_THRESHOLD = int(os.getenv("AUTO_TRADE_SCORE_THRESHOLD", "80"))
AUTO_ML_BULLISH_GATE = float(os.getenv("AUTO_TRADE_ML_BULLISH", "0.60"))
AUTO_ML_BEARISH_GATE = float(os.getenv("AUTO_TRADE_ML_BEARISH", "0.40"))
AUTO_VOL_SPIKE_THRESHOLD = float(os.getenv("AUTO_TRADE_VOL_SPIKE", "0.10"))

# Cache for sector trends to solve circular dependency in scoring
_last_sector_heatmap: dict = {}
_last_sector_update: datetime = datetime.min

_http_client: Optional[httpx.AsyncClient] = None
_http_lock = asyncio.Lock()

async def get_http_client() -> httpx.AsyncClient:
    """Returns a shared httpx.AsyncClient for secondary fetches."""
    global _http_client
    async with _http_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                headers={"User-Agent": "FO-Scanner/4.0"}
            )
    return _http_client

async def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    client = await get_http_client()
    try:
        await client.post(url, json=payload, timeout=5)
    except Exception as e:
        log.error(f"Telegram Alert Failed: {e}")

async def send_telegram_document(filename: str, content: str, caption: str = ""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {"document": (filename, content.encode("utf-8"), "text/csv")}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    client = await get_http_client()
    try:
        r = await client.post(url, data=data, files=files, timeout=10)
        if r.status_code != 200:
            log.error(f"Telegram Document Alert Failed: {r.text}")
    except Exception as e:
        log.error(f"Telegram Document Alert Failed: {e}")

NSE_HEADERS = {
    "User-Agent":       "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "en-US,en;q=0.9",
    "Accept-Encoding":  "gzip, deflate, br",
    "Referer":          "https://www.nseindia.com/option-chain",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua":        '"Chromium";v="122","Not(A:Brand";v="24","Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest":   "empty",
    "sec-fetch-mode":   "cors",
    "sec-fetch-site":   "same-origin",
    "Connection":       "keep-alive",
    "Cache-Control":    "no-cache",
    "Pragma":           "no-cache",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


def _load_auto_trade_config():
    """Reload persisted auto-trade thresholds after DB init."""
    global AUTO_SCORE_THRESHOLD, AUTO_ML_BULLISH_GATE, AUTO_ML_BEARISH_GATE, AUTO_VOL_SPIKE_THRESHOLD
    stored_score = db.get_setting("auto_score_threshold", AUTO_SCORE_THRESHOLD)
    stored_bull = db.get_setting("auto_ml_bullish_gate", AUTO_ML_BULLISH_GATE)
    stored_bear = db.get_setting("auto_ml_bearish_gate", AUTO_ML_BEARISH_GATE)
    stored_vol  = db.get_setting("auto_vol_spike_threshold", AUTO_VOL_SPIKE_THRESHOLD)
    try:
        AUTO_SCORE_THRESHOLD = int(stored_score)
    except (TypeError, ValueError):
        log.warning("Invalid auto_score_threshold setting: %s", stored_score)
    try:
        AUTO_ML_BULLISH_GATE = float(stored_bull)
    except (TypeError, ValueError):
        log.warning("Invalid auto_ml_bullish_gate setting: %s", stored_bull)
    try:
        AUTO_ML_BEARISH_GATE = float(stored_bear)
    except (TypeError, ValueError):
        log.warning("Invalid auto_ml_bearish_gate setting: %s", stored_bear)
    try:
        AUTO_VOL_SPIKE_THRESHOLD = float(stored_vol)
    except (TypeError, ValueError):
        log.warning("Invalid auto_vol_spike_threshold setting: %s", stored_vol)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _load_auto_trade_config()
    
    # Connect Redis cache (falls back to in-memory if unavailable)
    await cache.connect()

    # Wire up the scheduler
    Scheduler.init_scheduler(
        fetch_chain_fn      = fetch_nse_chain,
        send_telegram_fn    = send_telegram_alert,
        is_market_open_fn   = is_market_open,
        scan_fn             = _internal_scan,
        train_fn           = ml_train_model,
        all_symbols         = INDEX_SYMBOLS + FO_STOCKS,
        scan_symbol_fn      = _process_single_symbol,
        send_telegram_doc_fn = send_telegram_document,
    )

    asyncio.create_task(paper_trade_manager())
    # asyncio.create_task(_background_cache_warmer())  # disabled
    await Scheduler.start_all()
    yield
    
    # Cleanup on shutdown
    await cache.close()
    
    # Close shared session clients
    global _ind_client, _http_client
    if _ind_client:
        try: await _ind_client.close()
        except: pass
        _ind_client = None
    if _http_client:
        try: await _http_client.aclose()
        except: pass
        _http_client = None
    log.info("Lifespan cleanup: Sessions and cache closed.")

app = FastAPI(title="NSE F&O Scanner API", version="4.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def _background_cache_warmer():
    """Keep the scan cache fresh by running a scan every 60s in the background."""
    # Wait for app startup completion
    await asyncio.sleep(10)
    log.info("🔥 Background Cache Warmer active. Warming up default scan...")
    while True:
        try:
            # We only warm the full list to satisfy both Scanner and Suggestions tabs
            await scan_all(limit=SUGGESTION_SCAN_LIMIT)
        except Exception as e:
            log.error(f"Cache warmer error: {e}")
        await asyncio.sleep(60)

# ── Market Hours ──────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    """NSE is open Mon–Fri, 9:15 AM – 3:30 PM IST."""
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)

def is_optimal_trade_time() -> bool:
    """Avoid suboptimal entry times:
       - First 15 mins (9:15-9:30): opening volatility
       - Lunch lull (12:00-13:00): low volume
       - Last 30 mins (15:00-15:30): EOD dump risk
    """
    now = datetime.now(IST).time()
    if now < dtime(9, 30):       # Opening volatility
        return False
    # if dtime(12, 0) <= now < dtime(13, 0):  # Relaxed for testing: Lunch lull
    #     return False
    if now >= dtime(15, 0):      # Last 30 mins
        return False
    return True

def market_status() -> dict:
    now = datetime.now(IST)
    open_ = is_market_open()
    return {
        "open":     open_,
        "ist_time": now.strftime("%H:%M:%S"),
        "ist_date": now.strftime("%Y-%m-%d"),
        "weekday":  now.strftime("%A"),
        "message":  "Market OPEN" if open_ else "Market CLOSED (opens Mon–Fri 9:15 AM IST)",
    }

# ── Paper Trading Manager ─────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# 3.  paper_trade_manager  — fixed
# ══════════════════════════════════════════════════════════════════════════════
# Bugs fixed:
#   #10  Flat % SL/TP ignores option price; cheap OTM gets stopped every candle
#        Now: OTM (<₹20) uses wider SL; once +25% hit, trailing stop activates

async def paper_trade_manager():
    """Background task to manage open paper trades with adaptive SL/TP and failure tracking."""
    log.info("Started Paper Trade Manager background loop.")
    while True:
        try:
            _maybe_reset_daily()

            if not is_market_open():
                await asyncio.sleep(300)    # 5 min sleep when market is closed
                continue

            # Check for stale trades (no price update for >5 minutes)
            stale_count = db.check_trade_staleness(max_minutes=5)
            if stale_count > 0:
                log.warning(f"⚠️ Marked {stale_count} trades as stale (no price update for >5 min)")

            open_trades   = db.get_open_trades()
            tracked_picks = db.get_tracked_picks()
            all_to_check  = open_trades + tracked_picks

            if all_to_check:
                log.info(f"Checking {len(open_trades)} trades + {len(tracked_picks)} tracked picks...")
                symbols = list(set([t["symbol"] for t in all_to_check]))

                sem = asyncio.Semaphore(6)
                async def fetch_and_update(sym):
                    async with sem:
                        try:
                            return sym, await fetch_nse_chain(sym)
                        except Exception as e:
                            log.error(f"Failed to fetch {sym}: {e}")
                            return sym, None

                results   = await asyncio.gather(*[fetch_and_update(s) for s in symbols])
                chain_map = {sym: data for sym, data in results if data}

                for trade in all_to_check:
                    sym   = trade["symbol"]
                    chain = chain_map.get(sym)

                    # Track price fetch failure
                    if not chain:
                        if trade["status"] == "OPEN":
                            db.update_trade_health_failure(trade["id"])
                            health = db.get_trade_health(trade["id"])
                            if health and health["health_status"] == "FAILED":
                                log.warning(f"⚠️ Trade {trade['id']} ({sym} {trade['type']} {trade['strike']}) marked as FAILED after {health['consecutive_fails']} consecutive failures - exiting")
                                # Auto-exit failing trade at last known price
                                current_price = trade.get("current_price") or trade.get("entry_price")
                                db.update_trade(trade["id"], current_price,
                                              exit_flag=True, reason="Failed Price Updates (3x)")
                        continue

                    records = chain.get("records", {}).get("data", [])
                    spot    = chain.get("records", {}).get("underlyingValue")
                    if not records or not spot:
                        if trade["status"] == "OPEN":
                            db.update_trade_health_failure(trade["id"])
                        continue

                    current_price = None
                    for row in records:
                        if row.get("strikePrice") == trade["strike"]:
                            opt_data = row.get(trade["type"])
                            if opt_data:
                                current_price = opt_data.get("lastPrice")
                            break

                    if not current_price:
                        if trade["status"] == "OPEN":
                            db.update_trade_health_failure(trade["id"])
                        continue

                    # Price fetch successful - mark health as good
                    if trade["status"] == "OPEN":
                        db.update_trade_health_success(trade["id"])

                    if trade["status"] == "TRACKED":
                        db.update_tracked_pick(trade["id"], current_price, stock_price=spot)
                        continue

                    # ── Adaptive SL/TP logic  (Bug 10 fix) ───────────────────
                    entry = trade["entry_price"]
                    if entry <= 0:
                        continue

                    pnl_pct = ((current_price - entry) / entry) * 100
                    db.update_trade(trade["id"], current_price)

                    now = datetime.now(IST)

                    # EOD square-off at 15:15
                    if now.time() >= dtime(15, 15):
                        db.update_trade(trade["id"], current_price,
                                        exit_flag=True, reason="EOD Square Off")
                        continue

                    # Determine SL and TP thresholds based on option price
                    if entry < 20:
                        # Cheap OTM: wider SL to avoid premature stop-out
                        sl_pct = -40.0
                        tp_pct =  80.0
                    elif entry < 50:
                        # Mid-range
                        sl_pct = -25.0
                        tp_pct =  50.0
                    else:
                        # ATM / expensive: tighter SL
                        sl_pct = -20.0
                        tp_pct =  40.0

                    # Trailing stop: once +25% hit, floor SL at +10%
                    if pnl_pct >= 25:
                        sl_pct = max(sl_pct, 10.0)

                    if pnl_pct <= sl_pct:
                        db.update_trade(trade["id"], current_price,
                                        exit_flag=True, reason=f"Stop Loss ({sl_pct:.0f}%)")
                        continue

                    if pnl_pct >= tp_pct:
                        db.update_trade(trade["id"], current_price,
                                        exit_flag=True, reason=f"Take Profit (+{tp_pct:.0f}%)")
                        continue

            await asyncio.sleep(60)

        except Exception as e:
            log.error(f"Paper Trade Manager Error: {e}")
            await asyncio.sleep(60)

_ind_client: Optional[AsyncSession] = None
_ind_lock = asyncio.Lock()
_ind_fail_count = 0
_IND_FAIL_THRESHOLD = 5  # Recreate session after this many consecutive failures

async def get_ind_client(force_new: bool = False) -> AsyncSession:
    """
    Returns a shared, thread-safe asynchronous curl_cffi session configured
    with browser impersonation to bypass basic CDN/WAF blocks. Using a global
    session drastically reduces TLS handshake overhead for subsequent requests.
    If force_new=True, the existing session is closed and a fresh one is created
    (used when the session is stale or rate-limited).
    """
    global _ind_client
    async with _ind_lock:
        if force_new and _ind_client is not None:
            try:
                _ind_client.close()
            except Exception:
                pass
            _ind_client = None
        if _ind_client is None:
            _ind_client = AsyncSession(
                impersonate="chrome120",
                timeout=15,
                headers={"referer": "https://www.indmoney.com/"}
            )
    return _ind_client

def find_oc_data(obj):
    """
    Recursively searcehs a complex JSON object (like a Next.js SSR state bundle)
    to find the specific dictionary block that contains the 'option_chain_data',
    'expiry_list', and 'entity_details' keys.
    """
    if isinstance(obj, dict):
        if "option_chain_data" in obj and "expiry_list" in obj and "entity_details" in obj:
            return obj
        for k, v in obj.items():
            res = find_oc_data(v)
            if res: return res
    elif isinstance(obj, list):
        for item in obj:
            res = find_oc_data(item)
            if res: return res
    return None

@cache.decorator(expire=300)  # Cache INDmoney scrape for 5 minutes
async def fetch_nse_chain(symbol: str) -> dict:
    """
    Main data retrieval function.
    Previously fetched data from official NSE endpoints. Now updated to scrape 
    the server-side rendered (SSR) HTML payload uniformly from INDmoney to 
    circumvent aggressive Akamai bot-protection and API rate limits.
    Returns the parsed option chain transformed back to the legacy NSE data schema
    so the frontend remains perfectly compatible.
    """
    global _ind_fail_count

    slug = SLUG_MAP.get(symbol)
    if not slug:
        # Don't log as error for non-F&O symbols (indices, sectors, etc.)
        log.info(f"  ℹ️ Skipping INDmoney fetch: No slug for {symbol}")
        return {}

    url = f"https://www.indmoney.com/options/{slug}"
    
    for attempt in range(3):
        try:
            # Randomized delay to reduce rate-limiting risk
            await asyncio.sleep(attempt * 0.5 + random.uniform(0.05, 0.3))

            # Recycle session after too many consecutive failures
            force_new = _ind_fail_count >= _IND_FAIL_THRESHOLD
            client = await get_ind_client(force_new=force_new)
            if force_new:
                _ind_fail_count = 0
                log.info("  ♻️ Recycled INDmoney session after consecutive failures")

            r = await client.get(url, timeout=12)
            log.info(f"  {symbol} → {r.status_code} len={len(r.content)} (attempt {attempt+1})")
            
            if r.status_code != 200:
                _ind_fail_count += 1
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")
            if not script:
                log.warning(f"  {symbol}: __NEXT_DATA__ not found inside HTML")
                _ind_fail_count += 1
                continue
                
            data = json.loads(script.string)
            oc_data = find_oc_data(data)
            
            if not oc_data:
                log.warning(f"  {symbol}: optionChainsData not found in Next.js state")
                _ind_fail_count += 1
                continue
                
            chains = oc_data.get("option_chain_data", [])
            spot = oc_data.get("entity_details", {}).get("live_price", 0)
            exp_raw = oc_data.get("expiry_list", [])
            if exp_raw and isinstance(exp_raw[0], dict):
                expiries = [e.get("key", "") for e in exp_raw]
            else:
                expiries = exp_raw
            
            formatted_data = []
            for row in chains:
                ce = row.get("call_data", {})
                pe = row.get("put_data", {})
                
                def _fmt(sd):
                    if not sd: return {}
                    oi = sd.get("oi", 0)
                    chg_pct = sd.get("oi_change", 0)
                    return {
                        "openInterest": oi,
                        "changeinOpenInterest": oi * chg_pct / 100 if oi else 0,
                        "totalTradedVolume": sd.get("volume", 0),
                        "impliedVolatility": sd.get("iv", 0),
                        "lastPrice": sd.get("current_price", 0)
                    }
                
                formatted_data.append({
                    "strikePrice": row.get("strike_price", 0),
                    "expiryDate": expiries[0] if expiries else "",
                    "CE": _fmt(ce),
                    "PE": _fmt(pe)
                })

            log.info(f"  ✅ {symbol}: {len(formatted_data)} strikes, spot={spot}")
            _ind_fail_count = 0  # Reset on success
            return {
                "records": {
                    "underlyingValue": spot,
                    "expiryDates": expiries,
                    "data": formatted_data
                }
            }

        except Exception as e:
            _ind_fail_count += 1
            log.warning(f"  Error {symbol} attempt {attempt+1}: {type(e).__name__}: {e}")

    log.error(f"  ❌ FAILED all attempts for {symbol}")
    return {}


async def fetch_indstocks_ltp(symbols: list) -> dict:
    """
    Fetch live LTP, volume, and % change for all symbols.
    Primary: NSE market watch (no token needed).
    Fallback: IndStocks API (if token is configured).
    """
    results = await _fetch_nse_market_watch(symbols)
    if results:
        return results

    # Fallback to IndStocks
    if INDSTOCKS_TOKEN and INDSTOCKS_TOKEN not in ("", "PASTE_YOUR_NEW_TOKEN_HERE"):
        results = await _fetch_indstocks_ltp_v1(symbols)

    return results


async def _fetch_nse_market_watch(symbols: list) -> dict:
    """Fetch live quotes from NSE market watch — no auth required."""
    # NSE market watch accepts comma-separated symbols
    INDEX_MAP = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "FINNIFTY": "NIFTY FIN SERVICE"}
    results = {}

    try:
        # Use the shared HTTP client with NSE cookies pre-seeded
        client = await get_http_client()
        # Seed NSE cookies first (re-seeding is fine, httpx handles cookie persistence if client is shared)
        # Note: NSE usually expects a fresh landing page visit to get certain session cookies.
        try:
            await client.get("https://www.nseindia.com", timeout=6)
        except Exception as e:
            log.warning(f"NSE cookie seeding failed: {e}")

            # Fetch equity market watch (FO stocks)
            fo_symbols = [s for s in symbols if s not in INDEX_MAP]
            if fo_symbols:
                try:
                    r = await client.get(
                        "https://www.nseindia.com/api/equity-stockIndices",
                        params={"index": "SECURITIES IN F&O"},
                        timeout=8,
                    )
                    if r.status_code == 200:
                        for item in r.json().get("data", []):
                            sym = item.get("symbol", "")
                            if sym in symbols:
                                results[sym] = {
                                    "ltp":    item.get("lastPrice", 0),
                                    "volume": item.get("totalTradedVolume", 0),
                                    "change": item.get("pChange", 0),
                                }
                        log.info(f"NSE market watch: {len(results)} FO stock prices")
                except Exception as e:
                    log.warning(f"NSE FO stocks fetch error: {e}")

            # Fetch index quotes
            for sym, index_name in INDEX_MAP.items():
                if sym not in symbols:
                    continue
                try:
                    r = await client.get(
                        "https://www.nseindia.com/api/equity-stockIndices",
                        params={"index": index_name},
                        timeout=6,
                    )
                    if r.status_code == 200:
                        data = r.json()
                        meta = data.get("metadata", {})
                        results[sym] = {
                            "ltp":    meta.get("last", 0),
                            "volume": 0,
                            "change": meta.get("percChange", 0),
                        }
                except Exception as e:
                    log.warning(f"NSE index {sym} fetch error: {e}")

    except Exception as e:
        log.warning(f"NSE market watch error: {e}")

    return results


async def _fetch_indstocks_ltp_v1(symbols: list) -> dict:
    """Fallback: IndStocks API (kept for backwards compatibility)."""
    headers = {"Authorization": f"Bearer {INDSTOCKS_TOKEN}"}
    results = {}
    async with httpx.AsyncClient(timeout=12) as client:
        for i in range(0, len(symbols), 50):
            batch = [f"NSE_{s}" for s in symbols[i:i+50]]
            try:
                r = await client.get(
                    f"{INDSTOCKS_BASE}/market/quotes/full",
                    params={"scrip-codes": ",".join(batch)},
                    headers=headers,
                )
                r.raise_for_status()
                for item in r.json().get("data", []):
                    code = item.get("scripCode", "").replace("NSE_", "")
                    results[code] = {
                        "ltp":    item.get("lastPrice", 0),
                        "volume": item.get("totalTradedVolume", 0),
                        "change": item.get("pChange", 0),
                    }
                log.info(f"IndStocks: {len(results)} prices")
            except Exception as e:
                log.debug(f"IndStocks fallback error: {e}")
    return results




@app.get("/api/debug-slugs")
async def debug_slugs():
    return {"slugs_len": len(SLUG_MAP), "RELIANCE_in_map": "RELIANCE" in SLUG_MAP, "keys": list(SLUG_MAP.keys())}

@app.get("/health")
async def health():
    return {**market_status(), "status": "ok", "version": "4.1", "time": datetime.now().isoformat()}

@app.get("/api/debug/auto-trade")
async def debug_auto_trade():
    status = ml_get_status()
    m_open = is_market_open()
    o_time = is_optimal_trade_time()
    return {
        "model_status": status,
        "market_open": m_open,
        "optimal_time": o_time,
        "thresholds": {
            "score": AUTO_SCORE_THRESHOLD,
            "ml_bullish": AUTO_ML_BULLISH_GATE,
            "ml_bearish": AUTO_ML_BEARISH_GATE,
            "vol_spike": AUTO_VOL_SPIKE_THRESHOLD,
        },
        "globals": {
            "daily_count": _daily_trade_count,
            "traded_today_count": len(_traded_today),
            "sector_counts": _sector_trade_count,
        },
        "time_ist": datetime.now(IST).isoformat(),
    }




@app.get("/api/debug/{symbol}")
async def debug_symbol(symbol: str):
    symbol = symbol.upper()
    try:
        data    = await fetch_nse_chain(symbol)
        records = data.get("records", {})
        return {
            "symbol":       symbol,
            "status":       "ok" if records.get("data") else "empty",
            "spot":         records.get("underlyingValue"),
            "expiries":     records.get("expiryDates", [])[:4],
            "strike_count": len(records.get("data", [])),
        }
    except Exception as e:
        return {"symbol": symbol, "status": "error", "error": str(e)}


@app.get("/api/debug-indstocks")
async def debug_indstocks(token: str = Query(...)):
    if token != os.getenv("DEBUG_TOKEN", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    global INDSTOCKS_TOKEN
    headers = {"Authorization": f"Bearer {INDSTOCKS_TOKEN}"}
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{INDSTOCKS_BASE}/market/instruments",
            params={"search": "SBIN", "exchange": "NFO"},
            headers=headers,
        )
        data = r.json().get("data", [])
        return {"raw": data[:10]}

# ══════════════════════════════════════════════════════════════════════════════
# 3.5.  Auto-Trade Entry Logic
# ══════════════════════════════════════════════════════════════════════════════

def _handle_auto_trade(symbol: str, stats: dict, ml_prob: Optional[float], top_picks: list):
    """
    Evaluates auto-trade entry conditions and records trades in DB.
    Called from both /api/scan and background scheduler loops.
    """
    global _daily_trade_count, _sector_trade_count, _traded_today

    stock_score = stats.get("score", 0)
    signal = stats.get("signal", "NEUTRAL")
    vol_spike = stats.get("vol_spike", 0)

    # ── Auto paper-trade entry conditions ──────────────────────────────────
    global _daily_trade_count
    limit = MAX_DAILY_AUTO_TRADES if MAX_DAILY_AUTO_TRADES is not None else 999
    if (stock_score >= AUTO_SCORE_THRESHOLD
        and signal != "NEUTRAL"
        and (ml_prob is None or (signal == "BULLISH" and ml_prob > AUTO_ML_BULLISH_GATE) or (signal == "BEARISH" and ml_prob < AUTO_ML_BEARISH_GATE))
        and vol_spike >= AUTO_VOL_SPIKE_THRESHOLD
        and is_market_open()
        and is_optimal_trade_time()
        and _daily_trade_count < limit):

        # Sector concentration guard
        from .signals_legacy import get_sector
        sym_sector = get_sector(symbol)
        sector_ct = _sector_trade_count.get(sym_sector, 0)

        for pick in top_picks:
            if _daily_trade_count >= limit:
                break
            if sector_ct >= MAX_SECTOR_TRADES:
                log.info(f"  ⚠️ Sector cap hit for {sym_sector} — skipping {symbol}")
                break

            # Hard guard: BULLISH → CE only, BEARISH → PE only
            if signal == "BULLISH" and pick["type"] != "CE":
                continue
            if signal == "BEARISH" and pick["type"] != "PE":
                continue
    
            trade_uid = f"{symbol}-{pick['type']}-{pick['strike']}-{datetime.now(IST).date()}"
            if trade_uid in _traded_today:
                continue
            
            _traded_today.add(trade_uid)
    
            reason = f"Auto: {signal} | Score {stock_score} | PCR {stats.get('pcr')}"
            auto_lot_size = LOT_SIZES.get(symbol, 1)

            # Persist trade with entry score
            db.add_trade(symbol, pick["type"], pick["strike"], pick["ltp"], reason, lot_size=auto_lot_size, entry_score=stock_score)

            _daily_trade_count += 1
            _sector_trade_count[sym_sector] = sector_ct + 1
            sector_ct += 1
            log.info(f"  📝 Auto-trade SUCCESS: {symbol} {pick['type']} {pick['strike']} @ ₹{pick['ltp']} (total trades today: #{_daily_trade_count})")
            return True  # Indicate success
    return False



async def _manage_suggestions_exits(scan_results: list):
    """
    Checks open 'Auto' trades (suggestions) against latest scan signals.
    Exits if signal reverses (e.g. Bullish trade becomes Bearish).
    """
    try:
        open_trades = [t for t in db.get_open_trades() if (t.get("reason") or "").startswith("Auto:")]
        if not open_trades or not scan_results:
            return

        # Map scan results for quick lookup
        latest_snaps = {r["symbol"].upper(): r for r in scan_results}

        for trade in open_trades:
            symbol = trade["symbol"].upper()
            snap = latest_snaps.get(symbol)
            if not snap:
                continue

            current_signal = (snap.get("signal") or "NEUTRAL").upper()
            reason = (trade.get("reason") or "").upper()
            
            # Simple reversal check
            is_bullish_trade = "BULL" in reason
            is_bearish_trade = "BEAR" in reason
            
            do_exit = False
            exit_reason = ""
            
            if is_bullish_trade and current_signal == "BEARISH":
                do_exit = True
                exit_reason = "Signal Reversal (Bearish detected)"
            elif is_bearish_trade and current_signal == "BULLISH":
                do_exit = True
                exit_reason = "Signal Reversal (Bullish detected)"
                
            if do_exit:
                log.info(f"🚩 Auto-Trade EXIT: {symbol} {trade['type']} {trade['strike']} due to {exit_reason}")
                # Fetch latest LTP from the snap if possible, or fallback to chain search
                exit_price = trade.get("current_price") or trade.get("entry_price")
                # Try to find more accurate LTP from the snap's top_pick_ltp if strikes match
                if snap.get("top_pick_strike") == trade["strike"] and snap.get("top_pick_type") == trade["type"]:
                    exit_price = snap.get("top_pick_ltp") or exit_price
                
                db.update_trade(trade["id"], exit_price, exit_flag=True, reason=f"Auto: {exit_reason}")
                
    except Exception as e:
        log.error(f"Error in suggestion exit manager: {e}")


async def _execute_suggestions_auto_trade(scan_results: list):

    """
    Evaluates scan results using the suggestion engine and triggers auto-trades
    for high-conviction ideas.
    """
    if not scan_results:
        log.info("Auto Trade: skipping - no scan results.")
        return
        
    if not is_market_open():
        log.info("Auto Trade: skipping - market closed.")
        return

    log.info(f"Auto Trade: evaluating {len(scan_results)} symbols...")

    # First, managed exits for existing trades
    await _manage_suggestions_exits(scan_results)

    from .suggestions import generate_suggestions
    suggestions = generate_suggestions(scan_results, LOT_SIZES, STRIKE_INTERVALS)
    
    # Only trade High (60+) conviction suggestions
    auto_suggestions = [s for s in suggestions if s.get("conviction", 0) >= 60]
    
    if not auto_suggestions:
        return

    log.info(f"🎯 Evaluating {len(auto_suggestions)} high-conviction suggestions for auto-trade...")
    
    global _daily_trade_count
    count = 0
    for s in auto_suggestions:
        # Avoid comparison with None
        limit = MAX_DAILY_AUTO_TRADES if MAX_DAILY_AUTO_TRADES is not None else 999
        if _daily_trade_count >= limit:
            log.info(f"  🛑 Daily auto-trade limit reached ({_daily_trade_count}/{limit}).")
            break

        symbol = s["symbol"].upper()
        signal = s["signal"]
        conviction = s["conviction"]
        entry = s["entry"]
        strat = s["strategy"]
        
        # Check if already traded today
        trade_uid = f"{symbol}-{entry['primary_type']}-{entry['primary_strike']}-{datetime.now(IST).date()}"
        if trade_uid in _traded_today:
            continue
            
        # Sector concentration check
        from .signals_legacy import get_sector
        sector = get_sector(symbol)
        sec_limit = MAX_SECTOR_TRADES if MAX_SECTOR_TRADES is not None else 99
        if _sector_trade_count.get(sector, 0) >= sec_limit:
            log.info(f"  ⚠️ Sector cap hit for {sector} ({_sector_trade_count.get(sector)}/{sec_limit}) — skipping {symbol}")
            continue

        # Add trade
        _traded_today.add(trade_uid)
        reason = f"Auto: Suggestion ({s['conviction_label']}) | Conviction {conviction} | {strat['strategy']}"
        lot = s["sizing"]["lot_size"]
        
        db.add_trade(
            symbol, entry["primary_type"], entry["primary_strike"], 
            entry["entry_premium"], reason, lot_size=lot, entry_score=conviction
        )
        
        _daily_trade_count += 1
        _sector_trade_count[sector] = _sector_trade_count.get(sector, 0) + 1
        count += 1
        log.info(f"  🚀 SUCCESS: Auto-traded {symbol} suggestion (#{_daily_trade_count})")

    if count > 0:
        log.info(f"✅ Suggestion auto-trade cycle complete: {count} trades placed.")


# ══════════════════════════════════════════════════════════════════════════════
# 4.  /api/scan endpoint  — fixed
# ══════════════════════════════════════════════════════════════════════════════
# Bugs fixed:
#   #6  No dedup → same trade entered on every scan refresh
#   #7  CE + PE both entered even on directional signal
#   #9  Stock score and option score conflated at same threshold

@app.get("/api/scan")
async def scan_all(limit: int = Query(90, ge=1, le=200)):
    """
    Unified scan endpoint with caching and request coalescing.
    If multiple requests hit this while a scan is running, they share the result.
    """
    # 1. Fast Cache Check
    cache_key = cache.cache_key("scan_result", "all", limit)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # 2. Coalescing: Check if a scan is already running for this limit
    global _scan_inflight_tasks
    # Use a task check that's robust to type-hint confusion
    inflight = _scan_inflight_tasks.get(limit)
    if not inflight or not hasattr(inflight, "done") or inflight.done():
        # Start a new scan task
        _scan_inflight_tasks[limit] = asyncio.create_task(_do_full_scan(limit))
        log.info(f"=== SCAN: Starting new scan task for limit={limit} ===")
    else:
        log.info(f"=== SCAN: Coalescing with existing inflight scan for limit={limit} ===")

    try:
        return await _scan_inflight_tasks[limit]
    except Exception as e:
        log.error(f"Inflight scan failed: {e}")
        # If the task failed, remove it so the next request can retry
        _scan_inflight_tasks.pop(limit, None)
        raise

_scan_inflight_tasks = {}

async def _do_full_scan(limit: int) -> dict:
    """The actual heavy lifting of scanning all symbols."""
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    log.info(f"=== SCAN: {len(all_symbols)} symbols (limit={limit}) ===")

    _maybe_reset_daily()

    # ── Fetch external market data once per scan cycle (cached 30 min) ────────
    ext_data = await market_external.fetch_external_market_data()
    global_cues_result = _compute_global_cues(ext_data)
    log.info(
        f"  GlobalCues score={global_cues_result.score:+.3f} "
        f"confidence={global_cues_result.confidence:.2f} "
        f"({global_cues_result.reason})"
    )

    # ── Fetch FII/DII data ───────────────────────────────────────────────────
    fii_dii_res = await fii_dii_data()
    fii_net = 0
    dii_net = 0
    if "data" in fii_dii_res and isinstance(fii_dii_res["data"], list):
        for row in fii_dii_res["data"]:
            if row.get("category") == "FII/FPI":
                # Convert string representation of value if needed or keep float if parsed
                val = row.get("net", 0)
                try: fii_net += float(val)
                except: pass
            elif row.get("category") == "DII":
                val = row.get("net", 0)
                try: dii_net += float(val)
                except: pass

    # Instantiate global FiiDiiSignal 
    fii_engine = FiiDiiSignal()
    fii_signal_result = fii_engine.compute(fii_net_futures=fii_net, dii_net=dii_net)

    ltp_map = await fetch_indstocks_ltp(all_symbols)
    # ⚡ High Concurrency: 30 symbols at once (faster load)
    sem = asyncio.Semaphore(30)
    
    batch_alerts_csv_rows = []

    async def process(symbol: str):
        async with sem:
            live = ltp_map.get(symbol, {})
            try:
                cj       = await fetch_nse_chain(symbol)
                
                # Validate chain structure
                if not cj or "records" not in cj:
                    log.warning(f"  {symbol}: Invalid chain structure from NSE")
                    return None
                
                records  = cj.get("records", {})
                spot     = records.get("underlyingValue") or live.get("ltp") or 0
                expiries = records.get("expiryDates", [])

                # Analytics v4 args mapping
                ivr   = db.get_iv_rank(symbol)
                exp   = expiries[0] if expiries else ""
                
                # Use cached sector signal
                sector = get_sector(symbol)
                sector_sig = _last_sector_heatmap.get(sector, {}).get("signal", "NEUTRAL")

                stats = compute_stock_score(cj, float(spot or 1), symbol, exp, ivr, sector_signal=sector_sig)
                if not spot:
                    return None
                
                # Add ML prediction and refine
                stats["spot_price"] = float(spot or 1)
                ml_prob = ml_predict(stats, symbol=symbol)
                stats["ml_bullish_probability"] = ml_prob
                
                if ml_prob is not None:
                    stats = compute_stock_score(cj, float(spot or 1), symbol, exp, ivr, sector_signal=sector_sig, ml_prob=ml_prob)
                    stats["ml_bullish_probability"] = ml_prob

                stock_score  = stats.get("score", 0)
                signal       = stats.get("signal", "NEUTRAL")
                top_picks    = stats.get("top_picks", [])
                reasons      = stats.get("signal_reasons", [])

                # ── ML Signal Refinement ──
                ml_score = 0
                if ml_prob is not None:
                    # Directional ML score: probability in the direction of the bias
                    if signal == "BULLISH":
                        ml_score = int(ml_prob * 100)
                    elif signal == "BEARISH":
                        ml_score = int((1 - ml_prob) * 100)
                    else:
                        ml_score = int(max(ml_prob, 1 - ml_prob) * 100)

                    # Rule 1: Confirmation
                    if stock_score >= 80 and ((signal == "BULLISH" and ml_prob > 0.70) or (signal == "BEARISH" and ml_prob < 0.30)):
                        reasons.append("🤖 AI Confirmation: High Probability Setup")
                        stats["score"] = min(100, stock_score + 5)
                    
                    # Rule 2: Divergence Guard (Downgrade)
                    elif (signal == "BULLISH" and ml_prob < 0.40) or (signal == "BEARISH" and ml_prob > 0.60):
                        stats["signal"] = "NEUTRAL"
                        reasons.append("⚠️ AI Divergence: Low Probability / Contrarian Bias")
                        stats["score"] = max(0, stock_score - 15)

                # ── Straddle Signal (P1.3) ──
                # Use screen_straddle from signals_legacy to find ATM prices and straddle setups
                straddle_info = screen_straddle(records.get("data", []), symbol, float(spot or 1), exp, stats.get("pcr", 1.0), ivr.get("current_iv", 0))
                if straddle_info:
                    straddle_engine = StraddleSignal()
                    # Calculate implied daily move from straddle cost
                    dte = stats.get("days_to_expiry", 30)
                    
                    s_res = straddle_engine.compute(
                        spot=float(spot or 1),
                        atm_ce_ltp=straddle_info.get("ce_ltp", 0),
                        atm_pe_ltp=straddle_info.get("pe_ltp", 0),
                        dte=dte
                    )
                    # If it detects fast decay or strong straddle edge -> boost score
                    if s_res.score > 50:
                        reasons.append(f"🎪 {s_res.reason} (+5 iv_edge)")
                        stats["score"] = min(100, stats["score"] + 5)
                        
                # Update shared stats before adjusting for global signals
                stats["ml_score"] = ml_score
                signal = stats.get("signal", "NEUTRAL")
                stock_score = stats.get("score", 0)

                # ── Global Cues Adjustment ─────────────────────────────────
                _apply_global_cues_adjustment(stats, global_cues_result, signal)
                signal = stats.get("signal", "NEUTRAL")
                
                # ── FII/DII Signal (P1.3) ──
                # The raw score is [-1.0, 1.0], scale to [-100, 100]
                fii_scaled = fii_signal_result.score * 100
                if fii_scaled != 0:
                    if signal == "BULLISH":
                        if fii_scaled <= -50:
                            reasons.append("⚠️ FII Heavily Net Short (-12)")
                            stats["score"] = max(0, stats["score"] - 12)
                        elif fii_scaled < 0:
                            reasons.append("⚠️ FII Mildly Net Short (-6)")
                            stats["score"] = max(0, stats["score"] - 6)
                    elif signal == "BEARISH":
                        if fii_scaled >= 50:
                            reasons.append("⚠️ FII Heavily Net Long (-12)")
                            stats["score"] = max(0, stats["score"] - 12)
                        elif fii_scaled > 0:
                            reasons.append("⚠️ FII Mildly Net Long (-6)")
                            stats["score"] = max(0, stats["score"] - 6)
                
                stats["signal_reasons"] = reasons
                stock_score = stats.get("score", 0)

                # ── Telegram alerts  (Bug 9 fixed: separate thresholds) ───────
                if stock_score >= 70 and signal != "NEUTRAL":
                    for pick in top_picks:
                        # Same direction guard as trade entry
                        if signal == "BULLISH" and pick["type"] != "CE":
                            continue
                        if signal == "BEARISH" and pick["type"] != "PE":
                            continue
                        if pick.get("score", 0) < 60:
                            continue
                
                        uid = f"{symbol}-{pick['type']}-{pick['strike']}-{datetime.now(IST).date()}"
                        if not db.is_notified(uid):
                            db.mark_notified(uid)
                            reasons_text = " | ".join(stats.get("signal_reasons", []))
                            # Add to batch for CSV
                            batch_alerts_csv_rows.append(
                                f"{symbol},{signal},{stock_score},{pick['strike']} {pick['type']},{pick['score']},{pick['ltp']},{stats.get('pcr',0)},{stats.get('vol_spike',0)},\"{reasons_text}\""
                            )

                            # Instant alert for excellent signals
                            is_excellent = stock_score >= 85 and pick.get("score", 0) >= 70
                            if is_excellent:
                                option_side = "Call" if pick["type"] == "CE" else "Put"
                                pcr_val = stats.get("pcr", 0) or 0
                                iv_rank_val = stats.get("iv_rank", 0) or 0
                                vol_spike_val = stats.get("vol_spike", 0) or 0
                                # Safeguard against unexpected types
                                try:
                                    iv_rank_val = float(iv_rank_val)
                                except (TypeError, ValueError):
                                    iv_rank_val = 0.0
                                try:
                                    pcr_val = float(pcr_val)
                                except (TypeError, ValueError):
                                    pcr_val = 0.0
                                try:
                                    vol_spike_val = float(vol_spike_val)
                                except (TypeError, ValueError):
                                    vol_spike_val = 0.0

                                msg_lines = [
                                    f"🚨 Excellent Signal: *{symbol}* ({signal})",
                                    f"Stock Score: *{stock_score}* | Option Score: *{pick.get('score',0)}*",
                                    f"Top Pick: {pick['strike']} {option_side} @ ₹{round(pick.get('ltp',0), 2)}",
                                ]
                                if stats.get("pcr") is not None:
                                    msg_lines.append(f"PCR: {round(pcr_val, 2)} · IVR: {round(iv_rank_val, 1)} · Vol Spike: {round(vol_spike_val, 2)}")
                                if reasons_text:
                                    msg_lines.append(f"Reasons: {reasons_text}")
                                asyncio.create_task(send_telegram_alert("\n".join(msg_lines)))

                return {
                    "symbol":         symbol,
                    "ltp":            round(spot, 2),
                    "volume":         live.get("volume", 0),
                    "change_pct":     round(live.get("change", 0), 2),
                    "expiries":       expiries[:4],
                    "signal_reasons": stats.get("signal_reasons", []),
                    "ml_bullish_probability": ml_prob,
                    **{k: v for k, v in stats.items() if k not in ["signal_reasons", "ml_bullish_probability"]},
                }

            except RuntimeError as e:
                log.error(f"  {symbol}: Runtime error: {e}")
                return {"symbol": symbol, "error": str(e), "stale": True}
            except Exception as e:
                log.error(f"  {symbol}: {e}")
                import traceback
                traceback.print_exc()
                return None

    raw    = await asyncio.gather(*[process(s) for s in all_symbols[:limit]])
    result = [r for r in raw if r and not r.get("stale")]
    stale_results = [r for r in raw if r and r.get("stale")]
    result.sort(key=lambda x: x.get("score", 0), reverse=True)
    log.info(f"=== SCAN DONE: {len(result)} stocks ===")
    
    # ── Dispatch Batched Telegram Alert CSV ─────────────────
    if batch_alerts_csv_rows:
        headers = "Symbol,Signal,Stock_Score,Contract,Option_Score,LTP,PCR,Vol_Spike,Reasons"
        csv_content = headers + "\n" + "\n".join(batch_alerts_csv_rows)
        filename = f"high_confidence_alerts_{_timestamp_suffix()}.csv"
        caption = f"🚀 *{len(batch_alerts_csv_rows)} High Confidence Trades Detected*\nSee attached CSV for details."
        asyncio.create_task(send_telegram_document(filename, csv_content, caption))
        log.info(f"Dispatched {len(batch_alerts_csv_rows)} telegram alerts via batched CSV.")
    
    response = {
        "timestamp":     datetime.now().isoformat(),
        "_fetched_at":   datetime.now(IST).isoformat(),
        "market_status": market_status(),
        "count":         len(result),
        "data":          result,
        "stale":         len(stale_results) > 0,
        "stale_count":   len(stale_results),
        "global_cues": {
            "score":          round(global_cues_result.score, 4),
            "confidence":     round(global_cues_result.confidence, 4),
            "reason":         global_cues_result.reason,
            "time_multiplier": global_cues_result.metadata.get("time_multiplier", 0.7),
        },
        "market_data": {
            "spx_change_pct":   ext_data.get("spx_change_pct", 0),
            "nasdaq_change_pct": ext_data.get("nasdaq_change_pct", 0),
            "dxy":              ext_data.get("dxy", 0),
            "crude_oil":        ext_data.get("crude_oil", 0),
            "usdinr":           ext_data.get("usdinr", 0),
            "cboe_vix":         ext_data.get("cboe_vix", 0),
            "last_updated":     ext_data.get("last_updated"),
        },
    }
    
    # ── Cache Result ──
    cache_key = cache.cache_key("scan_result", "all", limit)
    await cache.set(cache_key, response, ttl=60)
    
    return response


# ══════════════════════════════════════════════════════════════════════════════
# 4b.  /api/scan-stream  — SSE streaming scan for real-time UI updates
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/scan-stream")
async def scan_stream(limit: int = Query(90, ge=1, le=200)):
    """
    Server-Sent Events endpoint that streams scan results one stock at a time.
    Each result is sent as an SSE 'result' event as soon as the symbol is processed.
    A final 'done' event signals completion with summary metadata.
    """
    all_symbols = INDEX_SYMBOLS + FO_STOCKS

    async def event_generator():
        _maybe_reset_daily()

        # ── Fetch external market data once per scan cycle (cached 30 min) ──
        ext_data = await market_external.fetch_external_market_data()
        gc_result = _compute_global_cues(ext_data)

        ltp_map = await fetch_indstocks_ltp(all_symbols)
        sem = asyncio.Semaphore(10)  # Increased concurrency
        completed = 0
        total = min(limit, len(all_symbols))

        async def process_one(symbol: str):
            async with sem:
                live = ltp_map.get(symbol, {})
                try:
                    cj = await fetch_nse_chain(symbol)
                    if not cj or "records" not in cj:
                        return None

                    records = cj.get("records", {})
                    spot = records.get("underlyingValue") or live.get("ltp") or 0
                    expiries = records.get("expiryDates", [])

                    ivr = db.get_iv_rank(symbol)
                    exp = expiries[0] if expiries else ""
                    
                    # Use cached sector signal
                    sector = get_sector(symbol)
                    sector_sig = _last_sector_heatmap.get(sector, {}).get("signal", "NEUTRAL")

                    stats = compute_stock_score(cj, float(spot or 1), symbol, exp, ivr, sector_signal=sector_sig)
                    if not spot:
                        return None

                    stats["spot_price"] = float(spot or 1)
                    ml_prob = ml_predict(stats, symbol=symbol)
                    stats["ml_bullish_probability"] = ml_prob
                    
                    # Refine score with ML conviction
                    if ml_prob is not None:
                        stats = compute_stock_score(cj, float(spot or 1), symbol, exp, ivr, sector_signal=sector_sig, ml_prob=ml_prob)
                        stats["ml_bullish_probability"] = ml_prob

                    stock_score = stats.get("score", 0)
                    signal = stats.get("signal", "NEUTRAL")
                    reasons = stats.get("signal_reasons", [])

                    if ml_prob is not None:
                        if signal == "BULLISH":
                            ml_score = int(ml_prob * 100)
                        elif signal == "BEARISH":
                            ml_score = int((1 - ml_prob) * 100)
                        else:
                            ml_score = int(max(ml_prob, 1 - ml_prob) * 100)
                        stats["ml_score"] = ml_score

                        if stock_score >= 80 and ((signal == "BULLISH" and ml_prob > 0.70) or (signal == "BEARISH" and ml_prob < 0.30)):
                            stats["score"] = min(100, stock_score + 5)
                        elif (signal == "BULLISH" and ml_prob < 0.40) or (signal == "BEARISH" and ml_prob > 0.60):
                            stats["signal"] = "NEUTRAL"
                            stats["score"] = max(0, stock_score - 15)

                    signal = stats.get("signal", "NEUTRAL")
                    stock_score = stats.get("score", 0)

                    # ── Global Cues Adjustment ─────────────────────────────
                    _apply_global_cues_adjustment(stats, gc_result, signal)

                    return {
                        "symbol": symbol,
                        "ltp": round(spot, 2),
                        "volume": live.get("volume", 0),
                        "change_pct": round(live.get("change", 0), 2),
                        "expiries": expiries[:4],
                        "signal_reasons": stats.get("signal_reasons", []),
                        "ml_bullish_probability": ml_prob,
                        **{k: v for k, v in stats.items() if k not in ["signal_reasons", "ml_bullish_probability"]},
                    }
                except Exception as e:
                    log.error(f"  Stream {symbol}: {e}")
                    return None

        # Process symbols in batches to allow streaming
        batch_size = 10
        symbols_to_process = all_symbols[:total]
        for i in range(0, len(symbols_to_process), batch_size):
            batch = symbols_to_process[i:i + batch_size]
            results = await asyncio.gather(*[process_one(s) for s in batch])
            for r in results:
                if r and not r.get("stale"):
                    completed += 1
                    yield f"event: result\ndata: {json.dumps(r)}\n\n"

        yield f"event: done\ndata: {json.dumps({'count': completed, 'total': total, 'timestamp': datetime.now().isoformat(), 'market_status': market_status()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Paper Trade History Endpoints ─────────────────────────────────────────────

@app.get("/api/paper-trades/active-technical")
async def get_active_technical_trades():
    """Fetch all open paper trades triggered by Technical Score >= 70%."""
    all_open = db.get_open_trades()
    # Filter by specific reason prefix
    tech_trades = [t for t in all_open if (t.get("reason") or "").startswith("Auto: Technical Score")]
    return tech_trades

@app.get("/api/paper-trades/history/{trade_id}")
async def get_paper_trade_history(trade_id: int):
    """Fetch price history for a specific paper trade (for charting)."""
    history = db.get_trade_history(trade_id)
    return history


# ══════════════════════════════════════════════════════════════════════════════
# F&O Trade Suggestions — Best trade ideas ranked by conviction
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/fo-suggestions")
async def fo_suggestions():
    """
    Generate best F&O trade suggestions from latest scan data.
    Returns ranked strategies with specific strikes, risk/reward, and conviction scores.
    """
    from .analytics import STRIKE_INTERVALS
    # Use the scan endpoint internally (with cache); limit controls how many symbols are processed
    scan_result = await scan_all(limit=SUGGESTION_SCAN_LIMIT)
    scan_data = scan_result.get("data", [])

    if not scan_data:
        return {
            "timestamp": datetime.now().isoformat(),
            "market_status": market_status(),
            "count": 0,
            "suggestions": [],
            "message": "No scan data available. Run a scan first.",
        }

    suggestions = generate_suggestions(scan_data, LOT_SIZES, STRIKE_INTERVALS)

    return {
        "timestamp": datetime.now().isoformat(),
        "market_status": market_status(),
        "count": len(suggestions),
        "suggestions": suggestions,
    }


# ══════════════════════════════════════════════════════════════════════════════
# F&O Trade Discovery — Tiered pipeline with confluence & timing filters
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/fo-trades")
async def fo_trades_endpoint():
    """
    Run the tiered F&O trade discovery pipeline.
    Applies: liquidity gate → confluence filter → DTE validation → max pain convergence → bulk deal bonus.
    """
    from .analytics import STRIKE_INTERVALS
    from .fo_trades import run_pipeline

    scan_result = await scan_all(limit=SUGGESTION_SCAN_LIMIT)
    scan_data = scan_result.get("data", [])

    if not scan_data:
        return {
            "timestamp": datetime.now().isoformat(),
            "market_status": market_status(),
            "time_window": {},
            "pipeline": {"scanned": 0, "after_liquidity": 0, "after_confluence": 0, "after_dte": 0, "final": 0},
            "count": 0,
            "trades": [],
            "message": "No scan data available. Run a scan first.",
        }

    suggestions = generate_suggestions(scan_data, LOT_SIZES, STRIKE_INTERVALS)
    result = run_pipeline(scan_data, suggestions)
    result["market_status"] = market_status()

    # ── Telegram Alert ──
    trades = result.get("trades", [])
    if trades:
        try:
            p = result.get("pipeline", {})
            funnel_str = f"{p.get('scanned', 0)} Scanned → {p.get('after_liquidity', 0)} Liquid → {p.get('after_confluence', 0)} Confluent → {p.get('after_dte', 0)} Pattern OK → {len(trades)} Final"
            
            caption = f"🎯 *F&O Discovery Report*\n"
            caption += f"📡 Pipeline: {funnel_str}\n\n"
            caption += f"*Top High-Conviction Trades*:\n"
            
            for i, t in enumerate(trades[:5], 1):
                conf = t.get("confluence", {})
                c_str = f"{conf.get('aligned', 0)}/{conf.get('total', 5)}"
                caption += f"{i}. {t['symbol']} ({t['signal']}) | Conv: {t['conviction']} | Conf: {c_str}\n"
            
            caption += f"\n📊 Full detailed analysis attached."
            
            # CSV generation
            csv_headers = ["Symbol", "Signal", "Conviction", "Confluence", "Spot", "DTE", "Strategy", "Entry Strike", "Type", "Entry Price", "Target", "Stop", "Sector", "IVR"]
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(csv_headers)
            
            def blank(v):
                return "" if v is None else v

            for t in trades:
                conf = t.get("confluence", {})
                c_str = f"{conf.get('aligned', 0)}/{conf.get('total', 5)}"
                strat = t.get("strategy", {}) or {}
                entry = t.get("entry", {}) or {}
                rr = t.get("risk_reward", {}) or {}
                
                writer.writerow([
                    t["symbol"],
                    t["signal"],
                    t["conviction"],
                    c_str,
                    t["spot"],
                    t["dte"],
                    strat.get("strategy", ""),
                    entry.get("primary_strike", ""),
                    entry.get("primary_type", ""),
                    entry.get("entry_premium", ""),
                    rr.get("target_price", ""),
                    rr.get("stop_loss_price", ""),
                    t["sector"],
                    t["iv_rank"]
                ])
                
            csv_content = buffer.getvalue()
            filename = f"fo_discovery_{_timestamp_suffix()}.csv"
            await send_telegram_document(filename, csv_content, caption)
            result["telegram_dispatched"] = True
        except Exception as e:
            log.error(f"Failed to dispatch F&O trade telegram: {e}")
            result["telegram_dispatched"] = False

    return result


class PaperTradeRequest(BaseModel):
    symbol: str
    opt_type: str          # CE or PE
    strike: float
    entry_price: float
    lot_size: int = 1
    reason: str = ""


class AutoTradeConfig(BaseModel):
    score_threshold: Optional[int] = Field(None, ge=0, le=100)
    ml_bullish_gate: Optional[float] = Field(None, ge=0, le=1)
    ml_bearish_gate: Optional[float] = Field(None, ge=0, le=1)


@app.post("/api/fo-suggestions/force-auto-trade")
async def force_suggestions_auto_trade_endpoint():
    """
    Manually triggers a scan and immediately auto-trades any high-conviction
    suggestions found. This ignores the is_market_open() check for convenience.
    """
    log.info("⚡ Manually triggering suggestion-based auto-trade...")
    
    # Run scan
    results = await _internal_scan()
    
    # We need a force version or just call it directly without help of asyncio task
    # to wait for it to finish for the response.
    
    from .suggestions import generate_suggestions
    suggestions = generate_suggestions(results, LOT_SIZES, STRIKE_INTERVALS)
    auto_suggestions = [s for s in suggestions if s.get("conviction", 0) >= 60]
    
    count = 0
    for s in auto_suggestions:
        symbol = s["symbol"].upper()
        entry = s["entry"]
        strat = s["strategy"]
        conviction = s["conviction"]
        
        # Reason prefix for these forced ones
        reason = f"Auto: Suggestion (Forced) | Conviction {conviction} | {strat['strategy']}"
        lot = s["sizing"]["lot_size"]
        
        db.add_trade(
            symbol, entry["primary_type"], entry["primary_strike"], 
            entry["entry_premium"], reason, lot_size=lot, entry_score=conviction
        )
        count += 1
        log.info(f"  🚀 FORCED SUCCESS: Auto-traded {symbol}")

    return {
        "status": "success", 
        "message": f"Added {count} suggestions to paper trades.",
        "count": count
    }
async def suggestion_paper_trade(req: PaperTradeRequest):
    """
    Create a paper trade from a suggestion.
    Can be called regardless of market hours (for manual/testing use),
    but the response includes the current market status for the frontend
    to decide whether to prompt the user.
    """
    symbol = req.symbol.upper()
    opt_type = req.opt_type.upper()
    if opt_type not in ("CE", "PE"):
        raise HTTPException(status_code=400, detail="opt_type must be CE or PE")

    # Check for duplicate open trade
    if db.has_open_trade(symbol, opt_type, req.strike):
        return {
            "success": False,
            "message": f"Duplicate: {symbol} {opt_type} {req.strike} already has an open trade",
            "market_status": market_status(),
        }

    # Use consistent prefix so it shows in "Auto" section as requested by user
    prefix = "Auto: Suggestion"
    reason = f"{prefix} | {req.reason}" if req.reason else f"{prefix}: {symbol} {opt_type} {req.strike}"
    lot = max(1, req.lot_size)
    db.add_trade(symbol, opt_type, req.strike, req.entry_price, reason, lot_size=lot)

    return {
        "success": True,
        "message": f"Paper trade created: {symbol} {opt_type} {req.strike} @ ₹{req.entry_price}",
        "market_status": market_status(),
    }


@app.get("/api/paper-trades")
async def get_paper_trades(status: str = "all"):
    """Get paper trades with optional status filter and trade statistics."""
    if status == "open":
        trades = db.get_open_trades()
    elif status == "closed":
        trades = db.get_closed_trades()
    else:
        trades = db.get_all_trades()

    stats = db.get_trade_stats()
    auto_stats = db.get_trade_stats(trade_type="AUTO")
    manual_stats = db.get_trade_stats(trade_type="MANUAL")

    # Count open auto/manual trades for the summary
    all_trades = trades if status == "all" else db.get_all_trades()
    open_auto = sum(1 for t in all_trades if t["status"] == "OPEN" and (t.get("reason") or "").startswith("Auto:"))
    open_manual = sum(1 for t in all_trades if t["status"] == "OPEN" and not (t.get("reason") or "").startswith("Auto:"))

    return {
        "trades": trades,
        "stats": stats,
        "auto_accuracy": auto_stats,
        "manual_accuracy": manual_stats,
        "market_status": market_status(),
        "count": len(trades),
        "open_auto": open_auto,
        "open_manual": open_manual,
        "config": {
            "score_threshold": AUTO_SCORE_THRESHOLD,
            "ml_bullish_gate": AUTO_ML_BULLISH_GATE,
            "ml_bearish_gate": AUTO_ML_BEARISH_GATE,
            "max_daily_trades": MAX_DAILY_AUTO_TRADES,
            "max_sector_trades": MAX_SECTOR_TRADES,
            "daily_trades_today": _daily_trade_count,
        },
    }


@app.post("/api/paper-trades/config")
async def update_auto_trade_config(cfg: AutoTradeConfig):
    """
    Adjust auto-trade confidence thresholds at runtime.
    """
    global AUTO_SCORE_THRESHOLD, AUTO_ML_BULLISH_GATE, AUTO_ML_BEARISH_GATE
    if cfg.score_threshold is not None:
        AUTO_SCORE_THRESHOLD = int(cfg.score_threshold)
        db.set_setting("auto_score_threshold", AUTO_SCORE_THRESHOLD)
    if cfg.ml_bullish_gate is not None:
        AUTO_ML_BULLISH_GATE = float(cfg.ml_bullish_gate)
        db.set_setting("auto_ml_bullish_gate", AUTO_ML_BULLISH_GATE)
    if cfg.ml_bearish_gate is not None:
        AUTO_ML_BEARISH_GATE = float(cfg.ml_bearish_gate)
        db.set_setting("auto_ml_bearish_gate", AUTO_ML_BEARISH_GATE)
    return {
        "score_threshold": AUTO_SCORE_THRESHOLD,
        "ml_bullish_gate": AUTO_ML_BULLISH_GATE,
        "ml_bearish_gate": AUTO_ML_BEARISH_GATE,
    }


@app.get("/api/paper-trades/{trade_id}/history")
async def get_trade_history(trade_id: int):
    """
    Return a trade along with its recorded price history for charting.
    """
    trade = db.get_trade(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    history = db.get_trade_history(trade_id, limit=400)
    return {"trade": trade, "history": history}


@app.get("/api/paper-trades/auto-accuracy")
async def get_auto_trade_accuracy():
    """
    Dedicated endpoint to check accuracy of auto paper trades.
    Returns stats only for trades created automatically (reason starts with 'Auto:').
    """
    auto_stats = db.get_trade_stats(trade_type="AUTO")
    manual_stats = db.get_trade_stats(trade_type="MANUAL")

    return {
        "auto": auto_stats,
        "manual": manual_stats,
        "market_status": market_status(),
        "config": {
            "score_threshold": AUTO_SCORE_THRESHOLD,
            "ml_bullish_gate": AUTO_ML_BULLISH_GATE,
            "ml_bearish_gate": AUTO_ML_BEARISH_GATE,
            "max_daily_trades": MAX_DAILY_AUTO_TRADES,
            "max_sector_trades": MAX_SECTOR_TRADES,
            "daily_trades_today": _daily_trade_count,
        },
    }


@app.get("/api/paper-trades/health")
async def get_trades_health():
    """
    Get health status of all open trades.
    Returns summary stats and lists of failing/stale trades.
    """
    summary = db.get_trade_health_summary()
    failing_trades = db.get_failing_trades()
    stale_trades = db.get_stale_trades()

    return {
        "summary": summary,
        "failing_trades": failing_trades,
        "stale_trades": stale_trades,
        "timestamp": datetime.now(IST).isoformat(),
    }


@app.get("/api/paper-trades/{trade_id}/health")
async def get_trade_health_details(trade_id: int):
    """
    Get detailed health information for a specific trade.
    """
    trade = db.get_trade(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    health = db.get_trade_health(trade_id)
    if not health:
        # Initialize health tracking if missing
        db.init_trade_health(trade_id)
        health = db.get_trade_health(trade_id)

    return {
        "trade": trade,
        "health": health,
    }


@app.get("/api/chain/{symbol}")
async def get_chain(symbol: str, expiry: str = None):
    symbol = symbol.upper()
    data   = await fetch_nse_chain(symbol)
    records= data.get("records", {})
    spot   = records.get("underlyingValue", 0)
    rows   = records.get("data", [])
    expiry_dates = records.get("expiryDates", [])

    if not rows:
        raise HTTPException(status_code=404,
            detail=f"No chain data for {symbol}. NSE may be blocking — check server logs.")

    if expiry:
        rows = [r for r in rows if r.get("expiryDate") == expiry]

    ivr = db.get_iv_rank(symbol)
    sector = get_sector(symbol)
    sector_sig = _last_sector_heatmap.get(sector, {}).get("signal", "NEUTRAL")
    chain_stats = compute_stock_score(data, spot, symbol, sector_signal=sector_sig)
    top_picks = chain_stats.get("top_picks", [])
    
    ce_scores = {p["strike"]: p["score"] for p in top_picks if p["type"] == "CE"}
    pe_scores = {p["strike"]: p["score"] for p in top_picks if p["type"] == "PE"}

    strikes = []
    for row in rows:
        strike = row.get("strikePrice", 0)
        ce = row.get("CE", {}); pe = row.get("PE", {})
        ce_oi = ce.get("openInterest", 0); pe_oi = pe.get("openInterest", 0)
        ce_c  = ce.get("changeinOpenInterest", 0); pe_c = pe.get("changeinOpenInterest", 0)
        strikes.append({
            "strike":     strike,
            "isATM":      abs(strike - spot) <= (spot * 0.012),
            "expiryDate": row.get("expiryDate", ""),
            "CE": {
                "ltp":        ce.get("lastPrice", 0),
                "iv":         ce.get("impliedVolatility", 0),
                "oi":         ce_oi,
                "oi_chg":     ce_c,
                "oi_chg_pct": round(ce_c / max(1, ce_oi) * 100, 1),
                "volume":     ce.get("totalTradedVolume", 0),
                "score":      ce_scores.get(strike, 0),
            },
            "PE": {
                "ltp":        pe.get("lastPrice", 0),
                "iv":         pe.get("impliedVolatility", 0),
                "oi":         pe_oi,
                "oi_chg":     pe_c,
                "oi_chg_pct": round(pe_c / max(1, pe_oi) * 100, 1),
                "volume":     pe.get("totalTradedVolume", 0),
                "score":      pe_scores.get(strike, 0),
            },
        })

    return {
        "symbol":    symbol,
        "spot":      round(spot, 2),
        "expiry":    expiry or (expiry_dates[0] if expiry_dates else ""),
        "expiries":  expiry_dates[:6],
        "strikes":   strikes,
        "top_picks": top_picks[:4],
        "timestamp": datetime.now().isoformat(),
    }



# ── Lot sizes ─────────────────────────────────────────────────────────────────

@app.get("/api/lot-sizes")
async def get_lot_sizes():
    """Returns the lot size for every F&O symbol."""
    return LOT_SIZES



# ── Backtester API ────────────────────────────────────────────────────────────


class BacktestRequest(BaseModel):
    mode: str = "live"
    symbols: List[str] = []
    tp: float = 40.0
    sl: float = 20.0
    score: float = 75.0


@app.post("/api/backtest")
async def run_backtest(req: BacktestRequest):
    import sys, os
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
        
    import backtest as Backtest
    
    if req.mode == "db":
        log.info(f"=== BACKTEST: Replaying trades from DB (TP={req.tp}% SL={req.sl}%) ===")
        trades = await Backtest.backtest_from_db(tp=req.tp, sl=req.sl)
    else:
        log.info(f"=== BACKTEST: Live Scan (Score >={req.score} TP={req.tp}% SL={req.sl}%) ===")
        syms = req.symbols if req.symbols else INDEX_SYMBOLS + FO_STOCKS[:10]
        trades = await Backtest.backtest_live_signals(syms, score_threshold=req.score, tp=req.tp, sl=req.sl)
        
    return Backtest.generate_report(trades, tp=req.tp, sl=req.sl)

class HistoricalBacktestRequest(BaseModel):
    start: str = "2023-01-01"
    end: str = "2024-12-31"
    score: int = 40
    confidence: float = 0.0
    tp: float = 40.0
    sl: float = 25.0
    signal: Optional[str] = None
    regime: Optional[str] = None
    symbols: Optional[str] = None

@app.post("/api/historical-backtest")
async def run_historical_backtest(req: HistoricalBacktestRequest):
    import sys, os
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
        
    import backtest_runner as BTR
    db_path = os.path.join(backend_dir, "scanner.db")
    bt = BTR.EODBacktester(db_path)
    syms = req.symbols.split(",") if req.symbols else None
    sig = req.signal if req.signal and req.signal != "ALL" else None
    reg = req.regime if req.regime and req.regime != "ALL" else None
    
    res = bt.run(
        req.start, req.end, 
        score_threshold=req.score, 
        confidence_threshold=req.confidence, 
        tp_pct=req.tp, sl_pct=req.sl, 
        signal_filter=sig, regime_filter=reg, symbols=syms
    )
    return res.to_dict()


# ── Greeks ────────────────────────────────────────────────────────────────────

@app.get("/api/greeks/{symbol}")
async def get_greeks(symbol: str, expiry: str = None):
    """
    Returns full Greeks for all strikes of a symbol.
    Adds delta, gamma, theta, vega to every strike row.
    """
    symbol = symbol.upper()
    data   = await fetch_nse_chain(symbol)
    recs   = data.get("records", {})
    spot   = recs.get("underlyingValue", 0)
    rows   = recs.get("data", [])
    expiry_dates = recs.get("expiryDates", [])
    selected_expiry = expiry or (expiry_dates[0] if expiry_dates else "")

    if not rows:
        raise HTTPException(404, f"No data for {symbol}")

    dte = days_to_expiry(selected_expiry)
    result = []

    for row in rows:
        strike = row.get("strikePrice", 0)
        ce     = row.get("CE", {}) or {}
        pe     = row.get("PE", {}) or {}
        ce_iv  = ce.get("impliedVolatility", 0) or 0
        pe_iv  = pe.get("impliedVolatility", 0) or 0

        result.append({
            "strike":   strike,
            "CE": {
                **ce,
                "greeks": black_scholes_greeks(spot, strike, ce_iv or pe_iv or 20, dte, "CE")
            },
            "PE": {
                **pe,
                "greeks": black_scholes_greeks(spot, strike, pe_iv or ce_iv or 20, dte, "PE")
            },
        })

    return {
        "symbol":  symbol,
        "spot":    spot,
        "expiry":  selected_expiry,
        "dte":     dte,
        "strikes": result,
    }


# ── IV Rank ───────────────────────────────────────────────────────────────────

@app.get("/api/ivrank/{symbol}")
async def get_iv_rank(symbol: str):
    """Returns current IV Rank and 52-week IV high/low for a symbol."""
    symbol = symbol.upper()
    ivr    = db.get_iv_rank(symbol)
    if ivr["days_available"] < 5:
        return {**ivr, "warning": "Less than 5 days of IV history. Keep the scanner running daily to build history."}
    return ivr


# ── OI Heatmap ────────────────────────────────────────────────────────────────

@app.get("/api/oi-heatmap/{symbol}")
async def get_oi_heatmap(symbol: str, snap_date: str = None):
    """
    Returns intraday OI snapshots for building a heatmap.
    snap_date format: YYYY-MM-DD (defaults to today)
    """
    symbol = symbol.upper()
    data   = db.get_oi_heatmap(symbol, snap_date)
    return {"symbol": symbol, "date": snap_date or "today", "data": data, "count": len(data)}


@app.get("/api/oi-timeline/{symbol}")
async def get_oi_timeline(symbol: str, strike: float = None, opt_type: str = "CE"):
    """Returns OI over time for a specific strike. Used for OI buildup charts."""
    symbol = symbol.upper()
    if not strike:
        # Default to current ATM
        chain  = await fetch_nse_chain(symbol)
        spot   = chain.get("records", {}).get("underlyingValue", 0)
        from analytics import nearest_atm
        strike = nearest_atm(spot, symbol) if spot else 0

    data = db.get_oi_timeline(symbol, strike, opt_type.upper())
    return {"symbol": symbol, "strike": strike, "type": opt_type.upper(), "timeline": data}


# ── PCR History ───────────────────────────────────────────────────────────────

@app.get("/api/pcr-history/{symbol}")
async def pcr_history(symbol: str):
    """Returns intraday PCR timeline built from OI snapshots."""
    symbol   = symbol.upper()
    timeline = get_pcr_history(symbol)
    return {"symbol": symbol, "timeline": timeline}


# ── Unusual Options Activity ─────────────────────────────────────────────────

@app.get("/api/uoa")
async def unusual_options_activity(
    threshold: float = 5.0,
    limit: int = 20
):
    """
    Scans all F&O symbols for unusual options activity (volume ≥ N× 5-day avg).
    Returns sorted list of flagged contracts.
    """
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    all_uoa     = []
    sem         = asyncio.Semaphore(6)

    async def check_symbol(symbol):
        async with sem:
            try:
                chain = await fetch_nse_chain(symbol)
                recs  = chain.get("records", {}).get("data", [])
                spot  = chain.get("records", {}).get("underlyingValue", 0)
                if recs and spot:
                    uoa = detect_uoa(recs, symbol, spot, threshold)
                    return uoa
            except Exception as e:
                log.error(f"UOA check failed {symbol}: {e}")
            return []

    results = await asyncio.gather(*[check_symbol(s) for s in all_symbols])
    for r in results:
        all_uoa.extend(r)

    all_uoa.sort(key=lambda x: (x.get("ratio") or 0), reverse=True)
    return {
        "timestamp": datetime.now().isoformat(),
        "threshold": threshold,
        "count":     len(all_uoa[:limit]),
        "data":      all_uoa[:limit],
    }


# ── Straddle / Strangle Screener ──────────────────────────────────────────────

@app.get("/api/straddle-screen")
async def straddle_screener(min_iv: float = 15.0, max_pcr_delta: float = 0.3):
    """
    Finds symbols where PCR ≈ 1 and IV is in range — good straddle candidates.
    """
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    candidates  = []
    sem         = asyncio.Semaphore(6)

    async def check(symbol):
        async with sem:
            try:
                chain   = await fetch_nse_chain(symbol)
                recs    = chain.get("records", {}).get("data", [])
                spot    = chain.get("records", {}).get("underlyingValue", 0)
                expiries= chain.get("records", {}).get("expiryDates", [])
                if not recs or not spot: return None

                ivr     = db.get_iv_rank(symbol)
                exp     = expiries[0] if expiries else ""
                
                sector = get_sector(symbol)
                sector_sig = _last_sector_heatmap.get(sector, {}).get("signal", "NEUTRAL")
                
                stats   = compute_stock_score(chain, spot, symbol, expiry_str=exp, iv_rank_data=ivr, sector_signal=sector_sig)
                pcr     = stats.get("pcr", 1.0)
                atm_iv  = stats.get("iv", 0)

                result  = screen_straddle(recs, symbol, spot, exp, pcr, atm_iv)
                if result:
                    result["score"]  = stats.get("score", 0)
                    result["iv_rank"]= ivr.get("iv_rank", 50)
                return result
            except Exception as e:
                log.error(f"Straddle screen {symbol}: {e}")
            return None

    results = await asyncio.gather(*[check(s) for s in all_symbols])
    candidates = [r for r in results if r]
    candidates.sort(key=lambda x: x.get("iv", 0), reverse=True)

    return {
        "timestamp":  datetime.now().isoformat(),
        "count":      len(candidates),
        "candidates": candidates,
    }


# ── Sector Heatmap ────────────────────────────────────────────────────────────

@app.get("/api/sector-heatmap")
async def sector_heatmap():
    """
    Runs a fast scan and returns sector-level signal aggregation.
    Sectors: Banking, IT, Auto, Pharma, Energy, Metal, Finance, Consumer.
    """
    results_raw = await _internal_scan()
    # Handle dict vs list backward compatibility
    results_list = results_raw.get("candidates", []) if isinstance(results_raw, dict) else results_raw
    
    heatmap     = build_sector_heatmap(results_list)
    deals_map   = Signals.get_deals_for_scan(results_list)

    # Annotate symbols with bulk deal flags
    for sector_data in heatmap.values():
        for sym_entry in sector_data["symbols"]:
            sym = sym_entry["symbol"]
            if sym in deals_map:
                sym_entry["bulk_deals"] = len(deals_map[sym])

    return {
        "timestamp": datetime.now().isoformat(),
        "sectors":   heatmap,
    }







# ── Watchlist & Settings ──────────────────────────────────────────────────────

@app.get("/api/settings/watchlist")
async def get_watchlist():
    return {"watchlist": db.get_watchlist()}

@app.post("/api/settings/watchlist")
async def set_watchlist(symbols: list[str]):
    symbols = [s.upper() for s in symbols]
    db.set_watchlist(symbols)
    return {"status": "ok", "watchlist": symbols}

@app.get("/api/settings/capital")
async def get_capital():
    return {"capital": db.get_capital()}

@app.post("/api/settings/capital")
async def set_capital(amount: float):
    db.set_capital(amount)
    return {"status": "ok", "capital": amount}

@app.get("/api/settings/threshold/{symbol}")
async def get_threshold(symbol: str):
    symbol = symbol.upper()
    return {"symbol": symbol, "threshold": db.get_symbol_threshold(symbol)}

@app.post("/api/settings/threshold/{symbol}")
async def set_threshold(symbol: str, threshold: int):
    symbol = symbol.upper()
    db.set_symbol_threshold(symbol, threshold)
    return {"status": "ok", "symbol": symbol, "threshold": threshold}


# ── Bulk Deals ────────────────────────────────────────────────────────────────

@app.get("/api/bulk-deals")
async def bulk_deals(symbol: str = None, days: int = 3):
    """Returns recent NSE bulk/block deals, optionally filtered by symbol."""
    deals = db.get_bulk_deals(symbol.upper() if symbol else None, days)
    return {"count": len(deals), "data": deals}

@app.post("/api/bulk-deals/refresh")
async def refresh_bulk_deals():
    """Manually trigger a bulk deals refresh."""
    deals = await Signals.fetch_bulk_deals()
    return {"status": "ok", "fetched": len(deals)}



# ── Unified Market Evaluation ─────────────────────────────────────────────────

@app.get("/api/unified-evaluation")
async def unified_evaluation(include_technical: bool = False):
    """
    Unified market evaluation combining all models (OI-based, technical, ML, OI velocity, global cues).
    Returns the single best F&O option for each stock with a unified confidence score.

    Args:
        include_technical: Include technical scoring (slower, default=False)

    Returns:
        List of evaluations sorted by unified_score descending
    """
    try:
        # Get scan data
        scan_result = await scan_all(limit=SUGGESTION_SCAN_LIMIT)
        scan_data = scan_result.get("data", [])

        if not scan_data:
            return {
                "timestamp": datetime.now().isoformat(),
                "market_status": market_status(),
                "count": 0,
                "evaluations": [],
                "message": "No scan data available. Run a scan first.",
            }

        # Get unified evaluator
        evaluator = get_unified_evaluator()

        # Evaluate market
        evaluations = await evaluator.evaluate_market(
            scan_data=scan_data,
            include_technical=include_technical,
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "market_status": market_status(),
            "count": len(evaluations),
            "evaluations": evaluations,
            "model_weights": evaluator.WEIGHTS,
            "description": "Unified evaluation combining OI-based, technical, ML, OI velocity, and global cues models",
        }

    except Exception as e:
        log.error(f"Unified evaluation error: {e}", exc_info=True)
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "count": 0,
            "evaluations": [],
        }


@app.get("/api/unified-evaluation/accuracy")
async def unified_evaluation_accuracy(
    min_unified_score: float = 70.0,
    min_confidence: float = 0.65,
    days_back: int = 7,
):
    """
    Track accuracy of unified evaluation predictions.

    Args:
        min_unified_score: Minimum unified score threshold (default 70)
        min_confidence: Minimum unified confidence threshold (default 0.65)
        days_back: Number of days to look back (default 7)

    Returns:
        Accuracy statistics for unified evaluation predictions
    """
    try:
        from .accuracy_tracker import AccuracyTracker

        tracker = AccuracyTracker()

        # Get historical data from market_snapshots table
        conn = db._conn()
        cursor = conn.cursor()

        # Query market snapshots with unified evaluation data
        cursor.execute("""
            SELECT
                symbol,
                snapshot_time,
                score,
                signal,
                confidence,
                ml_bullish_probability,
                regime,
                spot_price,
                trade_result
            FROM market_snapshots
            WHERE snapshot_time >= datetime('now', '-' || ? || ' days')
            AND score >= ?
            AND confidence >= ?
            ORDER BY snapshot_time DESC
        """, (days_back, min_unified_score * 0.7, min_confidence * 0.7))  # Scale thresholds for OI scores

        snapshots = []
        for row in cursor.fetchall():
            snapshots.append({
                "symbol": row[0],
                "timestamp": row[1],
                "score": row[2],
                "signal": row[3],
                "confidence": row[4],
                "ml_probability": row[5],
                "regime": row[6],
                "spot_price": row[7],
                "result": row[8],
            })

        conn.close()

        # Calculate accuracy metrics
        total_predictions = len(snapshots)
        correct = sum(1 for s in snapshots if s["result"] == "WIN")
        incorrect = sum(1 for s in snapshots if s["result"] == "LOSS")
        pending = total_predictions - correct - incorrect

        accuracy_pct = (correct / (correct + incorrect) * 100) if (correct + incorrect) > 0 else 0

        # Group by signal
        by_signal = {}
        for s in snapshots:
            signal = s["signal"]
            if signal not in by_signal:
                by_signal[signal] = {"total": 0, "correct": 0, "incorrect": 0}
            by_signal[signal]["total"] += 1
            if s["result"] == "WIN":
                by_signal[signal]["correct"] += 1
            elif s["result"] == "LOSS":
                by_signal[signal]["incorrect"] += 1

        # Calculate accuracy per signal
        for signal, stats in by_signal.items():
            completed = stats["correct"] + stats["incorrect"]
            stats["accuracy"] = (stats["correct"] / completed * 100) if completed > 0 else 0

        return {
            "timestamp": datetime.now().isoformat(),
            "period_days": days_back,
            "filters": {
                "min_unified_score": min_unified_score,
                "min_confidence": min_confidence,
            },
            "overall": {
                "total_predictions": total_predictions,
                "correct": correct,
                "incorrect": incorrect,
                "pending": pending,
                "accuracy_pct": round(accuracy_pct, 2),
            },
            "by_signal": by_signal,
            "recent_predictions": snapshots[:20],  # Last 20 for display
        }

    except Exception as e:
        log.error(f"Unified evaluation accuracy error: {e}", exc_info=True)
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "overall": {"total_predictions": 0, "accuracy_pct": 0},
        }


@app.get("/api/unified-evaluation/export")
async def unified_evaluation_export(include_technical: bool = False):
    """
    Export unified market evaluation data as Excel with color-coded formatting.
    Returns HTML table format that can be opened in Excel.

    Args:
        include_technical: Include technical scoring (slower, default=False)

    Returns:
        Excel-formatted HTML table with color-coded cells
    """
    try:
        # Get scan data
        scan_result = await scan_all(limit=SUGGESTION_SCAN_LIMIT)
        scan_data = scan_result.get("data", [])

        if not scan_data:
            return {"error": "No scan data available. Run a scan first."}

        # Get unified evaluator
        evaluator = get_unified_evaluator()

        # Evaluate market
        evaluations = await evaluator.evaluate_market(
            scan_data=scan_data,
            include_technical=include_technical,
        )

        if not evaluations:
            return {"error": "No evaluations available"}

        # Build Excel HTML table
        html_parts = []

        # Add header with metadata
        html_parts.append('<table border="1" cellspacing="0" cellpadding="4" style="font-family: Arial, sans-serif; font-size: 11px;">')
        html_parts.append('<tr>')
        html_parts.append('<th colspan="20" style="background-color: #2563eb; color: white; font-size: 14px; padding: 10px;">Unified Market Evaluation Export</th>')
        html_parts.append('</tr>')
        html_parts.append('<tr>')
        html_parts.append(f'<th colspan="20" style="background-color: #f1f5f9; font-size: 10px; padding: 5px;">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Model Weights: OI={evaluator.WEIGHTS["oi_based"]}, Tech={evaluator.WEIGHTS["technical"]}, ML={evaluator.WEIGHTS["ml_ensemble"]}, OI-Vel={evaluator.WEIGHTS["oi_velocity"]}, Global={evaluator.WEIGHTS["global_cues"]}</th>')
        html_parts.append('</tr>')

        # Add column headers
        headers = [
            "Symbol", "Unified Score", "Signal", "Confidence",
            "Option Type", "Strike", "LTP", "IV", "Delta",
            "Target Price", "Stop Loss", "Lot Size",
            "Capital Required", "Potential Profit", "Potential Loss", "R:R Ratio",
            "Regime", "IV Rank", "PCR", "Days to Expiry"
        ]
        html_parts.append('<tr>')
        for header in headers:
            html_parts.append(f'<th style="background-color: #475569; color: white; padding: 6px; font-weight: bold;">{header}</th>')
        html_parts.append('</tr>')

        # Add data rows with color coding
        for eval_data in evaluations:
            symbol = eval_data.get("symbol", "")
            unified_score = eval_data.get("unified_score", 0)
            unified_signal = eval_data.get("unified_signal", "NEUTRAL")
            unified_confidence = eval_data.get("unified_confidence", 0)

            best_option = eval_data.get("best_option", {})
            risk_reward = eval_data.get("risk_reward", {})

            # Determine row background color based on signal
            if unified_signal == "BULLISH":
                row_bg = "#dcfce7"  # Light green
                signal_color = "#16a34a"  # Dark green
            elif unified_signal == "BEARISH":
                row_bg = "#fee2e2"  # Light red
                signal_color = "#dc2626"  # Dark red
            else:
                row_bg = "#f1f5f9"  # Light gray
                signal_color = "#64748b"  # Dark gray

            # Determine score color
            if unified_score >= 80:
                score_color = "#16a34a"  # Dark green
            elif unified_score >= 70:
                score_color = "#2563eb"  # Blue
            elif unified_score >= 60:
                score_color = "#f59e0b"  # Orange
            else:
                score_color = "#dc2626"  # Red

            html_parts.append(f'<tr style="background-color: {row_bg};">')

            # Symbol
            html_parts.append(f'<td style="font-weight: bold; padding: 4px;">{symbol}</td>')

            # Unified Score (with color)
            html_parts.append(f'<td style="color: {score_color}; font-weight: bold; padding: 4px; text-align: center;">{(unified_score or 0):.1f}</td>')

            # Signal (with color)
            html_parts.append(f'<td style="color: {signal_color}; font-weight: bold; padding: 4px; text-align: center;">{unified_signal}</td>')

            # Confidence
            conf_label = "VERY HIGH" if unified_confidence >= 0.85 else "HIGH" if unified_confidence >= 0.75 else "MODERATE" if unified_confidence >= 0.65 else "LOW"
            html_parts.append(f'<td style="padding: 4px; text-align: center;">{conf_label}</td>')

            # Option details
            html_parts.append(f'<td style="padding: 4px; text-align: center;">{best_option.get("type", "")}</td>')
            html_parts.append(f'<td style="padding: 4px; text-align: right;">{best_option.get("strike", "")}</td>')
            html_parts.append(f'<td style="padding: 4px; text-align: right;">₹{(best_option.get("ltp") or 0):.2f}</td>')
            html_parts.append(f'<td style="padding: 4px; text-align: right;">{(best_option.get("iv") or 0):.1f}%</td>')
            html_parts.append(f'<td style="padding: 4px; text-align: right;">{(best_option.get("delta") or 0):.3f}</td>')

            # Risk-reward metrics
            if risk_reward:
                html_parts.append(f'<td style="padding: 4px; text-align: right; background-color: #dcfce7;">₹{(risk_reward.get("target_price") or 0):.2f}</td>')
                html_parts.append(f'<td style="padding: 4px; text-align: right; background-color: #fee2e2;">₹{(risk_reward.get("stoploss_price") or 0):.2f}</td>')
                html_parts.append(f'<td style="padding: 4px; text-align: right; font-weight: bold;">{risk_reward.get("lot_size", 0)}</td>')
                html_parts.append(f'<td style="padding: 4px; text-align: right;">₹{(risk_reward.get("capital_required") or 0):,.0f}</td>')
                html_parts.append(f'<td style="padding: 4px; text-align: right; color: #16a34a;">₹{(risk_reward.get("potential_profit") or 0):,.0f}</td>')
                html_parts.append(f'<td style="padding: 4px; text-align: right; color: #dc2626;">₹{(risk_reward.get("potential_loss") or 0):,.0f}</td>')
                rr_ratio = risk_reward.get("risk_reward_ratio") or 0
                rr_color = "#16a34a" if rr_ratio >= 1.5 else "#f59e0b" if rr_ratio >= 1.0 else "#dc2626"
                html_parts.append(f'<td style="padding: 4px; text-align: center; color: {rr_color}; font-weight: bold;">{rr_ratio:.2f}</td>')
            else:
                html_parts.append('<td colspan="6" style="padding: 4px; text-align: center; color: #94a3b8;">N/A</td>')

            # Market metrics
            html_parts.append(f'<td style="padding: 4px; text-align: center;">{eval_data.get("regime", "")}</td>')
            html_parts.append(f'<td style="padding: 4px; text-align: right;">{(eval_data.get("iv_rank") or 0):.1f}</td>')
            html_parts.append(f'<td style="padding: 4px; text-align: right;">{(eval_data.get("pcr") or 0):.2f}</td>')
            html_parts.append(f'<td style="padding: 4px; text-align: right;">{eval_data.get("days_to_expiry", 0)}</td>')

            html_parts.append('</tr>')

        html_parts.append('</table>')

        # Join all parts
        html_table = ''.join(html_parts)

        return {
            "timestamp": datetime.now().isoformat(),
            "count": len(evaluations),
            "html": html_table,
            "filename": f"unified_evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xls"
        }

    except Exception as e:
        log.error(f"Unified evaluation export error: {e}", exc_info=True)
        return {
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


# ── FII/DII Data ──────────────────────────────────────────────────────────────

@app.get("/api/test-telegram")
async def test_telegram_alert_endpoint():
    """
    Manual trigger to test the Telegram alert formatting.
    """
    test_msg = (
        "⚡ *Technical Highlights (TEST)*\n\n"
        "🟢 *Top Bullish Setups:*\n"
        "• RELIANCE | Score: *85* | STRONG\n"
        "• TCS | Score: *78* | MEDIUM\n\n"
        "🔴 *Top Bearish Setups:*\n"
        "• INFY | Score: *82* | STRONG\n"
        "• HDFCBANK | Score: *75* | MEDIUM\n\n"
        "_This is a manual test message_"
    )
    await send_telegram_alert(test_msg)
    return {"status": "success", "message": "Test alert sent to Telegram"}

@app.get("/api/fii-dii")
async def fii_dii_data():
    """
    Fetches latest FII derivative stats from NSE.
    Returns net position of FIIs in index futures/options.
    """
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://www.nseindia.com/reports/fii-dii",
    }
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            await client.get("https://www.nseindia.com", timeout=5)
            r = await client.get(url, timeout=8)
            r.raise_for_status()
            data = r.json()

            # Parse the relevant rows
            result = []
            for row in data:
                category = row.get("category", "")
                if category in ("FII/FPI", "DII"):
                    result.append({
                        "category":   category,
                        "date":       row.get("date", ""),
                        "buy_value":  row.get("buyValue", 0),
                        "sell_value": row.get("sellValue", 0),
                        "net":        row.get("netValue", 0),
                    })
            return {"data": result, "source": "NSE"}
    except Exception as e:
        log.error(f"FII/DII fetch error: {e}")
        return {"data": [], "error": str(e)}

dist_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(dist_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")

# ── Internal scan helper (used by scheduler pre-market report) ────────────────

async def _process_single_symbol(symbol: str, ltp: float = 0):
    """
    Process one symbol for full F&O analytics, including 
    option chain fetching, scoring, Greeks, and ML predictions.
    Used by both the full scan loop and the technical alert scheduler.
    """
    try:
        cj    = await fetch_nse_chain(symbol)
        recs  = cj.get("records", {})
        spot  = recs.get("underlyingValue") or ltp or 0
        if spot == 0: return None
        ivr   = db.get_iv_rank(symbol)
        exp   = recs.get("expiryDates", [""])[0]
        
        # Use cached sector signal if available
        sector = get_sector(symbol)
        sector_sig = _last_sector_heatmap.get(sector, {}).get("signal", "NEUTRAL")
        
        # Initial score with sector alignment
        stats = compute_stock_score(cj, float(spot), symbol, exp, ivr, sector_signal=sector_sig)
        
        # Add ML prediction and refine score
        stats["spot_price"] = float(spot)
        ml_prob = ml_predict(stats, symbol=symbol)
        stats["ml_bullish_probability"] = ml_prob
        
        # Refine score with ML conviction
        if ml_prob is not None:
            stats = compute_stock_score(cj, spot, symbol, exp, ivr, sector_signal=sector_sig, ml_prob=ml_prob)
            stats["ml_bullish_probability"] = ml_prob # preserve it
        
        return {"symbol": symbol, "ltp": spot, **stats}
    except Exception as e:
        log.error(f"  {symbol}: Single-symbol process error: {e}")
        return None

async def _internal_scan() -> list:
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    ltp_map = await fetch_indstocks_ltp(all_symbols)
    # ⚡ High Concurrency: 30 symbols at once
    sem = asyncio.Semaphore(30)

    async def process(symbol):
        async with sem:
            live_ltp = ltp_map.get(symbol, {}).get("ltp", 0)
            return await _process_single_symbol(symbol, live_ltp)

    raw = await asyncio.gather(*[process(s) for s in all_symbols])
    results = [r for r in raw if r]
    
    # Update sector cache for next scan
    global _last_sector_heatmap, _last_sector_update
    _last_sector_heatmap = build_sector_heatmap(results)
    _last_sector_update = datetime.now()
    
    # ── Execute Suggestion-Based Auto-Trades ─────────────────
    if is_market_open():
        asyncio.create_task(_execute_suggestions_auto_trade(results))

    return results




# ══════════════════════════════════════════════════════════════════════════════
# ML Model Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/ml/train")
async def train_ml_model_endpoint():
    """Train the LightGBM model on historical market_snapshots data."""
    result = await asyncio.to_thread(ml_train_model)
    return result


@app.get("/api/ml/status")
async def ml_status_endpoint():
    """Check if the ML model is trained and available."""
    return ml_get_status()


@app.get("/api/ml/details")
async def ml_details_endpoint():
    """Return comprehensive model architecture, metrics, and training data stats."""
    return await asyncio.to_thread(ml_get_details)


@app.get("/api/ml/predictions")
async def ml_predictions_endpoint():
    """Return per-symbol LightGBM vs Neural Network prediction breakdown."""
    preds = await asyncio.to_thread(ml_get_predictions)
    return {"predictions": preds}


# ══════════════════════════════════════════════════════════════════════════════
# Technical Indicator Scoring (Experimental — for comparison only)
# ══════════════════════════════════════════════════════════════════════════════

def _compute_timeframe_consensus(tf_results: dict) -> dict:
    """Analyze cross-timeframe directional agreement.

    Args:
        tf_results: Dict with keys '5m', '15m', '30m' containing TechnicalScore dicts

    Returns:
        Consensus analysis with alignment metrics
    """
    from collections import Counter

    directions = {tf: res.get("direction", "NEUTRAL") for tf, res in tf_results.items()}

    # Count occurrences
    dir_counts = Counter(directions.values())

    # Majority direction
    majority_direction = dir_counts.most_common(1)[0][0]
    majority_count = dir_counts[majority_direction]

    # Check if all agree
    all_agree = len(set(directions.values())) == 1

    # Consensus strength (what % of timeframes agree)
    consensus_strength = majority_count / len(directions)

    # Identify aligned timeframes
    timeframes_aligned = [tf for tf, d in directions.items() if d == majority_direction]

    # Divergence warning: all three different
    divergence_warning = len(set(directions.values())) == 3

    return {
        "all_agree": all_agree,
        "majority_direction": majority_direction,
        "consensus_strength": consensus_strength,
        "timeframes_aligned": timeframes_aligned,
        "divergence_warning": divergence_warning,
        "detail": directions
    }


@app.get("/api/score-technical/{symbol}")
async def score_technical_endpoint(symbol: str):
    """Return the experimental technical-indicator score for *symbol*.

    Uses RSI, MACD, ADX, Stochastic, EMA alignment, Bollinger %B, Volume,
    and VWAP to produce a 0-100 directional score.  This endpoint is separate
    from the main OI/IV/Greeks scoring model and intended for comparison.

    Price data is fetched from Yahoo Finance (yfinance) — 15-minute bars for the
    most recent 5 trading days.
    """
    symbol = symbol.upper()

    try:
        import yfinance as yf
        import numpy as np
    except ImportError:
        raise HTTPException(status_code=500, detail="yfinance or numpy is not installed")

    # Map NSE symbols to yfinance tickers
    ticker = YFINANCE_TICKER_MAP.get(symbol, f"{symbol}.NS")

    try:
        import pandas as pd
        df = await asyncio.to_thread(
            lambda: yf.download(ticker, period="5d", interval="1m", progress=False)
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch price data: {exc}")

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")

    # Flatten columns if MultiIndex (common in newer yfinance versions for single tickers)
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # ── Lightweight data-quality watchdog ─────────────────────────────────────
    data_quality = {"missing_pct": 0.0, "stale_minutes": 0.0, "ltp_fallback_used": False, "low_liquidity": False}
    if len(df.index) > 1:
        ts_min, ts_max = df.index.min(), df.index.max()
        expected_bars = int(((ts_max - ts_min).total_seconds() // 60) + 1)
        data_quality["missing_pct"] = max(0.0, 1 - (len(df) / expected_bars)) if expected_bars > 0 else 0.0
        data_quality["stale_minutes"] = float((datetime.now() - ts_max).total_seconds() / 60)

    needs_ltp_patch = data_quality["stale_minutes"] > 10 or data_quality["missing_pct"] > 0.10
    if needs_ltp_patch:
        try:
            ltp_map = await fetch_indstocks_ltp([symbol])
            ltp_val = ltp_map.get(symbol, {}).get("ltp")
            if ltp_val:
                latest_time = df.index.max() if len(df.index) else datetime.now()
                patch_ts = latest_time + pd.Timedelta(minutes=1)
                df.loc[patch_ts] = {
                    "Open": ltp_val,
                    "High": ltp_val,
                    "Low": ltp_val,
                    "Close": ltp_val,
                    "Volume": 0,
                }
                df = df.sort_index()
                data_quality["ltp_fallback_used"] = True
        except Exception as exc:
            log.warning(f"  ⚠️ LTP fallback failed for {symbol}: {exc}")

    df_2m = df.resample('2min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    df_5m = df.resample('5min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    df_10m = df.resample('10min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    df_15m = df.resample('15min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()

    # Ensure we get Series, not DataFrames (in case of duplicate columns or remaining MultiIndex)
    def _to_list(series_or_df):
        if hasattr(series_or_df, "tolist"):
            return series_or_df.tolist()
        # If it's still a DataFrame, take the first column
        if hasattr(series_or_df, "iloc"):
            return series_or_df.iloc[:, 0].tolist()
        return list(series_or_df)

    def _flatten(lst):
        if lst and isinstance(lst[0], (list, tuple, np.ndarray)):
            return [x[0] if hasattr(x, "__len__") and len(x) > 0 else x for x in lst]
        return lst

    def _extract(data):
        c = _flatten(_to_list(data["Close"].dropna()))
        h = _flatten(_to_list(data["High"].dropna()))
        l = _flatten(_to_list(data["Low"].dropna()))
        v = _flatten(_to_list(data["Volume"].dropna()))
        return c, h, l, v

    c1, h1, l1, v1 = _extract(df)
    c2, h2, l2, v2 = _extract(df_2m)
    c5, h5, l5, v5 = _extract(df_5m)
    c10, h10, l10, v10 = _extract(df_10m)
    c15, h15, l15, v15 = _extract(df_15m)

    res_1m = compute_technical_score(c1, h1, l1, v1)
    res_2m = compute_technical_score(c2, h2, l2, v2)
    res_5m = compute_technical_score(c5, h5, l5, v5)
    res_10m = compute_technical_score(c10, h10, l10, v10)
    res_15m = compute_technical_score(c15, h15, l15, v15)

    # Compute timeframe consensus
    timeframe_consensus = _compute_timeframe_consensus({
        "1m": res_1m.to_dict(),
        "2m": res_2m.to_dict(),
        "5m": res_5m.to_dict(),
        "10m": res_10m.to_dict(),
        "15m": res_15m.to_dict()
    })

    # --- Compute True Composite Technical Score ---
    # Determine session reliability (favor slower frames when liquidity is thin or data is stale)
    recent_volumes = v1[-30:] if v1 else []
    avg_recent_vol = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
    low_liquidity = avg_recent_vol < 10_000
    data_quality["low_liquidity"] = bool(low_liquidity)

    base_weights = {"1m": 0.10, "2m": 0.10, "5m": 0.20, "10m": 0.25, "15m": 0.35}
    low_liq_weights = {"1m": 0.05, "2m": 0.10, "5m": 0.15, "10m": 0.25, "15m": 0.45}
    weights = low_liq_weights if low_liquidity else base_weights

    # Downweight noisy short frames when data quality issues detected
    if data_quality["missing_pct"] > 0.05 or data_quality["stale_minutes"] > 5:
        weights = {
            "1m": weights["1m"] * 0.5,
            "2m": weights["2m"] * 0.75,
            "5m": weights["5m"],
            "10m": weights["10m"] * 1.05,
            "15m": weights["15m"] * 1.1,
        }

    def _normalize(wdict):
        total = sum(wdict.values())
        return {k: v / total for k, v in wdict.items()} if total else wdict

    weights = _normalize(weights)

    scores_weighted = (
        res_1m.score * weights["1m"] +
        res_2m.score * weights["2m"] +
        res_5m.score * weights["5m"] +
        res_10m.score * weights["10m"] +
        res_15m.score * weights["15m"]
    )

    confidences_weighted = (
        res_1m.confidence * weights["1m"] +
        res_2m.confidence * weights["2m"] +
        res_5m.confidence * weights["5m"] +
        res_10m.confidence * weights["10m"] +
        res_15m.confidence * weights["15m"]
    )

    directions = {
        "1m": res_1m.direction,
        "2m": res_2m.direction,
        "5m": res_5m.direction,
        "10m": res_10m.direction,
        "15m": res_15m.direction,
    }
    dir_score = 0
    for tf, dir_val in directions.items():
        if dir_val == "BULLISH":
            dir_score += weights[tf]
        elif dir_val == "BEARISH":
            dir_score -= weights[tf]
    avg_direction = "BULLISH" if dir_score > 0.05 else "BEARISH" if dir_score < -0.05 else "NEUTRAL"

    strength_map = {"WEAK": 1, "MODERATE": 2, "STRONG": 3}
    strengths_weighted = (
        strength_map.get(res_1m.direction_strength, 1) * weights["1m"] +
        strength_map.get(res_2m.direction_strength, 1) * weights["2m"] +
        strength_map.get(res_5m.direction_strength, 1) * weights["5m"] +
        strength_map.get(res_10m.direction_strength, 1) * weights["10m"] +
        strength_map.get(res_15m.direction_strength, 1) * weights["15m"]
    )
    avg_strength = "STRONG" if strengths_weighted >= 2.5 else "MODERATE" if strengths_weighted >= 1.5 else "WEAK"

    composite_tech = res_15m.to_dict()
    composite_tech["score"] = round(scores_weighted, 1)
    composite_tech["direction"] = avg_direction
    composite_tech["confidence"] = round(confidences_weighted, 3)
    composite_tech["direction_strength"] = avg_strength
    composite_tech["is_composite"] = True
    composite_tech["weights"] = weights

    # Also compute the existing OI-based score for comparison if it's an F&O symbol
    existing_score = None
    if symbol in SLUG_MAP:
        try:
            cj = await fetch_nse_chain(symbol)
            if cj and "records" in cj:
                spot_val = cj.get("records", {}).get("underlyingValue", 0)
                if spot_val:
                    stats = compute_stock_score(cj, float(spot_val), symbol)
                    existing_score = {
                        "score": stats.get("score", 0),
                        "signal": stats.get("signal", "NEUTRAL"),
                        "confidence": stats.get("confidence", 0),
                    }
                    log.info(f"  ✅ Computed comparison OI score for {symbol}: {existing_score['score']}")
                else:
                    log.warning(f"  ⚠️ No spot price found for {symbol} in chain")
            else:
                log.warning(f"  ⚠️ No valid chain for {symbol} comparison")
        except Exception as e:
            log.error(f"  ❌ Error computing comparison score for {symbol}: {e}")
    else:
        log.info(f"  ℹ️ Skipping comparison score: {symbol} not in SLUG_MAP")

    # Fetch momentum from database history
    momentum_metrics = db.get_technical_momentum(symbol, "15m")

    return {
        "symbol": symbol,
        "technical_score": composite_tech,
        "timeframes": {
            "1m": res_1m.to_dict(),
            "2m": res_2m.to_dict(),
            "5m": res_5m.to_dict(),
            "10m": res_10m.to_dict(),
            "15m": res_15m.to_dict(),
        },
        "timeframe_consensus": timeframe_consensus,
        "existing_score": existing_score,
        "momentum": momentum_metrics,
        "data_quality": data_quality,
        "recommended_thresholds": TechnicalBacktester().get_recommended_thresholds(),
        "bars_used": len(c5),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Backfill Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/backfill/progress")
async def backfill_progress_endpoint():
    """Get current backfill progress."""
    return get_backfill_progress()


@app.post("/api/backfill/start")
async def start_backfill_endpoint(days: int = 252):
    """Start historical data backfill (runs in background)."""
    current_progress = get_backfill_progress()
    if current_progress["status"] == "running":
        return {"status": "already_running", "progress": current_progress}
    
    reset_backfill_progress()
    asyncio.create_task(run_backfill_with_progress(days))
    return {"status": "started", "days": days}


# ══════════════════════════════════════════════════════════════════════════════
# External Market Sentiment — Global cues for scoring context
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/market-sentiment")
async def market_sentiment(refresh: bool = False):
    """
    Return current global market sentiment indicators.

    Data sources (via Yahoo Finance, cached 30 min):
      - S&P 500 and NASDAQ overnight % change
      - Dollar Index (DXY) level and direction
      - WTI Crude Oil level and direction
      - USD/INR exchange rate
      - CBOE VIX (global volatility proxy)
      - NIFTY 50 previous close

    Also returns the computed GlobalCuesSignal score (-1 to +1) and
    a human-readable sentiment label.
    """
    ext = await market_external.fetch_external_market_data(force_refresh=refresh)

    gc_result = _compute_global_cues(ext)

    score = gc_result.score  # -1 to +1
    if score >= 0.4:
        sentiment_label = "BULLISH"
    elif score >= 0.1:
        sentiment_label = "MILDLY BULLISH"
    elif score <= -0.4:
        sentiment_label = "BEARISH"
    elif score <= -0.1:
        sentiment_label = "MILDLY BEARISH"
    else:
        sentiment_label = "NEUTRAL"

    return {
        "timestamp": datetime.now(IST).isoformat(),
        "market_data": ext,
        "global_cues": {
            "score": round(score, 4),
            "confidence": round(gc_result.confidence, 4),
            "sentiment": sentiment_label,
            "reason": gc_result.reason,
            "time_multiplier": gc_result.metadata.get("time_multiplier", 0.7),
            "metadata": gc_result.metadata,
        },
        "source_cached": ext.get("cached", False),
        "source_stale": ext.get("stale", False),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Accuracy Tracking Endpoints
# ══════════════════════════════════════════════════════════════════════════════

from .accuracy_tracker import get_accuracy_tracker

@app.get("/api/accuracy/config")
async def get_accuracy_config():
    """Get current accuracy tracking configuration."""
    tracker = get_accuracy_tracker()
    return tracker.load_config()


@app.post("/api/accuracy/config")
async def update_accuracy_config(config: dict):
    """Update accuracy tracking configuration."""
    tracker = get_accuracy_tracker()
    tracker.save_config(config)
    return {"status": "success", "config": config}


@app.post("/api/accuracy/start")
async def start_accuracy_run(run_type: str = "LIVE", start_date: str = None, end_date: str = None):
    """
    Start a new accuracy tracking run.

    Args:
        run_type: 'LIVE' for real-time tracking, 'HISTORICAL' for backtesting
        start_date: Start date for historical runs (YYYY-MM-DD)
        end_date: End date for historical runs (YYYY-MM-DD)
    """
    tracker = get_accuracy_tracker()

    if run_type == "HISTORICAL":
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="start_date and end_date required for historical runs")

        # Run historical accuracy test
        result = tracker.run_historical_accuracy_test(start_date, end_date)
        return result
    else:
        # Start live tracking run
        run_id = tracker.start_accuracy_run(run_type="LIVE")
        return {"status": "started", "run_id": run_id, "run_type": "LIVE"}


@app.get("/api/accuracy/runs")
async def get_accuracy_runs(limit: int = 50):
    """Get list of all accuracy tracking runs."""
    tracker = get_accuracy_tracker()
    runs = tracker.get_all_runs(limit=limit)
    return {"runs": runs}


@app.get("/api/accuracy/runs/{run_id}")
async def get_accuracy_run_detail(run_id: int):
    """Get detailed summary of a specific accuracy run."""
    tracker = get_accuracy_tracker()
    summary = tracker.get_run_summary(run_id)

    if not summary:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return summary


@app.get("/api/accuracy/runs/{run_id}/visualizations")
async def get_accuracy_visualizations(run_id: int):
    """Get visualization data for a specific accuracy run."""
    tracker = get_accuracy_tracker()
    viz_data = tracker.get_visualization_data(run_id)

    if not viz_data:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return viz_data


@app.post("/api/accuracy/runs/{run_id}/finalize")
async def finalize_accuracy_run(run_id: int):
    """Finalize an accuracy run and calculate final statistics."""
    tracker = get_accuracy_tracker()
    tracker.finalize_accuracy_run(run_id)

    # Get the updated summary
    summary = tracker.get_run_summary(run_id)
    return {"status": "finalized", "summary": summary}


@app.get("/api/accuracy/today-trades")
async def get_today_accuracy_trades():
    """Get all accuracy trades from today."""
    return {"trades": db.get_all_today_accuracy_trades()}


@app.get("/api/accuracy/history-snapshots")
async def get_accuracy_history_snapshots():
    """Get the latest accuracy snapshot."""
    snap = db.get_latest_accuracy_snapshot()
    if not snap:
        return {"error": "No snapshots found today", "trades": []}
    return snap


@app.get("/api/accuracy/trade/{trade_id}/history")
async def get_accuracy_trade_price_history(trade_id: int, limit: int = 50):
    """Get price history for a specific accuracy trade."""
    history = db.get_accuracy_trade_history(trade_id)
    return {"history": history[:limit]}


# ══════════════════════════════════════════════════════════════════════════════
# Technical Score Backtesting Endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TechnicalBacktestRequest(BaseModel):
    """Request model for running a technical backtest."""
    symbols: List[str] = Field(default_factory=lambda: ["NIFTY", "BANKNIFTY", "RELIANCE"])
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    timeframe: str = Field(default="15m", description="Bar interval: 5m, 15m, or 30m")
    min_score_threshold: int = Field(default=70, ge=0, le=100)
    min_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    holding_period_minutes: int = Field(default=1440, description="How long to hold position (default 1 day)")
    exit_on_direction_flip: bool = Field(default=True, description="Exit early if direction changes")


@app.post("/api/technical-backtest/run")
async def run_technical_backtest(request: TechnicalBacktestRequest):
    """
    Run a backtest on technical scoring signals.

    Returns comprehensive metrics including:
    - Overall win rate and profit factor
    - Performance by direction (bullish vs bearish)
    - Performance by strength (strong vs weak)
    - Performance by regime (trending vs ranging)
    - Statistical significance testing
    """
    try:
        backtester = TechnicalBacktester()

        metrics, trades = backtester.run_backtest(
            symbols=request.symbols,
            start_date=request.start_date,
            end_date=request.end_date,
            timeframe=request.timeframe,
            min_score_threshold=request.min_score_threshold,
            min_confidence=request.min_confidence,
            holding_period_minutes=request.holding_period_minutes,
            exit_on_direction_flip=request.exit_on_direction_flip
        )

        if metrics is None:
            return {"error": "Backtest failed - check server logs for details"}

        # Convert trades to dict for JSON serialization
        trades_dict = [t.to_dict() for t in trades]

        return {
            "status": "completed",
            "metrics": metrics.to_dict(),
            "trade_count": len(trades),
            "trades_summary": trades_dict[:10],  # First 10 trades for preview
            "config": {
                "symbols": request.symbols,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "timeframe": request.timeframe,
                "min_score_threshold": request.min_score_threshold,
                "min_confidence": request.min_confidence,
                "holding_period_minutes": request.holding_period_minutes
            }
        }

    except Exception as e:
        log.error(f"Error running technical backtest: {e}", exc_info=True)
        return {"error": str(e)}


@app.get("/api/technical-backtest/runs")
async def get_technical_backtest_runs(limit: int = 10):
    """Get list of recent technical backtest runs."""
    try:
        backtester = TechnicalBacktester()
        runs = backtester.get_backtest_runs(limit=limit)
        return {"runs": runs}
    except Exception as e:
        log.error(f"Error fetching backtest runs: {e}")
        return {"error": str(e), "runs": []}


@app.get("/api/technical-backtest/runs/{run_id}")
async def get_technical_backtest_run_details(run_id: int):
    """Get detailed results for a specific backtest run."""
    try:
        backtester = TechnicalBacktester()
        trades = backtester.get_backtest_trades(run_id)

        # Get run metadata
        runs = backtester.get_backtest_runs(limit=100)
        run = next((r for r in runs if r['id'] == run_id), None)

        if not run:
            return {"error": f"Backtest run {run_id} not found"}

        return {
            "run": run,
            "trades": trades,
            "trade_count": len(trades)
        }

    except Exception as e:
        log.error(f"Error fetching backtest run {run_id}: {e}")
        return {"error": str(e)}


@app.get("/api/technical-backtest/accuracy-summary")
    async def get_technical_accuracy_summary():
        """
        Get a summary of technical signal accuracy across all backtests.

    Returns aggregated metrics:
    - Average win rate across all runs
    - Best/worst performing symbols
    - Best/worst performing regimes
    - Trend over time
    """
    try:
        backtester = TechnicalBacktester()
        runs = backtester.get_backtest_runs(limit=50)

        if not runs:
            return {
                "total_runs": 0,
                "avg_win_rate": 0,
                "avg_profit_factor": 0,
                "message": "No backtest runs found. Run a backtest first."
            }

        # Calculate summary statistics
        total_runs = len(runs)
        avg_win_rate = sum(r['win_rate'] for r in runs) / total_runs
        avg_profit_factor = sum(r['profit_factor'] for r in runs if r['profit_factor']) / total_runs
        total_trades = sum(r['total_trades'] for r in runs)

        # Get latest run metrics for detailed breakdown
        latest_run = runs[0]
        latest_metrics = latest_run.get('metrics', {})

        thresholds = backtester.get_recommended_thresholds()

        return {
            "total_runs": total_runs,
            "total_trades_across_runs": total_trades,
            "avg_win_rate": round(avg_win_rate, 4),
            "avg_profit_factor": round(avg_profit_factor, 2),
            "production_thresholds": thresholds,
            "latest_run": {
                "id": latest_run['id'],
                "run_time": latest_run['run_time'],
                "symbols": latest_run['symbols'],
                "win_rate": latest_run['win_rate'],
                "profit_factor": latest_run['profit_factor'],
                "total_trades": latest_run['total_trades'],
                "by_direction": {
                    "bullish_win_rate": latest_metrics.get('bullish_win_rate', 0),
                    "bearish_win_rate": latest_metrics.get('bearish_win_rate', 0)
                },
                "by_strength": {
                    "strong_win_rate": latest_metrics.get('strong_win_rate', 0),
                    "weak_win_rate": latest_metrics.get('weak_win_rate', 0)
                },
                "by_regime": {
                    "trending_win_rate": latest_metrics.get('trending_win_rate', 0),
                    "ranging_win_rate": latest_metrics.get('ranging_win_rate', 0)
                },
                "statistical_significance": {
                    "z_score": latest_metrics.get('z_score'),
                    "p_value": latest_metrics.get('p_value'),
                    "is_significant": latest_metrics.get('is_significant', False)
                }
            },
            "runs_history": runs[:10]  # Last 10 runs for trend analysis
        }

    except Exception as e:
        log.error(f"Error generating accuracy summary: {e}")
        return {"error": str(e)}


# ── Frontend Catch-all ────────────────────────────────────────────────────────

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")

    index_path = os.path.join(dist_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Frontend build not found"}



if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════╗
║       NSE F&O OPTION CHAIN SCANNER v3.0              ║
╠══════════════════════════════════════════════════════╣
║  API:    http://localhost:8000                        ║
║  Docs:   http://localhost:8000/docs                   ║
║  Debug:  http://localhost:8000/api/debug/NIFTY        ║
╚══════════════════════════════════════════════════════╝
""")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="info")

# End of file
