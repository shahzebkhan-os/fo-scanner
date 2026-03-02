"""
NSE F&O Option Chain Scanner — Backend v3 (Akamai fix)
"""

import os, time, asyncio, logging
from typing import Optional
from datetime import datetime
import json
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

import httpx, uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

# Secure token logic: fallback to empty instead of hardcoding production secrets
INDSTOCKS_TOKEN = os.getenv("INDSTOCKS_TOKEN", "")
INDSTOCKS_BASE  = "https://api.indstocks.com/v1"
NSE_BASE        = "https://www.nseindia.com"

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

try:
    with open("slugs.json", "r") as f:
        SLUG_MAP = json.load(f)
except Exception:
    logging.warning("slugs.json not found, some stocks may fail.")
    SLUG_MAP = {
        "NIFTY": "nifty-50-share-price",
        "BANKNIFTY": "nifty-bank-share-price",
        "FINNIFTY": "nifty-fin-service-share-price"
    }

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

app = FastAPI(title="NSE F&O Scanner API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
        log.error(f"  ❌ No INDmoney slug for {symbol}")
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


def score_option(side: dict, spot: float) -> int:
    oi     = side.get("openInterest", 0)
    oi_chg = side.get("changeinOpenInterest", 0)
    vol    = side.get("totalTradedVolume", 0)
    iv     = side.get("impliedVolatility", 0)
    strike = side.get("strikePrice", 0)
    score  = 0
    score += min(30, max(0, (oi_chg / oi * 100) if oi > 0 else 0) * 2)
    score += min(20, vol / 10_000 * 20)
    if iv > 0:
        score += max(0, 20 - iv * 0.3)
    if spot > 0 and strike > 0:
        score += max(0, 30 - abs(spot - strike) / spot * 100 * 6)
    return min(100, int(score))


def compute_stock_score(chain_data: dict, spot: float) -> dict:
    records = chain_data.get("records", {}).get("data", [])
    if not records:
        return dict(pcr=1.0, iv=0, oi_change=0, vol_spike=0.0, signal="NEUTRAL", score=0)

    tce_oi = tpe_oi = tce_vol = tpe_vol = 0
    oi_changes = []; atm_iv = 0
    atm_strike = round(spot / 50) * 50

    for row in records:
        ce = row.get("CE", {}); pe = row.get("PE", {})
        tce_oi  += ce.get("openInterest", 0)
        tpe_oi  += pe.get("openInterest", 0)
        tce_vol += ce.get("totalTradedVolume", 0)
        tpe_vol += pe.get("totalTradedVolume", 0)
        for s in [ce, pe]:
            oi = s.get("openInterest", 0)
            if oi > 0:
                oi_changes.append(s.get("changeinOpenInterest", 0) / oi * 100)
        if abs(row.get("strikePrice", 0) - atm_strike) < 60:
            atm_iv = ce.get("impliedVolatility") or pe.get("impliedVolatility") or 0

    pcr       = round(tpe_oi / tce_oi, 2) if tce_oi > 0 else 1.0
    avg_oi    = round(sum(oi_changes) / len(oi_changes), 2) if oi_changes else 0
    vol_spike = round((tce_vol + tpe_vol) / max(1, tce_oi) * 10, 2)
    signal    = "BULLISH" if pcr > 1.3 else "BEARISH" if pcr < 0.8 else "NEUTRAL"
    score     = min(100, int(
        (vol_spike * 8) + (abs(avg_oi) * 2) +
        (20 if signal == "BULLISH" else 15 if signal == "BEARISH" else 5) +
        (15 if 0 < atm_iv < 25 else 5 if atm_iv > 50 else 10)
    ))
    return dict(pcr=pcr, iv=round(atm_iv, 1), oi_change=avg_oi,
                vol_spike=vol_spike, signal=signal, score=score)


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
                stats    = compute_stock_score(cj, spot or 1)
                if spot == 0: return None
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
    return {"timestamp": datetime.now().isoformat(), "count": len(result), "data": result}


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
                "score":      score_option(ce, spot),
            },
            "PE": {
                "ltp":        pe.get("lastPrice", 0),
                "iv":         pe.get("impliedVolatility", 0),
                "oi":         pe_oi,
                "oi_chg":     pe_c,
                "oi_chg_pct": round(pe_c / max(1, pe_oi) * 100, 1),
                "volume":     pe.get("totalTradedVolume", 0),
                "score":      score_option(pe, spot),
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
