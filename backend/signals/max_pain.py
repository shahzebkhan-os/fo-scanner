"""
signals/max_pain.py — Max Pain & GEX Signal (Signal 3)

Max Pain calculation:
- For each strike S, calculate total loss to ALL option writers if index settles at S
- Max Pain = strike that minimizes writer_loss
- "Pinning" effect: near expiry (DTE < 2), index tends to gravitate toward max pain

Gamma Exposure (GEX):
- GEX = sum over all strikes of (CE_gamma * CE_OI - PE_gamma * PE_OI) * spot * lot_size
- Positive GEX → market makers long gamma → they BUY dips, SELL rips → range-bound
- Negative GEX → market makers short gamma → they SELL dips, BUY rips → trending/volatile
- Flip from positive to negative GEX → potential volatility expansion signal

Score: combine max_pain_distance + gex_sign + gex_flip_flag
"""

from __future__ import annotations
from typing import List, Dict, Optional
from .base import BaseSignal, SignalResult


class MaxPainSignal(BaseSignal):
    """
    Max Pain and Gamma Exposure Signal.
    
    Combines:
    - Max pain level and distance analysis
    - GEX (Gamma Exposure) sign and magnitude
    - GEX flip detection for volatility regime changes
    """
    
    name = "max_pain"
    
    # Max pain proximity threshold (in % of spot)
    MAX_PAIN_PROXIMITY_PCT = 0.5  # Within 0.5% considered "pinning"
    
    # GEX thresholds
    GEX_STRONG_POSITIVE = 1e9    # Strong positive gamma
    GEX_STRONG_NEGATIVE = -1e9   # Strong negative gamma
    
    def compute(
        self,
        records: List[dict],
        spot: float,
        lot_size: int = 50,
        dte: int = 30,
        prev_gex: float = None,
        **kwargs
    ) -> SignalResult:
        """
        Compute Max Pain and GEX signal.
        
        Args:
            records: Option chain data rows
            spot: Current underlying price
            lot_size: Contract lot size
            dte: Days to expiry
            prev_gex: Previous GEX value for flip detection
            
        Returns:
            SignalResult with combined max pain and GEX score
        """
        if not records or spot <= 0:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                reason="Insufficient data for max pain/GEX analysis"
            )
        
        # 1. Compute Max Pain
        max_pain, max_pain_score, max_pain_reason = self._compute_max_pain(records, spot, dte)
        
        # 2. Compute GEX
        gex_data = self._compute_gex(records, spot, lot_size)
        gex_score, gex_reason = self._analyze_gex(gex_data, prev_gex)
        
        # Weights based on DTE
        # Near expiry: max pain more important
        # Far expiry: GEX more important
        if dte <= 2:
            mp_weight = 0.60
            gex_weight = 0.40
        elif dte <= 7:
            mp_weight = 0.45
            gex_weight = 0.55
        else:
            mp_weight = 0.30
            gex_weight = 0.70
        
        composite_score = max_pain_score * mp_weight + gex_score * gex_weight
        
        # Confidence based on data quality
        confidence = 0.6
        if len(records) >= 20:
            confidence += 0.1
        if max_pain and abs((spot - max_pain) / spot) < 0.02:
            confidence += 0.1  # Near max pain = higher confidence in pinning
        if gex_data.get("total_oi", 0) > 1000000:
            confidence += 0.1
        if prev_gex is not None:
            confidence += 0.1  # Have flip detection data
        confidence = min(1.0, confidence)
        
        reasons = [max_pain_reason, gex_reason]
        combined_reason = " | ".join(r for r in reasons if r)
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata={
                "max_pain": max_pain,
                "max_pain_dist_pct": round((spot - max_pain) / spot * 100, 2) if max_pain else None,
                "net_gex": gex_data.get("net_gex", 0),
                "gex_regime": gex_data.get("regime", "UNKNOWN"),
                "zero_gamma_level": gex_data.get("zero_gamma_level"),
                "gex_flip": gex_data.get("flip_detected", False),
                "max_pain_score": round(max_pain_score, 3),
                "gex_score": round(gex_score, 3),
            }
        )
    
    def _compute_max_pain(
        self, records: List[dict], spot: float, dte: int
    ) -> tuple[Optional[float], float, str]:
        """
        Compute max pain strike and signal.
        
        Max Pain = strike that minimizes total writer loss.
        Writer loss = sum of intrinsic values at settlement × OI.
        """
        strikes = sorted({r.get("strikePrice", 0) for r in records if r.get("strikePrice")})
        if not strikes:
            return None, 0.0, "No strike data"
        
        # Build OI maps
        ce_oi = {}
        pe_oi = {}
        for r in records:
            strike = r.get("strikePrice", 0)
            ce = r.get("CE", {}) or {}
            pe = r.get("PE", {}) or {}
            ce_oi[strike] = ce.get("openInterest", 0) or 0
            pe_oi[strike] = pe.get("openInterest", 0) or 0
        
        # Calculate writer loss at each strike
        min_pain = float("inf")
        max_pain_strike = strikes[0]
        
        for candidate in strikes:
            # Total writer loss if settled at 'candidate'
            total_loss = 0
            
            # CE writers lose on ITM calls (strike < candidate)
            for k in strikes:
                if k < candidate:
                    total_loss += (candidate - k) * ce_oi.get(k, 0)
            
            # PE writers lose on ITM puts (strike > candidate)
            for k in strikes:
                if k > candidate:
                    total_loss += (k - candidate) * pe_oi.get(k, 0)
            
            if total_loss < min_pain:
                min_pain = total_loss
                max_pain_strike = candidate
        
        # Calculate score based on distance and DTE
        distance_pct = (spot - max_pain_strike) / spot * 100
        
        # Near expiry pinning effect
        if dte <= 2 and abs(distance_pct) < self.MAX_PAIN_PROXIMITY_PCT:
            score = 0.0  # Neutral, expect pinning
            reason = f"Max pain {max_pain_strike:.0f} (pinning expected, DTE={dte})"
        elif dte <= 2:
            # Near expiry, expect drift toward max pain
            if distance_pct > 0:
                score = -0.4  # Price above max pain, expect pullback
                reason = f"Price above max pain by {distance_pct:.1f}% (DTE={dte}, drift expected)"
            else:
                score = 0.4  # Price below max pain, expect rally
                reason = f"Price below max pain by {abs(distance_pct):.1f}% (DTE={dte}, drift expected)"
        else:
            # Farther expiry, max pain is just a reference
            if abs(distance_pct) < 1.0:
                score = 0.0
                reason = f"Near max pain {max_pain_strike:.0f}"
            elif distance_pct > 2.0:
                score = -0.2
                reason = f"Price {distance_pct:.1f}% above max pain {max_pain_strike:.0f}"
            elif distance_pct < -2.0:
                score = 0.2
                reason = f"Price {abs(distance_pct):.1f}% below max pain {max_pain_strike:.0f}"
            else:
                score = 0.0
                reason = f"Max pain {max_pain_strike:.0f} ({distance_pct:+.1f}%)"
        
        return max_pain_strike, score, reason
    
    def _compute_gex(
        self, records: List[dict], spot: float, lot_size: int
    ) -> dict:
        """
        Compute Gamma Exposure (GEX).
        
        GEX = sum over all strikes of (CE_gamma * CE_OI - PE_gamma * PE_OI) * spot * lot_size
        
        Positive GEX → MM long gamma → stabilizing
        Negative GEX → MM short gamma → destabilizing
        """
        total_call_gex = 0.0
        total_put_gex = 0.0
        total_oi = 0
        gex_by_strike = []
        
        for row in records:
            strike = row.get("strikePrice", 0)
            ce = row.get("CE", {}) or {}
            pe = row.get("PE", {}) or {}
            
            ce_oi = ce.get("openInterest", 0) or 0
            pe_oi = pe.get("openInterest", 0) or 0
            ce_gamma = ce.get("gamma", 0.0) or 0.0
            pe_gamma = pe.get("gamma", 0.0) or 0.0
            
            total_oi += ce_oi + pe_oi
            
            # Compute GEX contribution
            if ce_oi and ce_gamma:
                call_gex = ce_oi * ce_gamma * lot_size * (spot ** 2) / 100
                total_call_gex += call_gex
            
            if pe_oi and pe_gamma:
                # Puts have negative gamma exposure for dealers (they're short)
                put_gex = pe_oi * pe_gamma * lot_size * (spot ** 2) / 100
                total_put_gex -= put_gex  # Note: subtracting
            
            if ce_oi or pe_oi:
                net_gex_at_strike = (ce_oi * ce_gamma) - (pe_oi * pe_gamma)
                gex_by_strike.append({
                    "strike": strike,
                    "net_gex": net_gex_at_strike,
                    "ce_gex": ce_oi * ce_gamma,
                    "pe_gex": pe_oi * pe_gamma,
                })
        
        net_gex = total_call_gex + total_put_gex
        
        # Find zero gamma level (where net GEX flips sign)
        zero_gamma_level = spot
        sorted_strikes = sorted(gex_by_strike, key=lambda x: x["strike"])
        for i in range(len(sorted_strikes) - 1):
            curr = sorted_strikes[i]
            next_s = sorted_strikes[i + 1]
            if curr["net_gex"] * next_s["net_gex"] < 0:  # Sign flip
                # Linear interpolation
                zero_gamma_level = (curr["strike"] + next_s["strike"]) / 2
                break
        
        regime = "POSITIVE" if net_gex > 0 else "NEGATIVE"
        
        return {
            "net_gex": net_gex,
            "total_call_gex": total_call_gex,
            "total_put_gex": total_put_gex,
            "total_oi": total_oi,
            "gex_by_strike": gex_by_strike,
            "zero_gamma_level": zero_gamma_level,
            "regime": regime,
        }
    
    def _analyze_gex(
        self, gex_data: dict, prev_gex: float = None
    ) -> tuple[float, str]:
        """
        Analyze GEX for trading signal.
        
        - Positive GEX → range-bound, mean reversion
        - Negative GEX → trending, momentum
        - Flip detection → volatility regime change
        """
        net_gex = gex_data.get("net_gex", 0)
        regime = gex_data.get("regime", "UNKNOWN")
        zero_gamma = gex_data.get("zero_gamma_level", 0)
        
        reasons = []
        score = 0.0
        
        # GEX regime scoring
        if regime == "POSITIVE":
            score = 0.2  # Slightly bullish bias (mean reversion favors current price)
            reasons.append(f"Positive GEX ({net_gex/1e9:.1f}B)")
        else:
            score = -0.1  # Slightly bearish bias (trending can go either way)
            reasons.append(f"Negative GEX ({net_gex/1e9:.1f}B)")
        
        # Check for GEX flip
        flip_detected = False
        if prev_gex is not None:
            if prev_gex > 0 and net_gex < 0:
                flip_detected = True
                score -= 0.3  # Flip to negative = volatility expansion
                reasons.append("GEX FLIP to negative (vol expansion)")
                gex_data["flip_detected"] = True
            elif prev_gex < 0 and net_gex > 0:
                flip_detected = True
                score += 0.3  # Flip to positive = volatility contraction
                reasons.append("GEX FLIP to positive (vol contraction)")
                gex_data["flip_detected"] = True
        
        gex_data["flip_detected"] = flip_detected
        
        # Magnitude adjustment
        if abs(net_gex) > self.GEX_STRONG_POSITIVE:
            if net_gex > 0:
                score += 0.1
                reasons.append("Strong positive gamma")
            else:
                score -= 0.1
                reasons.append("Strong negative gamma")
        
        reason = " | ".join(reasons)
        return score, reason
