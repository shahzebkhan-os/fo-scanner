"""
signals.py — Advanced Signal Detection v4
  - Unusual Options Activity (UOA) detector
  - Straddle / Strangle screener
  - Sector grouping & heatmap
  - NSE Bulk/Block deals fetcher
  - PCR history aggregator
"""

from __future__ import annotations
import asyncio, logging
from datetime import date, datetime
from typing import Optional
import httpx
from . import db

log = logging.getLogger(__name__)

# ── Sector Map ────────────────────────────────────────────────────────────────
SECTORS: dict[str, list[str]] = {
    "Banking":    ["HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK",
                   "INDUSINDBK", "BANKBARODA", "FEDERALBNK"],
    "IT":         ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM", "MPHASIS"],
    "Auto":       ["TATAMOTORS", "MARUTI", "MM", "HEROMOTOCO", "BAJAJ-AUTO", "EICHERMOT"],
    "Pharma":     ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "BIOCON"],
    "Energy":     ["RELIANCE", "ONGC", "BPCL", "NTPC", "POWERGRID", "COALINDIA"],
    "Metal":      ["TATASTEEL", "HINDALCO", "JSWSTEEL", "SAIL", "VEDL", "NMDC"],
    "Finance":    ["BAJFINANCE", "BAJAJFINSV", "HDFC", "LICHSGFIN", "MUTHOOTFIN"],
    "Consumer":   ["ITC", "NESTLEIND", "HINDUNILVR", "TITAN", "ASIANPAINT",
                   "PIDILITIND", "HAVELLS", "VOLTAS"],
    "Capital":    ["LT", "SIEMENS", "ABB", "BHEL", "ADANIENT"],
    "Cement":     ["ULTRACEMCO", "GRASIM", "ACC", "AMBUJACEM", "SHREECEM"],
}

# Reverse lookup: symbol → sector
SYMBOL_SECTOR: dict[str, str] = {
    sym: sector
    for sector, syms in SECTORS.items()
    for sym in syms
}

def get_sector(symbol: str) -> str:
    return SYMBOL_SECTOR.get(symbol.upper(), "Other")


# ══════════════════════════════════════════════════════════════════════════════
# Unusual Options Activity (UOA)
# ══════════════════════════════════════════════════════════════════════════════

def detect_uoa(
    records:  list,
    symbol:   str,
    spot:     float,
    threshold: float = 5.0,   # volume must be N× the 5-day average
) -> list[dict]:
    """
    Flags strikes where today's volume is ≥ threshold × 5-day average volume.
    Returns list of UOA events sorted by volume ratio descending.
    """
    uoa_events = []

    for row in records:
        strike = row.get("strikePrice", 0)
        for side in ["CE", "PE"]:
            sd = row.get(side, {}) or {}
            vol = sd.get("totalTradedVolume", 0) or 0
            oi  = sd.get("openInterest", 0) or 0
            ltp = sd.get("lastPrice", 0) or 0

            if vol <= 0 or ltp <= 0:
                continue

            # Fetch baseline from DB (returns 0 if no history yet)
            baseline = db.get_volume_baseline(symbol, strike, side, days=5)

            if baseline > 0:
                ratio = vol / baseline
                if ratio >= threshold:
                    uoa_events.append({
                        "symbol":     symbol,
                        "strike":     strike,
                        "type":       side,
                        "volume":     int(vol),
                        "avg_volume": int(baseline),
                        "ratio":      round(ratio, 1),
                        "oi":         int(oi),
                        "ltp":        ltp,
                        "spot":       spot,
                        "dist_pct":   round((strike - spot) / spot * 100, 1),
                        "label":      f"{ratio:.1f}× avg volume",
                    })
            elif vol > 50_000:
                # No history yet but very high absolute volume — still flag
                uoa_events.append({
                    "symbol":     symbol,
                    "strike":     strike,
                    "type":       side,
                    "volume":     int(vol),
                    "avg_volume": 0,
                    "ratio":      0,
                    "oi":         int(oi),
                    "ltp":        ltp,
                    "spot":       spot,
                    "dist_pct":   round((strike - spot) / spot * 100, 1),
                    "label":      "High absolute volume (no baseline)",
                })

    return sorted(uoa_events, key=lambda x: (x["ratio"] or x["volume"]), reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# Straddle / Strangle Screener
# ══════════════════════════════════════════════════════════════════════════════

def screen_straddle(
    records:  list,
    symbol:   str,
    spot:     float,
    expiry:   str   = "",
    pcr:      float = 1.0,
    atm_iv:   float = 0.0,
) -> Optional[dict]:
    """
    Identifies whether a straddle/strangle setup is favourable.
    Conditions: PCR near 1.0 AND IV in mid range AND active volume both sides.

    Returns straddle details or None if not a straddle setup.
    """
    # Straddle only makes sense when market is directionless
    if abs(pcr - 1.0) > 0.3:
        return None
    if atm_iv <= 0 or atm_iv > 60:
        return None

    from .analytics import nearest_atm, get_strike_interval
    atm = nearest_atm(spot, symbol)
    interval = get_strike_interval(symbol)

    atm_ce = atm_pe = None
    otm_ce = otm_pe = None   # for strangle: 1 interval OTM each side

    for row in records:
        strike = row.get("strikePrice", 0)
        if strike == atm:
            atm_ce = row.get("CE", {}) or {}
            atm_pe = row.get("PE", {}) or {}
        if strike == atm + interval:
            otm_ce = row.get("CE", {}) or {}
        if strike == atm - interval:
            otm_pe = row.get("PE", {}) or {}

    if not atm_ce or not atm_pe:
        return None

    ce_ltp = atm_ce.get("lastPrice", 0) or 0
    pe_ltp = atm_pe.get("lastPrice", 0) or 0
    if ce_ltp <= 0 or pe_ltp <= 0:
        return None

    straddle_cost = ce_ltp + pe_ltp
    # Breakeven = spot ± straddle_cost
    be_upper = spot + straddle_cost
    be_lower = spot - straddle_cost
    move_needed_pct = straddle_cost / spot * 100

    result: dict = {
        "symbol":           symbol,
        "atm_strike":       atm,
        "ce_ltp":           ce_ltp,
        "pe_ltp":           pe_ltp,
        "straddle_cost":    round(straddle_cost, 2),
        "breakeven_upper":  round(be_upper, 2),
        "breakeven_lower":  round(be_lower, 2),
        "move_needed_pct":  round(move_needed_pct, 2),
        "iv":               atm_iv,
        "pcr":              pcr,
        "strategy":         "STRADDLE",
    }

    # Also compute strangle if OTM data available
    if otm_ce and otm_pe:
        oc_ltp = otm_ce.get("lastPrice", 0) or 0
        op_ltp = otm_pe.get("lastPrice", 0) or 0
        if oc_ltp > 0 and op_ltp > 0:
            strangle_cost = oc_ltp + op_ltp
            result["strangle"] = {
                "ce_strike": atm + interval,
                "pe_strike": atm - interval,
                "ce_ltp":    oc_ltp,
                "pe_ltp":    op_ltp,
                "cost":      round(strangle_cost, 2),
                "breakeven_upper": round(spot + strangle_cost + interval, 2),
                "breakeven_lower": round(spot - strangle_cost - interval, 2),
                "cheaper_by": round(straddle_cost - strangle_cost, 2),
            }

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Sector Heatmap
# ══════════════════════════════════════════════════════════════════════════════

def build_sector_heatmap(scan_results: list) -> dict:
    """
    Aggregates per-symbol scan results into sector-level signals.
    Input: list of scan result dicts (from /api/scan)
    Output: {sector: {signal, avg_score, bullish, bearish, neutral, symbols}}
    """
    sector_data: dict[str, dict] = {}

    for r in scan_results:
        sym    = r.get("symbol", "")
        sector = get_sector(sym)
        signal = r.get("signal", "NEUTRAL")
        score  = r.get("score", 0)

        if sector not in sector_data:
            sector_data[sector] = {
                "bullish": 0, "bearish": 0, "neutral": 0,
                "scores":  [], "symbols": []
            }

        sd = sector_data[sector]
        sd["scores"].append(score)
        sd["symbols"].append({"symbol": sym, "signal": signal, "score": score})
        sd[signal.lower()] += 1

    result = {}
    for sector, sd in sector_data.items():
        n       = sd["bullish"] + sd["bearish"] + sd["neutral"]
        avg_sc  = round(sum(sd["scores"]) / n, 1) if n else 0
        if sd["bullish"] > sd["bearish"] and sd["bullish"] > sd["neutral"]:
            sector_signal = "BULLISH"
        elif sd["bearish"] > sd["bullish"] and sd["bearish"] > sd["neutral"]:
            sector_signal = "BEARISH"
        else:
            sector_signal = "NEUTRAL"

        result[sector] = {
            "signal":    sector_signal,
            "avg_score": avg_sc,
            "bullish":   sd["bullish"],
            "bearish":   sd["bearish"],
            "neutral":   sd["neutral"],
            "total":     n,
            "symbols":   sorted(sd["symbols"], key=lambda x: x["score"], reverse=True),
        }

    return result


# ══════════════════════════════════════════════════════════════════════════════
# PCR History aggregation
# ══════════════════════════════════════════════════════════════════════════════

def get_pcr_history(symbol: str, days: int = 5) -> list:
    """
    Builds intraday PCR timeline from OI history snapshots.
    Groups by snap_time, sums CE/PE OI across all strikes.
    """
    heatmap = db.get_oi_heatmap(symbol)
    if not heatmap:
        return []

    # Group by snap_time
    snaps: dict[str, dict] = {}
    for row in heatmap:
        t = row["snap_time"]
        if t not in snaps:
            snaps[t] = {"ce_oi": 0, "pe_oi": 0}
        if row["opt_type"] == "CE":
            snaps[t]["ce_oi"] += row["oi"]
        else:
            snaps[t]["pe_oi"] += row["oi"]

    timeline = []
    for snap_time in sorted(snaps.keys()):
        sd = snaps[snap_time]
        pcr = round(sd["pe_oi"] / sd["ce_oi"], 3) if sd["ce_oi"] > 0 else 1.0
        timeline.append({
            "time":   snap_time[11:16],    # HH:MM
            "pcr":    pcr,
            "ce_oi":  int(sd["ce_oi"]),
            "pe_oi":  int(sd["pe_oi"]),
        })

    return timeline


# ══════════════════════════════════════════════════════════════════════════════
# NSE Bulk / Block Deals Fetcher
# ══════════════════════════════════════════════════════════════════════════════

NSE_BULK_URL   = "https://www.nseindia.com/api/bulk-deals"
NSE_BLOCK_URL  = "https://www.nseindia.com/api/block-deals"

NSE_HEADERS = {
    "User-Agent":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept":      "application/json",
    "Referer":     "https://www.nseindia.com/market-data/bulk-block-deals",
}

async def fetch_bulk_deals() -> list:
    """
    Fetches today's NSE bulk & block deals and stores them in DB.
    Called once daily by the scheduler.
    """
    all_deals = []
    today = date.today().isoformat()

    async with httpx.AsyncClient(timeout=10, headers=NSE_HEADERS) as client:
        for url, deal_label in [(NSE_BULK_URL, "BULK"), (NSE_BLOCK_URL, "BLOCK")]:
            try:
                # NSE requires a session cookie — hit the homepage first
                await client.get("https://www.nseindia.com", timeout=5)
                r = await client.get(url, timeout=8)
                if r.status_code == 404:
                    log.info(f"Bulk deals endpoint unavailable ({deal_label}): {url}")
                    continue
                r.raise_for_status()
                data = r.json().get("data", [])

                for item in data:
                    sym = item.get("symbol", "").upper()
                    all_deals.append({
                        "date":     today,
                        "symbol":   sym,
                        "client":   item.get("clientName", ""),
                        "type":     item.get("buySell", ""),
                        "quantity": float(item.get("quantityTraded", 0) or 0),
                        "price":    float(item.get("tradePrice", 0) or 0),
                        "category": deal_label,
                    })

                log.info(f"Bulk/Block deals: fetched {len(data)} {deal_label} deals")

            except Exception as e:
                log.warning(f"Bulk deals fetch error ({deal_label}): {e}")

    if all_deals:
        db.save_bulk_deals(all_deals)

    return all_deals


def get_deals_for_scan(scan_results: list) -> dict:
    """
    Cross-references scan results with recent bulk deals.
    Returns {symbol: [deals]} for symbols in the scan.
    """
    symbols = {r["symbol"] for r in scan_results}
    all_deals = db.get_bulk_deals(days=3)

    deals_by_symbol: dict[str, list] = {}
    for deal in all_deals:
        sym = deal.get("symbol", "")
        if sym in symbols:
            if sym not in deals_by_symbol:
                deals_by_symbol[sym] = []
            deals_by_symbol[sym].append(deal)

    return deals_by_symbol
