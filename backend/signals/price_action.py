"""
signals/price_action.py — Price Action & VWAP Signal (Signal 5)

Components:
- VWAP relationship (above/below/oscillating)
- Opening range breakout detection
- Gap analysis
- Key levels from previous day
"""

from __future__ import annotations
from typing import List, Dict, Optional
from datetime import datetime, time
from .base import BaseSignal, SignalResult


class PriceActionSignal(BaseSignal):
    """
    Price Action Signal — VWAP, Opening Range, Gap Analysis.
    
    Combines:
    - VWAP position and duration
    - Opening range (first 15 min) breakout/breakdown
    - Gap analysis (overnight gap > 0.5%)
    - Previous day levels (close, high, low)
    """
    
    name = "price_action"
    
    # VWAP duration threshold (minutes above/below)
    VWAP_TREND_DURATION_MIN = 30
    
    # Gap threshold
    GAP_THRESHOLD_PCT = 0.5
    
    # Opening range breakout threshold
    OR_BREAKOUT_BUFFER_PCT = 0.1
    
    def compute(
        self,
        spot: float,
        vwap: float = 0.0,
        minutes_above_vwap: int = 0,
        minutes_below_vwap: int = 0,
        or_high: float = 0.0,
        or_low: float = 0.0,
        prev_close: float = 0.0,
        prev_high: float = 0.0,
        prev_low: float = 0.0,
        current_time: datetime = None,
        open_price: float = 0.0,
        ce_wall: float = 0.0,
        pe_wall: float = 0.0,
        **kwargs
    ) -> SignalResult:
        """
        Compute price action signal.
        
        Args:
            spot: Current underlying price
            vwap: Current VWAP value
            minutes_above_vwap: Duration above VWAP in minutes
            minutes_below_vwap: Duration below VWAP in minutes
            or_high: Opening range (first 15 min) high
            or_low: Opening range low
            prev_close: Previous day close
            prev_high: Previous day high
            prev_low: Previous day low
            current_time: Current market time
            open_price: Today's open price
            ce_wall: Resistance from OI wall
            pe_wall: Support from OI wall
            
        Returns:
            SignalResult with price action score
        """
        if spot <= 0:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                reason="No price data"
            )
        
        scores = []
        reasons = []
        
        # 1. VWAP Signal
        vwap_score, vwap_reason = self._compute_vwap_signal(
            spot, vwap, minutes_above_vwap, minutes_below_vwap
        )
        if vwap_score != 0:
            scores.append(vwap_score)
            reasons.append(vwap_reason)
        
        # 2. Opening Range Signal
        or_score, or_reason = self._compute_or_signal(spot, or_high, or_low, current_time)
        if or_score != 0:
            scores.append(or_score)
            reasons.append(or_reason)
        
        # 3. Gap Signal
        gap_score, gap_reason = self._compute_gap_signal(open_price, prev_close, spot)
        if gap_score != 0:
            scores.append(gap_score)
            reasons.append(gap_reason)
        
        # 4. Key Levels Signal
        levels_score, levels_reason = self._compute_levels_signal(
            spot, prev_close, prev_high, prev_low, ce_wall, pe_wall
        )
        if levels_score != 0:
            scores.append(levels_score)
            reasons.append(levels_reason)
        
        # Composite score (average of active signals)
        if scores:
            composite_score = sum(scores) / len(scores)
        else:
            composite_score = 0.0
        
        # Confidence based on data availability
        confidence = 0.5
        if vwap > 0:
            confidence += 0.15
        if or_high > 0 and or_low > 0:
            confidence += 0.15
        if prev_close > 0:
            confidence += 0.1
        if ce_wall > 0 and pe_wall > 0:
            confidence += 0.1
        confidence = min(1.0, confidence)
        
        combined_reason = " | ".join(reasons) if reasons else "No strong price action signals"
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata={
                "vwap": vwap,
                "vwap_score": round(vwap_score, 3),
                "or_high": or_high,
                "or_low": or_low,
                "or_score": round(or_score, 3),
                "gap_pct": round((open_price - prev_close) / prev_close * 100, 2) if prev_close else 0,
                "gap_score": round(gap_score, 3),
                "levels_score": round(levels_score, 3),
            }
        )
    
    def _compute_vwap_signal(
        self, spot: float, vwap: float, min_above: int, min_below: int
    ) -> tuple[float, str]:
        """
        Compute VWAP-based signal.
        
        - Price > VWAP for >30 min → bullish bias for intraday
        - Price < VWAP for >30 min → bearish bias
        - Price oscillating around VWAP → range-bound
        """
        if vwap <= 0:
            return 0.0, ""
        
        dist_pct = (spot - vwap) / vwap * 100
        
        # Check for sustained position
        if min_above >= self.VWAP_TREND_DURATION_MIN:
            score = 0.5 + min(0.3, min_above / 60 * 0.1)  # Stronger with duration
            return score, f"Above VWAP for {min_above}min (+{dist_pct:.2f}%)"
        
        if min_below >= self.VWAP_TREND_DURATION_MIN:
            score = -0.5 - min(0.3, min_below / 60 * 0.1)
            return score, f"Below VWAP for {min_below}min ({dist_pct:.2f}%)"
        
        # Oscillating around VWAP
        if abs(dist_pct) < 0.2:
            return 0.0, "Oscillating around VWAP (range-bound)"
        
        # Short-term position
        if dist_pct > 0.2:
            return 0.2, f"Above VWAP (+{dist_pct:.2f}%)"
        elif dist_pct < -0.2:
            return -0.2, f"Below VWAP ({dist_pct:.2f}%)"
        
        return 0.0, ""
    
    def _compute_or_signal(
        self, spot: float, or_high: float, or_low: float, current_time: datetime = None
    ) -> tuple[float, str]:
        """
        Compute Opening Range breakout signal.
        
        - Breakout above OR range → bullish entry trigger
        - Breakdown below OR range → bearish entry trigger
        """
        if or_high <= 0 or or_low <= 0:
            return 0.0, ""
        
        # Check if we're past the opening range period
        if current_time:
            market_open = current_time.replace(hour=9, minute=15, second=0, microsecond=0)
            or_end = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
            
            if current_time < or_end:
                return 0.0, "Within opening range period"
        
        or_range = or_high - or_low
        buffer = or_range * self.OR_BREAKOUT_BUFFER_PCT / 100
        
        # Breakout
        if spot > or_high + buffer:
            pct_above = (spot - or_high) / or_range * 100
            score = 0.6 + min(0.3, pct_above / 50)
            return score, f"OR breakout (+{pct_above:.1f}% above range)"
        
        # Breakdown
        if spot < or_low - buffer:
            pct_below = (or_low - spot) / or_range * 100
            score = -0.6 - min(0.3, pct_below / 50)
            return score, f"OR breakdown (-{pct_below:.1f}% below range)"
        
        # Within range
        position_in_range = (spot - or_low) / or_range if or_range > 0 else 0.5
        if position_in_range > 0.8:
            return 0.2, "Near OR high"
        elif position_in_range < 0.2:
            return -0.2, "Near OR low"
        
        return 0.0, f"Within OR range ({position_in_range*100:.0f}%)"
    
    def _compute_gap_signal(
        self, open_price: float, prev_close: float, spot: float
    ) -> tuple[float, str]:
        """
        Compute gap analysis signal.
        
        - Gap > 0.5% → assess fill probability
        - Gap up typically has 70% fill probability
        - Gap down typically has 65% fill probability
        """
        if open_price <= 0 or prev_close <= 0:
            return 0.0, ""
        
        gap_pct = (open_price - prev_close) / prev_close * 100
        
        if abs(gap_pct) < self.GAP_THRESHOLD_PCT:
            return 0.0, ""
        
        # Current position relative to gap
        if gap_pct > 0:  # Gap up
            if spot < open_price:  # Filling the gap
                fill_pct = (open_price - spot) / (open_price - prev_close) * 100
                if fill_pct > 50:
                    score = -0.3  # Gap filling, bearish pressure
                    return score, f"Gap up {gap_pct:.1f}% filling ({fill_pct:.0f}% filled)"
                else:
                    score = 0.2  # Gap holding
                    return score, f"Gap up {gap_pct:.1f}% holding"
            else:  # Extending above open
                score = 0.4
                return score, f"Gap up {gap_pct:.1f}% extending"
        else:  # Gap down
            if spot > open_price:  # Filling the gap
                fill_pct = (spot - open_price) / (prev_close - open_price) * 100
                if fill_pct > 50:
                    score = 0.3  # Gap filling, bullish pressure
                    return score, f"Gap down {gap_pct:.1f}% filling ({fill_pct:.0f}% filled)"
                else:
                    score = -0.2  # Gap holding
                    return score, f"Gap down {gap_pct:.1f}% holding"
            else:  # Extending below open
                score = -0.4
                return score, f"Gap down {gap_pct:.1f}% extending"
    
    def _compute_levels_signal(
        self, spot: float, prev_close: float, prev_high: float, prev_low: float,
        ce_wall: float = 0.0, pe_wall: float = 0.0
    ) -> tuple[float, str]:
        """
        Compute signal from key levels (previous day and OI walls).
        
        - Above prev day high → strong bullish
        - Below prev day low → strong bearish
        - Near OI walls → expect support/resistance
        """
        if prev_close <= 0:
            return 0.0, ""
        
        # Previous day levels
        if prev_high > 0 and spot > prev_high:
            pct_above = (spot - prev_high) / prev_high * 100
            score = 0.5 + min(0.3, pct_above / 2)
            return score, f"Above prev high (+{pct_above:.2f}%)"
        
        if prev_low > 0 and spot < prev_low:
            pct_below = (prev_low - spot) / prev_low * 100
            score = -0.5 - min(0.3, pct_below / 2)
            return score, f"Below prev low (-{pct_below:.2f}%)"
        
        # OI wall proximity
        if ce_wall > 0 and pe_wall > 0:
            dist_to_resistance = (ce_wall - spot) / spot * 100
            dist_to_support = (spot - pe_wall) / spot * 100
            
            if dist_to_resistance < 0.5:
                return -0.3, f"Near CE wall {ce_wall:.0f} (resistance)"
            if dist_to_support < 0.5:
                return 0.3, f"Near PE wall {pe_wall:.0f} (support)"
        
        # Position relative to prev close
        close_dist_pct = (spot - prev_close) / prev_close * 100
        if close_dist_pct > 0.5:
            return 0.2, f"Above prev close (+{close_dist_pct:.2f}%)"
        elif close_dist_pct < -0.5:
            return -0.2, f"Below prev close ({close_dist_pct:.2f}%)"
        
        return 0.0, "Near prev close"
