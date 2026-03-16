"""
analytics.py — Option Analytics Engine v4
Covers: Black-Scholes Greeks, IV Rank, Max Pain, OI Walls,
        score_option, compute_stock_score, position sizing
"""

from __future__ import annotations
import math
from collections import deque, defaultdict
from datetime import datetime
from typing import Optional

import numpy as np
import pytz

try:
    from .signals.oi_velocity import OiVelocitySignal
except ImportError:
    from signals.oi_velocity import OiVelocitySignal

# Module-level singleton — maintains rolling OI history across scans
_oi_velocity = OiVelocitySignal()
_price_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
_pcr_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
_IST = pytz.timezone("Asia/Kolkata")

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
    # ── Additional F&O stocks ──
    "BHARTIARTL": 20, "BANKBARODA": 5, "BEL": 5, "DLF": 10, "HAL": 50,
    "IRCTC": 20, "TATAPOWER": 5, "TATACONSUM": 10, "TRENT": 50, "PNB": 2,
    "CANBK": 2, "SBILIFE": 20, "SBICARD": 10, "PFC": 5, "RECLTD": 5,
    "BIOCON": 5, "LUPIN": 20, "JUBLFOOD": 10, "LICHSGFIN": 5, "MOTHERSON": 5,
    "CHOLAFIN": 20, "MUTHOOTFIN": 20, "FEDERALBNK": 2, "UPL": 10, "POLYCAB": 50,
    "SRF": 50, "DABUR": 10, "GODREJCP": 20, "BANDHANBNK": 5, "IDFCFIRSTB": 2,
    "INDUSTOWER": 5, "NAUKRI": 100, "BHARATFORG": 20, "COFORGE": 50, "GODREJPROP": 50,
    "PETRONET": 5, "RBLBANK": 5, "TATACOMM": 20, "INDHOTEL": 10, "PAGEIND": 200,
}

def get_strike_interval(symbol: str) -> int:
    return STRIKE_INTERVALS.get(symbol.upper(), 10)

def nearest_atm(spot: float, symbol: str) -> float:
    iv = get_strike_interval(symbol)
    return round(spot / iv) * iv


def _compute_price_indicators(symbol: str, spot: float, timestamp: datetime) -> dict:
    """
    Maintain a short rolling price history per symbol and compute common
    price-action technical indicators. Uses pandas/numpy for robustness.
    """
    history = _price_history[symbol]
    history.append((timestamp, float(spot)))

    prices = np.array([p for _, p in history], dtype=float)
    if prices.size == 0:
        return {}

    last_price = float(prices[-1])

    # RSI(14) using simple Wilder average on the last 14 deltas
    deltas = np.diff(prices[-15:])  # at most last 15 prices → 14 deltas
    gains = np.clip(deltas, a_min=0, a_max=None)
    losses = -np.clip(deltas, a_min=None, a_max=0)
    avg_gain = gains.mean() if gains.size else 0.0
    avg_loss = losses.mean() if losses.size else 0.0
    if avg_loss == 0 and avg_gain == 0:
        last_rsi = 50.0
    elif avg_loss == 0:
        last_rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        last_rsi = 100 - (100 / (1 + rs))

    # SMA20
    sma_window = prices[-20:] if prices.size >= 1 else prices
    last_sma20 = float(np.mean(sma_window)) if sma_window.size else last_price

    # EMA9 computed iteratively over the last 9 samples (or fewer if not available)
    ema_values = prices[-9:] if prices.size > 0 else prices
    if ema_values.size:
        alpha = 2 / (9 + 1)
        ema = ema_values[0]
        for v in ema_values[1:]:
            ema = (v - ema) * alpha + ema
        last_ema9 = float(ema)
    else:
        last_ema9 = last_price

    # Bollinger distances based on 20-period window
    bb_window = prices[-20:] if prices.size else prices
    if bb_window.size:
        mean = float(np.mean(bb_window))
        std = float(np.std(bb_window))
        last_upper = mean + 2 * std
        last_lower = mean - 2 * std
    else:
        last_upper = last_lower = last_price

    # Distances scaled to price to avoid magnitude drift
    upper_dist = (last_price - last_upper) / last_price if last_price else 0.0
    lower_dist = (last_price - last_lower) / last_price if last_price else 0.0

    return {
        "rsi_14": round(last_rsi, 3) if np.isfinite(last_rsi) else 50.0,
        "sma_20": round(last_sma20, 3),
        "ema_9": round(last_ema9, 3),
        "bb_upper_dist": round(upper_dist, 4) if np.isfinite(upper_dist) else 0.0,
        "bb_lower_dist": round(lower_dist, 4) if np.isfinite(lower_dist) else 0.0,
    }


def _compute_pcr_velocity(symbol: str, pcr_value: float, timestamp: datetime, window: int = 5) -> float:
    """
    Track PCR over recent snapshots and return the per-snapshot rate of change.
    Positive → PCR rising, Negative → PCR falling.
    """
    history = _pcr_history[symbol]
    history.append((timestamp, float(pcr_value)))

    if len(history) < 2:
        return 0.0

    # Use the last `window` observations
    relevant = list(history)[-window:]
    values = [v for _, v in relevant]
    if len(values) < 2:
        return 0.0

    delta = values[-1] - values[0]
    steps = max(len(values) - 1, 1)
    return round(delta / steps, 4)


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


def days_to_expiry(expiry_str: str, as_of: date = None) -> int:
    """
    Parse INDmoney expiry string and return days remaining.
    If as_of is provided, calculate relative to that date (for historical data).
    """
    from datetime import datetime, date
    if as_of is None:
        as_of = date.today()
    
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d%b%Y"):
        try:
            exp_date = datetime.strptime(expiry_str.strip(), fmt).date()
            return max(0, (exp_date - as_of).days)
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
    "PINNED":   {"gex": 0.30, "vol_pcr": 0.10, "dwoi": 0.40, "skew": 0.10, "buildup": 0.02, "oi_velocity": 0.08},
    "TRENDING": {"gex": 0.15, "vol_pcr": 0.25, "dwoi": 0.15, "skew": 0.20, "buildup": 0.13, "oi_velocity": 0.12},
    "EXPIRY":   {"gex": 0.10, "vol_pcr": 0.40, "dwoi": 0.10, "skew": 0.10, "buildup": 0.18, "oi_velocity": 0.12},
    "SQUEEZE":  {"gex": 0.40, "vol_pcr": 0.30, "dwoi": 0.10, "skew": 0.10, "buildup": 0.02, "oi_velocity": 0.08},
}

PCR_BULLISH_THRESHOLD = 1.2
PCR_BEARISH_THRESHOLD = 0.8
IV_SKEW_CRITICAL_LEVEL = 2.0


def compute_gex(records: list, spot: float, lot_size: int = 50) -> dict:
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
    
    bull_pts = 0
    bear_pts = 0
    
    strike_buildups = {}
    
    for row in records:
        strike = row.get("strikePrice", 0)
        p_row = prev_map.get(strike)
        if not p_row: continue
        
        # ── CE side buildup analysis ──
        ce = row.get("CE", {}) or {}; p_ce = p_row.get("CE", {}) or {}
        c_oi_chg = (ce.get("openInterest", 0) or 0) - (p_ce.get("openInterest", 0) or 0)
        c_ltp_chg = (ce.get("lastPrice", 0) or 0) - (p_ce.get("lastPrice", 0) or 0)
        
        ce_state = "NEUTRAL"
        if c_ltp_chg > 0 and c_oi_chg > 0:
            ce_state = "CE_LONG_BUILDUP"; bull_pts += 1    # CE price ↑ + OI ↑ = bullish
        elif c_ltp_chg < 0 and c_oi_chg > 0:
            ce_state = "CE_SHORT_BUILDUP"; bear_pts += 1   # CE price ↓ + OI ↑ = bearish
        elif c_ltp_chg < 0 and c_oi_chg < 0:
            ce_state = "CE_LONG_UNWINDING"; bear_pts += 1  # CE price ↓ + OI ↓ = bearish
        elif c_ltp_chg > 0 and c_oi_chg < 0:
            ce_state = "CE_SHORT_COVERING"; bull_pts += 1  # CE price ↑ + OI ↓ = bullish

        # ── PE side buildup analysis ──
        pe = row.get("PE", {}) or {}; p_pe = p_row.get("PE", {}) or {}
        p_oi_chg = (pe.get("openInterest", 0) or 0) - (p_pe.get("openInterest", 0) or 0)
        p_ltp_chg = (pe.get("lastPrice", 0) or 0) - (p_pe.get("lastPrice", 0) or 0)

        pe_state = "NEUTRAL"
        if p_ltp_chg > 0 and p_oi_chg > 0:
            pe_state = "PE_LONG_BUILDUP"; bear_pts += 1    # PE price ↑ + OI ↑ = bearish
        elif p_ltp_chg < 0 and p_oi_chg > 0:
            pe_state = "PE_SHORT_BUILDUP"; bull_pts += 1   # PE price ↓ + OI ↑ = bullish
        elif p_ltp_chg < 0 and p_oi_chg < 0:
            pe_state = "PE_LONG_UNWINDING"; bull_pts += 1  # PE price ↓ + OI ↓ = bullish
        elif p_ltp_chg > 0 and p_oi_chg < 0:
            pe_state = "PE_SHORT_COVERING"; bear_pts += 1  # PE price ↑ + OI ↓ = bearish

        strike_buildups[strike] = {"CE": ce_state, "PE": pe_state}

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
    abs_delta = abs(delta)

    oi = side.get("openInterest", 0) or 0
    vol = side.get("totalTradedVolume", 0) or 0
    iv = side.get("impliedVolatility", 0) or 0

    d_score = abs_delta * 25

    liq_ratio = (vol / max(1, oi)) if oi > 0 else 0
    l_score = min(50, liq_ratio * 10)

    iv_score = 0
    if 15 < iv < 40: iv_score = 25
    elif iv <= 15: iv_score = 15
    else: iv_score = max(0, 25 - (iv - 40))

    # Moneyness proximity bonus — prefer ATM / slightly OTM over deep OTM
    if 0.40 <= abs_delta <= 0.60:
        moneyness_score = 20       # ATM sweet spot
    elif 0.25 <= abs_delta < 0.40:
        moneyness_score = 15       # slightly OTM — still good
    elif 0.60 < abs_delta <= 0.75:
        moneyness_score = 12       # slightly ITM
    elif 0.15 <= abs_delta < 0.25:
        moneyness_score = 5        # further OTM
    elif abs_delta > 0.75:
        moneyness_score = 8        # deep ITM — high premium, less bang-for-buck
    else:
        moneyness_score = -10      # deep OTM (delta < 0.15) — penalize

    total = min(100, max(0, d_score + l_score + iv_score + moneyness_score))

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
    as_of: date = None
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

    ts_now = datetime.now(_IST) if as_of is None else _IST.localize(datetime.combine(as_of, datetime.min.time()))

    # Push new OI snapshot to velocity tracker
    _oi_velocity.push_snapshot(
        symbol=symbol,
        records=records,
        spot=spot,
        timestamp=ts_now,
    )
    # Compute velocity signal
    velocity_signal = _oi_velocity.compute(symbol=symbol, records=records, spot=spot)
    velocity_meta = velocity_signal.metadata

    # Price-action technicals
    price_indicators = _compute_price_indicators(symbol, spot, ts_now)

    dte = days_to_expiry(expiry_str, as_of) if expiry_str else 5
    iv_rank = (iv_rank_data or {}).get("iv_rank", 50.0)
    
    lot_size = DEFAULT_LOT_SIZE.get(symbol, 50)
    
    # Compute Greeks for all strikes BEFORE regime detection so that
    # detect_regime → compute_gex can use accurate gamma values.
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

    regime = detect_regime(records, spot, symbol, dte, iv_rank)
    weights = REGIME_WEIGHTS[regime]

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
    
    # Velocity of PCR across recent snapshots
    pcr_velocity = _compute_pcr_velocity(symbol, pcr, ts_now)
    
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
        
    # ── Direction-aware sub-scores ──────────────────────────────────────────
    # Sub-scores represent "alignment with detected direction" so that both
    # BULLISH and BEARISH setups can reach high conviction scores.
    if direction == "BEARISH":
        # Invert binary factors: bearish factor → 100, bullish → 0
        sub_gex     = 100 if factors[0] == -1 else (0 if factors[0] == 1 else 50)
        sub_volpcr  = min(100, max(0, (2.0 - vol_pcr) * 50))
        sub_dwoipcr = min(100, max(0, (2.0 - dwoi_pcr) * 50))
        sub_skew    = skew_data["skew_percentile"]          # higher percentile = more bearish
        sub_build   = 100 if factors[4] == -1 else (0 if factors[4] == 1 else 50)
        sub_velocity = max(0, min(100, 50 - (velocity_signal.score * 40)))
    else:
        sub_gex     = 100 if factors[0] == 1 else (0 if factors[0] == -1 else 50)
        sub_volpcr  = min(100, max(0, vol_pcr * 50))
        sub_dwoipcr = min(100, max(0, dwoi_pcr * 50))
        sub_skew    = 100 - skew_data["skew_percentile"]
        sub_build   = 100 if factors[4] == 1 else (0 if factors[4] == -1 else 50)
        sub_velocity = max(0, min(100, 50 + (velocity_signal.score * 40)))
    
    weighted_score = (
        (sub_gex      * weights["gex"]) +
        (sub_volpcr   * weights["vol_pcr"]) +
        (sub_dwoipcr  * weights["dwoi"]) +
        (sub_skew     * weights["skew"]) +
        (sub_build    * weights["buildup"]) +
        (sub_velocity * weights["oi_velocity"])
    )
    
    if direction == "BEARISH" and fii_net < 0 and symbol in ["NIFTY", "BANKNIFTY"]:
        weighted_score = max(0, weighted_score / 1.15)

    # UOA override: if UOA detected with high confidence, boost/dampen score
    UOA_SCORE_BOOST = 8  # Points added/subtracted when institutional UOA detected
    if velocity_meta.get("is_uoa") and velocity_signal.confidence > 0.6:
        # Boost when UOA velocity aligns with detected direction
        velocity_aligned = (
            (direction == "BULLISH" and velocity_signal.score > 0)
            or (direction == "BEARISH" and velocity_signal.score < 0)
        )
        uoa_boost = UOA_SCORE_BOOST if velocity_aligned else -UOA_SCORE_BOOST
        weighted_score = max(0, min(100, weighted_score + uoa_boost))
        
    def _directional_picks(options, signal):
        # Filter to strikes within ±5 intervals of ATM to avoid deep OTM picks
        atm = nearest_atm(spot, symbol)
        interval = get_strike_interval(symbol)
        max_dist = interval * 5  # stay within 5 strike intervals of ATM

        def _near_atm(o):
            return abs(o["strike"] - atm) <= max_dist

        if signal == "BULLISH":
            candidates = [o for o in options if o["type"] == "CE" and _near_atm(o)]
            if not candidates:  # fallback if too restrictive
                candidates = [o for o in options if o["type"] == "CE"]
        elif signal == "BEARISH":
            candidates = [o for o in options if o["type"] == "PE" and _near_atm(o)]
            if not candidates:
                candidates = [o for o in options if o["type"] == "PE"]
        else:
            ce_near = [o for o in options if o["type"] == "CE" and _near_atm(o)]
            pe_near = [o for o in options if o["type"] == "PE" and _near_atm(o)]
            if not ce_near: ce_near = [o for o in options if o["type"] == "CE"]
            if not pe_near: pe_near = [o for o in options if o["type"] == "PE"]
            ce_best = sorted(ce_near, key=lambda x: x["score"], reverse=True)[:1]
            pe_best = sorted(pe_near, key=lambda x: x["score"], reverse=True)[:1]
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

    # Build UOA stats for frontend
    uoa_stats = {}
    if velocity_meta.get("is_uoa") and velocity_signal.confidence > 0.6:
        uoa_stats["uoa_detected"] = True
        uoa_stats["uoa_strike"] = velocity_meta.get("top_strike")
        ce_v = abs(velocity_meta.get("top_ce_velocity", 0))
        pe_v = abs(velocity_meta.get("top_pe_velocity", 0))
        uoa_stats["uoa_side"] = "CE" if ce_v > pe_v else "PE"

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
            "zgl": gex_data["zero_gamma_level"],
            "vol_pcr": round(vol_pcr, 2),
            "dwoi_pcr": round(dwoi_pcr, 2),
            "iv_skew": round(skew_data["skew_value"], 2),
            "pcr_velocity": pcr_velocity,
            "rsi_14": price_indicators.get("rsi_14", 50.0),
            "sma_20": price_indicators.get("sma_20", spot),
            "ema_9": price_indicators.get("ema_9", spot),
            "bb_upper_dist": price_indicators.get("bb_upper_dist", 0.0),
            "bb_lower_dist": price_indicators.get("bb_lower_dist", 0.0),
        },
        net_gex            = gex_data["net_gex"],
        zero_gamma_level   = gex_data["zero_gamma_level"],
        oi_velocity_score  = velocity_signal.score,
        oi_velocity_conf   = velocity_signal.confidence,
        oi_velocity_reason = velocity_signal.reason,
        pcr_velocity       = pcr_velocity,
        **price_indicators,
        **uoa_stats,
    )
