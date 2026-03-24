"""
fo_trades.py — Tiered F&O Trade Discovery Pipeline

Applies research-backed filters to scan data:
  1. Liquidity Gate — skip illiquid symbols
  2. Confluence Gate — require ≥3 of 5 scoring factors to align
  3. DTE-Strategy Match — filter bad DTE/strategy combos
  4. Time Window Advisory — tag entry window quality
  5. Max Pain Convergence — flag range-bound setups near expiry
  6. Bulk Deal Bonus — boost conviction when deals align
"""

from __future__ import annotations

import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional

from .constants import LOT_SIZES
from .signals_legacy import get_sector, get_deals_for_scan
from .earnings import get_days_to_earnings
from . import db

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

# ── Filter thresholds ─────────────────────────────────────────────────────────
MIN_VOLUME_MULTIPLIER = 5       # option volume must be ≥ N × lot_size
MIN_CONFLUENCE_FACTORS = 3      # at least N of 5 factors must individually align
MIN_CONVICTION = 55             # floor for final conviction score
BULK_DEAL_BONUS = 8             # conviction pts added when bulk deals align
MAX_PAIN_CONVERGENCE_PCT = 1.0  # |spot - max_pain| / spot * 100

# DTE windows per strategy type
STRATEGY_DTE_RANGES = {
    "long_call":        (3, 20),
    "long_put":         (3, 20),
    "bull_call_spread":  (10, 45),
    "bear_put_spread":   (10, 45),
    "bull_put_spread":   (10, 45),
    "bear_call_spread":  (10, 45),
    "iron_condor":       (15, 50),
    "short_straddle":    (5, 20),
}

# Time-of-day windows (IST hours)
TIME_WINDOWS = [
    (( 9, 15), ( 9, 45), "avoid",   "Opening volatility — avoid new entries"),
    (( 9, 45), (10, 30), "optimal", "Best entry window — OI building, spreads tight"),
    ((10, 30), (13,  0), "good",    "Mid-day stability — reliable signals"),
    ((13,  0), (14, 30), "okay",    "Afternoon drift — watch momentum"),
    ((14, 30), (15,  0), "optimal", "Expiry week Max Pain convergence window"),
    ((15,  0), (15, 30), "avoid",   "Closing auction — avoid distortions"),
]


def is_safe_entry_window(now: Optional[datetime] = None) -> tuple[bool, Optional[str]]:
    now = now or datetime.now(IST)
    from datetime import time
    current_time = now.time()
    
    BLOCKED_WINDOWS = [
        (time(9, 15), time(9, 45)),   # Opening volatility flush
        (time(15, 0), time(15, 30)),  # Closing auction distortion
    ]
    
    for start, end in BLOCKED_WINDOWS:
        if start <= current_time <= end:
            return False, f"Blocked window: {start}–{end}"
    
    return True, None

def _get_time_window(now: Optional[datetime] = None) -> dict:
    """Return current time window advisory."""
    now = now or datetime.now(IST)
    h, m = now.hour, now.minute

    for (sh, sm), (eh, em), quality, reason in TIME_WINDOWS:
        start = sh * 60 + sm
        end   = eh * 60 + em
        curr  = h  * 60 + m
        if start <= curr < end:
            return {"quality": quality, "reason": reason, "time": now.strftime("%H:%M")}

    if h < 9 or (h == 9 and m < 15):
        return {"quality": "pre_market", "reason": "Market not open yet", "time": now.strftime("%H:%M")}
    return {"quality": "closed", "reason": "Market closed", "time": now.strftime("%H:%M")}


def _check_confluence(stock: dict) -> dict:
    """
    Evaluate 5 independent factors on a 0-100 scale.
    Requires at least 3 factors to score >= 40.
    At least one must be Price Action, and one from Derivatives.
    """

    signal = stock.get("signal", "NEUTRAL")
    metrics = stock.get("metrics", {})
    spot = stock.get("ltp", 0)

    factors = {}

    # 1. GEX (Group A)
    gex = metrics.get("gex", 0)
    gex_score = 0
    if signal == "BULLISH" and gex > 50_000: gex_score = 80
    elif signal == "BEARISH" and gex < -50_000: gex_score = 80
    factors["gex"] = {"group": "group_a", "score": gex_score, "value": gex}

    # 2. PCR (Group A)
    pcr = stock.get("pcr", 1.0)
    pcr_score = 0
    if signal == "BULLISH" and pcr > 1.1: pcr_score = 80
    elif signal == "BEARISH" and pcr < 0.9: pcr_score = 80
    factors["pcr"] = {"group": "group_a", "score": pcr_score, "value": pcr}

    # 3. IV Skew (Group A)
    iv_skew = metrics.get("iv_skew", 0)
    skew_score = 0
    if signal == "BULLISH" and iv_skew < -0.2: skew_score = 80
    elif signal == "BEARISH" and iv_skew > 0.2: skew_score = 80
    factors["iv_skew"] = {"group": "group_a", "score": skew_score, "value": iv_skew}

    # 4. OI Velocity (Group B)
    oi_vel = stock.get("oi_velocity_score", 0)
    vel_score = 0
    if signal == "BULLISH" and oi_vel > 0.3: vel_score = 80
    elif signal == "BEARISH" and oi_vel < -0.3: vel_score = 80
    factors["oi_velocity"] = {"group": "group_b", "score": vel_score, "value": oi_vel}

    # 5. Price Action (Group B)
    rsi = metrics.get("rsi_14", 50)
    ema = metrics.get("ema_9", spot)
    pa_score = 0
    if signal == "BULLISH" and spot > ema and rsi >= 50: pa_score = 80
    elif signal == "BEARISH" and spot < ema and rsi <= 50: pa_score = 80
    factors["price_action"] = {"group": "group_b", "score": pa_score, "value": rsi}

    MIN_FACTOR_SCORE = 40
    MIN_FACTORS_ALIGNED = 3

    aligned_factors = {k: v for k, v in factors.items() if v["score"] >= MIN_FACTOR_SCORE}
    aligned_count = len(aligned_factors)

    group_a_count = sum(1 for v in aligned_factors.values() if v["group"] == "group_a")
    group_b_count = sum(1 for v in aligned_factors.values() if v["group"] == "group_b")

    passed = (group_a_count >= 2) and (group_b_count >= 1)

    # Format output backwards compatible with UI
    formatted_factors = []
    for k, v in factors.items():
        formatted_factors.append({"name": k.upper(), "aligned": v["score"] >= MIN_FACTOR_SCORE, "value": round(v["value"], 2) if isinstance(v["value"], float) else v["value"]})

    return {"passed": passed, "aligned": aligned_count, "total": len(factors), "factors": formatted_factors}


def _check_multi_day_oi_trend(symbol: str, signal: str) -> dict:
    """Check if the OI trend aligns with the signal over the last 3 days."""
    try:
        from . import db
        totals = db.get_daily_oi_totals(symbol, days=3)
        if len(totals) < 2:
            return {"valid": True, "aligned": False, "reason": "Not enough OI history to confirm trend"}
            
        dates = sorted(list(totals.keys()))
        first = totals[dates[0]]
        last = totals[dates[-1]]
        
        ce_chg = last.get("CE", 0) - first.get("CE", 0)
        pe_chg = last.get("PE", 0) - first.get("PE", 0)
        
        # We want to see a minimum threshold of change (e.g., 0.5% of total OI)
        total_oi = last.get("CE", 0) + last.get("PE", 0)
        threshold = total_oi * 0.005  
        
        if signal == "BULLISH":
            aligned = pe_chg > ce_chg and pe_chg > threshold
            reason = "PE writing (bulls defending puts)" if aligned else "Contradictory OI trend"
            return {"valid": aligned, "aligned": aligned, "reason": f"{reason} (PE change: {pe_chg:,.0f}, CE change: {ce_chg:,.0f})"}
        elif signal == "BEARISH":
            aligned = ce_chg > pe_chg and ce_chg > threshold
            reason = "CE writing (bears defending calls)" if aligned else "Contradictory OI trend"
            return {"valid": aligned, "aligned": aligned, "reason": f"{reason} (CE change: {ce_chg:,.0f}, PE change: {pe_chg:,.0f})"}
            
        return {"valid": True, "aligned": False, "reason": "Neutral signal"}
        
    except Exception as e:
        return {"valid": True, "aligned": False, "reason": f"Error checking OI trend: {e}"}


def _check_dte_strategy_match(strategy_code: str, dte: int) -> dict:
    """Check if DTE fits the strategy. Returns {valid, reason}."""
    dte_range = STRATEGY_DTE_RANGES.get(strategy_code)
    if not dte_range:
        return {"valid": True, "reason": "No DTE constraint for this strategy"}

    lo, hi = dte_range
    if dte < lo:
        return {"valid": False, "reason": f"DTE {dte} too low for {strategy_code} (min {lo})"}
    if dte > hi:
        return {"valid": False, "reason": f"DTE {dte} too high for {strategy_code} (max {hi})"}
    return {"valid": True, "reason": f"DTE {dte} within range ({lo}–{hi})"}

PREMIUM_SELL_STRATEGIES = ['short_straddle', 'iron_condor', 'credit_spread']

def _iv_rank_gate(strategy: str, iv_rank: float) -> dict:
    if not strategy or not iv_rank:
        return {'pass': True, "reason": ""}
        
    s = strategy.lower()
    if s in PREMIUM_SELL_STRATEGIES:
        if iv_rank < 40:
            return {'pass': False, 'reason': f"IV Rank {iv_rank} too low for premium selling"}
    
    if s in ['long_call', 'long_put']:
        if iv_rank > 75:
            return {'pass': False, 'reason': f"IV Rank {iv_rank} too high — buying expensive premium"}
            
    return {'pass': True, 'reason': f"IV Rank {iv_rank} valid for {strategy}"}


def _check_max_pain_convergence(stock: dict) -> dict:
    """Check if spot is converging to max pain near expiry."""
    max_pain = stock.get("max_pain")
    spot = stock.get("ltp", 0) or stock.get("spot_price", 0)
    dte = stock.get("days_to_expiry", 30)

    if not max_pain or not spot:
        return {"converging": False, "distance_pct": None, "reason": "No max pain data"}

    dist_pct = abs(spot - max_pain) / spot * 100
    converging = dist_pct <= MAX_PAIN_CONVERGENCE_PCT and dte <= 3

    return {
        "converging": converging,
        "distance_pct": round(dist_pct, 2),
        "max_pain": max_pain,
        "dte": dte,
        "reason": f"Spot {dist_pct:.1f}% from max pain, DTE={dte}" + (" → CONVERGENCE" if converging else ""),
    }


def run_pipeline(scan_data: list, suggestions: list, now: Optional[datetime] = None) -> dict:
    """
    Run the full tiered pipeline on scan data + suggestions.

    Returns:
    {
        "timestamp": str,
        "time_window": dict,
        "pipeline": { "scanned": int, "after_liquidity": int, "after_confluence": int, "after_dte": int, "final": int },
        "trades": [ ... enriched trade dicts ... ]
    }
    """
    now = now or datetime.now(IST)
    time_window = _get_time_window(now)
    
    safe_window, safe_reason = is_safe_entry_window(now)
    if not safe_window:
        log.warning(f"Pipeline execution blocked by time guard. {safe_reason}")
        # Return an empty set if it's not a safe entry window
        return {
            "timestamp": now.isoformat(),
            "time_window": time_window,
            "pipeline": {"scanned": len(scan_data), "after_liquidity": 0, "after_confluence": 0, "after_dte": 0, "final": 0},
            "count": 0,
            "trades": []
        }

    # Build lookup from suggestions
    sug_map = {}
    for s in suggestions:
        sug_map[s.get("symbol", "")] = s

    # Bulk deal lookup
    try:
        deals_map = get_deals_for_scan(scan_data)
    except Exception:
        deals_map = {}

    # Pipeline counts
    pipeline = {
        "scanned": len(scan_data),
        "after_liquidity": 0,
        "after_confluence": 0,
        "after_dte": 0,
        "final": 0,
    }

    trades = []

    for stock in scan_data:
        symbol = stock.get("symbol", "")
        signal = stock.get("signal", "NEUTRAL")
        score  = stock.get("score", 0)
        spot   = stock.get("ltp", 0)
        dte    = stock.get("days_to_expiry", 30)

        # Skip neutrals with low scores
        if signal == "NEUTRAL" and score < 60:
            continue

        # ── Stage 1: Liquidity Gate ──
        total_vol = stock.get("metrics", {}).get("total_volume", 0)
        # Fallback: use ce_vol + pe_vol if available
        if not total_vol:
            total_vol = (stock.get("metrics", {}).get("ce_vol", 0) or 0) + (stock.get("metrics", {}).get("pe_vol", 0) or 0)
        lot_size = LOT_SIZES.get(symbol, 50)
        min_vol  = lot_size * MIN_VOLUME_MULTIPLIER

        # If we have volume data, enforce the gate; otherwise pass through
        liquidity_pass = total_vol >= min_vol if total_vol > 0 else True
        if not liquidity_pass:
            continue
        pipeline["after_liquidity"] += 1

        # ── Stage 2: Confluence Gate ──
        confluence = _check_confluence(stock)
        if signal != "NEUTRAL" and not confluence["passed"]:
            continue
        pipeline["after_confluence"] += 1

        # ── Stage 3: DTE-Strategy Match ──
        sug = sug_map.get(symbol, {})
        strategy_code = (sug.get("strategy", {}) or {}).get("strategy_code", "")
        dte_check = _check_dte_strategy_match(strategy_code, dte)
        if not dte_check["valid"]:
            log.info(f"{symbol} dropped | strategy={strategy_code} | dte={dte} | " + 
                     f"valid_range={STRATEGY_DTE_RANGES.get(strategy_code)}")
            continue
        pipeline["after_dte"] += 1
        
        # ── Stage 3.5: IV Rank Gate ──
        iv_rank = stock.get("iv_rank", 50)
        iv_gate_check = _iv_rank_gate(strategy_code, iv_rank)
        if not iv_gate_check["pass"]:
            log.info(f"{symbol} dropped | strategy={strategy_code} | iv_rank={iv_rank} | reason={iv_gate_check['reason']}")
            continue

        # ── Stage 4: Multi-Day OI Trend (P1.1) ──
        oi_trend = _check_multi_day_oi_trend(symbol, signal)
        
        # ── Stage 4.5: Max Pain Convergence ──
        mp_check = _check_max_pain_convergence(stock)

        # ── Stage 4.8: Earnings Event Gate ──
        earnings_event = get_days_to_earnings(symbol)
        if earnings_event.get("data_missing"):
            stock.setdefault("signal_reasons", []).append("⚠️ Event data unavailable — verify manually")
            score = max(0, score - 5)
        else:
            dte_earnings = earnings_event.get("days_away", 999)
            if dte_earnings <= 5:
                if strategy_code in ("long_call", "long_put", "short_straddle", "strangle"):
                    # Drop naked long options and short volatility plays going into earnings
                    continue
                # Note: For defined risk spreads, we allow the trade but penalize score/add alert
                score = max(0, score - 10)
                stock.setdefault("signal_reasons", []).append(f"⚠️ High Volatility Event (Earnings in {dte_earnings}d)")

        # ── Stage 5: Bulk Deal Bonus (P1.2) ──
        sym_deals = deals_map.get(symbol, [])
        deal_score_modifier = 0
        has_aligned_deal = False
        today_iso = date.today().isoformat()
        if sym_deals:
            for deal in sym_deals:
                # Ensure the deal is from today
                if deal.get("date") != today_iso:
                    continue
                deal_type = deal.get("type", "").upper()
                if (signal == "BULLISH" and "BUY" in deal_type) or (signal == "BEARISH" and "SELL" in deal_type):
                    deal_score_modifier += 5
                    has_aligned_deal = True
                elif (signal == "BULLISH" and "SELL" in deal_type) or (signal == "BEARISH" and "BUY" in deal_type):
                    deal_score_modifier -= 8
                else:
                    deal_score_modifier += 2 # Unknown direction

        # ── Compute Final Conviction ──
        conviction = score
        if deal_score_modifier != 0:
            conviction = min(100, max(0, conviction + deal_score_modifier))
        if oi_trend["aligned"]:
            conviction = min(100, conviction + 5)
        if mp_check["converging"] and signal == "NEUTRAL":
            conviction = min(100, conviction + 5)

        if conviction < MIN_CONVICTION:
            continue

        pipeline["final"] += 1

        # ── Build enriched trade object ──
        entry = sug.get("entry", {})
        rr    = sug.get("risk_reward", {})
        sizing = sug.get("sizing", {})

        trade = {
            "symbol":      symbol,
            "signal":      signal,
            "score":       score,
            "conviction":  conviction,
            "conviction_label": _conviction_label(conviction),
            "sector":      get_sector(symbol),
            "spot":        round(spot, 2),
            "regime":      stock.get("regime", "TRENDING"),
            "iv":          stock.get("iv", 0),
            "iv_rank":     stock.get("iv_rank", 50),
            "pcr":         stock.get("pcr", 1.0),
            "dte":         dte,
            "max_pain":    stock.get("max_pain"),
            "ml_prob":     stock.get("ml_bullish_probability"),

            # Strategy
            "strategy":    sug.get("strategy", {}),
            "entry":       entry,
            "risk_reward": rr,
            "sizing":      sizing,

            # Pipeline analysis
            "confluence":    confluence,
            "dte_check":     dte_check,
            "oi_trend":      oi_trend,
            "max_pain_conv": mp_check,
            "time_window":   time_window,
            "bulk_deals":    len(sym_deals),
            "bulk_aligned":  has_aligned_deal,

            # Signal reasons
            "tags":    sug.get("tags", stock.get("signal_reasons", [])),
            "reasons": stock.get("signal_reasons", [])[:5],
        }

        trades.append(trade)

    # Sort by conviction descending
    trades.sort(key=lambda t: t["conviction"], reverse=True)

    return {
        "timestamp":   now.isoformat(),
        "time_window": time_window,
        "pipeline":    pipeline,
        "count":       len(trades),
        "trades":      trades,
    }


def _conviction_label(score: int) -> str:
    if score >= 90: return "VERY HIGH"
    if score >= 80: return "HIGH"
    if score >= 70: return "MODERATE"
    if score >= 60: return "LOW"
    return "VERY LOW"
