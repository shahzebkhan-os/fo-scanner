"""
analytics.py — Option Analytics Engine v4
Covers: Black-Scholes Greeks, IV Rank, Max Pain, OI Walls,
        score_option, compute_stock_score, position sizing
"""

from __future__ import annotations
import math
from typing import Optional
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

# Timezone for market time calculations
_IST = ZoneInfo("Asia/Kolkata")

# OI Velocity singleton for tracking velocity across scans
from backend.signals.oi_velocity import OiVelocitySignal
_oi_velocity = OiVelocitySignal()

# ── Strike Intervals ──────────────────────────────────────────────────────────
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

def get_strike_interval(symbol: str) -> int:
    return STRIKE_INTERVALS.get(symbol.upper(), 10)

def nearest_atm(spot: float, symbol: str) -> float:
    iv = get_strike_interval(symbol)
    return round(spot / iv) * iv


# ══════════════════════════════════════════════════════════════════════════════
# Black-Scholes Greeks
# ══════════════════════════════════════════════════════════════════════════════

def _norm_cdf(x: float) -> float:
    """Standard normal CDF using Abramowitz & Stegun approximation."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def black_scholes_greeks(
    spot:    float,
    strike:  float,
    iv:      float,         # annualised implied volatility (e.g. 20 for 20%)
    dte:     float,         # days to expiry
    opt_type: str = "CE",   # "CE" or "PE"
    r:       float = 0.065, # risk-free rate (India ~6.5%)
) -> dict:
    """
    Returns full Greeks dict for one option contract.
    Returns zeros if inputs are degenerate (avoid crashes on missing data).
    """
    empty = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0,
             "rho": 0, "intrinsic": 0, "time_value": 0, "moneyness": "OTM"}

    if spot <= 0 or strike <= 0 or iv <= 0 or dte <= 0:
        return empty

    sigma = iv / 100.0
    T     = dte / 365.0

    try:
        sqrt_T = math.sqrt(T)
        d1 = (math.log(spot / strike) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        nd1  = _norm_cdf(d1)
        nd2  = _norm_cdf(d2)
        nd1n = _norm_cdf(-d1)
        nd2n = _norm_cdf(-d2)
        pdf1 = _norm_pdf(d1)

        er   = math.exp(-r * T)

        if opt_type == "CE":
            delta     = nd1
            rho_v     = strike * T * er * nd2 / 100
            intrinsic = max(0.0, spot - strike)
        else:
            delta     = nd1 - 1.0
            rho_v     = -strike * T * er * nd2n / 100
            intrinsic = max(0.0, strike - spot)

        gamma = pdf1 / (spot * sigma * sqrt_T)
        theta = (-(spot * pdf1 * sigma) / (2 * sqrt_T) -
                 r * strike * er * (nd2 if opt_type=="CE" else nd2n)) / 365
        vega  = spot * pdf1 * sqrt_T / 100

        # Moneyness label
        pct = (spot - strike) / strike * 100
        if opt_type == "CE":
            if pct >  1.5: moneyness = "ITM"
            elif pct < -1.5: moneyness = "OTM"
            else: moneyness = "ATM"
        else:
            if pct < -1.5: moneyness = "ITM"
            elif pct >  1.5: moneyness = "OTM"
            else: moneyness = "ATM"

        # Theoretical price
        if opt_type == "CE":
            theo = spot * nd1 - strike * er * nd2
        else:
            theo = strike * er * nd2n - spot * nd1n

        return {
            "delta":      round(delta, 4),
            "gamma":      round(gamma, 6),
            "theta":      round(theta, 4),       # daily decay in ₹ per lot
            "vega":       round(vega, 4),
            "rho":        round(rho_v, 4),
            "intrinsic":  round(intrinsic, 2),
            "time_value": round(max(0, theo - intrinsic), 2),
            "moneyness":  moneyness,
            "theo_price": round(theo, 2),
        }

    except (ValueError, ZeroDivisionError):
        return empty


def days_to_expiry(expiry_str: str) -> int:
    """
    Parse INDmoney expiry string and return days remaining.
    Handles formats: '2025-01-30', '30-Jan-2025', '30Jan2025'
    """
    from datetime import datetime, date
    today = date.today()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d%b%Y"):
        try:
            exp_date = datetime.strptime(expiry_str.strip(), fmt).date()
            return max(0, (exp_date - today).days)
        except ValueError:
            continue
    return 30  # fallback assumption


# ══════════════════════════════════════════════════════════════════════════════
# Max Pain
# ══════════════════════════════════════════════════════════════════════════════

def compute_max_pain(records: list) -> Optional[float]:
    if not records:
        return None
    strikes = sorted({r.get("strikePrice", 0) for r in records if r.get("strikePrice")})
    if not strikes:
        return None

    ce_oi = {r["strikePrice"]: (r.get("CE") or {}).get("openInterest", 0) for r in records}
    pe_oi = {r["strikePrice"]: (r.get("PE") or {}).get("openInterest", 0) for r in records}

    best_strike, min_pain = strikes[0], float("inf")
    for candidate in strikes:
        pain = sum(ce_oi.get(k, 0) * max(0, k - candidate) for k in strikes) + \
               sum(pe_oi.get(k, 0) * max(0, candidate - k) for k in strikes)
        if pain < min_pain:
            min_pain   = pain
            best_strike = candidate
    return best_strike


# ══════════════════════════════════════════════════════════════════════════════
# OI Walls
# ══════════════════════════════════════════════════════════════════════════════

def oi_walls(records: list, spot: float, n: int = 3) -> dict:
    ce_above = [(r["strikePrice"], (r.get("CE") or {}).get("openInterest", 0))
                for r in records if r.get("strikePrice", 0) > spot]
    pe_below = [(r["strikePrice"], (r.get("PE") or {}).get("openInterest", 0))
                for r in records if r.get("strikePrice", 0) < spot]

    return {
        "resistance": [{"strike": s, "oi": int(o)}
                       for s, o in sorted(ce_above, key=lambda x: x[1], reverse=True)[:n]],
        "support":    [{"strike": s, "oi": int(o)}
                       for s, o in sorted(pe_below, key=lambda x: x[1], reverse=True)[:n]],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Quantitative Option Scoring System v2 (Rebuild)
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_LOT_SIZE = {"NIFTY": 50, "BANKNIFTY": 15, "FINNIFTY": 25}

REGIME_WEIGHTS = {
    # oi_velocity takes weight from buildup (which does a weaker version of velocity detection)
    # global influences market sentiment, weighted higher during trending, lower during pinned/expiry
    "PINNED":   {"gex": 0.30, "vol_pcr": 0.08, "dwoi": 0.35, "skew": 0.07, "buildup": 0.02, "oi_velocity": 0.10, "global": 0.08},
    "TRENDING": {"gex": 0.12, "vol_pcr": 0.18, "dwoi": 0.12, "skew": 0.15, "buildup": 0.15, "oi_velocity": 0.13, "global": 0.15},
    "EXPIRY":   {"gex": 0.08, "vol_pcr": 0.35, "dwoi": 0.08, "skew": 0.07, "buildup": 0.20, "oi_velocity": 0.17, "global": 0.05},
    "SQUEEZE":  {"gex": 0.35, "vol_pcr": 0.25, "dwoi": 0.08, "skew": 0.07, "buildup": 0.05, "oi_velocity": 0.10, "global": 0.10},
}

PCR_BULLISH_THRESHOLD = 1.2
PCR_BEARISH_THRESHOLD = 0.8
IV_SKEW_CRITICAL_LEVEL = 2.0


def _time_of_day_adjustment(score: float, is_expiry_day: bool = False) -> float:
    """
    Discount score during high-noise market periods.
    Call at the end of compute_stock_score_v2() before returning.
    
    Time adjustments:
    - 9:15-10:30 IST: 15% discount (morning volatility)
    - 15:15+: 20% discount (end-of-day noise)
    - Expiry day 14:00+: additional 10% discount
    """
    now = datetime.now(_IST).time()

    if dtime(9, 15) <= now <= dtime(10, 30):
        score = score * 0.85          # Morning volatility: 15% discount

    if is_expiry_day and now >= dtime(14, 0):
        score = score * 0.90          # Expiry afternoon: additional 10% discount

    if now >= dtime(15, 15):
        score = score * 0.80          # Last 15 min: 20% discount (end-of-day noise)

    return round(min(100, max(0, score)))


def _dynamic_pcr_thresholds(pcr_history: list) -> tuple:
    """
    Bollinger-band style adaptive PCR thresholds.
    Falls back to fixed 1.2/0.8 if < 10 data points.
    
    Args:
        pcr_history: List of recent PCR values from market_snapshots
        
    Returns:
        Tuple of (bullish_threshold, bearish_threshold)
    """
    if not pcr_history or len(pcr_history) < 10:
        return PCR_BULLISH_THRESHOLD, PCR_BEARISH_THRESHOLD   # Static fallback
    
    try:
        import numpy as np
        mean = np.mean(pcr_history)
        std = np.std(pcr_history)
        # Avoid extreme thresholds
        bull = min(2.0, max(1.0, mean + 1.5 * std))
        bear = max(0.5, min(1.0, mean - 1.5 * std))
        return (bull, bear)
    except Exception:
        return PCR_BULLISH_THRESHOLD, PCR_BEARISH_THRESHOLD


def compute_gex(records: list, spot: dict|float, lot_size: int = 50) -> dict:
    total_call_gex = 0.0
    total_put_gex = 0.0
    gex_by_strike = []
    
    for row in records:
        ce = row.get("CE", {}) or {}
        pe = row.get("PE", {}) or {}
        strike = row.get("strikePrice", 0)
        
        ce_oi = ce.get("openInterest", 0) or 0
        ce_gamma = ce.get("gamma", 0.0) or 0.0
        if ce_oi and ce_gamma:
            cgex = (ce_oi * ce_gamma * lot_size * (spot ** 2)) / 100
            total_call_gex += cgex
            
        pe_oi = pe.get("openInterest", 0) or 0
        pe_gamma = pe.get("gamma", 0.0) or 0.0
        if pe_oi and pe_gamma:
            pgex = (pe_oi * pe_gamma * lot_size * (spot ** 2)) / 100
            total_put_gex += pgex
            
        if ce_oi or pe_oi:
            gex_by_strike.append({
                "strike": strike,
                "net_gex_at_strike": (ce_oi * ce_gamma) - (pe_oi * pe_gamma)
            })
            
    net_gex = total_call_gex - total_put_gex
    regime = "POSITIVE" if net_gex > 0 else "NEGATIVE"
    
    sorted_strikes = sorted(gex_by_strike, key=lambda x: abs(x["net_gex_at_strike"]))
    zgl = sorted_strikes[0]["strike"] if sorted_strikes else spot

    return {
        "net_gex": net_gex,
        "gex_by_strike": gex_by_strike,
        "zero_gamma_level": zgl,
        "gex_regime": regime
    }


def compute_iv_skew(records: list, spot: float, symbol: str) -> dict:
    closest_dist = float('inf')
    atm_row = None
    for row in records:
        dist = abs(row.get("strikePrice", 0) - spot)
        if dist < closest_dist:
            closest_dist = dist
            atm_row = row
            
    if not atm_row:
        return {"skew_value": 0.0, "skew_signal": "NEUTRAL", "skew_percentile": 50}
        
    ce_iv = (atm_row.get("CE") or {}).get("impliedVolatility", 0.0)
    pe_iv = (atm_row.get("PE") or {}).get("impliedVolatility", 0.0)
    
    skew = pe_iv - ce_iv
    
    if skew > IV_SKEW_CRITICAL_LEVEL:
        signal = "BEARISH"
    elif skew < -1.0:
        signal = "BULLISH"
    else:
        signal = "NEUTRAL"
        
    percentile = max(0, min(100, (skew + 1.5) * 20))
    
    return {
        "skew_value": skew,
        "skew_signal": signal,
        "skew_percentile": percentile
    }


def detect_buildup_type(records: list, spot: float, prev_records: list = None) -> dict:
    if not prev_records:
        return {"overall": "NEUTRAL", "strikes": {}}
        
    prev_map = {r.get("strikePrice"): r for r in prev_records}
    
    long_buildup_pts = 0
    short_buildup_pts = 0
    long_unwind_pts = 0
    short_cover_pts = 0
    
    strike_buildups = {}
    
    for row in records:
        strike = row.get("strikePrice", 0)
        p_row = prev_map.get(strike)
        if not p_row: continue
        
        ce = row.get("CE", {}) or {}; p_ce = p_row.get("CE", {}) or {}
        c_oi_chg = (ce.get("openInterest", 0) or 0) - (p_ce.get("openInterest", 0) or 0)
        c_ltp_chg = (ce.get("lastPrice", 0) or 0) - (p_ce.get("lastPrice", 0) or 0)
        
        ce_state = "NEUTRAL"
        if c_ltp_chg > 0 and c_oi_chg > 0:
            ce_state = "LONG_BUILDUP"; long_buildup_pts += 1
        elif c_ltp_chg < 0 and c_oi_chg > 0:
            ce_state = "SHORT_BUILDUP"; short_buildup_pts += 1
        elif c_ltp_chg < 0 and c_oi_chg < 0:
            ce_state = "LONG_UNWINDING"; long_unwind_pts += 1
        elif c_ltp_chg > 0 and c_oi_chg < 0:
            ce_state = "SHORT_COVERING"; short_cover_pts += 1
            
        strike_buildups[strike] = ce_state

    bull_pts = long_buildup_pts + short_cover_pts
    bear_pts = short_buildup_pts + long_unwind_pts
    
    overall = "NEUTRAL"
    if bull_pts > bear_pts * 1.5: overall = "BULLISH"
    elif bear_pts > bull_pts * 1.5: overall = "BEARISH"
    
    return {
        "overall": overall,
        "strikes": strike_buildups
    }


def detect_regime(records: list, spot: float, symbol: str, dte: int, ivr: float) -> str:
    if dte <= 2:
        return "EXPIRY"
        
    gex_data = compute_gex(records, spot)
    net_gex = gex_data["net_gex"]
    
    total_oi = 0
    strike_ois = []
    for r in records:
        o = (r.get("CE", {}) or {}).get("openInterest", 0) + (r.get("PE", {}) or {}).get("openInterest", 0)
        total_oi += o
        strike_ois.append(o)
    
    strike_ois.sort(reverse=True)
    top_3_oi = sum(strike_ois[:3])
    ocr = (top_3_oi / total_oi) if total_oi > 0 else 0
    
    if ocr > 0.45 and ivr < 30 and dte <= 5 and net_gex < 0:
        return "SQUEEZE"
        
    if net_gex > 0:
        return "PINNED"
        
    return "TRENDING"


def score_option_v2(side: dict, spot: float, symbol: str, dte: int, iv_rank: float, regime: str, greeks: dict) -> dict:
    delta = greeks.get("delta", 0.5)
    
    oi = side.get("openInterest", 0) or 0
    vol = side.get("totalTradedVolume", 0) or 0
    iv = side.get("impliedVolatility", 0) or 0
    
    d_score = abs(delta) * 25
    
    liq_ratio = (vol / max(1, oi)) if oi > 0 else 0
    l_score = min(50, liq_ratio * 10)
    
    iv_score = 0
    if 15 < iv < 40: iv_score = 25
    elif iv <= 15: iv_score = 15
    else: iv_score = max(0, 25 - (iv-40))
    
    total = min(100, d_score + l_score + iv_score)
    
    return {
        "score": int(total),
        "confidence": round(min(1.0, l_score / 50.0), 2),
    }


def compute_stock_score_v2(
    chain_data:  dict,
    spot:        float,
    symbol:      str   = "",
    expiry_str:  str   = "",
    iv_rank_data: dict = None,
    prev_chain_data: dict = None,
    fii_net: float = 0.0,
    global_score: float = 0.0,
    global_confidence: float = 0.0
) -> dict:
    
    records = chain_data.get("records", {}).get("data", [])
    _empty  = dict(
        pcr=1.0, iv=0, oi_change=0, vol_spike=0.0,
        signal="NEUTRAL", score=0, top_picks=[], confidence=0, regime="TRENDING", metrics={},
        max_pain=None, oi_walls={}, signal_reasons=[],
        greeks_atm={}, days_to_expiry=30, iv_rank=50.0
    )
    if not records or spot <= 0:
        return _empty
    
    # Push OI snapshot to velocity tracker for this symbol
    _oi_velocity.push_snapshot(
        symbol=symbol,
        records=records,
        spot=spot,
        timestamp=datetime.now(_IST)
    )
    # Compute OI velocity signal
    velocity_result = _oi_velocity.compute(symbol, records, spot)
        
    dte = days_to_expiry(expiry_str) if expiry_str else 5
    is_expiry_day = (dte <= 1)  # Consider DTE 0 or 1 as expiry day
    iv_rank = (iv_rank_data or {}).get("iv_rank", 50.0)
    
    regime = detect_regime(records, spot, symbol, dte, iv_rank)
    weights = REGIME_WEIGHTS[regime]
    
    lot_size = DEFAULT_LOT_SIZE.get(symbol, 50)
    
    # Needs greeks computation for all strikes to be accurate
    for row in records:
        strike = row.get("strikePrice", 0)
        ce = row.get("CE", {}) or {}
        pe = row.get("PE", {}) or {}
        
        iv_ce = ce.get("impliedVolatility", 20.0) or 20.0
        iv_pe = pe.get("impliedVolatility", 20.0) or 20.0
        
        ce_greeks = black_scholes_greeks(spot, strike, iv_ce, dte, "CE")
        pe_greeks = black_scholes_greeks(spot, strike, iv_pe, dte, "PE")
        
        if "CE" in row and row["CE"]: row["CE"].update(ce_greeks)
        if "PE" in row and row["PE"]: row["PE"].update(pe_greeks)

    gex_data = compute_gex(records, spot, lot_size)
    is_spot_above_zgl = spot > gex_data["zero_gamma_level"]
    gex_bullish = is_spot_above_zgl and gex_data["net_gex"] > 0
    
    ce_dwoi = pe_dwoi = ce_vol = pe_vol = tce_oi = tpe_oi = 0
    all_options = []
    
    for r in records:
        c = r.get("CE", {}) or {}; p = r.get("PE", {}) or {}
        strike = r.get("strikePrice", 0)
        
        ce_oi = c.get("openInterest", 0) or 0
        pe_oi = p.get("openInterest", 0) or 0
        
        tce_oi += ce_oi
        tpe_oi += pe_oi
        
        ce_vol += c.get("totalTradedVolume", 0) or 0
        pe_vol += p.get("totalTradedVolume", 0) or 0
        
        ce_dwoi += ce_oi * abs(c.get("delta", 0.5))
        pe_dwoi += pe_oi * abs(p.get("delta", 0.5))
        
        if c.get("lastPrice", 0) > 0:
            c_s = score_option_v2(c, spot, symbol, dte, iv_rank, regime, c)
            all_options.append({"type": "CE", "strike": strike, "ltp": c["lastPrice"], "score": c_s["score"]})
        if p.get("lastPrice", 0) > 0:
            p_s = score_option_v2(p, spot, symbol, dte, iv_rank, regime, p)
            all_options.append({"type": "PE", "strike": strike, "ltp": p["lastPrice"], "score": p_s["score"]})
        
    dwoi_pcr = pe_dwoi / ce_dwoi if ce_dwoi > 0 else 1.0
    vol_pcr = pe_vol / ce_vol if ce_vol > 0 else 1.0
    pcr = tpe_oi / tce_oi if tce_oi > 0 else 1.0
    
    skew_data = compute_iv_skew(records, spot, symbol)
    prev_records = prev_chain_data.get("records", {}).get("data", []) if prev_chain_data else None
    buildup_data = detect_buildup_type(records, spot, prev_records)
    
    factors = []
    
    if gex_bullish: factors.append(1)
    elif not is_spot_above_zgl: factors.append(-1)
    else: factors.append(0)
        
    if vol_pcr > PCR_BULLISH_THRESHOLD: factors.append(1)
    elif vol_pcr < PCR_BEARISH_THRESHOLD: factors.append(-1)
    else: factors.append(0)
        
    if dwoi_pcr > PCR_BULLISH_THRESHOLD: factors.append(1)
    elif dwoi_pcr < PCR_BEARISH_THRESHOLD: factors.append(-1)
    else: factors.append(0)
        
    if skew_data["skew_signal"] == "BULLISH": factors.append(1)
    elif skew_data["skew_signal"] == "BEARISH": factors.append(-1)
    else: factors.append(0)
        
    if buildup_data["overall"] == "BULLISH": factors.append(1)
    elif buildup_data["overall"] == "BEARISH": factors.append(-1)
    else: factors.append(0)
        
    bull_count = factors.count(1)
    bear_count = factors.count(-1)
    
    direction = "NEUTRAL"
    confidence = 0.0
    
    # We only have 4 active factors in historical backtest context (buildup is dead)
    # 2 out of 4 aligned factors is a strong enough confluence.
    active_indicators = len([f for f in factors if f != 0]) or 1
    
    if bull_count >= 2 and bull_count > bear_count:
        direction = "BULLISH"
        confidence = bull_count / active_indicators
    elif bear_count >= 2 and bear_count > bull_count:
        direction = "BEARISH"
        confidence = bear_count / active_indicators
        
    sub_gex     = 100 if factors[0] == 1 else (0 if factors[0] == -1 else 50)
    sub_volpcr  = min(100, max(0, vol_pcr * 50))
    sub_dwoipcr = min(100, max(0, dwoi_pcr * 50))
    sub_skew    = 100 - skew_data["skew_percentile"]
    sub_build   = 100 if factors[4] == 1 else (0 if factors[4] == -1 else 50)
    
    # OI Velocity sub-score: Convert -1..+1 to 10..90 range
    sub_velocity = 50 + (velocity_result.score * 40)
    sub_velocity = max(0, min(100, sub_velocity))
    
    # Global influence sub-score: Convert -1..+1 to 10..90 range
    sub_global = 50 + (global_score * 40)
    sub_global = max(0, min(100, sub_global))
    
    weighted_score = (
        (sub_gex      * weights["gex"]) +
        (sub_volpcr   * weights["vol_pcr"]) +
        (sub_dwoipcr  * weights["dwoi"]) +
        (sub_skew     * weights["skew"]) +
        (sub_build    * weights["buildup"]) +
        (sub_velocity * weights["oi_velocity"]) +
        (sub_global   * weights["global"])
    )
    
    # UOA override: if UOA detected with high confidence, boost/dampen score
    uoa_detected = False
    uoa_strike = None
    uoa_side = None
    if velocity_result.is_uoa and velocity_result.confidence > 0.6:
        uoa_boost = 8 if velocity_result.score > 0 else -8
        weighted_score = max(0, min(100, weighted_score + uoa_boost))
        uoa_detected = True
        uoa_strike = velocity_result.top_strike
        uoa_side = "CE" if velocity_result.top_ce_velocity > abs(velocity_result.top_pe_velocity) else "PE"
    
    # Pre-market double weight for global cues (09:00–09:45 IST)
    now_ist = datetime.now(_IST).time()
    if dtime(9, 0) <= now_ist <= dtime(9, 45) and global_confidence > 0.3:
        # Boost the global component influence during pre-market/opening
        weighted_score = (weighted_score * 0.80) + (sub_global * 0.20)
    
    if direction == "BEARISH" and fii_net < 0 and symbol in ["NIFTY", "BANKNIFTY"]:
        weighted_score = max(0, weighted_score / 1.15)
        
    def _directional_picks(options, signal):
        if signal == "BULLISH":
            candidates = [o for o in options if o["type"] == "CE"]
        elif signal == "BEARISH":
            candidates = [o for o in options if o["type"] == "PE"]
        else:
            ce_best = sorted([o for o in options if o["type"] == "CE"],
                             key=lambda x: x["score"], reverse=True)[:1]
            pe_best = sorted([o for o in options if o["type"] == "PE"],
                             key=lambda x: x["score"], reverse=True)[:1]
            return ce_best + pe_best
        return sorted(candidates, key=lambda x: x["score"], reverse=True)[:2]
    
    top_picks = _directional_picks(all_options, direction)
    
    mp = compute_max_pain(records)
    walls = oi_walls(records, spot)
    
    atm_strike = nearest_atm(spot, symbol)
    atm_iv_ce = atm_iv_pe = 20.0
    greeks_atm = {}
    
    for row in records:
        if row.get("strikePrice") == atm_strike:
            atm_iv_ce = (row.get("CE") or {}).get("impliedVolatility", 20.0) or 20.0
            atm_iv_pe = (row.get("PE") or {}).get("impliedVolatility", 20.0) or 20.0
            
            greeks_atm = {
                "CE": black_scholes_greeks(spot, atm_strike, atm_iv_ce, dte, "CE"),
                "PE": black_scholes_greeks(spot, atm_strike, atm_iv_pe, dte, "PE"),
                "strike": atm_strike,
            }
            break

    atm_iv = round((atm_iv_ce + atm_iv_pe) / 2, 1)
    
    # Apply time-of-day adjustment to score (Phase 1B)
    weighted_score = _time_of_day_adjustment(weighted_score, is_expiry_day=is_expiry_day)

    return dict(
        pcr            = round(pcr, 3),
        iv             = atm_iv,
        oi_change      = 0, # Deprecated in v2 but kept for schema compatibility
        vol_spike      = round((ce_vol + pe_vol) / max(1, tce_oi + tpe_oi), 3),
        signal         = direction,
        score          = int(weighted_score),
        top_picks      = top_picks,
        max_pain       = mp,
        oi_walls       = walls,
        signal_reasons = [f"Regime: {regime}"], # Reused generic signals reason logic
        greeks_atm     = greeks_atm,
        days_to_expiry = dte,
        iv_rank        = iv_rank,
        confidence     = confidence,
        regime         = regime,
        metrics        = {
            "gex": gex_data["net_gex"],
            "vol_pcr": round(vol_pcr, 2),
            "dwoi_pcr": round(dwoi_pcr, 2),
            "iv_skew": round(skew_data["skew_value"], 2)
        },
        # OI Velocity output
        oi_velocity_score  = velocity_result.score,
        oi_velocity_conf   = velocity_result.confidence,
        oi_velocity_reason = velocity_result.reason,
        uoa_detected       = uoa_detected,
        uoa_strike         = uoa_strike,
        uoa_side           = uoa_side,
        # Global influence output (passed through from main.py)
        global_score       = global_score,
    )

