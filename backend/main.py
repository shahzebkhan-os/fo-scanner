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
from analytics import score_option, compute_stock_score, nearest_atm

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

async def paper_trade_manager():
    """Background task to manage open paper trades."""
    log.info("Started Paper Trade Manager background loop.")
    while True:
        try:
            if not is_market_open():
                await asyncio.sleep(300)
                continue

            open_trades = db.get_open_trades()
            tracked_picks = db.get_tracked_picks()
            all_to_check = open_trades + tracked_picks
            if all_to_check:
                    log.info(f"Checking {len(open_trades)} OPEN paper trades and {len(tracked_picks)} TRACKED picks...")
                    symbols = list(set([t['symbol'] for t in all_to_check]))
                    
                    sem = asyncio.Semaphore(3)
                    async def fetch_and_update(sym):
                        async with sem:
                            try:
                                chain_data = await fetch_nse_chain(sym)
                                return sym, chain_data
                            except Exception as e:
                                log.error(f"Failed to fetch {sym} for paper trading: {e}")
                                return sym, None
                                
                    results = await asyncio.gather(*[fetch_and_update(s) for s in symbols])
                    chain_map = {sym: data for sym, data in results if data}
                    
                    for trade in all_to_check:
                        sym = trade['symbol']
                        chain = chain_map.get(sym)
                        if not chain: continue
                        
                        records = chain.get("records", {}).get("data", [])
                        spot = chain.get("records", {}).get("underlyingValue")
                        if not records or not spot: continue
                        
                        current_price = None
                        for row in records:
                            if row.get("strikePrice") == trade['strike']:
                                opt_data = row.get("CE") if trade['type'] == "CE" else row.get("PE")
                                if opt_data:
                                    current_price = opt_data.get("lastPrice")
                                break
                                
                        if current_price:
                            if trade['status'] == 'TRACKED':
                                db.update_tracked_pick(trade['id'], current_price, stock_price=spot)
                            else:
                                db.update_trade(trade['id'], current_price)
                                pnl_pct = ((current_price - trade['entry_price']) / trade['entry_price']) * 100
                                
                                now = datetime.now(IST)
                                if now.time() >= dtime(15, 15):
                                    db.update_trade(trade['id'], current_price, exit_flag=True, reason="EOD Square Off")
                                    continue
                                    
                                if pnl_pct <= -20:
                                    db.update_trade(trade['id'], current_price, exit_flag=True, reason="Stop Loss (-20%)")
                                    continue
                                    
                                if pnl_pct >= 40:
                                    db.update_trade(trade['id'], current_price, exit_flag=True, reason="Take Profit (+40%)")
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

@app.get("/api/scan")
async def scan_all(limit: int = Query(48, ge=1, le=100)):
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    log.info(f"=== SCAN: {len(all_symbols)} symbols ===")
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
                stats    = compute_stock_score(cj, spot or 1, symbol=symbol)
                if spot == 0: return None
                
                # Telegram Alerts & Auto-Log for high-scoring setups
                if stats.get("score", 0) >= 80 and is_market_open():
                    for pick in stats.get("top_picks", []):
                        opt_type = pick["type"]
                        strike = pick["strike"]
                        entry_price = pick["ltp"]
                        reason = f"Top Pick {opt_type} @ {strike} (Score: {stats['score']})"
                        db.add_trade(symbol, opt_type, strike, entry_price, reason)
                        
                if stats.get("score", 0) >= 70:
                    for pick in stats.get("top_picks", []):
                        opt_type = pick["type"]
                        strike = pick["strike"]
                        uid = f"{symbol}-{opt_type}-{strike}-{datetime.now().date()}"
                        
                        if pick.get("score", 0) >= 70 and not db.is_signal_notified(uid):
                            db.mark_signal_notified(uid)
                            msg = f"🚀 *HIGH CONFIDENCE ALERT*\n\n" \
                                  f"Symbol: *{symbol}*\n" \
                                  f"Contract: *{strike} {opt_type}*\n" \
                                  f"LTP: ₹{pick['ltp']}\n" \
                                  f"Score: *{pick['score']}*\n\n" \
                                  f"Signal: {stats.get('signal', 'UNKNOWN')}\n" \
                                  f"Volume Spike: {stats.get('vol_spike', 0)}x\n"
                            # Schedule background execution so it doesn't block the scanner
                            asyncio.create_task(send_telegram_alert(msg))

                return {
                    "symbol":     symbol,
                    "ltp":        round(spot, 2),
                    "volume":     live.get("volume", 0),
                    "change_pct": round(live.get("change", 0), 2),
                    "expiries":   expiries[:4],
                    **stats,
                }
            except Exception as e:
                log.error(f"  {symbol}: {e}")
                return None

    raw    = await asyncio.gather(*[process(s) for s in all_symbols[:limit]])
    result = [r for r in raw if r]
    result.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"=== SCAN DONE: {len(result)} stocks ===")
    return {"timestamp": datetime.now().isoformat(), "market_status": market_status(), "count": len(result), "data": result}


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
