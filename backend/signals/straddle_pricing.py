"""
signals/straddle_pricing.py — Straddle Signal (Signal 9)

ATM straddle price = ATM CE LTP + ATM PE LTP
Expected daily move % = (ATM straddle price / NIFTY spot) * 100

Use cases:
1. Compare implied move to actual realized volatility (HV20):
   - If implied_move > HV20 * sqrt(DTE/252) → options overpriced → sell straddle
   - If implied_move << HV20 * sqrt(DTE/252) → options underpriced → buy straddle

2. Breakeven levels:
   - Upper breakeven = ATM strike + straddle price
   - Lower breakeven = ATM strike - straddle price
   - These act as magnet levels during expiry week

3. Straddle price decay tracking:
   - Straddle should decay by ~20–25% per day on theta (DTE=3 to DTE=0)
   - If decaying faster → IV crush, exit long straddles early
   - If not decaying → event uncertainty persists, hold premium sellers
"""

from __future__ import annotations
from typing import List, Dict, Optional
import math
from .base import BaseSignal, SignalResult


class StraddleSignal(BaseSignal):
    """
    Straddle Pricing Signal — implied move and breakeven analysis.
    
    Analyzes:
    - Implied move vs. realized volatility
    - Breakeven levels as support/resistance
    - Theta decay rate tracking
    """
    
    name = "straddle_pricing"
    
    # Historical volatility annualization factor
    TRADING_DAYS = 252
    
    # Decay expectations
    NORMAL_DECAY_PER_DAY_PCT = 0.22  # 22% per day is normal near expiry
    
    def compute(
        self,
        spot: float,
        atm_strike: float = 0.0,
        atm_ce_ltp: float = 0.0,
        atm_pe_ltp: float = 0.0,
        dte: int = 30,
        hv20: float = 0.0,
        prev_straddle_price: float = 0.0,
        prev_dte: int = 0,
        **kwargs
    ) -> SignalResult:
        """
        Compute straddle pricing signal.
        
        Args:
            spot: Current underlying price
            atm_strike: ATM strike price
            atm_ce_ltp: ATM Call LTP
            atm_pe_ltp: ATM Put LTP
            dte: Days to expiry
            hv20: 20-day historical volatility (annualized %)
            prev_straddle_price: Previous straddle price for decay tracking
            prev_dte: Previous DTE for decay calculation
            
        Returns:
            SignalResult with straddle analysis
        """
        if spot <= 0:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                reason="No spot price data"
            )
        
        # Calculate straddle price
        straddle_price = atm_ce_ltp + atm_pe_ltp
        
        if straddle_price <= 0:
            return SignalResult(
                score=0.0,
                confidence=0.2,
                reason="No straddle price data"
            )
        
        # Calculate implied move
        implied_move_pct = (straddle_price / spot) * 100
        
        # Breakeven levels
        upper_be = atm_strike + straddle_price
        lower_be = atm_strike - straddle_price
        
        scores = []
        reasons = []
        
        # 1. Implied vs. Realized Volatility
        iv_rv_score, iv_rv_reason = self._compare_implied_realized(
            implied_move_pct, hv20, dte
        )
        scores.append(("iv_rv", iv_rv_score, 0.40))
        if iv_rv_reason:
            reasons.append(iv_rv_reason)
        
        # 2. Breakeven Analysis
        be_score, be_reason = self._analyze_breakevens(
            spot, upper_be, lower_be, dte
        )
        scores.append(("breakeven", be_score, 0.30))
        if be_reason:
            reasons.append(be_reason)
        
        # 3. Decay Rate Analysis
        decay_score, decay_reason = self._analyze_decay_rate(
            straddle_price, prev_straddle_price, dte, prev_dte
        )
        scores.append(("decay", decay_score, 0.30))
        if decay_reason:
            reasons.append(decay_reason)
        
        # Composite score
        total_weight = sum(s[2] for s in scores)
        composite_score = sum(s[1] * s[2] for s in scores) / total_weight if total_weight > 0 else 0
        
        # Confidence
        confidence = 0.6
        if hv20 > 0:
            confidence += 0.15
        if prev_straddle_price > 0:
            confidence += 0.15
        if dte <= 7:
            confidence += 0.1  # More meaningful near expiry
        confidence = min(1.0, confidence)
        
        combined_reason = " | ".join(reasons) if reasons else "Straddle neutral"
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata={
                "straddle_price": round(straddle_price, 2),
                "implied_move_pct": round(implied_move_pct, 2),
                "upper_breakeven": round(upper_be, 2),
                "lower_breakeven": round(lower_be, 2),
                "dte": dte,
                "hv20": hv20,
                "iv_rv_score": round(iv_rv_score, 3),
                "be_score": round(be_score, 3),
                "decay_score": round(decay_score, 3),
            }
        )
    
    def _compare_implied_realized(
        self, implied_move_pct: float, hv20: float, dte: int
    ) -> tuple[float, str]:
        """
        Compare implied move to realized volatility.
        
        - If implied_move > HV20 * sqrt(DTE/252) → options overpriced → sell straddle
        - If implied_move << HV20 * sqrt(DTE/252) → options underpriced → buy straddle
        """
        if hv20 <= 0 or implied_move_pct <= 0:
            return 0.0, ""
        
        # Expected move from historical volatility
        # Daily volatility = Annual vol / sqrt(252)
        # For DTE days: Expected move = Daily vol * sqrt(DTE)
        expected_move = hv20 / math.sqrt(self.TRADING_DAYS) * math.sqrt(max(1, dte))
        
        # Ratio of implied to expected
        ratio = implied_move_pct / expected_move if expected_move > 0 else 1.0
        
        if ratio > 1.3:
            # Options overpriced - sell straddle opportunity
            score = -0.5 - min(0.4, (ratio - 1.3) / 2)
            reason = f"Options overpriced (IV/RV: {ratio:.2f}x)"
        elif ratio < 0.8:
            # Options underpriced - buy straddle opportunity
            score = 0.5 + min(0.4, (0.8 - ratio) / 0.4)
            reason = f"Options underpriced (IV/RV: {ratio:.2f}x)"
        else:
            # Fair value
            score = 0.0
            reason = f"Options fairly priced (IV/RV: {ratio:.2f}x)"
        
        return score, reason
    
    def _analyze_breakevens(
        self, spot: float, upper_be: float, lower_be: float, dte: int
    ) -> tuple[float, str]:
        """
        Analyze breakeven levels as potential support/resistance.
        
        During expiry week, breakevens act as magnet levels.
        """
        if upper_be <= 0 or lower_be <= 0:
            return 0.0, ""
        
        # Distance to breakevens as % of spot
        dist_to_upper = (upper_be - spot) / spot * 100
        dist_to_lower = (spot - lower_be) / spot * 100
        
        # Near expiry, breakevens are more significant
        expiry_weight = 1.0 if dte <= 3 else (0.7 if dte <= 7 else 0.4)
        
        # Position analysis
        if spot > upper_be:
            # Above upper breakeven - straddle buyers are profitable
            # This usually means strong directional move
            score = 0.4 * expiry_weight
            reason = f"Above upper BE ({dist_to_upper:+.1f}%)"
        elif spot < lower_be:
            # Below lower breakeven - straddle buyers profitable on downside
            score = -0.4 * expiry_weight
            reason = f"Below lower BE ({dist_to_lower:.1f}% below)"
        elif dist_to_upper < dist_to_lower:
            # Closer to upper breakeven
            proximity = 1 - (dist_to_upper / max(dist_to_lower, 0.01))
            score = 0.2 * proximity * expiry_weight
            reason = f"Closer to upper BE ({dist_to_upper:.1f}% away)"
        else:
            # Closer to lower breakeven
            proximity = 1 - (dist_to_lower / max(dist_to_upper, 0.01))
            score = -0.2 * proximity * expiry_weight
            reason = f"Closer to lower BE ({dist_to_lower:.1f}% away)"
        
        return score, reason
    
    def _analyze_decay_rate(
        self, current_price: float, prev_price: float,
        current_dte: int, prev_dte: int
    ) -> tuple[float, str]:
        """
        Analyze straddle theta decay rate.
        
        - Normal decay: ~20-25% per day near expiry
        - Faster decay → IV crush, exit long straddles
        - Slower decay → event uncertainty, hold premium sellers
        """
        if prev_price <= 0 or current_price <= 0:
            return 0.0, ""
        
        if prev_dte == 0 or prev_dte == current_dte:
            return 0.0, ""
        
        # Calculate actual decay
        days_passed = prev_dte - current_dte
        if days_passed <= 0:
            return 0.0, ""
        
        actual_decay_pct = (prev_price - current_price) / prev_price * 100
        decay_per_day = actual_decay_pct / days_passed
        
        # Expected decay
        expected_decay = self.NORMAL_DECAY_PER_DAY_PCT * 100 * days_passed
        
        # Ratio of actual to expected
        decay_ratio = actual_decay_pct / expected_decay if expected_decay > 0 else 1.0
        
        if decay_ratio > 1.3:
            # Faster than normal decay - IV crush
            score = -0.3  # Bearish for long vega positions
            reason = f"IV crush (decay {decay_per_day:.1f}%/day)"
        elif decay_ratio < 0.7:
            # Slower than normal decay - event uncertainty
            score = 0.2  # Good for premium sellers
            reason = f"Slow decay (event risk, {decay_per_day:.1f}%/day)"
        else:
            score = 0.0
            reason = f"Normal decay ({decay_per_day:.1f}%/day)"
        
        return score, reason
