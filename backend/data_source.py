import json
import logging
import asyncio
import httpx
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
import os
from .constants import SLUG_MAP, INDSTOCKS_BASE, NSE_BASE

log = logging.getLogger(__name__)

_ind_client = None
_ind_lock = asyncio.Lock()

async def get_ind_client() -> AsyncSession:
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
    slug = SLUG_MAP.get(symbol)
    if not slug:
        log.info(f"  ℹ️ Skipping INDmoney fetch: No slug for {symbol}")
        return {}

    url = f"https://www.indmoney.com/options/{slug}"
    
    for attempt in range(3):
        try:
            await asyncio.sleep(attempt * 0.5)
            client = await get_ind_client()
            r = await client.get(url, timeout=10)
            
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")
            if not script:
                continue
                
            data = json.loads(script.string)
            oc_data = find_oc_data(data)
            
            if not oc_data:
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

            return {
                "records": {
                    "underlyingValue": spot,
                    "expiryDates": expiries,
                    "data": formatted_data
                }
            }
        except Exception as e:
            log.warning(f"  Error {symbol} attempt {attempt+1}: {e}")

    return {}

async def fetch_indstocks_ltp(symbols: list, token: str = "") -> dict:
    results = await _fetch_nse_market_watch(symbols)
    if results:
        return results

    # Commented out dead IndStocks API to prevent 404s
    # if token and token not in ("", "PASTE_YOUR_NEW_TOKEN_HERE"):
    #     results = await _fetch_indstocks_ltp_v1(symbols, token)
    return results

async def _fetch_nse_market_watch(symbols: list) -> dict:
    INDEX_MAP = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "FINNIFTY": "NIFTY FIN SERVICE"}
    results = {}
    try:
        nse_headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/market-data/live-equity-market",
        }
        async with httpx.AsyncClient(timeout=10, headers=nse_headers) as client:
            await client.get("https://www.nseindia.com", timeout=6)
            fo_symbols = [s for s in symbols if s not in INDEX_MAP]
            if fo_symbols:
                r = await client.get("https://www.nseindia.com/api/equity-stockIndices", params={"index": "SECURITIES IN F&O"}, timeout=8)
                if r.status_code == 200:
                    for item in r.json().get("data", []):
                        sym = item.get("symbol", "")
                        if sym in symbols:
                            results[sym] = {"ltp": item.get("lastPrice", 0), "volume": item.get("totalTradedVolume", 0), "change": item.get("pChange", 0)}

            for sym, index_name in INDEX_MAP.items():
                if sym not in symbols: continue
                r = await client.get("https://www.nseindia.com/api/equity-stockIndices", params={"index": index_name}, timeout=6)
                if r.status_code == 200:
                    meta = r.json().get("metadata", {})
                    results[sym] = {"ltp": meta.get("last", 0), "volume": 0, "change": meta.get("percChange", 0)}
    except Exception as e:
        log.warning(f"NSE market watch error: {e}")
    return results

async def _fetch_indstocks_ltp_v1(symbols: list, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    async with httpx.AsyncClient(timeout=12) as client:
        for i in range(0, len(symbols), 50):
            batch = [f"NSE_{s}" for s in symbols[i:i+50]]
            try:
                r = await client.get(f"{INDSTOCKS_BASE}/market/quotes/full", params={"scrip-codes": ",".join(batch)}, headers=headers)
                r.raise_for_status()
                for item in r.json().get("data", []):
                    code = item.get("scripCode", "").replace("NSE_", "")
                    results[code] = {"ltp": item.get("lastPrice", 0), "volume": item.get("totalTradedVolume", 0), "change": item.get("pChange", 0)}
            except Exception: pass
    return results
