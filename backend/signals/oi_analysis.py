"""
signals/oi_analysis.py — OI Signal (Signal 1)

Computes signals from Option Chain OI data:
1. PCR (Put-Call Ratio) signal - contrarian indicator
2. OI buildup signal - support/resistance detection
3. Max OI wall detection - range boundaries

Score formula:
  pcr_score * 0.35 + oi_buildup_score * 0.40 + wall_distance_score * 0.25
"""

from __future__ import annotations
from typing import List, Dict, Optional
from .base import BaseSignal, SignalResult


class OiSignal(BaseSignal):
    """
    OI Analysis Signal — reads from OptionChainSnapshot
    
    Computes:
    1. PCR signal (contrarian)
    2. OI buildup signal (last 3 snapshots)
    3. Max OI wall detection
    """
    
    name = "oi_analysis"
    
    # PCR thresholds for contrarian signals
    PCR_HIGH_FEAR = 1.5      # Too much fear → contrarian bullish
    PCR_LOW_FEAR = 0.7       # Too much greed → contrarian bearish
    PCR_NEUTRAL_LOW = 0.9
    PCR_NEUTRAL_HIGH = 1.1
    
    def compute(
        self,
        records: List[dict],
        spot: float,
        pcr: float = 1.0,
        pcr_history: List[float] = None,
        oi_snapshots: List[dict] = None,
        symbol: str = "",
        **kwargs
    ) -> SignalResult:
        """
        Compute OI-based signal.
        
        Args:
            records: Option chain data rows
            spot: Current underlying price
            pcr: Current Put-Call Ratio
            pcr_history: Historical PCR values for trend detection
            oi_snapshots: Last 3 OI snapshots for buildup detection
            symbol: Underlying symbol
            
        Returns:
            SignalResult with composite OI score
        """
        if not records or spot <= 0:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                reason="Insufficient data for OI analysis"
            )
        
        # 1. PCR Signal
        pcr_score, pcr_reason = self._compute_pcr_signal(pcr, pcr_history or [])
        
        # 2. OI Buildup Signal
        buildup_score, buildup_reason = self._compute_oi_buildup(
            records, spot, oi_snapshots or []
        )
        
        # 3. Wall Distance Signal
        wall_score, wall_reason, wall_data = self._compute_wall_distance(records, spot)
        
        # Composite score with weights
        composite_score = (
            pcr_score * 0.35 +
            buildup_score * 0.40 +
            wall_score * 0.25
        )
        
        # Confidence based on data availability
        confidence = 0.7
        if pcr_history and len(pcr_history) >= 3:
            confidence += 0.1
        if oi_snapshots and len(oi_snapshots) >= 3:
            confidence += 0.1
        if wall_data.get("ce_wall") and wall_data.get("pe_wall"):
            confidence += 0.1
        confidence = min(1.0, confidence)
        
        reasons = [pcr_reason, buildup_reason, wall_reason]
        combined_reason = " | ".join(r for r in reasons if r)
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata={
                "pcr": pcr,
                "pcr_score": round(pcr_score, 3),
                "buildup_score": round(buildup_score, 3),
                "wall_score": round(wall_score, 3),
                "wall_data": wall_data,
            }
        )
    
    def _compute_pcr_signal(
        self, pcr: float, pcr_history: List[float]
    ) -> tuple[float, str]:
        """
        Compute PCR-based signal (contrarian).
        
        - PCR > 1.5 AND rising → contrarian bullish (too much fear = buy CE)
        - PCR < 0.7 AND falling → contrarian bearish (too much greed = buy PE)
        - PCR 0.9–1.1 → neutral
        """
        if not pcr or pcr <= 0:
            return 0.0, "PCR data unavailable"
        
        # Determine PCR trend from history
        pcr_rising = False
        pcr_falling = False
        
        if len(pcr_history) >= 2:
            recent_avg = sum(pcr_history[-2:]) / 2
            older_avg = sum(pcr_history[:-2]) / max(1, len(pcr_history) - 2) if len(pcr_history) > 2 else recent_avg
            pcr_rising = recent_avg > older_avg
            pcr_falling = recent_avg < older_avg
        
        # High PCR (fear) → contrarian bullish
        if pcr >= self.PCR_HIGH_FEAR:
            score = 0.6 + (0.4 if pcr_rising else 0.0)  # Stronger if rising
            return score, f"High PCR {pcr:.2f} (contrarian bullish)"
        
        # Low PCR (greed) → contrarian bearish
        if pcr <= self.PCR_LOW_FEAR:
            score = -0.6 - (0.4 if pcr_falling else 0.0)  # Stronger if falling
            return score, f"Low PCR {pcr:.2f} (contrarian bearish)"
        
        # Neutral zone
        if self.PCR_NEUTRAL_LOW <= pcr <= self.PCR_NEUTRAL_HIGH:
            return 0.0, f"Neutral PCR {pcr:.2f}"
        
        # Mild bias zones
        if pcr > self.PCR_NEUTRAL_HIGH:
            score = (pcr - self.PCR_NEUTRAL_HIGH) / (self.PCR_HIGH_FEAR - self.PCR_NEUTRAL_HIGH) * 0.5
            return score, f"PCR {pcr:.2f} mildly elevated"
        else:
            score = (self.PCR_NEUTRAL_LOW - pcr) / (self.PCR_NEUTRAL_LOW - self.PCR_LOW_FEAR) * -0.5
            return score, f"PCR {pcr:.2f} mildly depressed"
    
    def _compute_oi_buildup(
        self, records: List[dict], spot: float, oi_snapshots: List[dict]
    ) -> tuple[float, str]:
        """
        Compute OI buildup signal from last 3 snapshots.
        
        - CE OI rising at ATM + 1-2 strikes + price falling → strong resistance
        - PE OI rising at ATM - 1-2 strikes + price rising → strong support
        - OI unwinding (OI falling while price moving away) → momentum confirmation
        """
        if not oi_snapshots or len(oi_snapshots) < 2:
            # Fall back to current snapshot analysis
            return self._analyze_current_oi_structure(records, spot)
        
        # Compare latest vs. oldest snapshot
        latest = oi_snapshots[-1]
        oldest = oi_snapshots[0]
        
        # Calculate ATM zone (within 2 strikes)
        atm_range = self._get_atm_range(records, spot)
        
        ce_oi_change = 0
        pe_oi_change = 0
        
        for strike in atm_range:
            latest_ce = self._get_oi_at_strike(latest, strike, "CE")
            oldest_ce = self._get_oi_at_strike(oldest, strike, "CE")
            latest_pe = self._get_oi_at_strike(latest, strike, "PE")
            oldest_pe = self._get_oi_at_strike(oldest, strike, "PE")
            
            ce_oi_change += latest_ce - oldest_ce
            pe_oi_change += latest_pe - oldest_pe
        
        # Analyze price movement
        price_change = 0
        if "spot" in latest and "spot" in oldest:
            price_change = latest["spot"] - oldest["spot"]
        
        # CE OI rising + price falling → resistance forming (bearish)
        if ce_oi_change > 0 and price_change < 0:
            score = -0.4 - min(0.4, ce_oi_change / 1000000)
            return score, "CE OI buildup with price drop (resistance)"
        
        # PE OI rising + price rising → support forming (bullish)
        if pe_oi_change > 0 and price_change > 0:
            score = 0.4 + min(0.4, pe_oi_change / 1000000)
            return score, "PE OI buildup with price rise (support)"
        
        # OI unwinding detection
        if ce_oi_change < 0 and price_change > 0:
            score = 0.3  # Bullish momentum
            return score, "CE OI unwinding (bullish momentum)"
        
        if pe_oi_change < 0 and price_change < 0:
            score = -0.3  # Bearish momentum
            return score, "PE OI unwinding (bearish momentum)"
        
        return 0.0, "Neutral OI buildup"
    
    def _analyze_current_oi_structure(
        self, records: List[dict], spot: float
    ) -> tuple[float, str]:
        """Analyze current OI distribution when historical data unavailable."""
        if not records:
            return 0.0, "No OI data"
        
        total_ce_oi = 0
        total_pe_oi = 0
        weighted_ce = 0
        weighted_pe = 0
        
        for row in records:
            strike = row.get("strikePrice", 0)
            ce = row.get("CE", {}) or {}
            pe = row.get("PE", {}) or {}
            
            ce_oi = ce.get("openInterest", 0) or 0
            pe_oi = pe.get("openInterest", 0) or 0
            
            total_ce_oi += ce_oi
            total_pe_oi += pe_oi
            
            # Weight by distance from spot
            distance = abs(strike - spot)
            weight = 1.0 / (1.0 + distance / spot * 10)
            
            weighted_ce += ce_oi * weight
            weighted_pe += pe_oi * weight
        
        if weighted_ce == 0 and weighted_pe == 0:
            return 0.0, "No weighted OI"
        
        # Compare weighted OI
        ratio = weighted_pe / max(1, weighted_ce)
        
        if ratio > 1.3:
            return 0.3, f"PE heavy near ATM (ratio: {ratio:.2f})"
        elif ratio < 0.7:
            return -0.3, f"CE heavy near ATM (ratio: {ratio:.2f})"
        
        return 0.0, "Balanced OI structure"
    
    def _compute_wall_distance(
        self, records: List[dict], spot: float
    ) -> tuple[float, str, dict]:
        """
        Compute signal from max OI wall detection.
        
        - Find strike with highest CE OI (resistance wall)
        - Find strike with highest PE OI (support wall)
        - Distance from current price to walls → how much range available
        """
        if not records:
            return 0.0, "No wall data", {}
        
        max_ce_strike = None
        max_ce_oi = 0
        max_pe_strike = None
        max_pe_oi = 0
        
        for row in records:
            strike = row.get("strikePrice", 0)
            ce = row.get("CE", {}) or {}
            pe = row.get("PE", {}) or {}
            
            ce_oi = ce.get("openInterest", 0) or 0
            pe_oi = pe.get("openInterest", 0) or 0
            
            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                max_ce_strike = strike
            
            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                max_pe_strike = strike
        
        wall_data = {
            "ce_wall": max_ce_strike,
            "ce_wall_oi": max_ce_oi,
            "pe_wall": max_pe_strike,
            "pe_wall_oi": max_pe_oi,
        }
        
        if not max_ce_strike or not max_pe_strike:
            return 0.0, "Incomplete wall data", wall_data
        
        # Calculate distances
        resistance_dist = (max_ce_strike - spot) / spot * 100 if max_ce_strike > spot else 0
        support_dist = (spot - max_pe_strike) / spot * 100 if max_pe_strike < spot else 0
        
        wall_data["resistance_dist_pct"] = round(resistance_dist, 2)
        wall_data["support_dist_pct"] = round(support_dist, 2)
        
        # Signal based on asymmetry
        if resistance_dist > 0 and support_dist > 0:
            asymmetry = (resistance_dist - support_dist) / max(resistance_dist, support_dist)
            
            if asymmetry > 0.3:
                # More room to upside
                score = 0.3 + min(0.3, asymmetry / 2)
                return score, f"More upside room ({resistance_dist:.1f}% vs {support_dist:.1f}% down)", wall_data
            elif asymmetry < -0.3:
                # More room to downside
                score = -0.3 - min(0.3, abs(asymmetry) / 2)
                return score, f"More downside room ({support_dist:.1f}% vs {resistance_dist:.1f}% up)", wall_data
            else:
                return 0.0, f"Balanced walls ({resistance_dist:.1f}% up, {support_dist:.1f}% down)", wall_data
        
        # Edge cases
        if resistance_dist > 0 and support_dist == 0:
            return -0.2, f"Near support, {resistance_dist:.1f}% to resistance", wall_data
        if support_dist > 0 and resistance_dist == 0:
            return 0.2, f"Near resistance, {support_dist:.1f}% to support", wall_data
        
        return 0.0, "Price outside wall range", wall_data
    
    def _get_atm_range(self, records: List[dict], spot: float, strikes: int = 2) -> List[float]:
        """Get ATM +/- N strikes."""
        all_strikes = sorted({r.get("strikePrice", 0) for r in records if r.get("strikePrice")})
        if not all_strikes:
            return []
        
        # Find ATM
        atm = min(all_strikes, key=lambda s: abs(s - spot))
        atm_idx = all_strikes.index(atm)
        
        # Get range
        start = max(0, atm_idx - strikes)
        end = min(len(all_strikes), atm_idx + strikes + 1)
        
        return all_strikes[start:end]
    
    def _get_oi_at_strike(self, snapshot: dict, strike: float, opt_type: str) -> int:
        """Get OI at specific strike from snapshot."""
        data = snapshot.get("data", [])
        for row in data:
            if row.get("strikePrice") == strike:
                side = row.get(opt_type, {}) or {}
                return side.get("openInterest", 0) or 0
        return 0
