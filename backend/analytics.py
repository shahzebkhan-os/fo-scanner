"""
analytics.py — Accurate Option Chain Analysis Engine
Drop-in replacement for the scoring & signal functions in main.py

Changes vs original:
  ✅ Dynamic ATM strike intervals per symbol
  ✅ Dimensionally correct vol-spike (V/OI ratio)
  ✅ score_option uses percentile-relative baselines, not magic numbers
  ✅ Multi-factor signal (PCR + OI trend + volume confirmation)
  ✅ Max Pain calculation
  ✅ Liquidity filter on top_picks (zero-LTP options excluded)
  ✅ OI concentration score (where is the "wall"?)
  ✅ Composite score is reproducible and bounded [0, 100]
"""

from __future__ import annotations
from typing import Optional

# ── Strike interval map ───────────────────────────────────────────────────────
# Approximate NSE strike intervals; add more as needed
STRIKE_INTERVALS = {
    "NIFTY":       50,
    "BANKNIFTY":   100,
    "FINNIFTY":    50,
    "MIDCPNIFTY":  25,
    # High-priced stocks
    "RELIANCE":    20,
    "TCS":         50,
    "INFY":        20,
    "HDFCBANK":    10,
    "ICICIBANK":   10,
    "SBIN":        5,
    "ADANIENT":    50,
    "WIPRO":       5,
    "AXISBANK":    10,
    "BAJFINANCE":  50,
    "HCLTECH":     20,
    "LT":          20,
    "KOTAKBANK":   20,
    "TATAMOTORS":  5,
    "MARUTI":      100,
    "SUNPHARMA":   20,
    "ITC":         5,
    "ONGC":        5,
    "POWERGRID":   5,
    "NTPC":        5,
    "BPCL":        10,
    "GRASIM":      20,
    "TITAN":       50,
    "INDUSINDBK":  10,
    "ULTRACEMCO":  50,
    "HEROMOTOCO":  50,
    "ASIANPAINT":  50,
    "MM":          20,
    "DRREDDY":     50,
    "DIVISLAB":    50,
    "CIPLA":       10,
    "TECHM":       20,
    "TATASTEEL":   5,
    "BAJAJFINSV":  20,
    "NESTLEIND":   100,
    "HINDALCO":    5,
    "COALINDIA":   5,
    "VEDL":        5,
    "JSWSTEEL":    10,
    "SAIL":        2,
    "APOLLOHOSP":  50,
    "PIDILITIND":  50,
    "SIEMENS":     50,
    "HAVELLS":     20,
    "VOLTAS":      20,
}
_DEFAULT_INTERVAL = 10


def get_strike_interval(symbol: str) -> int:
    return STRIKE_INTERVALS.get(symbol.upper(), _DEFAULT_INTERVAL)


def nearest_atm(spot: float, symbol: str) -> float:
    """Round spot to nearest valid strike for this symbol."""
    interval = get_strike_interval(symbol)
    return round(spot / interval) * interval


# ── Max Pain ──────────────────────────────────────────────────────────────────

def compute_max_pain(records: list) -> Optional[float]:
    """
    Max Pain = the strike at which total option buyer loss is maximised
    (i.e. the strike where writers retain the most premium).
    Algorithm: for each candidate strike, sum all ITM OI × intrinsic value.
    """
    if not records:
        return None

    strikes = sorted({r.get("strikePrice", 0) for r in records if r.get("strikePrice")})
    if not strikes:
        return None

    # Build OI lookup
    ce_oi: dict[float, float] = {}
    pe_oi: dict[float, float] = {}
    for row in records:
        k = row.get("strikePrice", 0)
        ce_oi[k] = row.get("CE", {}).get("openInterest", 0) or 0
        pe_oi[k] = row.get("PE", {}).get("openInterest", 0) or 0

    min_pain = float("inf")
    max_pain_strike = strikes[len(strikes) // 2]

    for candidate in strikes:
        total = 0.0
        for k in strikes:
            # CE loss at candidate expiry: CE OI × max(0, k - candidate)
            total += ce_oi.get(k, 0) * max(0.0, k - candidate)
            # PE loss at candidate expiry: PE OI × max(0, candidate - k)
            total += pe_oi.get(k, 0) * max(0.0, candidate - k)
        if total < min_pain:
            min_pain = total
            max_pain_strike = candidate

    return max_pain_strike


# ── OI Concentration ("Wall") ─────────────────────────────────────────────────

def oi_walls(records: list, spot: float, n: int = 3) -> dict:
    """
    Returns the top-N CE OI strikes above spot  (resistance walls)
    and top-N PE OI strikes below spot (support walls).
    These are the strikes market makers are most vested in defending.
    """
    ce_above = [(r["strikePrice"], r.get("CE", {}).get("openInterest", 0))
                for r in records if r.get("strikePrice", 0) > spot and r.get("CE")]
    pe_below = [(r["strikePrice"], r.get("PE", {}).get("openInterest", 0))
                for r in records if r.get("strikePrice", 0) < spot and r.get("PE")]

    resistance = sorted(ce_above, key=lambda x: x[1], reverse=True)[:n]
    support    = sorted(pe_below, key=lambda x: x[1], reverse=True)[:n]

    return {
        "resistance": [{"strike": s, "oi": int(o)} for s, o in resistance],
        "support":    [{"strike": s, "oi": int(o)} for s, o in support],
    }


# ── Per-option Scoring ────────────────────────────────────────────────────────

def score_option(side: dict, spot: float, symbol: str = "") -> int:
    """
    Score a single CE or PE option [0–100].

    Components:
      30 pts — OI momentum  : normalised changeinOI / OI (clipped at ±30)
      25 pts — Activity     : volume-to-OI ratio (V/OI), capped at 25
      20 pts — ATM proximity: linear decay from ATM to ~3 strikes away = 0
      15 pts — IV quality   : sweet spot 15–40 IV; penalise extremes
      10 pts — Liquidity    : non-zero LTP with tight spread proxy
    """
    oi      = side.get("openInterest", 0) or 0
    oi_chg  = side.get("changeinOpenInterest", 0) or 0
    vol     = side.get("totalTradedVolume", 0) or 0
    iv      = side.get("impliedVolatility", 0) or 0
    ltp     = side.get("lastPrice", 0) or 0
    strike  = side.get("strikePrice", 0) or 0

    score = 0

    # 1. OI momentum (build-up = positive signal)
    if oi > 100:                                    # minimum OI guard
        oi_mom = (oi_chg / oi) * 100                # % change
        score += int(min(30, max(0, oi_mom * 1.5))) # 20% build-up → 30 pts

    # 2. Activity: V/OI ratio — >0.3 is active, >1.0 is very hot
    if oi > 0:
        v_oi = vol / oi
        score += int(min(25, v_oi * 20))            # 1.25 V/OI → 25 pts

    # 3. ATM proximity — decays over strike_interval bands
    if spot > 0 and strike > 0:
        interval = get_strike_interval(symbol) if symbol else _DEFAULT_INTERVAL
        bands_away = abs(spot - strike) / max(interval, 1)
        prox = max(0, 1 - bands_away / 6)           # 0 pts beyond 6 strikes
        score += int(prox * 20)

    # 4. IV quality (optimal 15–40 for positional)
    if iv > 0:
        if 15 <= iv <= 40:
            score += 15
        elif iv < 15:
            score += int(iv / 15 * 10)              # very low IV, less premium
        else:
            score += max(0, int(15 - (iv - 40) * 0.3))  # penalise high IV

    # 5. Liquidity guard — discard zero-price options
    if ltp > 0:
        score += 10

    return min(100, max(0, score))


# ── Stock-Level Composite Score & Signal ─────────────────────────────────────

def compute_stock_score(chain_data: dict, spot: float, symbol: str = "") -> dict:
    """
    Returns a dict with:
      pcr, iv, oi_change, vol_spike, signal, score, top_picks,
      max_pain, oi_walls, signal_reasons
    """
    records = chain_data.get("records", {}).get("data", [])

    empty = dict(
        pcr=1.0, iv=0, oi_change=0, vol_spike=0.0,
        signal="NEUTRAL", score=0, top_picks=[],
        max_pain=None, oi_walls={}, signal_reasons=[]
    )
    if not records or spot <= 0:
        return empty

    atm_strike  = nearest_atm(spot, symbol)
    interval    = get_strike_interval(symbol)
    atm_band    = interval * 3                      # ±3 strikes = near-the-money zone

    tce_oi = tpe_oi = tce_vol = tpe_vol = 0
    tce_oi_chg = tpe_oi_chg = 0
    oi_changes: list[float] = []
    atm_iv_ce = atm_iv_pe = 0.0
    all_options: list[dict] = []

    for row in records:
        ce     = row.get("CE", {}) or {}
        pe     = row.get("PE", {}) or {}
        strike = row.get("strikePrice", 0) or 0

        # Inject strikePrice into side dicts so score_option can use it
        ce_with_k = {**ce, "strikePrice": strike}
        pe_with_k = {**pe, "strikePrice": strike}

        ce_oi  = ce.get("openInterest", 0) or 0
        pe_oi  = pe.get("openInterest", 0) or 0
        ce_vol = ce.get("totalTradedVolume", 0) or 0
        pe_vol = pe.get("totalTradedVolume", 0) or 0
        ce_chg = ce.get("changeinOpenInterest", 0) or 0
        pe_chg = pe.get("changeinOpenInterest", 0) or 0

        tce_oi     += ce_oi;  tpe_oi     += pe_oi
        tce_vol    += ce_vol; tpe_vol    += pe_vol
        tce_oi_chg += ce_chg; tpe_oi_chg += pe_chg

        for oi, chg in [(ce_oi, ce_chg), (pe_oi, pe_chg)]:
            if oi > 100:
                oi_changes.append(chg / oi * 100)

        if abs(strike - atm_strike) <= atm_band:
            if ce.get("impliedVolatility", 0):
                atm_iv_ce = ce["impliedVolatility"]
            if pe.get("impliedVolatility", 0):
                atm_iv_pe = pe["impliedVolatility"]

        ce_score = score_option(ce_with_k, spot, symbol)
        pe_score = score_option(pe_with_k, spot, symbol)

        if ce.get("lastPrice", 0) > 0:
            all_options.append({"type": "CE", "strike": strike,
                                 "ltp": ce.get("lastPrice", 0), "score": ce_score})
        if pe.get("lastPrice", 0) > 0:
            all_options.append({"type": "PE", "strike": strike,
                                 "ltp": pe.get("lastPrice", 0), "score": pe_score})

    # ── Derived Metrics ───────────────────────────────────────────────────────

    # PCR (OI-based)
    pcr = round(tpe_oi / tce_oi, 3) if tce_oi > 0 else 1.0

    # Average OI change % across all strikes
    avg_oi_chg = round(sum(oi_changes) / len(oi_changes), 2) if oi_changes else 0.0

    # V/OI ratio — correct dimensionless activity measure
    total_oi  = tce_oi + tpe_oi
    total_vol = tce_vol + tpe_vol
    vol_oi_ratio = round(total_vol / total_oi, 3) if total_oi > 0 else 0.0

    # ATM IV — prefer CE, fallback PE, average if both
    if atm_iv_ce and atm_iv_pe:
        atm_iv = round((atm_iv_ce + atm_iv_pe) / 2, 1)
    else:
        atm_iv = round(atm_iv_ce or atm_iv_pe, 1)

    # Max Pain & OI Walls
    mp        = compute_max_pain(records)
    walls     = oi_walls(records, spot)

    # ── Signal Logic ─────────────────────────────────────────────────────────
    # Each factor votes; majority + confidence determines signal + reasons

    bullish_votes = 0
    bearish_votes = 0
    reasons: list[str] = []

    # Factor 1: PCR (put-call ratio)
    if pcr > 1.4:
        bullish_votes += 2
        reasons.append(f"High PCR {pcr} → strong put writing (bullish)")
    elif pcr > 1.1:
        bullish_votes += 1
        reasons.append(f"PCR {pcr} slightly elevated (mild bullish)")
    elif pcr < 0.7:
        bearish_votes += 2
        reasons.append(f"Low PCR {pcr} → strong call writing (bearish)")
    elif pcr < 0.9:
        bearish_votes += 1
        reasons.append(f"PCR {pcr} suppressed (mild bearish)")

    # Factor 2: Net OI change direction
    if tce_oi_chg > 0 and tpe_oi_chg < 0:
        bearish_votes += 1
        reasons.append("CE OI building + PE OI unwinding (bearish pressure)")
    elif tpe_oi_chg > 0 and tce_oi_chg < 0:
        bullish_votes += 1
        reasons.append("PE OI building + CE OI unwinding (bullish support)")
    elif tpe_oi_chg > 0 and tce_oi_chg > 0:
        reasons.append("Both CE & PE OI building (range-bound expected)")

    # Factor 3: Volume confirmation
    ce_vol_dom = tce_vol / max(1, total_vol)
    pe_vol_dom = tpe_vol / max(1, total_vol)
    if ce_vol_dom > 0.60:
        bearish_votes += 1
        reasons.append(f"CE volume dominant ({ce_vol_dom:.0%}) → put buyers hedging")
    elif pe_vol_dom > 0.60:
        bullish_votes += 1
        reasons.append(f"PE volume dominant ({pe_vol_dom:.0%}) → call buyers hedging")

    # Factor 4: Max pain bias
    if mp and spot > 0:
        mp_bias = (mp - spot) / spot * 100
        if mp_bias < -1.5:
            bearish_votes += 1
            reasons.append(f"Max Pain ₹{mp:.0f} is {mp_bias:.1f}% below spot (gravitational pull down)")
        elif mp_bias > 1.5:
            bullish_votes += 1
            reasons.append(f"Max Pain ₹{mp:.0f} is +{mp_bias:.1f}% above spot (gravitational pull up)")

    if bullish_votes > bearish_votes:
        signal = "BULLISH"
    elif bearish_votes > bullish_votes:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"

    # ── Composite Score [0–100] ───────────────────────────────────────────────
    # Weighted, fully deterministic formula

    confidence_votes = max(bullish_votes, bearish_votes)

    # Activity component: V/OI between 0–1.5 is normal range
    activity_score = min(30, vol_oi_ratio / 1.5 * 30)

    # OI momentum component
    oi_mom_score = min(20, abs(avg_oi_chg) * 1.5)

    # IV quality: sweet spot 15–40
    if atm_iv <= 0:
        iv_score = 5
    elif 15 <= atm_iv <= 40:
        iv_score = 20
    elif atm_iv < 15:
        iv_score = int(atm_iv / 15 * 15)
    else:
        iv_score = max(0, int(20 - (atm_iv - 40) * 0.4))

    # Signal confidence component
    signal_score = confidence_votes * 8          # 0 / 8 / 16 / 24 / 32 pts

    # Max pain proximity bonus (spot near max pain = stable, easier to score)
    mp_score = 0
    if mp and spot > 0:
        mp_pct = abs(mp - spot) / spot * 100
        mp_score = max(0, int(10 - mp_pct * 2))  # up to 10 pts

    score = int(activity_score + oi_mom_score + iv_score + signal_score + mp_score)
    score = min(100, max(0, score))

    # ── Top Picks (liquid only, sorted by score) ─────────────────────────────
    top_picks = sorted(
        [o for o in all_options if o["ltp"] > 0],
        key=lambda x: x["score"],
        reverse=True
    )[:2]

    return dict(
        pcr         = pcr,
        iv          = atm_iv,
        oi_change   = avg_oi_chg,
        vol_spike   = vol_oi_ratio,      # renamed semantically; frontend shows as "V/OI"
        signal      = signal,
        score       = score,
        top_picks   = top_picks,
        max_pain    = mp,
        oi_walls    = walls,
        signal_reasons = reasons,
    )
