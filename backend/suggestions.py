"""
suggestions.py — Best F&O Trade Suggestions Engine

Analyzes scan results to generate ranked, actionable trade suggestions
with specific strategies, strikes, entry/exit levels, and risk/reward ratios.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Optional


def _strategy_for_signal(signal: str, regime: str, iv_rank: float, pcr: float) -> dict:
    """Determine the best F&O strategy based on signal, regime, IV, and PCR."""

    if signal == "BULLISH":
        if regime in ("PINNED", "SQUEEZE") and iv_rank > 60:
            return {
                "strategy": "Bull Put Spread",
                "strategy_code": "bull_put_spread",
                "legs": 2,
                "risk_type": "defined",
                "description": "Sell ATM PE, Buy OTM PE — collect premium in range-bound high-IV environment",
            }
        if regime == "TRENDING" and iv_rank < 40:
            return {
                "strategy": "Buy CE",
                "strategy_code": "long_call",
                "legs": 1,
                "risk_type": "defined",
                "description": "Buy ATM/slightly-OTM CE — directional play in low-IV trending market",
            }
        return {
            "strategy": "Bull Call Spread",
            "strategy_code": "bull_call_spread",
            "legs": 2,
            "risk_type": "defined",
            "description": "Buy ATM CE, Sell OTM CE — limited risk bullish play",
        }

    if signal == "BEARISH":
        if regime in ("PINNED", "SQUEEZE") and iv_rank > 60:
            return {
                "strategy": "Bear Call Spread",
                "strategy_code": "bear_call_spread",
                "legs": 2,
                "risk_type": "defined",
                "description": "Sell ATM CE, Buy OTM CE — collect premium with bearish bias",
            }
        if regime == "TRENDING" and iv_rank < 40:
            return {
                "strategy": "Buy PE",
                "strategy_code": "long_put",
                "legs": 1,
                "risk_type": "defined",
                "description": "Buy ATM/slightly-OTM PE — directional bearish play in low-IV trend",
            }
        return {
            "strategy": "Bear Put Spread",
            "strategy_code": "bear_put_spread",
            "legs": 2,
            "risk_type": "defined",
            "description": "Buy ATM PE, Sell OTM PE — limited risk bearish play",
        }

    # NEUTRAL
    if iv_rank > 65:
        return {
            "strategy": "Iron Condor",
            "strategy_code": "iron_condor",
            "legs": 4,
            "risk_type": "defined",
            "description": "Sell OTM CE+PE, Buy further OTM CE+PE — premium collection in high-IV neutral market",
        }
    return {
        "strategy": "Short Straddle",
        "strategy_code": "short_straddle",
        "legs": 2,
        "risk_type": "undefined",
        "description": "Sell ATM CE+PE — theta decay play in low-IV range-bound market",
    }


def _compute_risk_reward(strategy_code: str, entry_premium: float, spot: float, strike_interval: float) -> dict:
    """Compute risk/reward parameters for a given strategy."""

    if strategy_code in ("long_call", "long_put"):
        return {
            "max_loss": round(entry_premium, 2),
            "target": round(entry_premium * 1.5, 2),
            "stop_loss": round(entry_premium * 0.6, 2),
            "risk_reward_ratio": "1:1.5",
            "breakeven_distance": round(entry_premium / spot * 100, 2) if spot else 0,
        }

    if strategy_code in ("bull_call_spread", "bear_put_spread"):
        # 1-strike-wide ATM debit spread: net debit ≈ 50% of spread width
        spread_width = strike_interval
        net_debit = round(spread_width * 0.50, 2)
        max_profit = round(spread_width - net_debit, 2)
        rr = round(max_profit / net_debit, 1) if net_debit > 0 else 1.0
        return {
            "max_loss": net_debit,
            "target": round(max_profit * 0.7, 2),
            "stop_loss": net_debit,
            "risk_reward_ratio": f"1:{rr}",
            "breakeven_distance": round(net_debit / spot * 100, 2) if spot else 0,
        }

    if strategy_code in ("bull_put_spread", "bear_call_spread"):
        # 1-strike-wide OTM credit spread: net credit ≈ 35% of spread width
        spread_width = strike_interval
        net_credit = round(spread_width * 0.35, 2)
        max_loss = round(spread_width - net_credit, 2)
        rr = round(net_credit / max_loss, 1) if max_loss > 0 else 0.5
        return {
            "max_loss": max_loss,
            "target": round(net_credit * 0.7, 2),
            "stop_loss": round(max_loss * 1.0, 2),
            "risk_reward_ratio": f"1:{rr}",
            "breakeven_distance": round(net_credit / spot * 100, 2) if spot else 0,
        }

    if strategy_code == "iron_condor":
        # Sell 2-strike-wide IC: net credit ≈ 30% of wing width
        wing_width = strike_interval
        net_credit = round(wing_width * 0.30, 2)
        max_loss = round(wing_width - net_credit, 2)
        rr = round(net_credit / max_loss, 1) if max_loss > 0 else 0.4
        return {
            "max_loss": max_loss,
            "target": round(net_credit * 0.5, 2),
            "stop_loss": max_loss,
            "risk_reward_ratio": f"1:{rr}",
            "breakeven_distance": round(wing_width / spot * 100, 2) if spot else 0,
        }

    if strategy_code == "short_straddle":
        return {
            "max_loss": round(entry_premium * 2, 2),
            "target": round(entry_premium * 0.5, 2),
            "stop_loss": round(entry_premium * 1.5, 2),
            "risk_reward_ratio": "1:0.5",
            "breakeven_distance": round(entry_premium / spot * 100, 2) if spot else 0,
        }

    return {
        "max_loss": round(entry_premium, 2),
        "target": round(entry_premium * 1.0, 2),
        "stop_loss": round(entry_premium * 0.7, 2),
        "risk_reward_ratio": "1:1",
        "breakeven_distance": 0,
    }


def _conviction_label(score: int) -> str:
    if score >= 90:
        return "VERY HIGH"
    if score >= 80:
        return "HIGH"
    if score >= 70:
        return "MODERATE"
    if score >= 60:
        return "LOW"
    return "VERY LOW"


def generate_suggestions(scan_data: list, lot_sizes: dict, strike_intervals: dict) -> list:
    """
    Generate ranked F&O trade suggestions from scan results.

    Parameters:
        scan_data: list of dicts from /api/scan response["data"]
        lot_sizes: dict mapping symbol to lot size
        strike_intervals: dict mapping symbol to strike interval

    Returns:
        list of suggestion dicts, sorted by conviction score descending
    """
    suggestions = []

    for stock in scan_data:
        symbol = stock.get("symbol", "")
        score = stock.get("score", 0)
        signal = stock.get("signal", "NEUTRAL")
        regime = stock.get("regime", "TRENDING")
        spot = stock.get("ltp", 0)
        pcr = stock.get("pcr", 1.0)
        iv_rank = stock.get("iv_rank", 50.0)
        iv = stock.get("iv", 0)
        ml_prob = stock.get("ml_bullish_probability")
        top_picks = stock.get("top_picks", [])
        dte = stock.get("days_to_expiry", 30)
        metrics = stock.get("metrics", {})
        reasons = stock.get("signal_reasons", [])
        confidence = stock.get("confidence", 0)
        max_pain = stock.get("max_pain")
        oi_walls = stock.get("oi_walls", {})

        # Only suggest if score >= 60 and we have a directional signal or high-IV neutral
        if score < 60:
            continue
        if signal == "NEUTRAL" and iv_rank < 55:
            continue

        strategy_info = _strategy_for_signal(signal, regime, iv_rank, pcr)

        lot_size = lot_sizes.get(symbol, 50)
        strike_interval = strike_intervals.get(symbol, 50)

        # Compute entry premium estimate from top picks
        entry_premium = 0
        primary_strike = None
        primary_type = None
        if top_picks:
            best_pick = top_picks[0]
            entry_premium = best_pick.get("ltp", 0)
            primary_strike = best_pick.get("strike", 0)
            primary_type = best_pick.get("type", "CE")

        if entry_premium <= 0:
            continue

        risk_reward = _compute_risk_reward(
            strategy_info["strategy_code"], entry_premium, spot, strike_interval
        )

        # Capital required (based on max loss for the strategy)
        capital_per_lot = risk_reward["max_loss"] * lot_size
        if strategy_info["risk_type"] == "undefined":
            capital_per_lot = spot * lot_size * 0.15  # ~15% margin for undefined risk

        # Conviction score: blend of stock score, ML confidence, and option quality
        conviction = score
        if ml_prob is not None:
            if signal == "BULLISH" and ml_prob > 0.6:
                conviction = min(100, conviction + int((ml_prob - 0.5) * 20))
            elif signal == "BEARISH" and ml_prob < 0.4:
                conviction = min(100, conviction + int((0.5 - ml_prob) * 20))
            elif signal == "NEUTRAL":
                conviction = min(100, conviction + 3)

        # Penalize low DTE (theta risk for buyers)
        if strategy_info["strategy_code"] in ("long_call", "long_put") and dte < 3:
            conviction = max(0, conviction - 10)

        # Build support/resistance context
        support_levels = [w["strike"] for w in oi_walls.get("support", [])]
        resistance_levels = [w["strike"] for w in oi_walls.get("resistance", [])]

        # Build signal reasons list
        signal_tags = []
        if score >= 85:
            signal_tags.append("🔥 High Score")
        if ml_prob is not None and ((signal == "BULLISH" and ml_prob > 0.7) or (signal == "BEARISH" and ml_prob < 0.3)):
            signal_tags.append("🤖 AI Confirmed")
        if stock.get("uoa_detected"):
            signal_tags.append("🎯 UOA Detected")
        if iv_rank > 70:
            signal_tags.append("📈 High IV Rank")
        elif iv_rank < 30:
            signal_tags.append("📉 Low IV Rank")
        if pcr > 1.3:
            signal_tags.append("🐂 High PCR (Bullish)")
        elif pcr < 0.7:
            signal_tags.append("🐻 Low PCR (Bearish)")
        if metrics.get("gex", 0) > 0:
            signal_tags.append("🛡 Positive GEX")

        suggestion = {
            "symbol": symbol,
            "signal": signal,
            "conviction": conviction,
            "conviction_label": _conviction_label(conviction),
            "score": score,
            "strategy": strategy_info,
            "entry": {
                "primary_strike": primary_strike,
                "primary_type": primary_type,
                "entry_premium": round(entry_premium, 2),
                "spot_at_signal": round(spot, 2),
            },
            "risk_reward": risk_reward,
            "sizing": {
                "lot_size": lot_size,
                "capital_per_lot": round(capital_per_lot, 2),
                "suggested_lots": 1,
            },
            "context": {
                "regime": regime,
                "iv": round(iv, 1),
                "iv_rank": round(iv_rank, 1),
                "pcr": round(pcr, 3),
                "dte": dte,
                "max_pain": max_pain,
                "gex": metrics.get("gex", 0),
                "iv_skew": metrics.get("iv_skew", 0),
                "support": support_levels[:2],
                "resistance": resistance_levels[:2],
            },
            "ml": {
                "probability": round(ml_prob, 4) if ml_prob is not None else None,
                "ml_score": stock.get("ml_score", 0),
            },
            "tags": signal_tags,
            "reasons": reasons[:5],
            "timestamp": datetime.now().isoformat(),
        }

        suggestions.append(suggestion)

    # Sort by conviction descending
    suggestions.sort(key=lambda x: x["conviction"], reverse=True)

    # Return top 10 suggestions
    return suggestions[:10]
