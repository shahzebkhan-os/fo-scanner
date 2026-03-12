"""
signals/greeks_signal.py — Greeks Composite Signal (Signal 12)

Computes signal from aggregate options market Greeks:

1. Aggregate delta exposure:
   - Net delta of all open CE vs. PE across all strikes
   - Net positive delta → market leans bullish

2. Charm (delta decay rate over time):
   - As DTE decreases, OTM deltas collapse → OTM option prices accelerate to zero
   - Charm effect most powerful last 2 days before expiry → avoid buying OTM options

3. Vanna (delta sensitivity to IV):
   - If IV spikes, high-vanna OTM options jump faster than BS model predicts
   - Track this for position sizing in volatile regimes

4. Position Greeks (per open trade):
   - Track net delta, theta, vega for the ENTIRE portfolio
   - If net vega > threshold → portfolio is too long volatility → balance
   - If net theta < -THETA_BURN_LIMIT per day → too much premium bought, reduce
"""

from __future__ import annotations
from typing import List, Dict, Optional
import math
from .base import BaseSignal, SignalResult


class GreeksSignal(BaseSignal):
    """
    Greeks Composite Signal — aggregate options Greeks analysis.
    
    Analyzes:
    - Net delta exposure across strikes
    - Charm effects near expiry
    - Vanna exposure for IV sensitivity
    - Portfolio-level Greeks balance
    """
    
    name = "greeks_signal"
    
    # Portfolio thresholds
    VEGA_IMBALANCE_THRESHOLD = 10000   # Net vega exposure limit
    THETA_BURN_LIMIT = -5000           # Max daily theta burn (negative = cost)
    DELTA_NEUTRAL_BAND = 0.1           # ±10% from neutral
    
    # Charm warning thresholds
    CHARM_WARNING_DTE = 2  # Warn about charm effects within 2 DTE
    
    def compute(
        self,
        records: List[dict] = None,
        spot: float = 0.0,
        dte: int = 30,
        lot_size: int = 50,
        portfolio_positions: List[dict] = None,
        iv_change_1d: float = 0.0,
        **kwargs
    ) -> SignalResult:
        """
        Compute Greeks composite signal.
        
        Args:
            records: Option chain data rows with Greeks
            spot: Current underlying price
            dte: Days to expiry
            lot_size: Contract lot size
            portfolio_positions: List of open positions with Greeks
            iv_change_1d: 1-day IV change (%) for vanna analysis
            
        Returns:
            SignalResult with Greeks analysis
        """
        records = records or []
        portfolio_positions = portfolio_positions or []
        
        if spot <= 0:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                reason="No spot price data"
            )
        
        scores = []
        reasons = []
        
        # 1. Aggregate Delta Exposure
        delta_data = self._compute_aggregate_delta(records, spot, lot_size)
        delta_score, delta_reason = self._analyze_delta(delta_data)
        scores.append(("delta", delta_score, 0.30))
        if delta_reason:
            reasons.append(delta_reason)
        
        # 2. Charm Analysis (DTE sensitivity)
        charm_score, charm_reason = self._analyze_charm(records, spot, dte)
        scores.append(("charm", charm_score, 0.20))
        if charm_reason:
            reasons.append(charm_reason)
        
        # 3. Vanna Analysis (IV sensitivity)
        vanna_score, vanna_reason = self._analyze_vanna(records, spot, iv_change_1d)
        scores.append(("vanna", vanna_score, 0.20))
        if vanna_reason:
            reasons.append(vanna_reason)
        
        # 4. Portfolio Greeks Balance
        portfolio_data = self._compute_portfolio_greeks(portfolio_positions)
        portfolio_score, portfolio_reason = self._analyze_portfolio_balance(portfolio_data)
        scores.append(("portfolio", portfolio_score, 0.30))
        if portfolio_reason:
            reasons.append(portfolio_reason)
        
        # Composite score
        total_weight = sum(s[2] for s in scores)
        composite_score = sum(s[1] * s[2] for s in scores) / total_weight if total_weight > 0 else 0
        
        # Confidence
        confidence = 0.5
        if records:
            confidence += 0.2
        if portfolio_positions:
            confidence += 0.2
        if dte <= 7:
            confidence += 0.1  # Greeks more meaningful near expiry
        confidence = min(1.0, confidence)
        
        combined_reason = " | ".join(reasons) if reasons else "Greeks neutral"
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata={
                "aggregate_delta": delta_data,
                "charm_warning": dte <= self.CHARM_WARNING_DTE,
                "portfolio_greeks": portfolio_data,
                "delta_score": round(delta_score, 3),
                "charm_score": round(charm_score, 3),
                "vanna_score": round(vanna_score, 3),
                "portfolio_score": round(portfolio_score, 3),
            }
        )
    
    def _compute_aggregate_delta(
        self, records: List[dict], spot: float, lot_size: int
    ) -> dict:
        """
        Compute aggregate delta exposure across all strikes.
        
        Net positive delta → market leans bullish.
        """
        total_ce_delta = 0.0
        total_pe_delta = 0.0
        weighted_ce_delta = 0.0
        weighted_pe_delta = 0.0
        total_ce_oi = 0
        total_pe_oi = 0
        
        for row in records:
            ce = row.get("CE", {}) or {}
            pe = row.get("PE", {}) or {}
            
            ce_oi = ce.get("openInterest", 0) or 0
            pe_oi = pe.get("openInterest", 0) or 0
            ce_delta = ce.get("delta", 0.0) or 0.0
            pe_delta = pe.get("delta", 0.0) or 0.0
            
            # Aggregate delta * OI
            total_ce_delta += ce_delta * ce_oi
            total_pe_delta += abs(pe_delta) * pe_oi  # PE delta is negative
            
            # Weighted by OI
            weighted_ce_delta += ce_delta * ce_oi * lot_size
            weighted_pe_delta += pe_delta * pe_oi * lot_size
            
            total_ce_oi += ce_oi
            total_pe_oi += pe_oi
        
        # Net delta exposure
        net_delta = weighted_ce_delta + weighted_pe_delta  # PE delta is negative
        
        # Delta ratio (normalized)
        if total_ce_oi + total_pe_oi > 0:
            avg_ce_delta = total_ce_delta / total_ce_oi if total_ce_oi > 0 else 0
            avg_pe_delta = total_pe_delta / total_pe_oi if total_pe_oi > 0 else 0
        else:
            avg_ce_delta = 0.5
            avg_pe_delta = 0.5
        
        return {
            "net_delta": net_delta,
            "total_ce_delta": round(total_ce_delta, 2),
            "total_pe_delta": round(total_pe_delta, 2),
            "avg_ce_delta": round(avg_ce_delta, 4),
            "avg_pe_delta": round(avg_pe_delta, 4),
            "delta_bias": "BULLISH" if net_delta > 0 else "BEARISH",
        }
    
    def _analyze_delta(self, delta_data: dict) -> tuple[float, str]:
        """Analyze aggregate delta for directional signal."""
        net_delta = delta_data.get("net_delta", 0)
        
        # Normalize to reasonable score range
        # Large positive net delta = bullish
        # Large negative net delta = bearish
        
        if net_delta > 100000:
            score = 0.4 + min(0.4, net_delta / 500000)
            reason = f"Strong bullish delta bias ({net_delta/1000:.0f}k)"
        elif net_delta > 50000:
            score = 0.2 + (net_delta - 50000) / 100000 * 0.2
            reason = f"Bullish delta bias ({net_delta/1000:.0f}k)"
        elif net_delta < -100000:
            score = -0.4 - min(0.4, abs(net_delta) / 500000)
            reason = f"Strong bearish delta bias ({net_delta/1000:.0f}k)"
        elif net_delta < -50000:
            score = -0.2 - (abs(net_delta) - 50000) / 100000 * 0.2
            reason = f"Bearish delta bias ({net_delta/1000:.0f}k)"
        else:
            score = 0.0
            reason = "Neutral delta exposure"
        
        return max(-1.0, min(1.0, score)), reason
    
    def _analyze_charm(
        self, records: List[dict], spot: float, dte: int
    ) -> tuple[float, str]:
        """
        Analyze charm effects (delta decay over time).
        
        Near expiry, OTM deltas collapse rapidly.
        This affects position sizing and entry timing.
        """
        if dte > self.CHARM_WARNING_DTE:
            return 0.0, ""
        
        # Near expiry - charm effects are significant
        # OTM options will see accelerated time decay
        
        # Count OTM options with significant OI
        otm_ce_oi = 0
        otm_pe_oi = 0
        atm_range = spot * 0.02  # Within 2% of spot
        
        for row in records:
            strike = row.get("strikePrice", 0)
            ce = row.get("CE", {}) or {}
            pe = row.get("PE", {}) or {}
            
            if strike > spot + atm_range:
                otm_ce_oi += ce.get("openInterest", 0) or 0
            if strike < spot - atm_range:
                otm_pe_oi += pe.get("openInterest", 0) or 0
        
        # High OTM OI near expiry = charm risk
        if otm_ce_oi > 1000000 or otm_pe_oi > 1000000:
            if otm_ce_oi > otm_pe_oi:
                score = -0.3
                reason = f"Charm warning: OTM CE OI high, DTE={dte}"
            else:
                score = 0.3
                reason = f"Charm warning: OTM PE OI high, DTE={dte}"
        else:
            score = 0.0
            reason = f"Charm active (DTE={dte})"
        
        return score, reason
    
    def _analyze_vanna(
        self, records: List[dict], spot: float, iv_change: float
    ) -> tuple[float, str]:
        """
        Analyze vanna exposure (delta sensitivity to IV).
        
        If IV spikes, high-vanna OTM options move faster than expected.
        """
        if abs(iv_change) < 1:  # Less than 1% IV change
            return 0.0, ""
        
        # Find high-vanna strikes (far OTM with significant OI)
        high_vanna_strikes = []
        
        for row in records:
            strike = row.get("strikePrice", 0)
            ce = row.get("CE", {}) or {}
            pe = row.get("PE", {}) or {}
            
            dist_pct = abs(strike - spot) / spot * 100
            
            if dist_pct > 3:  # More than 3% OTM
                ce_oi = ce.get("openInterest", 0) or 0
                pe_oi = pe.get("openInterest", 0) or 0
                
                if ce_oi > 100000 or pe_oi > 100000:
                    high_vanna_strikes.append({
                        "strike": strike,
                        "ce_oi": ce_oi,
                        "pe_oi": pe_oi,
                        "dist_pct": dist_pct,
                    })
        
        if not high_vanna_strikes:
            return 0.0, ""
        
        # IV rising with high OTM OI
        if iv_change > 3:
            score = 0.3  # OTM calls/puts may outperform
            reason = f"Vanna boost (IV +{iv_change:.1f}%)"
        elif iv_change < -3:
            score = -0.2  # OTM options may underperform
            reason = f"Vanna drag (IV {iv_change:.1f}%)"
        else:
            score = iv_change / 10  # Proportional effect
            reason = f"Vanna effect (IV {iv_change:+.1f}%)"
        
        return score, reason
    
    def _compute_portfolio_greeks(self, positions: List[dict]) -> dict:
        """
        Compute aggregate Greeks for portfolio positions.
        
        Each position should have:
        - delta, gamma, theta, vega per lot
        - qty (number of lots)
        - direction (1 for long, -1 for short)
        """
        net_delta = 0.0
        net_gamma = 0.0
        net_theta = 0.0
        net_vega = 0.0
        
        for pos in positions:
            qty = pos.get("qty", 0)
            direction = pos.get("direction", 1)
            multiplier = qty * direction
            
            net_delta += pos.get("delta", 0) * multiplier
            net_gamma += pos.get("gamma", 0) * multiplier
            net_theta += pos.get("theta", 0) * multiplier
            net_vega += pos.get("vega", 0) * multiplier
        
        return {
            "net_delta": round(net_delta, 2),
            "net_gamma": round(net_gamma, 4),
            "net_theta": round(net_theta, 2),
            "net_vega": round(net_vega, 2),
            "position_count": len(positions),
        }
    
    def _analyze_portfolio_balance(self, portfolio: dict) -> tuple[float, str]:
        """
        Analyze portfolio Greeks balance.
        
        - If net vega > threshold → too long volatility
        - If net theta < -THETA_BURN_LIMIT → too much premium bought
        """
        if portfolio.get("position_count", 0) == 0:
            return 0.0, ""
        
        net_vega = portfolio.get("net_vega", 0)
        net_theta = portfolio.get("net_theta", 0)
        net_delta = portfolio.get("net_delta", 0)
        
        reasons = []
        score = 0.0
        
        # Vega imbalance
        if abs(net_vega) > self.VEGA_IMBALANCE_THRESHOLD:
            if net_vega > 0:
                score -= 0.2
                reasons.append(f"Long vega imbalance ({net_vega:.0f})")
            else:
                score += 0.1
                reasons.append(f"Short vega ({net_vega:.0f})")
        
        # Theta burn
        if net_theta < self.THETA_BURN_LIMIT:
            score -= 0.3
            reasons.append(f"High theta burn ({net_theta:.0f}/day)")
        elif net_theta > 0:
            score += 0.2
            reasons.append(f"Positive theta ({net_theta:.0f}/day)")
        
        # Delta neutrality
        delta_normalized = net_delta / 100  # Normalize
        if abs(delta_normalized) > self.DELTA_NEUTRAL_BAND:
            if delta_normalized > 0:
                reasons.append(f"Delta long ({net_delta:.0f})")
            else:
                reasons.append(f"Delta short ({net_delta:.0f})")
        
        reason = "; ".join(reasons) if reasons else "Portfolio balanced"
        return max(-1.0, min(1.0, score)), reason
