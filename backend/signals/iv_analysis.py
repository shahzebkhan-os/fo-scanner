"""
signals/iv_analysis.py — IV Signal (Signal 2) and India VIX Signal (Signal 4)

Computed from current IV vs. historical IV.
Requires: store rolling 252-day IV history for NIFTY and BANKNIFTY

Metrics:
1. IV Rank (IVR) = (current_IV - 52wk_low_IV) / (52wk_high_IV - 52wk_low_IV) * 100
2. IV Percentile (IVP) = % of days in last 252 days where IV was BELOW current IV
3. IV Skew signal
4. Term structure (backwardation/contango)

India VIX signal:
- VIX > 20 → elevated fear → sell far-OTM options (wider spreads)
- VIX < 12 → complacency → look for long vega plays ahead of events
- VIX rate of change tracking
"""

from __future__ import annotations
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from .base import BaseSignal, SignalResult


class IvSignal(BaseSignal):
    """
    IV Analysis Signal — comprehensive volatility analysis.
    
    Combines:
    - IV Rank and IV Percentile
    - IV Skew analysis
    - Term structure analysis
    - India VIX signal
    """
    
    name = "iv_analysis"
    
    # IVR thresholds
    IVR_HIGH = 70  # Sell premium
    IVR_LOW = 30   # Buy premium
    
    # VIX thresholds
    VIX_HIGH = 20
    VIX_LOW = 12
    VIX_SPIKE_THRESHOLD = 0.15  # 15% 1-day spike
    
    # Skew thresholds
    SKEW_HIGH = 5.0   # Elevated fear
    SKEW_LOW = 1.0    # Complacency
    
    def compute(
        self,
        current_iv: float = 0.0,
        iv_history: List[float] = None,
        vix: float = 0.0,
        vix_history: List[float] = None,
        ce_iv_25d: float = 0.0,
        pe_iv_25d: float = 0.0,
        near_expiry_iv: float = 0.0,
        next_expiry_iv: float = 0.0,
        symbol: str = "",
        **kwargs
    ) -> SignalResult:
        """
        Compute IV-based signals.
        
        Args:
            current_iv: Current ATM implied volatility
            iv_history: Historical IV values (252 days)
            vix: Current India VIX value
            vix_history: Historical VIX values for rate of change
            ce_iv_25d: 25-delta CE IV for skew calculation
            pe_iv_25d: 25-delta PE IV for skew calculation
            near_expiry_iv: Near-term expiry IV
            next_expiry_iv: Next expiry IV for term structure
            symbol: Underlying symbol
            
        Returns:
            SignalResult with composite IV score
        """
        iv_history = iv_history or []
        vix_history = vix_history or []
        
        # 1. Compute IV Rank
        ivr, ivr_score, ivr_reason = self._compute_iv_rank(current_iv, iv_history)
        
        # 2. Compute IV Percentile
        ivp, ivp_score = self._compute_iv_percentile(current_iv, iv_history)
        
        # 3. Compute IV Skew
        skew, skew_score, skew_reason = self._compute_iv_skew(ce_iv_25d, pe_iv_25d)
        
        # 4. Compute Term Structure
        term_score, term_reason = self._compute_term_structure(near_expiry_iv, next_expiry_iv)
        
        # 5. Compute VIX Signal
        vix_score, vix_reason, vix_flags = self._compute_vix_signal(vix, vix_history, current_iv)
        
        # Composite score weights:
        # IVR/IVP: 30%, Skew: 25%, Term Structure: 15%, VIX: 30%
        ivr_ivp_avg = (ivr_score + ivp_score) / 2
        
        composite_score = (
            ivr_ivp_avg * 0.30 +
            skew_score * 0.25 +
            term_score * 0.15 +
            vix_score * 0.30
        )
        
        # Confidence based on data availability
        confidence = 0.5
        if len(iv_history) >= 20:
            confidence += 0.15
        if len(iv_history) >= 100:
            confidence += 0.15
        if vix > 0:
            confidence += 0.1
        if ce_iv_25d > 0 and pe_iv_25d > 0:
            confidence += 0.1
        confidence = min(1.0, confidence)
        
        reasons = [ivr_reason, skew_reason, term_reason, vix_reason]
        combined_reason = " | ".join(r for r in reasons if r)
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata={
                "iv_rank": round(ivr, 2),
                "iv_percentile": round(ivp, 2),
                "current_iv": current_iv,
                "iv_skew": round(skew, 2),
                "vix": vix,
                "vix_flags": vix_flags,
                "ivr_score": round(ivr_score, 3),
                "ivp_score": round(ivp_score, 3),
                "skew_score": round(skew_score, 3),
                "term_score": round(term_score, 3),
                "vix_score": round(vix_score, 3),
            }
        )
    
    def _compute_iv_rank(
        self, current_iv: float, iv_history: List[float]
    ) -> tuple[float, float, str]:
        """
        Compute IV Rank (IVR).
        
        IVR = (current_IV - 52wk_low_IV) / (52wk_high_IV - 52wk_low_IV) * 100
        
        - IVR > 70 → sell premium (short straddle, iron condor)
        - IVR < 30 → buy premium (long straddle, ahead of events)
        """
        if not iv_history or current_iv <= 0:
            return 50.0, 0.0, "Insufficient IV history"
        
        iv_low = min(iv_history)
        iv_high = max(iv_history)
        
        if iv_high == iv_low:
            return 50.0, 0.0, "IV range too narrow"
        
        ivr = (current_iv - iv_low) / (iv_high - iv_low) * 100
        ivr = max(0, min(100, ivr))
        
        # Score: High IVR → bearish for premium buyers (sell premium opportunity)
        # Low IVR → bullish for premium buyers (buy premium opportunity)
        if ivr >= self.IVR_HIGH:
            score = -0.6  # High IV, expect mean reversion down
            reason = f"IVR {ivr:.0f}% - sell premium"
        elif ivr <= self.IVR_LOW:
            score = 0.6  # Low IV, potential expansion
            reason = f"IVR {ivr:.0f}% - buy premium"
        else:
            # Linear interpolation
            normalized = (ivr - 50) / 50  # -1 to +1
            score = -normalized * 0.4
            reason = f"IVR {ivr:.0f}% - neutral zone"
        
        return ivr, score, reason
    
    def _compute_iv_percentile(
        self, current_iv: float, iv_history: List[float]
    ) -> tuple[float, float]:
        """
        Compute IV Percentile (IVP).
        
        IVP = % of days in last 252 days where IV was BELOW current IV.
        More robust than IVR for skewed distributions.
        """
        if not iv_history or current_iv <= 0:
            return 50.0, 0.0
        
        below_count = sum(1 for iv in iv_history if iv < current_iv)
        ivp = (below_count / len(iv_history)) * 100
        
        # Score similar to IVR
        if ivp >= self.IVR_HIGH:
            score = -0.5
        elif ivp <= self.IVR_LOW:
            score = 0.5
        else:
            normalized = (ivp - 50) / 50
            score = -normalized * 0.3
        
        return ivp, score
    
    def _compute_iv_skew(
        self, ce_iv_25d: float, pe_iv_25d: float
    ) -> tuple[float, float, str]:
        """
        Compute IV Skew signal.
        
        Skew = (25-delta PE IV) - (25-delta CE IV)
        
        - Skew > 5% → elevated fear → look for put spreads to sell
        - Skew < 1% → complacency → pre-event long straddle opportunity
        """
        if ce_iv_25d <= 0 or pe_iv_25d <= 0:
            return 0.0, 0.0, ""
        
        skew = pe_iv_25d - ce_iv_25d
        
        if skew >= self.SKEW_HIGH:
            # Elevated fear in puts - potentially contrarian bullish
            score = 0.4
            reason = f"IV skew {skew:.1f}% (elevated put fear)"
        elif skew <= self.SKEW_LOW:
            # Complacency - potential event risk
            score = -0.2
            reason = f"IV skew {skew:.1f}% (complacent)"
        else:
            # Normal skew
            score = 0.0
            reason = f"IV skew {skew:.1f}% (normal)"
        
        return skew, score, reason
    
    def _compute_term_structure(
        self, near_iv: float, far_iv: float
    ) -> tuple[float, str]:
        """
        Compute term structure signal.
        
        - Backwardation (near > far) → elevated fear, potential mean reversion
        - Contango (near < far) → normal term structure
        """
        if near_iv <= 0 or far_iv <= 0:
            return 0.0, ""
        
        ratio = near_iv / far_iv
        
        if ratio > 1.05:
            # Backwardation - elevated near-term fear
            score = 0.3  # Mean reversion opportunity
            return score, f"IV backwardation (near/far: {ratio:.2f})"
        elif ratio < 0.95:
            # Strong contango - very calm near-term
            score = -0.2
            return score, f"IV contango (near/far: {ratio:.2f})"
        else:
            return 0.0, "Normal term structure"
    
    def _compute_vix_signal(
        self, vix: float, vix_history: List[float], stock_iv: float = 0.0
    ) -> tuple[float, str, dict]:
        """
        Compute India VIX signal.
        
        - VIX > 20 → elevated fear → sell far-OTM options (wider spreads)
        - VIX < 12 → complacency → look for long vega plays ahead of events
        - VIX spike > +15% in 1 day → do not sell naked options
        - Stock IV > VIX → stock has elevated fear premium
        """
        flags = {
            "elevated_fear": False,
            "complacency": False,
            "spike_warning": False,
            "iv_crush_expected": False,
            "stock_premium": False,
        }
        
        if vix <= 0:
            return 0.0, "", flags
        
        # VIX level analysis
        if vix >= self.VIX_HIGH:
            flags["elevated_fear"] = True
            score = -0.4  # Be cautious, but can sell premium
            reason = f"VIX {vix:.1f} (elevated fear)"
        elif vix <= self.VIX_LOW:
            flags["complacency"] = True
            score = 0.3  # Look for long vega plays
            reason = f"VIX {vix:.1f} (complacency)"
        else:
            normalized = (vix - 16) / 8  # Center around 16
            score = -normalized * 0.2
            reason = f"VIX {vix:.1f} (normal)"
        
        # Rate of change analysis
        if len(vix_history) >= 2:
            # 1-day change
            one_day_change = (vix - vix_history[-1]) / vix_history[-1] if vix_history[-1] > 0 else 0
            
            if one_day_change >= self.VIX_SPIKE_THRESHOLD:
                flags["spike_warning"] = True
                score -= 0.3  # Strong warning signal
                reason += f" | VIX spike {one_day_change*100:.1f}%!"
            elif one_day_change <= -0.10:  # VIX falling > 10%
                flags["iv_crush_expected"] = True
                score += 0.2
                reason += " | IV crush expected"
        
        # 5-day change
        if len(vix_history) >= 5:
            five_day_change = (vix - vix_history[-5]) / vix_history[-5] if vix_history[-5] > 0 else 0
            if five_day_change <= -0.15:
                flags["iv_crush_expected"] = True
        
        # Stock IV vs VIX comparison
        if stock_iv > 0 and stock_iv > vix * 1.2:
            flags["stock_premium"] = True
            score -= 0.1  # Stock has elevated fear premium
        
        return score, reason, flags
