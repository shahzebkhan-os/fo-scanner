"""
NSE F&O Option Chain Scanner — Backend v3 (Akamai fix)
"""

import os, time, asyncio, logging
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
from .ml_model import predict as ml_predict, train_model as ml_train_model, get_model_status as ml_get_status
from .historical_loader import get_backfill_progress, run_backfill_with_progress, reset_backfill_progress

# ── Deduplication sets (in-memory, keyed by date so they reset daily) ────────
# Bug 6 fix: tracks which trades have already been entered today
# Bug 5 fix: separate sets for trades vs alerts so thresholds are independent
_traded_today: set  = set()   # "SYMBOL-TYPE-STRIKE-DATE"
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
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

# Secure token logic: fallback to empty instead of hardcoding production secrets
INDSTOCKS_TOKEN = os.getenv("INDSTOCKS_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

INDSTOCKS_BASE  = "https://api.indstocks.com/v1"
NSE_BASE        = "https://www.nseindia.com"

# Telegram alerts are deduplicated via db.is_signal_notified / mark_signal_notified

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

FO_STOCKS = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","ADANIENT","WIPRO",
    "AXISBANK","BAJFINANCE","HCLTECH","LT","KOTAKBANK","TATAMOTORS","MARUTI",
    "SUNPHARMA","ITC","ONGC","POWERGRID","NTPC","BPCL","GRASIM","TITAN",
    "INDUSINDBK","ULTRACEMCO","HEROMOTOCO","ASIANPAINT","MM","DRREDDY",
    "DIVISLAB","CIPLA","TECHM","TATASTEEL","BAJAJFINSV","NESTLEIND",
    "HINDALCO","COALINDIA","VEDL","JSWSTEEL","SAIL","APOLLOHOSP",
    "PIDILITIND","SIEMENS","HAVELLS","VOLTAS",
]
INDEX_SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY"]

LOT_SIZES = {
    "NIFTY": 75, "BANKNIFTY": 30, "FINNIFTY": 65, "MIDCPNIFTY": 120,
    "RELIANCE": 500, "TCS": 175, "INFY": 400, "HDFCBANK": 550, "ICICIBANK": 700,
    "SBIN": 750, "ADANIENT": 300, "WIPRO": 3000, "AXISBANK": 625, "BAJFINANCE": 750,
    "HCLTECH": 350, "LT": 175, "KOTAKBANK": 2000, "TATAMOTORS": 1425, "MARUTI": 50,
    "SUNPHARMA": 350, "ITC": 1600, "ONGC": 2250, "POWERGRID": 1900, "NTPC": 1500,
    "BPCL": 1975, "GRASIM": 250, "TITAN": 175, "INDUSINDBK": 700, "ULTRACEMCO": 50,
    "HEROMOTOCO": 150, "ASIANPAINT": 250, "MM": 350, "DRREDDY": 625,
    "BAJAJFINSV": 250, "HINDALCO": 700, "TATASTEEL": 5500, "DIVISLAB": 100, "CIPLA": 375,
    "TECHM": 600, "NESTLEIND": 500, "COALINDIA": 1350, "VEDL": 1150, "JSWSTEEL": 675, "SAIL": 4700,
    "APOLLOHOSP": 125, "PIDILITIND": 500, "SIEMENS": 175, "HAVELLS": 500, "VOLTAS": 375
}

try:
    slugs_path = os.path.join(os.path.dirname(__file__), "slugs.json")
    with open(slugs_path, "r") as f:
        SLUG_MAP = json.load(f)
except Exception as e:
    print(f"FAILED TO LOAD slugs.json from {os.path.join(os.path.dirname(__file__), 'slugs.json')}: {e}")
    SLUG_MAP = {
        "NIFTY": "nifty-50-share-price",
        "BANKNIFTY": "nifty-bank-share-price",
        "FINNIFTY": "nifty-fin-service-share-price"
    }

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    
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

                sem = asyncio.Semaphore(3)
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

async def get_ind_client() -> AsyncSession:
    """
    Returns a shared, thread-safe asynchronous curl_cffi session configured
    with browser impersonation to bypass basic CDN/WAF blocks. Using a global
    session drastically reduces TLS handshake overhead for subsequent requests.
    """
    global _ind_client
    async with _ind_lock:
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

async def fetch_nse_chain(symbol: str) -> dict:
    """
    Main data retrieval function.
    Previously fetched data from official NSE endpoints. Now updated to scrape 
    the server-side rendered (SSR) HTML payload uniformly from INDmoney to 
    circumvent aggressive Akamai bot-protection and API rate limits.
    Returns the parsed option chain transformed back to the legacy NSE data schema
    so the frontend remains perfectly compatible.
    """
    slug = SLUG_MAP.get(symbol)
    if not slug:
        log.error(f"  ❌ No INDmoney slug for symbol={repr(symbol)}, in dict={symbol in SLUG_MAP}")
        return {}

    url = f"https://www.indmoney.com/options/{slug}"
    
    for attempt in range(3):
        try:
            await asyncio.sleep(attempt * 0.5)
            client = await get_ind_client()
            r = await client.get(url, timeout=10)
            log.info(f"  {symbol} → {r.status_code} len={len(r.content)} (attempt {attempt+1})")
            
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")
            if not script:
                log.warning(f"  {symbol}: __NEXT_DATA__ not found inside HTML")
                continue
                
            data = json.loads(script.string)
            oc_data = find_oc_data(data)
            
            if not oc_data:
                log.warning(f"  {symbol}: optionChainsData not found in Next.js state")
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
            return {
                "records": {
                    "underlyingValue": spot,
                    "expiryDates": expiries,
                    "data": formatted_data
                }
            }

        except Exception as e:
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
    return {"status": "ok", "version": "4.0", "time": datetime.now().isoformat()}




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
async def scan_all(limit: int = Query(48, ge=1, le=100)):
    # Check cache first for the full scan result
    cache_key = cache.cache_key("scan_result", "all", limit)
    cached = await cache.get(cache_key)
    if cached:
        log.info(f"=== SCAN: returning cached result ===")
        return cached
    
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    log.info(f"=== SCAN: {len(all_symbols)} symbols ===")

    _maybe_reset_daily()                        # Bug 6 fix: reset dedup sets on new day

    ltp_map = await fetch_indstocks_ltp(all_symbols)
    sem = asyncio.Semaphore(3)
    
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

                # ── Auto paper-trade entry  (v6: Stricter ML-refined gate) ──
                if (stock_score >= 85
                    and signal != "NEUTRAL"
                    and (ml_prob is None or (signal == "BULLISH" and ml_prob > 0.65) or (signal == "BEARISH" and ml_prob < 0.35))
                    and stats.get("vol_spike", 0) > 0.4
                    and is_market_open()
                    and is_optimal_trade_time()
                    and _daily_trade_count < MAX_DAILY_AUTO_TRADES):

                    # Sector concentration guard
                    from signals_legacy import get_sector
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
    }
    
    # Cache the result for 60 seconds
    await cache.set(cache_key, response, ttl=cache.DEFAULT_TTLS["scan_result"])
    
    return response


# ── Trade Tracker (Today's Live Trades) ───────────────────────────────────────

@app.get("/api/trade-tracker/latest")
async def get_latest_tracked_trades():
    """Returns the latest snapshot from today with all trades and their current prices."""
    latest_snapshot = db.get_latest_accuracy_snapshot()
    if not latest_snapshot:
        return {
            "status": "empty",
            "message": "No trades tracked today yet. Snapshots are taken every 15 minutes during market hours.",
            "snapshot": None,
            "trades": []
        }
    
    # Get the full details for this snapshot
    details = db.get_accuracy_snapshot_details(latest_snapshot["id"])
    if not details:
        return {
            "status": "empty",
            "message": "No trades found",
            "snapshot": latest_snapshot,
            "trades": []
        }
    
    # Add performance calculations
    for t in details["trades"]:
        entry = t.get("entry_price") or 0
        current = t.get("current_price") or entry
        # Only calculate P&L if we have valid entry price
        if entry > 0:
            t["pnl_pct"] = round(((current - entry) / entry) * 100, 2)
        else:
            t["pnl_pct"] = 0
        t["lot_value"] = round(current * (t.get("lot_size", 1) or 1), 2)
        
        # Get recent price history for 5m change
        history = db.get_accuracy_trade_history(t["id"])
        if len(history) >= 2:
            prev_entry = history[-2]
            curr_entry = history[-1]
            prev = prev_entry.get("price", 0) if isinstance(prev_entry, dict) else 0
            curr = curr_entry.get("price", 0) if isinstance(curr_entry, dict) else 0
            t["diff_5m"] = round(curr - prev, 2) if prev and curr else 0
            t["diff_5m_pct"] = round((t["diff_5m"] / prev * 100), 2) if prev > 0 else 0
        else:
            t["diff_5m"] = 0
            t["diff_5m_pct"] = 0
    
    return {
        "status": "ok",
        "snapshot": details["snapshot"],
        "trades": details["trades"],
        "trade_count": len(details["trades"])
    }

@app.get("/api/trade-tracker/today")
async def get_all_today_trades():
    """Returns all trades from all snapshots taken today."""
    trades = db.get_all_today_accuracy_trades()
    
    # Add performance calculations
    for t in trades:
        entry = t.get("entry_price") or 0
        current = t.get("current_price") or entry
        # Only calculate P&L if we have valid entry price
        if entry > 0:
            t["pnl_pct"] = round(((current - entry) / entry) * 100, 2)
        else:
            t["pnl_pct"] = 0
        t["lot_value"] = round(current * (t.get("lot_size", 1) or 1), 2)
    
    return {
        "status": "ok",
        "trades": trades,
        "trade_count": len(trades)
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


# ── Paper Trading API ────────────────────────────────────────────────────────

@app.get("/api/paper-trades/active")
async def get_active_trades():
    return db.get_open_trades()

@app.get("/api/paper-trades/history")
async def get_trade_history():
    return db.get_closed_trades()

@app.get("/api/paper-trades/stats")
async def get_trade_statistics():
    return db.get_trade_stats()

# ── Lot sizes (used by manual trade form) ────────────────────────────────────

@app.get("/api/lot-sizes")
async def get_lot_sizes():
    """Returns the lot size for every F&O symbol."""
    return LOT_SIZES

# ── Manual Paper Trade Entry ──────────────────────────────────────────────────

from pydantic import BaseModel

class ManualTradeRequest(BaseModel):
    symbol:      str
    type:        str          # "CE" or "PE"
    strike:      float
    entry_price: float
    lots:        int   = 1
    reason:      str   = "Manual"

@app.post("/api/paper-trades")
async def add_manual_trade(req: ManualTradeRequest):
    """Manually enter a paper trade with lot count."""
    if req.type not in ("CE", "PE"):
        raise HTTPException(400, "type must be CE or PE")
    if req.entry_price <= 0:
        raise HTTPException(400, "entry_price must be > 0")
    if req.lots < 1:
        raise HTTPException(400, "lots must be >= 1")

    lot_size = LOT_SIZES.get(req.symbol, 1)
    qty      = req.lots * lot_size
    reason   = f"{req.reason} | {req.lots} lot(s) × {lot_size} = {qty} qty"
    trade_id = db.add_trade(req.symbol, req.type, req.strike, req.entry_price, reason, lot_size=qty)
    return {
        "status":    "created",
        "trade_id":  trade_id,
        "symbol":    req.symbol,
        "type":      req.type,
        "strike":    req.strike,
        "entry":     req.entry_price,
        "lots":      req.lots,
        "lot_size":  lot_size,
        "qty":       req.lots * lot_size,
        "capital":   round(req.entry_price * req.lots * lot_size, 2),
    }


@app.post("/api/paper-trades/{trade_id}/exit")
async def exit_manual_trade(trade_id: int, exit_price: Optional[float] = None):
    """Exit (close) an open manual trade at a given price (defaults to current_price)."""
    with db._conn() as c:
        row = c.execute("SELECT * FROM paper_trades WHERE id=? AND status='OPEN'", (trade_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Trade not found or already closed")

    trade = dict(row)
    price = exit_price if exit_price is not None else (trade.get("current_price") or trade["entry_price"])
    db.update_trade(trade_id, price, exit_flag=True, reason="Manual exit")
    return {"status": "closed", "trade_id": trade_id, "exit_price": price}


# ── Backtester API ────────────────────────────────────────────────────────────

from pydantic import BaseModel
from typing import List

class BacktestRequest(BaseModel):
    mode: str = "live"
    symbols: List[str] = []
    tp: float = 40.0
    sl: float = 20.0
    score: float = 75.0

class TrackPickRequest(BaseModel):
    symbol: str
    type: str
    strike: float
    entry_price: float
    score: int
    stock_price: float = 0.0

@app.post("/api/track-pick")
async def track_pick(req: TrackPickRequest):
    lot_size = LOT_SIZES.get(req.symbol, 0)
    success = db.add_tracked_pick(req.symbol, req.type, req.strike, req.entry_price, req.score, req.stock_price, lot_size)
    if success:
        return {"status": "success", "message": "Option tracked."}
    else:
        return {"status": "error", "message": "Already tracking this option today."}

@app.get("/api/tracked-picks")
async def get_tracked_picks():
    picks = db.get_tracked_picks()
    return {"status": "ok", "data": picks}

@app.delete("/api/track-pick/{trade_id}")
async def untrack_pick(trade_id: int):
    success = db.delete_tracked_pick(trade_id)
    if success:
        return {"status": "success", "message": "Option untracked."}
    else:
        return {"status": "error", "message": "Failed to untrack option or it does not exist."}

@app.delete("/api/tracked-picks")
async def untrack_all_picks():
    success = db.delete_all_tracked_picks()
    if success:
        return {"status": "success", "message": "All tracked options removed."}
    else:
        return {"status": "error", "message": "Failed to untrack all options."}

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
    sem         = asyncio.Semaphore(3)

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
    sem         = asyncio.Semaphore(3)

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


# ── Portfolio P&L Dashboard ───────────────────────────────────────────────────

@app.get("/api/portfolio")
async def portfolio_dashboard():
    """
    Full portfolio view: equity curve, sector breakdown,
    win rate by signal type, max drawdown, best/worst trades.
    """
    stats      = db.get_trade_stats()
    open_trades= db.get_open_trades()

    # Unrealised PnL on open positions
    unrealised = sum(
        ((t.get("current_price") or t["entry_price"]) - t["entry_price"])
        * (t.get("lot_size") or 1)
        for t in open_trades
    )

    return {
        "closed_trades":     stats,
        "auto_stats":        db.get_trade_stats("AUTO"),
        "manual_stats":      db.get_trade_stats("MANUAL"),
        "open_positions":    len(open_trades),
        "unrealised_pnl":    round(unrealised, 2),
        "capital":           db.get_capital(),
    }


# ── Position Sizing Calculator ────────────────────────────────────────────────

@app.get("/api/position-size")
async def position_size(
    symbol:      str,
    entry_price: float,
    sl_pct:      float = 25.0,
):
    """
    Calculates how many lots to trade based on capital and risk settings.
    Uses 2% per-trade risk rule by default.
    """
    symbol   = symbol.upper()
    capital  = db.get_capital()
    lot_size = LOT_SIZES.get(symbol, 1)

    from analytics import compute_lot_size_for_risk
    sizing = compute_lot_size_for_risk(capital, entry_price, lot_size, 2.0, sl_pct)
    return {
        "symbol":    symbol,
        "capital":   capital,
        "lot_size":  lot_size,
        **sizing,
    }


# ── Trade Journal ─────────────────────────────────────────────────────────────

@app.post("/api/paper-trades/{trade_id}/note")
async def add_note(trade_id: int, note: str):
    """Add a journal note to a trade."""
    db.add_trade_note(trade_id, note)
    return {"status": "ok"}

@app.get("/api/paper-trades/{trade_id}/notes")
async def get_notes(trade_id: int):
    """Get all journal notes for a trade."""
    return {"notes": db.get_trade_notes(trade_id)}


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


# ── CSV Export ────────────────────────────────────────────────────────────────

from fastapi.responses import StreamingResponse
import csv, io

CSV_HEADERS = [
    "id", "symbol", "type", "strike", "entry_price", "current_price",
    "exit_price", "status", "pnl", "pnl_pct", "reason", "created_at", "updated_at"
]

@app.get("/api/paper-trades/export")
async def export_trades():
    """Exports all paper trades as a CSV file. Returns empty CSV with headers if no trades."""
    trades = db.get_all_trades()
    output = io.StringIO()

    if trades:
        writer = csv.DictWriter(output, fieldnames=trades[0].keys(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    else:
        # Return empty CSV with standard headers so the download still works
        writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
        writer.writeheader()

    output.seek(0)
    filename = f"fo_scanner_trades_{datetime.now(IST).strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
    sem = asyncio.Semaphore(3)

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
# Strategy Builder / Backtest Endpoint
# ══════════════════════════════════════════════════════════════════════════════

class BacktestParams(BaseModel):
    symbol: str = "NIFTY"
    regime_filter: List[str] = ["TRENDING", "SQUEEZE"]
    min_score: float = 0.6
    strategy_type: str = "SHORT_STRADDLE"
    entry_time: str = "10:00"
    exit_time: str = "15:00"
    stop_loss_pct: float = 50.0
    target_pct: float = 75.0
    lookback_days: int = 90
    lot_size: int = 1


@app.post("/api/backtest/run")
async def run_backtest_endpoint(params: BacktestParams):
    """
    Run backtest with user-provided parameters from Strategy Builder UI.
    Returns equity curve + trade log as JSON.
    """
    from backtest_runner import run_strategy_backtest
    results = await asyncio.to_thread(
        run_strategy_backtest,
        symbol=params.symbol,
        regime_filter=params.regime_filter,
        min_score=params.min_score,
        strategy_type=params.strategy_type,
        entry_time=params.entry_time,
        exit_time=params.exit_time,
        stop_loss_pct=params.stop_loss_pct,
        target_pct=params.target_pct,
        lookback_days=params.lookback_days,
        lot_size=params.lot_size,
    )
    return results


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


