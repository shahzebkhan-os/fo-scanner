"""
signals/global_cues.py — Global Cues Signal (Signal 7)

Fetches and analyzes global market data at market open (09:00 IST).
Updates every 30 minutes during market hours.

Data sources:
1. GIFT Nifty (previously SGX Nifty) — gap estimate
2. US markets (previous night close) — S&P 500, Nasdaq
3. Dollar Index (DXY) — FII flow indicator
4. Crude oil (NYMEX WTI) — inflationary pressure
5. USD/INR — FII selling pressure

Weight global cues more heavily at 09:15–09:45 (opening session).
Reduce weight after 11:00 as domestic factors dominate.
"""

from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime, time
from .base import BaseSignal, SignalResult


class GlobalCuesSignal(BaseSignal):
    """
    Global Cues Signal — external market factors.
    
    Analyzes:
    - GIFT Nifty premium/discount
    - US markets (SPX, NASDAQ)
    - Dollar Index (DXY)
    - Crude Oil
    - USD/INR
    """
    
    name = "global_cues"
    
    # Thresholds
    GIFT_SIGNIFICANT_PCT = 1.0   # ±1% is significant
    SPX_STRONG_MOVE_PCT = 1.0   # SPX ±1% affects India
    OIL_HIGH_LEVEL = 90         # $90+ is inflationary
    OIL_LOW_LEVEL = 70          # $70- is deflationary
    DXY_HIGH = 106              # Strong dollar
    DXY_LOW = 100               # Weak dollar
    USDINR_WEAK = 84            # INR weakness threshold
    
    def compute(
        self,
        gift_nifty: float = 0.0,
        nifty_prev_close: float = 0.0,
        spx_change_pct: float = 0.0,
        nasdaq_change_pct: float = 0.0,
        dxy: float = 0.0,
        dxy_prev: float = 0.0,
        crude_oil: float = 0.0,
        crude_prev: float = 0.0,
        usdinr: float = 0.0,
        usdinr_prev: float = 0.0,
        current_time: datetime = None,
        **kwargs
    ) -> SignalResult:
        """
        Compute global cues signal.
        
        Args:
            gift_nifty: Current GIFT Nifty value
            nifty_prev_close: Previous NIFTY close
            spx_change_pct: S&P 500 overnight change %
            nasdaq_change_pct: NASDAQ overnight change %
            dxy: Current Dollar Index
            dxy_prev: Previous Dollar Index
            crude_oil: Current WTI crude price
            crude_prev: Previous crude price
            usdinr: Current USD/INR rate
            usdinr_prev: Previous USD/INR rate
            current_time: Current market time (for weighting)
            
        Returns:
            SignalResult with global cues score
        """
        scores = []
        reasons = []
        metadata = {}
        
        # 1. GIFT Nifty signal
        gift_score, gift_reason = self._compute_gift_signal(gift_nifty, nifty_prev_close)
        if gift_score != 0:
            scores.append(("gift", gift_score, 0.25))
            reasons.append(gift_reason)
        metadata["gift_premium_pct"] = round((gift_nifty - nifty_prev_close) / nifty_prev_close * 100, 2) if nifty_prev_close > 0 and gift_nifty > 0 else 0
        
        # 2. US markets signal
        us_score, us_reason = self._compute_us_signal(spx_change_pct, nasdaq_change_pct)
        if us_score != 0:
            scores.append(("us", us_score, 0.25))
            reasons.append(us_reason)
        metadata["spx_change"] = spx_change_pct
        metadata["nasdaq_change"] = nasdaq_change_pct
        
        # 3. DXY signal
        dxy_score, dxy_reason = self._compute_dxy_signal(dxy, dxy_prev)
        if dxy_score != 0:
            scores.append(("dxy", dxy_score, 0.15))
            reasons.append(dxy_reason)
        metadata["dxy"] = dxy
        
        # 4. Crude oil signal
        oil_score, oil_reason = self._compute_oil_signal(crude_oil, crude_prev)
        if oil_score != 0:
            scores.append(("oil", oil_score, 0.15))
            reasons.append(oil_reason)
        metadata["crude_oil"] = crude_oil
        
        # 5. USD/INR signal
        inr_score, inr_reason = self._compute_usdinr_signal(usdinr, usdinr_prev)
        if inr_score != 0:
            scores.append(("usdinr", inr_score, 0.20))
            reasons.append(inr_reason)
        metadata["usdinr"] = usdinr
        
        # Time-based weighting
        time_multiplier = self._get_time_multiplier(current_time)
        metadata["time_multiplier"] = time_multiplier
        
        # Composite score
        if scores:
            # Weighted average
            total_weight = sum(s[2] for s in scores)
            composite_score = sum(s[1] * s[2] for s in scores) / total_weight if total_weight > 0 else 0
            # Apply time multiplier
            composite_score *= time_multiplier
        else:
            composite_score = 0.0
        
        # Confidence based on data availability
        data_points = sum(1 for x in [gift_nifty, spx_change_pct, dxy, crude_oil, usdinr] if x != 0)
        confidence = 0.3 + (data_points / 5) * 0.5
        # Higher confidence during opening session
        if time_multiplier >= 0.8:
            confidence += 0.2
        confidence = min(1.0, confidence)
        
        combined_reason = " | ".join(reasons) if reasons else "No significant global cues"
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata=metadata
        )
    
    def _compute_gift_signal(
        self, gift_nifty: float, prev_close: float
    ) -> tuple[float, str]:
        """
        Compute GIFT Nifty signal.
        
        - > +1% → bullish open expected
        - < -1% → bearish open expected
        """
        if gift_nifty <= 0 or prev_close <= 0:
            return 0.0, ""
        
        premium_pct = (gift_nifty - prev_close) / prev_close * 100
        
        if premium_pct >= self.GIFT_SIGNIFICANT_PCT:
            score = 0.5 + min(0.4, (premium_pct - self.GIFT_SIGNIFICANT_PCT) / 2)
            return score, f"GIFT Nifty +{premium_pct:.1f}% (bullish gap)"
        elif premium_pct <= -self.GIFT_SIGNIFICANT_PCT:
            score = -0.5 - min(0.4, (abs(premium_pct) - self.GIFT_SIGNIFICANT_PCT) / 2)
            return score, f"GIFT Nifty {premium_pct:.1f}% (bearish gap)"
        else:
            score = premium_pct / self.GIFT_SIGNIFICANT_PCT * 0.3
            return score, f"GIFT Nifty {premium_pct:+.1f}%"
    
    def _compute_us_signal(
        self, spx_change: float, nasdaq_change: float
    ) -> tuple[float, str]:
        """
        Compute US markets signal.
        
        SPX > +1% → positive cue for NIFTY, especially IT/tech names.
        """
        if spx_change == 0 and nasdaq_change == 0:
            return 0.0, ""
        
        # Weight SPX more (60%) than NASDAQ (40%)
        combined = spx_change * 0.6 + nasdaq_change * 0.4
        
        if abs(combined) >= self.SPX_STRONG_MOVE_PCT:
            score = 0.6 if combined > 0 else -0.6
            score += 0.2 * (combined / 2) if abs(combined) > 1 else 0
            score = max(-1.0, min(1.0, score))
            direction = "strong rally" if combined > 0 else "strong selloff"
            return score, f"US {direction} (SPX {spx_change:+.1f}%, NASDAQ {nasdaq_change:+.1f}%)"
        else:
            score = combined / self.SPX_STRONG_MOVE_PCT * 0.4
            return score, f"US SPX {spx_change:+.1f}%, NASDAQ {nasdaq_change:+.1f}%"
    
    def _compute_dxy_signal(
        self, dxy: float, dxy_prev: float
    ) -> tuple[float, str]:
        """
        Compute Dollar Index signal.
        
        DXY rising → FII outflows → bearish for NIFTY.
        """
        if dxy <= 0:
            return 0.0, ""
        
        # Level-based signal
        if dxy >= self.DXY_HIGH:
            score = -0.4
            reason = f"DXY {dxy:.1f} (strong dollar)"
        elif dxy <= self.DXY_LOW:
            score = 0.3
            reason = f"DXY {dxy:.1f} (weak dollar)"
        else:
            score = 0.0
            reason = f"DXY {dxy:.1f}"
        
        # Rate of change adjustment
        if dxy_prev > 0:
            change_pct = (dxy - dxy_prev) / dxy_prev * 100
            if change_pct > 0.5:
                score -= 0.2
                reason += " (rising)"
            elif change_pct < -0.5:
                score += 0.2
                reason += " (falling)"
        
        return score, reason
    
    def _compute_oil_signal(
        self, crude: float, crude_prev: float
    ) -> tuple[float, str]:
        """
        Compute crude oil signal.
        
        Oil > $90 → inflationary pressure → negative for broader market.
        """
        if crude <= 0:
            return 0.0, ""
        
        # Level-based signal
        if crude >= self.OIL_HIGH_LEVEL:
            score = -0.4 - min(0.3, (crude - self.OIL_HIGH_LEVEL) / 20)
            reason = f"Crude ${crude:.1f} (inflationary)"
        elif crude <= self.OIL_LOW_LEVEL:
            score = 0.2
            reason = f"Crude ${crude:.1f} (deflationary)"
        else:
            score = 0.0
            reason = f"Crude ${crude:.1f}"
        
        # Rate of change
        if crude_prev > 0:
            change_pct = (crude - crude_prev) / crude_prev * 100
            if change_pct > 3:
                score -= 0.2
                reason += " (spiking)"
            elif change_pct < -3:
                score += 0.2
                reason += " (falling)"
        
        return score, reason
    
    def _compute_usdinr_signal(
        self, usdinr: float, usdinr_prev: float
    ) -> tuple[float, str]:
        """
        Compute USD/INR signal.
        
        INR weakening (USDINR > 84) → FII selling pressure.
        """
        if usdinr <= 0:
            return 0.0, ""
        
        # Level-based signal
        if usdinr >= self.USDINR_WEAK:
            score = -0.4 - min(0.3, (usdinr - self.USDINR_WEAK))
            reason = f"INR {usdinr:.2f} (weak, FII selling likely)"
        else:
            score = 0.1
            reason = f"INR {usdinr:.2f} (stable)"
        
        # Rate of change
        if usdinr_prev > 0:
            change_pct = (usdinr - usdinr_prev) / usdinr_prev * 100
            if change_pct > 0.3:
                score -= 0.2
                reason += " (weakening)"
            elif change_pct < -0.3:
                score += 0.2
                reason += " (strengthening)"
        
        return score, reason
    
    def _get_time_multiplier(self, current_time: datetime = None) -> float:
        """
        Get time-based weight multiplier.
        
        Weight global cues more heavily at 09:15–09:45 (opening session).
        Reduce weight after 11:00 as domestic factors dominate.
        """
        if current_time is None:
            return 0.7  # Default mid-weight
        
        market_time = current_time.time()
        
        # Pre-market (before 9:15)
        if market_time < time(9, 15):
            return 1.0  # Full weight
        
        # Opening session (9:15 - 9:45)
        if market_time < time(9, 45):
            return 1.0  # Full weight
        
        # First hour (9:45 - 10:30)
        if market_time < time(10, 30):
            return 0.8
        
        # Mid-morning (10:30 - 11:00)
        if market_time < time(11, 0):
            return 0.6
        
        # Late morning onwards
        if market_time < time(14, 0):
            return 0.4
        
        # Afternoon (less relevant)
        return 0.3
