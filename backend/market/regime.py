"""
market/regime.py — Market Regime Classifier (Signal 11)

Classifies current market into one of 4 regimes:

TRENDING_UP:
  - Price above 20 EMA on 15-min chart
  - Supertrend bullish
  - NIFTY > previous day high after 10:30 IST
  - Strategy: bull call spreads, sell OTM PE

TRENDING_DOWN:
  - Price below 20 EMA
  - Supertrend bearish
  - Strategy: bear put spreads, sell OTM CE

RANGE_BOUND:
  - Price oscillating within ±0.3% of VWAP
  - Positive GEX (market makers dampen moves)
  - Strategy: iron condor, short straddle (if IVR > 60)

HIGH_VOLATILITY:
  - VIX > 18 OR India VIX spike > +10% intraday
  - GEX negative (market makers amplify moves)
  - Straddle price > 1.5x normal
  - Strategy: long straddle, wide iron condor, reduce all short vega positions by 50%

Regime drives strategy selection and position sizing multiplier:
  RANGE_BOUND: size multiplier 1.0 (ideal for premium selling)
  TRENDING:    size multiplier 0.7
  HIGH_VOLATILITY: size multiplier 0.4, no new premium selling
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, time


class MarketRegime(str, Enum):
    """Market regime classification."""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGE_BOUND = "RANGE_BOUND"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeResult:
    """Result of regime classification."""
    regime: MarketRegime
    confidence: float
    reasons: list
    size_multiplier: float
    recommended_strategies: list
    avoid_strategies: list
    
    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "confidence": round(self.confidence, 3),
            "reasons": self.reasons,
            "size_multiplier": self.size_multiplier,
            "recommended_strategies": self.recommended_strategies,
            "avoid_strategies": self.avoid_strategies,
        }


class RegimeClassifier:
    """
    Market Regime Classifier — runs every 15 minutes.
    
    Classifies market into TRENDING_UP, TRENDING_DOWN, RANGE_BOUND, or HIGH_VOLATILITY.
    """
    
    # Thresholds
    VWAP_RANGE_THRESHOLD = 0.3      # ±0.3% from VWAP = range-bound
    VIX_HIGH_THRESHOLD = 18         # VIX > 18 = high volatility
    VIX_SPIKE_THRESHOLD = 10        # VIX +10% intraday = vol spike
    STRADDLE_SPIKE_MULTIPLIER = 1.5 # Straddle > 1.5x normal = elevated vol
    
    # Size multipliers by regime
    SIZE_MULTIPLIERS = {
        MarketRegime.RANGE_BOUND: 1.0,
        MarketRegime.TRENDING_UP: 0.7,
        MarketRegime.TRENDING_DOWN: 0.7,
        MarketRegime.HIGH_VOLATILITY: 0.4,
        MarketRegime.UNKNOWN: 0.5,
    }
    
    # Strategy recommendations by regime
    REGIME_STRATEGIES = {
        MarketRegime.TRENDING_UP: {
            "recommended": ["bull_call_spread", "sell_otm_pe", "long_ce", "covered_call"],
            "avoid": ["short_straddle", "iron_condor", "sell_otm_ce", "long_pe"],
        },
        MarketRegime.TRENDING_DOWN: {
            "recommended": ["bear_put_spread", "sell_otm_ce", "long_pe", "protective_put"],
            "avoid": ["short_straddle", "iron_condor", "sell_otm_pe", "long_ce"],
        },
        MarketRegime.RANGE_BOUND: {
            "recommended": ["iron_condor", "short_straddle", "iron_butterfly", "credit_spread"],
            "avoid": ["long_straddle", "long_strangle", "directional_plays"],
        },
        MarketRegime.HIGH_VOLATILITY: {
            "recommended": ["long_straddle", "long_strangle", "wide_iron_condor"],
            "avoid": ["short_straddle", "narrow_iron_condor", "naked_options"],
        },
        MarketRegime.UNKNOWN: {
            "recommended": ["wait", "reduce_exposure"],
            "avoid": ["all_new_positions"],
        },
    }
    
    def classify(
        self,
        spot: float,
        vwap: float = 0.0,
        ema_20: float = 0.0,
        prev_day_high: float = 0.0,
        prev_day_low: float = 0.0,
        supertrend_bullish: bool = None,
        vix: float = 0.0,
        vix_open: float = 0.0,
        net_gex: float = 0.0,
        straddle_price: float = 0.0,
        normal_straddle_price: float = 0.0,
        ivr: float = 50.0,
        current_time: datetime = None,
        **kwargs
    ) -> RegimeResult:
        """
        Classify current market regime.
        
        Args:
            spot: Current underlying price
            vwap: Current VWAP
            ema_20: 20-period EMA (15-min chart)
            prev_day_high: Previous day high
            prev_day_low: Previous day low
            supertrend_bullish: True if Supertrend is bullish
            vix: Current India VIX
            vix_open: VIX at market open (for spike detection)
            net_gex: Net Gamma Exposure
            straddle_price: Current ATM straddle price
            normal_straddle_price: Average/expected straddle price
            ivr: IV Rank (0-100)
            current_time: Current market time
            
        Returns:
            RegimeResult with classification and recommendations
        """
        if spot <= 0:
            return RegimeResult(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                reasons=["No price data"],
                size_multiplier=0.5,
                recommended_strategies=["wait"],
                avoid_strategies=["all_positions"],
            )
        
        # Score each regime
        scores = {
            MarketRegime.HIGH_VOLATILITY: self._score_high_volatility(
                vix, vix_open, net_gex, straddle_price, normal_straddle_price
            ),
            MarketRegime.TRENDING_UP: self._score_trending_up(
                spot, ema_20, prev_day_high, supertrend_bullish, current_time
            ),
            MarketRegime.TRENDING_DOWN: self._score_trending_down(
                spot, ema_20, prev_day_low, supertrend_bullish
            ),
            MarketRegime.RANGE_BOUND: self._score_range_bound(
                spot, vwap, net_gex, ivr
            ),
        }
        
        # Collect reasons for each regime
        all_reasons = {}
        for regime, (score, reasons) in scores.items():
            all_reasons[regime] = reasons
        
        # HIGH_VOLATILITY takes precedence if score is high
        if scores[MarketRegime.HIGH_VOLATILITY][0] >= 0.6:
            selected_regime = MarketRegime.HIGH_VOLATILITY
        else:
            # Select highest scoring regime
            selected_regime = max(scores.keys(), key=lambda r: scores[r][0])
        
        # If no clear winner, default to RANGE_BOUND
        if scores[selected_regime][0] < 0.3:
            selected_regime = MarketRegime.RANGE_BOUND
        
        # Get strategy recommendations
        strategies = self.REGIME_STRATEGIES.get(selected_regime, {})
        
        return RegimeResult(
            regime=selected_regime,
            confidence=scores[selected_regime][0],
            reasons=all_reasons[selected_regime],
            size_multiplier=self.SIZE_MULTIPLIERS[selected_regime],
            recommended_strategies=strategies.get("recommended", []),
            avoid_strategies=strategies.get("avoid", []),
        )
    
    def _score_high_volatility(
        self, vix: float, vix_open: float, net_gex: float,
        straddle_price: float, normal_straddle_price: float
    ) -> tuple[float, list]:
        """
        Score HIGH_VOLATILITY regime.
        
        Criteria:
        - VIX > 18 OR VIX spike > +10% intraday
        - Negative GEX (market makers amplify moves)
        - Straddle price > 1.5x normal
        """
        score = 0.0
        reasons = []
        
        # VIX level
        if vix > 0:
            if vix >= self.VIX_HIGH_THRESHOLD:
                score += 0.35
                reasons.append(f"VIX {vix:.1f} > {self.VIX_HIGH_THRESHOLD}")
            
            # VIX spike
            if vix_open > 0:
                vix_change_pct = (vix - vix_open) / vix_open * 100
                if vix_change_pct >= self.VIX_SPIKE_THRESHOLD:
                    score += 0.30
                    reasons.append(f"VIX spike +{vix_change_pct:.1f}%")
        
        # Negative GEX
        if net_gex < 0:
            score += 0.20
            reasons.append("Negative GEX (destabilizing)")
        
        # Straddle price spike
        if straddle_price > 0 and normal_straddle_price > 0:
            straddle_ratio = straddle_price / normal_straddle_price
            if straddle_ratio >= self.STRADDLE_SPIKE_MULTIPLIER:
                score += 0.15
                reasons.append(f"Straddle {straddle_ratio:.1f}x normal")
        
        return min(1.0, score), reasons
    
    def _score_trending_up(
        self, spot: float, ema_20: float, prev_high: float,
        supertrend_bullish: bool, current_time: datetime
    ) -> tuple[float, list]:
        """
        Score TRENDING_UP regime.
        
        Criteria:
        - Price above 20 EMA on 15-min chart
        - Supertrend bullish
        - NIFTY > previous day high after 10:30 IST
        """
        score = 0.0
        reasons = []
        
        # Price above EMA
        if ema_20 > 0 and spot > ema_20:
            pct_above = (spot - ema_20) / ema_20 * 100
            score += 0.30 + min(0.15, pct_above / 2)
            reasons.append(f"Price {pct_above:.2f}% above 20 EMA")
        
        # Supertrend bullish
        if supertrend_bullish is True:
            score += 0.30
            reasons.append("Supertrend bullish")
        
        # Above previous day high (after 10:30)
        if prev_high > 0 and spot > prev_high:
            is_after_1030 = True
            if current_time:
                is_after_1030 = current_time.time() >= time(10, 30)
            
            if is_after_1030:
                score += 0.25
                reasons.append(f"Above prev day high {prev_high:.0f}")
        
        return min(1.0, score), reasons
    
    def _score_trending_down(
        self, spot: float, ema_20: float, prev_low: float,
        supertrend_bullish: bool
    ) -> tuple[float, list]:
        """
        Score TRENDING_DOWN regime.
        
        Criteria:
        - Price below 20 EMA
        - Supertrend bearish
        - Below previous day low
        """
        score = 0.0
        reasons = []
        
        # Price below EMA
        if ema_20 > 0 and spot < ema_20:
            pct_below = (ema_20 - spot) / ema_20 * 100
            score += 0.35 + min(0.15, pct_below / 2)
            reasons.append(f"Price {pct_below:.2f}% below 20 EMA")
        
        # Supertrend bearish
        if supertrend_bullish is False:
            score += 0.30
            reasons.append("Supertrend bearish")
        
        # Below previous day low
        if prev_low > 0 and spot < prev_low:
            score += 0.25
            reasons.append(f"Below prev day low {prev_low:.0f}")
        
        return min(1.0, score), reasons
    
    def _score_range_bound(
        self, spot: float, vwap: float, net_gex: float, ivr: float
    ) -> tuple[float, list]:
        """
        Score RANGE_BOUND regime.
        
        Criteria:
        - Price oscillating within ±0.3% of VWAP
        - Positive GEX (market makers dampen moves)
        - IVR > 60 is bonus for premium selling
        """
        score = 0.0
        reasons = []
        
        # VWAP proximity
        if vwap > 0:
            vwap_dist_pct = abs(spot - vwap) / vwap * 100
            if vwap_dist_pct <= self.VWAP_RANGE_THRESHOLD:
                score += 0.35
                reasons.append(f"Within {vwap_dist_pct:.2f}% of VWAP")
            elif vwap_dist_pct <= 0.5:
                score += 0.20
                reasons.append(f"Near VWAP ({vwap_dist_pct:.2f}%)")
        
        # Positive GEX
        if net_gex > 0:
            score += 0.30
            reasons.append("Positive GEX (stabilizing)")
        
        # IVR for premium selling
        if ivr >= 60:
            score += 0.15
            reasons.append(f"IVR {ivr:.0f} (premium selling favorable)")
        
        # If nothing suggests trending, default to range
        if not reasons:
            score = 0.25
            reasons.append("No clear trend detected")
        
        return min(1.0, score), reasons
    
    def get_regime_weights(self, regime: MarketRegime) -> dict:
        """
        Get signal weights for aggregation based on regime.
        
        Different regimes weight signals differently for strategy selection.
        """
        if regime == MarketRegime.RANGE_BOUND:
            return {
                "oi_analysis": 0.20,
                "iv_analysis": 0.20,
                "max_pain": 0.15,
                "straddle_pricing": 0.15,
                "greeks_signal": 0.10,
                "price_action": 0.08,
                "technicals": 0.05,
                "vix": 0.07,
            }
        elif regime in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]:
            return {
                "price_action": 0.25,
                "technicals": 0.20,
                "global_cues": 0.15,
                "oi_analysis": 0.15,
                "fii_dii": 0.10,
                "vix": 0.08,
                "iv_analysis": 0.07,
            }
        elif regime == MarketRegime.HIGH_VOLATILITY:
            return {
                "vix": 0.25,
                "news_scanner": 0.20,
                "iv_analysis": 0.20,
                "straddle_pricing": 0.15,
                "greeks_signal": 0.10,
                "oi_analysis": 0.10,
            }
        else:
            # Unknown - equal weights
            return {
                "oi_analysis": 0.12,
                "iv_analysis": 0.12,
                "max_pain": 0.12,
                "price_action": 0.12,
                "technicals": 0.12,
                "global_cues": 0.10,
                "fii_dii": 0.10,
                "straddle_pricing": 0.10,
                "greeks_signal": 0.05,
                "news_scanner": 0.05,
            }
