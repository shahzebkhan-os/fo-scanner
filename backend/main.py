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
from . import db
from pydantic import BaseModel, Field
from . import analytics as Analytics
from . import signals_legacy as Signals
from . import scheduler as Scheduler
from .analytics import compute_stock_score_v2 as compute_stock_score, score_option_v2 as score_option, black_scholes_greeks, days_to_expiry
from .signals_legacy import build_sector_heatmap, detect_uoa, screen_straddle, get_pcr_history
from .cache import cache
from .ml_model import predict as ml_predict, train_model as ml_train_model, get_model_status as ml_get_status, get_model_details as ml_get_details, get_symbol_predictions as ml_get_predictions
from .historical_loader import get_backfill_progress, run_backfill_with_progress, reset_backfill_progress
from .suggestions import generate_suggestions
from . import market_external
from .signals.global_cues import GlobalCuesSignal
from .scoring_technical import compute_technical_score

# Module-level GlobalCuesSignal singleton (stateless, safe to share)
_global_cues_signal = GlobalCuesSignal()


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

MAX_DAILY_AUTO_TRADES = 10
MAX_SECTOR_TRADES     = 3

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

async def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload, timeout=5)
        except Exception as e:
            log.error(f"Telegram Alert Failed: {e}")

async def send_telegram_document(filename: str, content: str, caption: str = ""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {"document": (filename, content.encode("utf-8"), "text/csv")}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    async with httpx.AsyncClient() as client:
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

from .constants import FO_STOCKS, INDEX_SYMBOLS, LOT_SIZES, SLUG_MAP, YFINANCE_TICKER_MAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def _load_auto_trade_config():
    """Reload persisted auto-trade thresholds after DB init."""
    global AUTO_SCORE_THRESHOLD, AUTO_ML_BULLISH_GATE, AUTO_ML_BEARISH_GATE
    stored_score = db.get_setting("auto_score_threshold", AUTO_SCORE_THRESHOLD)
    stored_bull = db.get_setting("auto_ml_bullish_gate", AUTO_ML_BULLISH_GATE)
    stored_bear = db.get_setting("auto_ml_bearish_gate", AUTO_ML_BEARISH_GATE)
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

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _load_auto_trade_config()
    
    # Connect Redis cache (falls back to in-memory if unavailable)
    await cache.connect()

    # Wire up the scheduler
    Scheduler.init_scheduler(
        fetch_chain_fn    = fetch_nse_chain,
        send_telegram_fn  = send_telegram_alert,
        is_market_open_fn = is_market_open,
        scan_fn           = _internal_scan,
        train_fn         = ml_train_model,
        all_symbols       = INDEX_SYMBOLS + FO_STOCKS,
    )

    asyncio.create_task(paper_trade_manager())
    await Scheduler.start_all()
    yield
    
    # Cleanup on shutdown
    await cache.close()

app = FastAPI(title="NSE F&O Scanner API", version="4.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    if dtime(12, 0) <= now < dtime(13, 0):  # Lunch lull
        return False
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
    """Background task to manage open paper trades with adaptive SL/TP."""
    log.info("Started Paper Trade Manager background loop.")
    while True:
        try:
            _maybe_reset_daily()

            if not is_market_open():
                await asyncio.sleep(300)    # 5 min sleep when market is closed
                continue

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
                    if not chain: continue

                    records = chain.get("records", {}).get("data", [])
                    spot    = chain.get("records", {}).get("underlyingValue")
                    if not records or not spot: continue

                    current_price = None
                    for row in records:
                        if row.get("strikePrice") == trade["strike"]:
                            opt_data = row.get(trade["type"])
                            if opt_data:
                                current_price = opt_data.get("lastPrice")
                            break

                    if not current_price:
                        continue

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
        log.error(f"  ❌ No INDmoney slug for symbol={repr(symbol)}, in dict={symbol in SLUG_MAP}")
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
        # Use a throwaway httpx client with NSE cookies pre-seeded
        nse_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/market-data/live-equity-market",
        }
        async with httpx.AsyncClient(timeout=10, headers=nse_headers) as client:
            # Seed NSE cookies first
            await client.get("https://www.nseindia.com", timeout=6)

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
    return {**market_status(), "status": "ok", "version": "4.0", "time": datetime.now().isoformat()}




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
# 4.  /api/scan endpoint  — fixed
# ══════════════════════════════════════════════════════════════════════════════
# Bugs fixed:
#   #6  No dedup → same trade entered on every scan refresh
#   #7  CE + PE both entered even on directional signal
#   #9  Stock score and option score conflated at same threshold

@app.get("/api/scan")
async def scan_all(limit: int = Query(90, ge=1, le=200)):
    # Check cache first for the full scan result
    cache_key = cache.cache_key("scan_result", "all", limit)
    cached = await cache.get(cache_key)
    if cached:
        log.info(f"=== SCAN: returning cached result ===")
        return cached
    
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    log.info(f"=== SCAN: {len(all_symbols)} symbols ===")

    _maybe_reset_daily()                        # Bug 6 fix: reset dedup sets on new day

    # ── Fetch external market data once per scan cycle (cached 30 min) ────────
    ext_data = await market_external.fetch_external_market_data()
    global_cues_result = _compute_global_cues(ext_data)
    log.info(
        f"  GlobalCues score={global_cues_result.score:+.3f} "
        f"confidence={global_cues_result.confidence:.2f} "
        f"({global_cues_result.reason})"
    )

    ltp_map = await fetch_indstocks_ltp(all_symbols)
    sem = asyncio.Semaphore(8)
    
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
                stats = compute_stock_score(cj, float(spot or 1), symbol, exp, ivr, prev_chain_data=None, fii_net=0.0)
                if not spot:
                    return None
                
                # Add ML prediction if model is trained
                ml_prob = ml_predict(stats, symbol=symbol)
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

                # Update shared stats
                stats["ml_score"] = ml_score
                stats["signal_reasons"] = reasons
                signal = stats["signal"]
                stock_score = stats["score"]

                # ── Global Cues Adjustment ─────────────────────────────────
                _apply_global_cues_adjustment(stats, global_cues_result, signal)
                stock_score = stats["score"]

                # ── Auto paper-trade entry  (thresholds configurable) ───────
                if (stock_score > AUTO_SCORE_THRESHOLD
                    and signal != "NEUTRAL"
                    and (ml_prob is None or (signal == "BULLISH" and ml_prob > AUTO_ML_BULLISH_GATE) or (signal == "BEARISH" and ml_prob < AUTO_ML_BEARISH_GATE))
                    and stats.get("vol_spike", 0) > 0.4
                    and is_market_open()
                    and is_optimal_trade_time()
                    and _daily_trade_count < MAX_DAILY_AUTO_TRADES):

                    # Sector concentration guard
                    from .signals_legacy import get_sector
                    sym_sector = get_sector(symbol)
                    sector_ct = _sector_trade_count.get(sym_sector, 0)

                    for pick in top_picks:
                        if _daily_trade_count >= MAX_DAILY_AUTO_TRADES:
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
                        db.add_trade(symbol, pick["type"], pick["strike"], pick["ltp"], reason, lot_size=auto_lot_size)
                        _daily_trade_count += 1
                        _sector_trade_count[sym_sector] = sector_ct + 1
                        sector_ct += 1
                        log.info(f"  📝 Auto-trade: {symbol} {pick['type']} {pick['strike']} @ ₹{pick['ltp']} (trade #{_daily_trade_count})")
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
        filename = f"high_confidence_alerts_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}.csv"
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
    
    # Cache the result for 60 seconds
    await cache.set(cache_key, response, ttl=cache.DEFAULT_TTLS["scan_result"])
    
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
                    stats = compute_stock_score(cj, float(spot or 1), symbol, exp, ivr, prev_chain_data=None, fii_net=0.0)
                    if not spot:
                        return None

                    ml_prob = ml_predict(stats, symbol=symbol)
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

    # Use the scan endpoint internally (with cache)
    scan_result = await scan_all(limit=90)
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


@app.post("/api/fo-suggestions/paper-trade")
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

    reason = req.reason or f"Suggestion trade: {symbol} {opt_type} {req.strike}"
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

    chain_stats = compute_stock_score(data, spot, symbol, prev_chain_data=None, fii_net=0.0)
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
                stats   = compute_stock_score(chain, spot, symbol, expiry_str=exp, iv_rank_data=ivr, prev_chain_data=None, fii_net=0.0)
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



# ── FII/DII Data ──────────────────────────────────────────────────────────────

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

async def _internal_scan() -> list:
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    ltp_map = await fetch_indstocks_ltp(all_symbols)
    sem = asyncio.Semaphore(8)

    async def process(symbol):
        async with sem:
            try:
                cj    = await fetch_nse_chain(symbol)
                recs  = cj.get("records", {})
                spot  = recs.get("underlyingValue") or ltp_map.get(symbol, {}).get("ltp") or 0
                if spot == 0: return None
                ivr   = db.get_iv_rank(symbol)
                exp   = recs.get("expiryDates", [""])[0]
                stats = compute_stock_score(cj, spot, symbol, exp, ivr, prev_chain_data=None, fii_net=0.0)
                return {"symbol": symbol, "ltp": spot, **stats}
            except:
                return None

    raw = await asyncio.gather(*[process(s) for s in all_symbols])
    return [r for r in raw if r]




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
    except ImportError:
        raise HTTPException(status_code=500, detail="yfinance is not installed")

    # Map NSE symbols to yfinance tickers
    ticker = YFINANCE_TICKER_MAP.get(symbol, f"{symbol}.NS")

    try:
        df = await asyncio.to_thread(
            lambda: yf.download(ticker, period="5d", interval="15m", progress=False)
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch price data: {exc}")

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")

    closes = df["Close"].dropna().tolist()
    highs = df["High"].dropna().tolist()
    lows = df["Low"].dropna().tolist()
    volumes = df["Volume"].dropna().tolist()

    # Flatten multi-level columns that yfinance sometimes returns
    def _flatten(lst):
        if lst and isinstance(lst[0], (list, tuple)):
            return [x[0] if isinstance(x, (list, tuple)) else x for x in lst]
        return lst

    closes = _flatten(closes)
    highs = _flatten(highs)
    lows = _flatten(lows)
    volumes = _flatten(volumes)

    result = compute_technical_score(closes, highs, lows, volumes)

    # Also compute the existing OI-based score for comparison if chain data is available
    existing_score = None
    try:
        cj = await fetch_nse_chain(symbol)
        if cj and "records" in cj:
            spot = cj.get("records", {}).get("underlyingValue", 0)
            if spot:
                stats = compute_stock_score(cj, float(spot), symbol)
                existing_score = {
                    "score": stats.get("score", 0),
                    "signal": stats.get("signal", "NEUTRAL"),
                    "confidence": stats.get("confidence", 0),
                }
    except Exception:
        pass  # comparison is best-effort

    return {
        "symbol": symbol,
        "technical_score": result.to_dict(),
        "existing_score": existing_score,
        "bars_used": len(closes),
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
