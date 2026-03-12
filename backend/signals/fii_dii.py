"""
signals/fii_dii.py — FII/DII Flow Signal (Signal 8)

Source: NSE website (https://www.nseindia.com/api/fiidiiTradeReact)
Fetched once per day after 18:00 IST (data released after market close).

Metrics:
- FII net buy/sell in index futures (long/short ratio)
- FII net CE/PE buy in index options
- FII net position in NIFTY futures (from SEBI FII stats)
- DII net position (mutual funds + insurance)

This signal has 1-day lag — use as medium-term bias, not intraday trigger.
"""

from __future__ import annotations
from typing import List, Dict, Optional
from .base import BaseSignal, SignalResult


class FiiDiiSignal(BaseSignal):
    """
    FII/DII Flow Signal — institutional money flow analysis.
    
    Note: This signal has a 1-day lag and should be used as
    medium-term bias indicator, not for intraday decisions.
    """
    
    name = "fii_dii"
    
    # Thresholds (in crores INR)
    FII_STRONG_BULLISH = 5000     # Net long > +5000 cr
    FII_STRONG_BEARISH = -15000   # Cumulative 3-day selling > -15000 cr
    FII_MODERATE = 2000           # Moderate activity threshold
    
    # DII thresholds
    DII_STRONG = 3000
    
    def compute(
        self,
        fii_net_futures: float = 0.0,
        fii_net_options_ce: float = 0.0,
        fii_net_options_pe: float = 0.0,
        fii_index_position: float = 0.0,
        dii_net: float = 0.0,
        fii_3day_cumulative: float = 0.0,
        fii_long_short_ratio: float = 1.0,
        data_date: str = "",
        **kwargs
    ) -> SignalResult:
        """
        Compute FII/DII flow signal.
        
        Args:
            fii_net_futures: FII net buy/sell in index futures (crores)
            fii_net_options_ce: FII net CE buy (crores)
            fii_net_options_pe: FII net PE buy (crores)
            fii_index_position: FII net position in NIFTY futures
            dii_net: DII net position (crores)
            fii_3day_cumulative: 3-day cumulative FII flow
            fii_long_short_ratio: FII futures long/short ratio
            data_date: Date of the data (for staleness check)
            
        Returns:
            SignalResult with institutional flow score
        """
        scores = []
        reasons = []
        metadata = {
            "fii_net_futures": fii_net_futures,
            "fii_net_options": fii_net_options_ce + fii_net_options_pe,
            "dii_net": dii_net,
            "fii_3day": fii_3day_cumulative,
            "data_date": data_date,
        }
        
        # 1. FII Futures Flow
        fut_score, fut_reason = self._analyze_fii_futures(
            fii_net_futures, fii_long_short_ratio
        )
        if fut_score != 0:
            scores.append(("futures", fut_score, 0.35))
            reasons.append(fut_reason)
        
        # 2. FII Options Flow
        opt_score, opt_reason = self._analyze_fii_options(
            fii_net_options_ce, fii_net_options_pe
        )
        if opt_score != 0:
            scores.append(("options", opt_score, 0.25))
            reasons.append(opt_reason)
        
        # 3. Cumulative Flow (3-day)
        cum_score, cum_reason = self._analyze_cumulative_flow(fii_3day_cumulative)
        if cum_score != 0:
            scores.append(("cumulative", cum_score, 0.25))
            reasons.append(cum_reason)
        
        # 4. DII Counterbalance
        dii_score, dii_reason = self._analyze_dii(dii_net)
        if dii_score != 0:
            scores.append(("dii", dii_score, 0.15))
            reasons.append(dii_reason)
        
        # Composite score
        if scores:
            total_weight = sum(s[2] for s in scores)
            composite_score = sum(s[1] * s[2] for s in scores) / total_weight if total_weight > 0 else 0
        else:
            composite_score = 0.0
        
        # Confidence (lower due to 1-day lag)
        confidence = 0.5  # Base confidence is lower due to lagged data
        if fii_net_futures != 0:
            confidence += 0.15
        if fii_3day_cumulative != 0:
            confidence += 0.1
        if dii_net != 0:
            confidence += 0.1
        confidence = min(0.85, confidence)  # Cap at 0.85 due to lag
        
        combined_reason = " | ".join(reasons) if reasons else "No significant institutional flow"
        if data_date:
            combined_reason += f" (data: {data_date})"
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata=metadata
        )
    
    def _analyze_fii_futures(
        self, net_futures: float, long_short_ratio: float
    ) -> tuple[float, str]:
        """
        Analyze FII futures positioning.
        
        FII futures net long > +5000 crore → strong bullish signal.
        """
        if net_futures == 0 and long_short_ratio == 1.0:
            return 0.0, ""
        
        # Net position analysis
        if net_futures >= self.FII_STRONG_BULLISH:
            score = 0.7
            reason = f"FII futures +{net_futures:.0f}cr (strong bullish)"
        elif net_futures >= self.FII_MODERATE:
            score = 0.4
            reason = f"FII futures +{net_futures:.0f}cr (bullish)"
        elif net_futures <= -self.FII_MODERATE:
            score = -0.4
            reason = f"FII futures {net_futures:.0f}cr (bearish)"
        elif net_futures <= -self.FII_STRONG_BULLISH:
            score = -0.7
            reason = f"FII futures {net_futures:.0f}cr (strong bearish)"
        else:
            score = net_futures / self.FII_MODERATE * 0.3
            reason = f"FII futures {net_futures:+.0f}cr"
        
        # Long/short ratio adjustment
        if long_short_ratio > 1.5:
            score += 0.2
            reason += f" (L/S: {long_short_ratio:.2f})"
        elif long_short_ratio < 0.7:
            score -= 0.2
            reason += f" (L/S: {long_short_ratio:.2f})"
        
        return max(-1.0, min(1.0, score)), reason
    
    def _analyze_fii_options(
        self, net_ce: float, net_pe: float
    ) -> tuple[float, str]:
        """
        Analyze FII options activity.
        
        FII selling puts (closing PE positions) → bullish confirmation.
        FII buying puts → bearish hedge activity.
        """
        if net_ce == 0 and net_pe == 0:
            return 0.0, ""
        
        net_total = net_ce + net_pe
        
        # Put selling (negative PE = closing/selling puts)
        if net_pe < -1000:
            score = 0.4  # Bullish - FII selling puts
            reason = f"FII PE selling ({net_pe:.0f}cr)"
        elif net_pe > 1000:
            score = -0.3  # Bearish - FII buying puts
            reason = f"FII PE buying (+{net_pe:.0f}cr)"
        # Call activity
        elif net_ce > 1000:
            score = 0.3  # Bullish - FII buying calls
            reason = f"FII CE buying (+{net_ce:.0f}cr)"
        elif net_ce < -1000:
            score = -0.3  # Bearish - FII selling calls
            reason = f"FII CE selling ({net_ce:.0f}cr)"
        else:
            score = 0.0
            reason = f"FII options net {net_total:.0f}cr"
        
        return score, reason
    
    def _analyze_cumulative_flow(self, cumulative_3day: float) -> tuple[float, str]:
        """
        Analyze 3-day cumulative FII flow.
        
        Consecutive 3-day FII selling > -15000 crore cumulative → bearish regime.
        """
        if cumulative_3day == 0:
            return 0.0, ""
        
        if cumulative_3day <= self.FII_STRONG_BEARISH:
            score = -0.8
            reason = f"FII 3-day {cumulative_3day:.0f}cr (bearish regime)"
        elif cumulative_3day >= abs(self.FII_STRONG_BEARISH):
            score = 0.6
            reason = f"FII 3-day +{cumulative_3day:.0f}cr (bullish regime)"
        elif cumulative_3day > 0:
            score = cumulative_3day / abs(self.FII_STRONG_BEARISH) * 0.5
            reason = f"FII 3-day +{cumulative_3day:.0f}cr"
        else:
            score = cumulative_3day / abs(self.FII_STRONG_BEARISH) * 0.5
            reason = f"FII 3-day {cumulative_3day:.0f}cr"
        
        return max(-1.0, min(1.0, score)), reason
    
    def _analyze_dii(self, dii_net: float) -> tuple[float, str]:
        """
        Analyze DII (mutual funds + insurance) activity.
        
        DII buying often counterbalances FII selling.
        Strong DII buying during FII selling → support for market.
        """
        if dii_net == 0:
            return 0.0, ""
        
        if dii_net >= self.DII_STRONG:
            score = 0.4
            reason = f"DII +{dii_net:.0f}cr (strong buying)"
        elif dii_net <= -self.DII_STRONG:
            score = -0.3
            reason = f"DII {dii_net:.0f}cr (selling)"
        else:
            score = dii_net / self.DII_STRONG * 0.3
            reason = f"DII {dii_net:+.0f}cr"
        
        return score, reason
