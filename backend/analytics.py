"""
analytics.py — Option Analytics Engine v4
Covers: Black-Scholes Greeks, IV Rank, Max Pain, OI Walls,
        score_option, compute_stock_score, position sizing
"""

from __future__ import annotations
import math
from typing import Optional

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
# Position Sizing
# ══════════════════════════════════════════════════════════════════════════════

def compute_lot_size_for_risk(
    capital: float,
    entry_price: float,
    lot_size: int,
    risk_pct: float = 2.0,
    sl_pct:   float = 25.0,
) -> dict:
    """
    Given total capital and a max-risk-per-trade percentage,
    returns how many lots to trade and the rupee risk.

    risk_pct : % of capital to risk per trade (default 2%)
    sl_pct   : stop-loss % (default 25%)
    """
    if entry_price <= 0 or lot_size <= 0:
        return {"lots": 1, "risk_per_lot": 0, "total_risk": 0, "allocation": 0}

    max_risk_rs    = capital * risk_pct / 100
    risk_per_lot   = entry_price * lot_size * sl_pct / 100
    lots           = max(1, int(max_risk_rs / risk_per_lot)) if risk_per_lot > 0 else 1
    actual_risk    = lots * risk_per_lot
    allocation     = lots * lot_size * entry_price

    return {
        "lots":        lots,
        "risk_per_lot": round(risk_per_lot, 2),
        "total_risk":  round(actual_risk, 2),
        "allocation":  round(allocation, 2),
        "risk_pct_of_capital": round(actual_risk / capital * 100, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
# score_option  (v4 — all bugs fixed)
# ══════════════════════════════════════════════════════════════════════════════

def score_option(
    side:     dict,
    spot:     float,
    symbol:   str  = "",
    dte:      int  = 30,
    iv_rank:  float = 50.0,
) -> int:
    """
    Score a single option [0–100].
    MUST have strikePrice injected: {**ce, "strikePrice": strike}

    Components:
      30 pts  OI momentum   (% build-up, min 100 OI guard)
      25 pts  Activity      (V/OI ratio, self-scaling)
      20 pts  ATM proximity (per-symbol interval)
      15 pts  IV quality    (15-40 sweet spot; IVR-adjusted)
      10 pts  Liquidity     (non-zero LTP)
    """
    oi     = side.get("openInterest", 0) or 0
    oi_chg = side.get("changeinOpenInterest", 0) or 0
    vol    = side.get("totalTradedVolume", 0) or 0
    iv     = side.get("impliedVolatility", 0) or 0
    ltp    = side.get("lastPrice", 0) or 0
    strike = side.get("strikePrice", 0) or 0
    score  = 0

    # 1 — OI momentum
    if oi > 100:
        oi_pct = oi_chg / oi * 100
        score += int(min(30, max(0, oi_pct * 1.5)))

    # 2 — V/OI ratio
    if oi > 0:
        score += int(min(25, (vol / oi) * 20))

    # 3 — ATM proximity
    if spot > 0 and strike > 0:
        interval   = get_strike_interval(symbol) if symbol else 10
        bands_away = abs(spot - strike) / max(interval, 1)
        score     += int(max(0, 1.0 - bands_away / 6.0) * 20)

    # 4 — IV quality (IVR-aware)
    if iv > 0:
        if 15 <= iv <= 40:
            base_iv = 15
        elif iv < 15:
            base_iv = int(iv / 15 * 10)
        else:
            base_iv = max(0, int(15 - (iv - 40) * 0.35))

        # Bonus: if IVR < 30, buying options is cheaper — slight boost
        # Penalty: if IVR > 80, options are expensive — penalise buyers
        if iv_rank < 30:
            base_iv = min(15, int(base_iv * 1.2))
        elif iv_rank > 80:
            base_iv = int(base_iv * 0.7)
        score += base_iv

    # 5 — Liquidity
    if ltp > 0:
        score += 10

    return min(100, max(0, score))


# ══════════════════════════════════════════════════════════════════════════════
# compute_stock_score  (v4)
# ══════════════════════════════════════════════════════════════════════════════

def compute_stock_score(
    chain_data:  dict,
    spot:        float,
    symbol:      str   = "",
    expiry_str:  str   = "",
    iv_rank_data: dict = None,
) -> dict:
    """
    Full stock-level analysis.
    Returns: pcr, iv, oi_change, vol_spike, signal, score, top_picks,
             max_pain, oi_walls, signal_reasons, greeks_atm, days_to_expiry
    """
    records = chain_data.get("records", {}).get("data", [])
    _empty  = dict(
        pcr=1.0, iv=0, oi_change=0, vol_spike=0.0,
        signal="NEUTRAL", score=0, top_picks=[],
        max_pain=None, oi_walls={}, signal_reasons=[],
        greeks_atm={}, days_to_expiry=30
    )
    if not records or spot <= 0:
        return _empty

    dte        = days_to_expiry(expiry_str) if expiry_str else 30
    iv_rank    = (iv_rank_data or {}).get("iv_rank", 50.0)
    atm_strike = nearest_atm(spot, symbol)
    interval   = get_strike_interval(symbol)
    atm_band   = interval * 3

    tce_oi = tpe_oi = tce_vol = tpe_vol = tce_oi_chg = tpe_oi_chg = 0
    oi_changes: list = []
    atm_iv_ce = atm_iv_pe = 0.0
    all_options: list = []
    greeks_atm: dict = {}

    for row in records:
        ce     = row.get("CE", {}) or {}
        pe     = row.get("PE", {}) or {}
        strike = row.get("strikePrice", 0) or 0

        ce_k = {**ce, "strikePrice": strike}
        pe_k = {**pe, "strikePrice": strike}

        ce_oi  = ce.get("openInterest", 0) or 0
        pe_oi  = pe.get("openInterest", 0) or 0
        ce_vol = ce.get("totalTradedVolume", 0) or 0
        pe_vol = pe.get("totalTradedVolume", 0) or 0
        ce_chg = ce.get("changeinOpenInterest", 0) or 0
        pe_chg = pe.get("changeinOpenInterest", 0) or 0

        tce_oi += ce_oi; tpe_oi += pe_oi
        tce_vol += ce_vol; tpe_vol += pe_vol
        tce_oi_chg += ce_chg; tpe_oi_chg += pe_chg

        for oi, chg in [(ce_oi, ce_chg), (pe_oi, pe_chg)]:
            if oi > 100:
                oi_changes.append(chg / oi * 100)

        if abs(strike - atm_strike) <= atm_band:
            if ce.get("impliedVolatility"): atm_iv_ce = float(ce["impliedVolatility"])
            if pe.get("impliedVolatility"): atm_iv_pe = float(pe["impliedVolatility"])

        # Compute Greeks for ATM strike
        if strike == atm_strike and not greeks_atm:
            iv_for_greeks = atm_iv_ce or atm_iv_pe or 20.0
            greeks_atm = {
                "CE": black_scholes_greeks(spot, strike, iv_for_greeks, dte, "CE"),
                "PE": black_scholes_greeks(spot, strike, iv_for_greeks, dte, "PE"),
                "strike": strike,
            }

        ce_s = score_option(ce_k, spot, symbol, dte, iv_rank)
        pe_s = score_option(pe_k, spot, symbol, dte, iv_rank)

        if ce.get("lastPrice", 0) > 0:
            all_options.append({"type": "CE", "strike": strike,
                                 "ltp": ce["lastPrice"], "score": ce_s})
        if pe.get("lastPrice", 0) > 0:
            all_options.append({"type": "PE", "strike": strike,
                                 "ltp": pe["lastPrice"], "score": pe_s})

    # ── Metrics ───────────────────────────────────────────────────────────────
    pcr       = round(tpe_oi / tce_oi, 3) if tce_oi > 0 else 1.0
    avg_oi    = round(sum(oi_changes) / len(oi_changes), 2) if oi_changes else 0.0
    total_oi  = tce_oi + tpe_oi
    total_vol = tce_vol + tpe_vol
    vol_spike = round(total_vol / max(1, total_oi), 3)
    atm_iv    = round((atm_iv_ce + atm_iv_pe) / 2 if atm_iv_ce and atm_iv_pe
                      else atm_iv_ce or atm_iv_pe, 1)

    mp    = compute_max_pain(records)
    walls = oi_walls(records, spot)

    # ── Signal (multi-factor) ─────────────────────────────────────────────────
    bv = bev = 0
    reasons: list = []

    if pcr > 1.4:   bv += 2;  reasons.append(f"PCR {pcr} → heavy put writing (bullish)")
    elif pcr > 1.1: bv += 1;  reasons.append(f"PCR {pcr} elevated (mild bullish)")
    elif pcr < 0.7: bev += 2; reasons.append(f"PCR {pcr} → heavy call writing (bearish)")
    elif pcr < 0.9: bev += 1; reasons.append(f"PCR {pcr} suppressed (bearish)")

    if tce_oi_chg > 0 and tpe_oi_chg < 0:
        bev += 1; reasons.append("CE OI building + PE unwinding → bearish")
    elif tpe_oi_chg > 0 and tce_oi_chg < 0:
        bv += 1;  reasons.append("PE OI building + CE unwinding → bullish")

    if total_vol > 0:
        if tce_vol / total_vol > 0.62:
            bev += 1; reasons.append(f"CE volume dominant ({tce_vol/total_vol:.0%})")
        elif tpe_vol / total_vol > 0.62:
            bv += 1;  reasons.append(f"PE volume dominant ({tpe_vol/total_vol:.0%})")

    if mp and spot > 0:
        mp_pct = (mp - spot) / spot * 100
        if mp_pct < -1.5:   bev += 1; reasons.append(f"Max Pain ₹{mp:.0f} below spot ({mp_pct:+.1f}%)")
        elif mp_pct > 1.5:  bv += 1;  reasons.append(f"Max Pain ₹{mp:.0f} above spot ({mp_pct:+.1f}%)")

    # IVR factor
    if iv_rank > 0:
        if iv_rank > 75:
            reasons.append(f"IVR {iv_rank:.0f} → options expensive, favour selling")
        elif iv_rank < 25:
            reasons.append(f"IVR {iv_rank:.0f} → options cheap, favour buying")

    signal = "BULLISH" if bv > bev else "BEARISH" if bev > bv else "NEUTRAL"

    # ── Composite Score ───────────────────────────────────────────────────────
    activity_score = min(30, vol_spike / 1.5 * 30)
    oi_mom_score   = min(20, abs(avg_oi) * 1.5)
    iv_score       = (20 if 15 <= atm_iv <= 40 else
                      int(atm_iv / 15 * 15) if 0 < atm_iv < 15 else
                      max(0, int(20 - (atm_iv - 40) * 0.4)) if atm_iv > 40 else 5)
    signal_score   = max(bv, bev) * 8
    mp_score       = max(0, int(10 - abs(mp - spot) / spot * 100 * 2)) if mp and spot else 0
    # Expiry bonus: near expiry + good setup = higher urgency score
    expiry_bonus   = max(0, int((30 - dte) / 30 * 10)) if dte <= 30 else 0

    score = min(100, max(0, int(activity_score + oi_mom_score + iv_score +
                                signal_score + mp_score + expiry_bonus)))

    def _directional_picks(options, signal):
        """
        For a directional signal, only return the matching option type.
        BULLISH → CE only (buying calls on upward move)
        BEARISH → PE only (buying puts on downward move)
        NEUTRAL → return top 1 CE + top 1 PE for straddle awareness
        """
        if signal == "BULLISH":
            candidates = [o for o in options if o["type"] == "CE"]
        elif signal == "BEARISH":
            candidates = [o for o in options if o["type"] == "PE"]
        else:
            # NEUTRAL: return best of each side, labelled clearly
            ce_best = sorted([o for o in options if o["type"] == "CE"],
                             key=lambda x: x["score"], reverse=True)[:1]
            pe_best = sorted([o for o in options if o["type"] == "PE"],
                             key=lambda x: x["score"], reverse=True)[:1]
            return ce_best + pe_best
    
        return sorted(candidates, key=lambda x: x["score"], reverse=True)[:2]
    
    top_picks = _directional_picks(all_options, signal)

    return dict(
        pcr            = pcr,
        iv             = atm_iv,
        oi_change      = avg_oi,
        vol_spike      = vol_spike,
        signal         = signal,
        score          = score,
        top_picks      = top_picks,
        max_pain       = mp,
        oi_walls       = walls,
        signal_reasons = reasons,
        greeks_atm     = greeks_atm,
        days_to_expiry = dte,
        iv_rank        = iv_rank,
    )
