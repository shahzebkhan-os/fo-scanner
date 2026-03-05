"""
NSE F&O Option Chain Scanner — Backend v3 (Akamai fix)
"""

import os, time, asyncio, logging
from typing import Optional
from datetime import datetime, time as dtime
import json
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import db
import analytics as Analytics
import signals as Signals
import scheduler as Scheduler
from analytics import compute_stock_score, score_option, black_scholes_greeks, days_to_expiry
from signals import build_sector_heatmap, detect_uoa, screen_straddle, get_pcr_history
import db

# ── Deduplication sets (in-memory, keyed by date so they reset daily) ────────
# Bug 6 fix: tracks which trades have already been entered today
# Bug 5 fix: separate sets for trades vs alerts so thresholds are independent
_traded_today: set  = set()   # "SYMBOL-TYPE-STRIKE-DATE"
notified_signals: set = set() # "SYMBOL-TYPE-STRIKE-DATE"

def _reset_daily_sets():
    """Called at the start of each new trading day."""
    global _traded_today, notified_signals
    _traded_today.clear()
    notified_signals.clear()

_last_reset_date = None

def _maybe_reset_daily():
    global _last_reset_date
    today = datetime.now(IST).date()
    if _last_reset_date != today:
        _last_reset_date = today
        _reset_daily_sets()


# ── Strike interval per symbol (for accurate ATM proximity scoring) ───────────
# Bug 1 fix: replaces the hardcoded /50 in compute_stock_score
STRIKE_INTERVALS = {
    "NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50, "MIDCPNIFTY": 25,
    "RELIANCE": 20, "TCS": 50, "INFY": 20, "HDFCBANK": 10, "ICICIBANK": 10,
    "SBIN": 5, "ADANIENT": 50, "WIPRO": 5, "AXISBANK": 10, "BAJFINANCE": 50,
    "HCLTECH": 20, "LT": 20, "KOTAKBANK": 20, "TATAMOTORS": 5, "MARUTI": 100,
    "SUNPHARMA": 20, "ITC": 5, "ONGC": 5, "POWERGRID": 5, "NTPC": 5,
    "BPCL": 10, "GRASIM": 20, "TITAN": 50, "INDUSINDBK": 10, "ULTRACEMCO": 50,
    "HEROMOTOCO": 50, "ASIANPAINT": 50, "MM": 20, "DRREDDY": 50, "DIVISLAB": 50,
    "CIPLA": 10, "TECHM": 20, "TATASTEEL": 5, "BAJAJFINSV": 20, "NESTLEIND": 100,
    "HINDALCO": 5, "COALINDIA": 5, "VEDL": 5, "JSWSTEEL": 10, "SAIL": 2,
    "APOLLOHOSP": 50, "PIDILITIND": 50, "SIEMENS": 50, "HAVELLS": 20, "VOLTAS": 20,
}

def _get_interval(symbol: str) -> int:
    return STRIKE_INTERVALS.get(symbol.upper(), 10)

def _nearest_atm(spot: float, symbol: str) -> float:
    iv = _get_interval(symbol)
    return round(spot / iv) * iv


# ══════════════════════════════════════════════════════════════════════════════
# 1.  score_option  — fixed
# ══════════════════════════════════════════════════════════════════════════════
# Bugs fixed:
#   #1  strikePrice was always 0 (ATM proximity always scored 0)
#   #3  volume baseline 10,000 was meaningless; now uses V/OI ratio
#   #4  IV scoring rewarded near-zero IV; now rewards 15-40 sweet spot

def score_option(side: dict, spot: float, symbol: str = "") -> int:
    """
    Score a single CE or PE option contract [0–100].

    Caller MUST inject strikePrice into the dict before calling:
        score_option({**ce_dict, "strikePrice": strike}, spot, symbol)

    Components:
      30 pts  OI momentum   — % OI build-up (requires oi > 100 guard)
      25 pts  Activity      — V/OI ratio (self-scaling, works for all symbols)
      20 pts  ATM proximity — decays over per-symbol strike intervals
      15 pts  IV quality    — rewards 15–40 IV sweet spot
      10 pts  Liquidity     — non-zero LTP guard
    """
    oi     = side.get("openInterest", 0) or 0
    oi_chg = side.get("changeinOpenInterest", 0) or 0
    vol    = side.get("totalTradedVolume", 0) or 0
    iv     = side.get("impliedVolatility", 0) or 0
    ltp    = side.get("lastPrice", 0) or 0
    strike = side.get("strikePrice", 0) or 0   # ← Bug 1 fix: caller must inject this

    score = 0

    # 1. OI momentum: % build-up
    if oi > 100:                                        # minimum OI guard avoids ÷0 noise
        oi_pct = (oi_chg / oi) * 100
        score += int(min(30, max(0, oi_pct * 1.5)))    # 20% build-up → 30 pts

    # 2. Activity: V/OI ratio — self-scaling across all symbols  (Bug 3 fix)
    if oi > 0:
        v_oi = vol / oi
        score += int(min(25, v_oi * 20))                # V/OI=1.25 → full 25 pts

    # 3. ATM proximity using per-symbol interval  (Bug 1 fix)
    if spot > 0 and strike > 0:
        interval   = _get_interval(symbol) if symbol else 10
        bands_away = abs(spot - strike) / max(interval, 1)
        prox       = max(0.0, 1.0 - bands_away / 6.0)  # 0 pts beyond 6 strikes away
        score     += int(prox * 20)

    # 4. IV quality — sweet spot 15–40  (Bug 4 fix)
    if iv > 0:
        if 15 <= iv <= 40:
            score += 15
        elif iv < 15:
            score += int(iv / 15 * 10)                  # ramping: near-zero IV = near-zero pts
        else:
            score += max(0, int(15 - (iv - 40) * 0.35)) # penalise very high IV gradually

    # 5. Liquidity guard — zero-price = untradeable
    if ltp > 0:
        score += 10

    return min(100, max(0, score))


# ══════════════════════════════════════════════════════════════════════════════
# 2.  compute_stock_score  — fixed
# ══════════════════════════════════════════════════════════════════════════════
# Bugs fixed:
#   #1  ATM used round(spot/50)*50 — now uses per-symbol interval
#   #2  vol_spike divided only by CE OI — now uses total OI
#   #5  Signal was PCR-only and BEARISH scored less than BULLISH

def compute_stock_score(chain_data: dict, spot: float, symbol: str = "") -> dict:
    """
    Returns composite stock-level analysis dict:
        pcr, iv, oi_change, vol_spike (V/OI), signal, score [0-100],
        top_picks, signal_reasons
    """
    records = chain_data.get("records", {}).get("data", [])

    _empty = dict(
        pcr=1.0, iv=0, oi_change=0, vol_spike=0.0,
        signal="NEUTRAL", score=0, top_picks=[], signal_reasons=[]
    )
    if not records or spot <= 0:
        return _empty

    # Bug 1 fix: per-symbol ATM + band
    atm_strike = _nearest_atm(spot, symbol)
    interval   = _get_interval(symbol)
    atm_band   = interval * 3                       # ±3 strikes = near-the-money zone

    tce_oi = tpe_oi = tce_vol = tpe_vol = 0
    tce_oi_chg = tpe_oi_chg = 0
    oi_changes: list = []
    atm_iv_ce = atm_iv_pe = 0.0
    all_options: list = []

    for row in records:
        ce     = row.get("CE", {}) or {}
        pe     = row.get("PE", {}) or {}
        strike = row.get("strikePrice", 0) or 0

        # Bug 1 fix: inject strikePrice so score_option can use it
        ce_scored = {**ce, "strikePrice": strike}
        pe_scored = {**pe, "strikePrice": strike}

        ce_oi  = ce.get("openInterest", 0) or 0
        pe_oi  = pe.get("openInterest", 0) or 0
        ce_vol = ce.get("totalTradedVolume", 0) or 0
        pe_vol = pe.get("totalTradedVolume", 0) or 0
        ce_chg = ce.get("changeinOpenInterest", 0) or 0
        pe_chg = pe.get("changeinOpenInterest", 0) or 0

        tce_oi     += ce_oi;    tpe_oi     += pe_oi
        tce_vol    += ce_vol;   tpe_vol    += pe_vol
        tce_oi_chg += ce_chg;   tpe_oi_chg += pe_chg

        for oi, chg in [(ce_oi, ce_chg), (pe_oi, pe_chg)]:
            if oi > 100:
                oi_changes.append(chg / oi * 100)

        if abs(strike - atm_strike) <= atm_band:
            if ce.get("impliedVolatility"):
                atm_iv_ce = float(ce["impliedVolatility"])
            if pe.get("impliedVolatility"):
                atm_iv_pe = float(pe["impliedVolatility"])

        # Bug 1 fix: pass symbol so score_option uses correct interval
        ce_s = score_option(ce_scored, spot, symbol)
        pe_s = score_option(pe_scored, spot, symbol)

        # Bug 6 pre-condition: only keep liquid options in top_picks
        if ce.get("lastPrice", 0) > 0:
            all_options.append({"type": "CE", "strike": strike,
                                 "ltp": ce["lastPrice"], "score": ce_s})
        if pe.get("lastPrice", 0) > 0:
            all_options.append({"type": "PE", "strike": strike,
                                 "ltp": pe["lastPrice"], "score": pe_s})

    # ── Derived metrics ───────────────────────────────────────────────────────

    pcr       = round(tpe_oi / tce_oi, 3) if tce_oi > 0 else 1.0
    avg_oi    = round(sum(oi_changes) / len(oi_changes), 2) if oi_changes else 0.0
    total_oi  = tce_oi + tpe_oi
    total_vol = tce_vol + tpe_vol

    # Bug 2 fix: divide by TOTAL OI, not just CE OI
    vol_spike = round(total_vol / max(1, total_oi), 3)

    # ATM IV: prefer average of CE+PE, fallback to whichever exists
    if atm_iv_ce and atm_iv_pe:
        atm_iv = round((atm_iv_ce + atm_iv_pe) / 2, 1)
    else:
        atm_iv = round(atm_iv_ce or atm_iv_pe, 1)

    # ── Signal: multi-factor voting  (Bug 5 fix) ─────────────────────────────
    bullish_votes = bearish_votes = 0
    reasons: list = []

    # Factor 1 — PCR
    if pcr > 1.4:
        bullish_votes += 2
        reasons.append(f"PCR {pcr} → heavy put writing (bullish)")
    elif pcr > 1.1:
        bullish_votes += 1
        reasons.append(f"PCR {pcr} mildly elevated (bullish lean)")
    elif pcr < 0.7:
        bearish_votes += 2
        reasons.append(f"PCR {pcr} → heavy call writing (bearish)")
    elif pcr < 0.9:
        bearish_votes += 1
        reasons.append(f"PCR {pcr} suppressed (bearish lean)")

    # Factor 2 — Net OI change direction
    if tce_oi_chg > 0 and tpe_oi_chg < 0:
        bearish_votes += 1
        reasons.append("CE OI building + PE OI unwinding → bearish pressure")
    elif tpe_oi_chg > 0 and tce_oi_chg < 0:
        bullish_votes += 1
        reasons.append("PE OI building + CE OI unwinding → bullish support")
    elif tpe_oi_chg > 0 and tce_oi_chg > 0:
        reasons.append("Both sides building OI → range-bound / straddle territory")

    # Factor 3 — Volume dominance
    if total_vol > 0:
        ce_dom = tce_vol / total_vol
        pe_dom = tpe_vol / total_vol
        if ce_dom > 0.62:
            bearish_votes += 1
            reasons.append(f"CE volume {ce_dom:.0%} dominant → bearish activity")
        elif pe_dom > 0.62:
            bullish_votes += 1
            reasons.append(f"PE volume {pe_dom:.0%} dominant → bullish activity")

    if   bullish_votes > bearish_votes: signal = "BULLISH"
    elif bearish_votes > bullish_votes: signal = "BEARISH"
    else:                               signal = "NEUTRAL"

    confidence = max(bullish_votes, bearish_votes)

    # ── Composite score  (Bug 5 fix: BULLISH and BEARISH weighted equally) ───
    activity_score = min(30, vol_spike / 1.5 * 30)           # V/OI component
    oi_mom_score   = min(20, abs(avg_oi) * 1.5)              # OI momentum
    iv_score       = (20 if 15 <= atm_iv <= 40 else          # IV quality
                      int(atm_iv / 15 * 15) if 0 < atm_iv < 15 else
                      max(0, int(20 - (atm_iv - 40) * 0.4)) if atm_iv > 40 else 5)
    signal_score   = confidence * 8                          # 0/8/16/24 pts — same for BULL/BEAR

    score = min(100, max(0, int(activity_score + oi_mom_score + iv_score + signal_score)))

    # Top picks: sorted by option score, liquid only
    top_picks = sorted(all_options, key=lambda x: x["score"], reverse=True)[:2]

    return dict(
        pcr            = pcr,
        iv             = atm_iv,
        oi_change      = avg_oi,
        vol_spike      = vol_spike,
        signal         = signal,
        score          = score,
        top_picks      = top_picks,
        signal_reasons = reasons,
    )

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
    task = asyncio.create_task(paper_trade_manager())
    yield
    task.cancel()

app = FastAPI(title="NSE F&O Scanner API", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Market Hours ──────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    """NSE is open Mon–Fri, 9:15 AM – 3:30 PM IST."""
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)

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
    if not INDSTOCKS_TOKEN or INDSTOCKS_TOKEN == "PASTE_YOUR_NEW_TOKEN_HERE":
        log.warning("IndStocks token not set — skipping live LTP")
        return {}

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
                log.warning(f"IndStocks error: {e}")
    return results





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
                stats = compute_stock_score(cj, spot, symbol, exp, ivr)
                return {"symbol": symbol, "ltp": spot, **stats}
            except: return None
    raw = await asyncio.gather(*[process(s) for s in all_symbols])
    return [r for r in raw if r]

@app.get("/api/debug-slugs")
async def debug_slugs():
    return {"slugs_len": len(SLUG_MAP), "RELIANCE_in_map": "RELIANCE" in SLUG_MAP, "keys": list(SLUG_MAP.keys())}

@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0", "time": datetime.now().isoformat()}




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
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    log.info(f"=== SCAN: {len(all_symbols)} symbols ===")

    _maybe_reset_daily()                        # Bug 6 fix: reset dedup sets on new day

    ltp_map = await fetch_indstocks_ltp(all_symbols)
    sem = asyncio.Semaphore(3)

    async def process(symbol: str):
        async with sem:
            live = ltp_map.get(symbol, {})
            try:
                cj       = await fetch_nse_chain(symbol)
                records  = cj.get("records", {})
                spot     = records.get("underlyingValue") or live.get("ltp") or 0
                expiries = records.get("expiryDates", [])

                # Bug 1 fix: pass symbol into compute_stock_score
                stats = compute_stock_score(cj, spot or 1, symbol=symbol)
                if spot == 0:
                    return None

                stock_score  = stats.get("score", 0)
                signal       = stats.get("signal", "NEUTRAL")
                top_picks    = stats.get("top_picks", [])

                # ── Auto paper-trade entry  (Bugs 6 & 7 fixed) ───────────────
                if stock_score >= 80 and is_market_open() and signal != "NEUTRAL":
                    for pick in top_picks:
                        # Bug 7 fix: only enter the side matching the signal
                        if signal == "BULLISH" and pick["type"] != "CE": continue
                        if signal == "BEARISH" and pick["type"] != "PE": continue

                        opt_type    = pick["type"]
                        strike      = pick["strike"]
                        entry_price = pick["ltp"]

                        # Bug 6 fix: dedup by symbol+type+strike+date
                        trade_uid = f"{symbol}-{opt_type}-{strike}-{datetime.now(IST).date()}"
                        if trade_uid in _traded_today:
                            continue
                        _traded_today.add(trade_uid)

                        reason = f"Auto: {signal} score={stock_score}"
                        db.add_trade(symbol, opt_type, strike, entry_price, reason)
                        log.info(f"  📝 Auto-trade: {symbol} {opt_type} {strike} @ ₹{entry_price}")

                # ── Telegram alerts  (Bug 9 fixed: separate thresholds) ───────
                # Stock must score ≥ 70, AND the specific option must score ≥ 60
                if stock_score >= 70:
                    for pick in top_picks:
                        # Bug 9 fix: option score threshold is lower than stock threshold
                        if pick.get("score", 0) < 60:
                            continue

                        opt_type = pick["type"]
                        strike   = pick["strike"]
                        uid      = f"{symbol}-{opt_type}-{strike}-{datetime.now(IST).date()}"

                        if uid not in notified_signals:
                            notified_signals.add(uid)
                            reasons_text = "\n".join(
                                f"  • {r}" for r in stats.get("signal_reasons", [])
                            ) or "  • No specific reason"
                            msg = (
                                f"🚀 *HIGH CONFIDENCE ALERT*\n\n"
                                f"Symbol: *{symbol}*\n"
                                f"Contract: *{strike} {opt_type}*\n"
                                f"LTP: ₹{pick['ltp']}\n"
                                f"Option Score: *{pick['score']}* | Stock Score: *{stock_score}*\n\n"
                                f"Signal: *{signal}*\n"
                                f"PCR: {stats.get('pcr')} | V/OI: {stats.get('vol_spike')}x\n\n"
                                f"Reasons:\n{reasons_text}"
                            )
                            asyncio.create_task(send_telegram_alert(msg))

                return {
                    "symbol":         symbol,
                    "ltp":            round(spot, 2),
                    "volume":         live.get("volume", 0),
                    "change_pct":     round(live.get("change", 0), 2),
                    "expiries":       expiries[:4],
                    "signal_reasons": stats.get("signal_reasons", []),
                    **{k: v for k, v in stats.items() if k != "signal_reasons"},
                }

            except Exception as e:
                log.error(f"  {symbol}: {e}")
                return None

    raw    = await asyncio.gather(*[process(s) for s in all_symbols[:limit]])
    result = [r for r in raw if r]
    result.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"=== SCAN DONE: {len(result)} stocks ===")
    return {
        "timestamp":     datetime.now().isoformat(),
        "market_status": market_status(),
        "count":         len(result),
        "data":          result,
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
                "score":      score_option({**ce, "strikePrice": strike}, spot, symbol),
            },
            "PE": {
                "ltp":        pe.get("lastPrice", 0),
                "iv":         pe.get("impliedVolatility", 0),
                "oi":         pe_oi,
                "oi_chg":     pe_c,
                "oi_chg_pct": round(pe_c / max(1, pe_oi) * 100, 1),
                "volume":     pe.get("totalTradedVolume", 0),
                "score":      score_option({**pe, "strikePrice": strike}, spot, symbol),
            },
        })

    top_ce = sorted(strikes, key=lambda x: x["CE"]["score"], reverse=True)[:2]
    top_pe = sorted(strikes, key=lambda x: x["PE"]["score"], reverse=True)[:2]
    top_picks = sorted(
        [{"type":"CE","strike":r["strike"],**r["CE"]} for r in top_ce] +
        [{"type":"PE","strike":r["strike"],**r["PE"]} for r in top_pe],
        key=lambda x: x["score"], reverse=True
    )

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
                stats   = compute_stock_score(chain, spot, symbol, exp, ivr)
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
    results     = await _internal_scan()
    heatmap     = build_sector_heatmap(results)
    deals_map   = Signals.get_deals_for_scan(results)

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
        (t.get("current_price", t["entry_price"]) - t["entry_price"])
        * (t.get("lot_size") or 1)
        for t in open_trades
    )

    return {
        "closed_trades":     stats,
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

@app.get("/api/paper-trades/export")
async def export_trades():
    """Exports all paper trades as a CSV file."""
    trades = db.get_all_trades()
    if not trades:
        raise HTTPException(404, "No trades to export")

    output  = io.StringIO()
    writer  = csv.DictWriter(output, fieldnames=trades[0].keys())
    writer.writeheader()
    writer.writerows(trades)
    output.seek(0)

    filename = f"fo_scanner_trades_{date.today().isoformat()}.csv"
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")

# End of file


