"""
signals/engine.py — Master Signal Engine

Computes all 12 signals and aggregates them with regime-based weights.

RANGE_BOUND weights:
  oi_analysis: 0.20, iv_analysis: 0.20, max_pain: 0.15,
  straddle_pricing: 0.15, greeks: 0.10, price_action: 0.08,
  technicals: 0.05, vix: 0.07

TRENDING weights:
  price_action: 0.25, technicals: 0.20, global_cues: 0.15,
  oi_analysis: 0.15, fii_dii: 0.10, vix: 0.08, iv_analysis: 0.07

HIGH_VOLATILITY weights:
  vix: 0.25, news_events: 0.20, iv_analysis: 0.20,
  straddle_pricing: 0.15, greeks: 0.10, oi_analysis: 0.10

AggregatedSignal output:
{
  "composite_score": float,    # -1.0 to +1.0
  "confidence": float,         # 0 to 1
  "regime": str,
  "recommended_strategy": str, # from strategies/ module
  "individual_scores": dict,   # each signal's score and reason
  "trade": bool,               # True if abs(score) >= threshold AND confidence >= 0.6
  "blackout": bool             # True if news_scanner says high-impact event imminent
}

MINIMUM_COMPOSITE_SCORE: 0.45 (configurable)
MINIMUM_CONFIDENCE: 0.60 (configurable)
Do NOT trade if blackout=True
"""

from __future__ import annotations
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

from .base import SignalResult
from .oi_analysis import OiSignal
from .iv_analysis import IvSignal
from .max_pain import MaxPainSignal
from .price_action import PriceActionSignal
from .technicals import TechnicalSignal
from .global_cues import GlobalCuesSignal
from .fii_dii import FiiDiiSignal
from .straddle_pricing import StraddleSignal
from .news_scanner import NewsSignal
from .greeks_signal import GreeksSignal

# Handle import based on package structure
try:
    from ..market.regime import RegimeClassifier, MarketRegime
except ImportError:
    from market.regime import RegimeClassifier, MarketRegime


@dataclass
class AggregatedSignal:
    """
    Output of the Master Signal Engine aggregation.
    
    Contains composite score, confidence, regime, recommendations, and blackout status.
    """
    composite_score: float
    confidence: float
    regime: str
    recommended_strategy: str
    individual_scores: Dict[str, dict]
    trade: bool
    blackout: bool
    size_multiplier: float = 1.0
    regime_strategies: list = field(default_factory=list)
    avoid_strategies: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "composite_score": round(self.composite_score, 4),
            "confidence": round(self.confidence, 4),
            "regime": self.regime,
            "recommended_strategy": self.recommended_strategy,
            "individual_scores": self.individual_scores,
            "trade": self.trade,
            "blackout": self.blackout,
            "size_multiplier": self.size_multiplier,
            "regime_strategies": self.regime_strategies,
            "avoid_strategies": self.avoid_strategies,
            "reasons": self.reasons,
        }


class MasterSignalEngine:
    """
    Master Signal Engine — computes all 12 signals and aggregates them.
    
    Uses regime-based weights for signal aggregation.
    """
    
    # Trade thresholds
    MINIMUM_COMPOSITE_SCORE = 0.45
    MINIMUM_CONFIDENCE = 0.60
    
    # Regime-based weights
    REGIME_WEIGHTS = {
        MarketRegime.RANGE_BOUND: {
            "oi_analysis": 0.20,
            "iv_analysis": 0.20,
            "max_pain": 0.15,
            "straddle_pricing": 0.15,
            "greeks_signal": 0.10,
            "price_action": 0.08,
            "technicals": 0.05,
            "vix": 0.07,
        },
        MarketRegime.TRENDING_UP: {
            "price_action": 0.25,
            "technicals": 0.20,
            "global_cues": 0.15,
            "oi_analysis": 0.15,
            "fii_dii": 0.10,
            "vix": 0.08,
            "iv_analysis": 0.07,
        },
        MarketRegime.TRENDING_DOWN: {
            "price_action": 0.25,
            "technicals": 0.20,
            "global_cues": 0.15,
            "oi_analysis": 0.15,
            "fii_dii": 0.10,
            "vix": 0.08,
            "iv_analysis": 0.07,
        },
        MarketRegime.HIGH_VOLATILITY: {
            "vix": 0.25,
            "news_scanner": 0.20,
            "iv_analysis": 0.20,
            "straddle_pricing": 0.15,
            "greeks_signal": 0.10,
            "oi_analysis": 0.10,
        },
        MarketRegime.UNKNOWN: {
            "oi_analysis": 0.15,
            "iv_analysis": 0.15,
            "max_pain": 0.10,
            "price_action": 0.15,
            "technicals": 0.15,
            "global_cues": 0.10,
            "fii_dii": 0.10,
            "vix": 0.10,
        },
    }
    
    # Strategy recommendations by signal direction and regime
    STRATEGY_MAP = {
        MarketRegime.RANGE_BOUND: {
            "bullish": "iron_condor",
            "bearish": "iron_condor",
            "neutral": "short_straddle",
        },
        MarketRegime.TRENDING_UP: {
            "bullish": "bull_call_spread",
            "bearish": "sell_otm_pe",  # Contrarian
            "neutral": "iron_condor",
        },
        MarketRegime.TRENDING_DOWN: {
            "bullish": "sell_otm_ce",  # Contrarian
            "bearish": "bear_put_spread",
            "neutral": "iron_condor",
        },
        MarketRegime.HIGH_VOLATILITY: {
            "bullish": "long_straddle",
            "bearish": "long_straddle",
            "neutral": "wide_iron_condor",
        },
    }
    
    def __init__(self):
        """Initialize signal instances."""
        self.oi_signal = OiSignal()
        self.iv_signal = IvSignal()
        self.max_pain_signal = MaxPainSignal()
        self.price_action_signal = PriceActionSignal()
        self.technical_signal = TechnicalSignal()
        self.global_cues_signal = GlobalCuesSignal()
        self.fii_dii_signal = FiiDiiSignal()
        self.straddle_signal = StraddleSignal()
        self.news_signal = NewsSignal()
        self.greeks_signal = GreeksSignal()
        self.regime_classifier = RegimeClassifier()
    
    def compute_all_signals(
        self,
        # Market data
        spot: float,
        records: list = None,
        vwap: float = 0.0,
        ema_20: float = 0.0,
        prev_day_high: float = 0.0,
        prev_day_low: float = 0.0,
        prev_close: float = 0.0,
        # Option chain data
        atm_strike: float = 0.0,
        atm_ce_ltp: float = 0.0,
        atm_pe_ltp: float = 0.0,
        pcr: float = 1.0,
        dte: int = 30,
        lot_size: int = 50,
        # IV data
        current_iv: float = 0.0,
        iv_history: list = None,
        vix: float = 0.0,
        vix_history: list = None,
        vix_open: float = 0.0,
        # Technical data
        prices: list = None,
        highs: list = None,
        lows: list = None,
        closes: list = None,
        volumes: list = None,
        supertrend_bullish: bool = None,
        # Global data
        gift_nifty: float = 0.0,
        spx_change_pct: float = 0.0,
        nasdaq_change_pct: float = 0.0,
        dxy: float = 0.0,
        crude_oil: float = 0.0,
        usdinr: float = 0.0,
        # FII/DII data
        fii_net_futures: float = 0.0,
        dii_net: float = 0.0,
        fii_3day_cumulative: float = 0.0,
        # Event data
        events: list = None,
        current_time=None,
        # Historical comparison
        prev_gex: float = None,
        hv20: float = 0.0,
        prev_straddle_price: float = 0.0,
        # Portfolio
        portfolio_positions: list = None,
        # Additional
        symbol: str = "NIFTY",
        **kwargs
    ) -> AggregatedSignal:
        """
        Compute all 12 signals and aggregate them.
        
        Returns:
            AggregatedSignal with composite score and trading decision
        """
        records = records or []
        iv_history = iv_history or []
        vix_history = vix_history or []
        events = events or []
        portfolio_positions = portfolio_positions or []
        
        # First, classify the regime
        regime_result = self.regime_classifier.classify(
            spot=spot,
            vwap=vwap,
            ema_20=ema_20,
            prev_day_high=prev_day_high,
            prev_day_low=prev_day_low,
            supertrend_bullish=supertrend_bullish,
            vix=vix,
            vix_open=vix_open,
            net_gex=prev_gex or 0,
            straddle_price=atm_ce_ltp + atm_pe_ltp,
            ivr=self._get_ivr(current_iv, iv_history),
            current_time=current_time,
        )
        
        regime = regime_result.regime
        
        # Compute individual signals
        individual_results = {}
        
        # 1. OI Analysis (Signal 1)
        individual_results["oi_analysis"] = self.oi_signal.compute(
            records=records,
            spot=spot,
            pcr=pcr,
            symbol=symbol,
        )
        
        # 2. IV Analysis (Signal 2 & 4 - includes VIX)
        individual_results["iv_analysis"] = self.iv_signal.compute(
            current_iv=current_iv,
            iv_history=iv_history,
            vix=vix,
            vix_history=vix_history,
            symbol=symbol,
        )
        
        # Extract VIX-specific signal for separate weighting
        iv_result = individual_results["iv_analysis"]
        vix_score = iv_result.metadata.get("vix_score", 0)
        individual_results["vix"] = SignalResult(
            score=vix_score,
            confidence=iv_result.confidence,
            reason=f"VIX {vix:.1f}" if vix > 0 else "No VIX data",
            metadata={"vix": vix, "vix_flags": iv_result.metadata.get("vix_flags", {})}
        )
        
        # 3. Max Pain & GEX (Signal 3)
        individual_results["max_pain"] = self.max_pain_signal.compute(
            records=records,
            spot=spot,
            lot_size=lot_size,
            dte=dte,
            prev_gex=prev_gex,
        )
        
        # 5. Price Action (Signal 5)
        individual_results["price_action"] = self.price_action_signal.compute(
            spot=spot,
            vwap=vwap,
            prev_close=prev_close,
            prev_high=prev_day_high,
            prev_low=prev_day_low,
            current_time=current_time,
        )
        
        # 6. Technicals (Signal 6)
        individual_results["technicals"] = self.technical_signal.compute(
            closes=closes or prices,
            highs=highs,
            lows=lows,
            volumes=volumes,
            current_price=spot,
        )
        
        # 7. Global Cues (Signal 7)
        individual_results["global_cues"] = self.global_cues_signal.compute(
            gift_nifty=gift_nifty,
            nifty_prev_close=prev_close,
            spx_change_pct=spx_change_pct,
            nasdaq_change_pct=nasdaq_change_pct,
            dxy=dxy,
            crude_oil=crude_oil,
            usdinr=usdinr,
            current_time=current_time,
        )
        
        # 8. FII/DII (Signal 8)
        individual_results["fii_dii"] = self.fii_dii_signal.compute(
            fii_net_futures=fii_net_futures,
            dii_net=dii_net,
            fii_3day_cumulative=fii_3day_cumulative,
        )
        
        # 9. Straddle Pricing (Signal 9)
        individual_results["straddle_pricing"] = self.straddle_signal.compute(
            spot=spot,
            atm_strike=atm_strike,
            atm_ce_ltp=atm_ce_ltp,
            atm_pe_ltp=atm_pe_ltp,
            dte=dte,
            hv20=hv20,
            prev_straddle_price=prev_straddle_price,
        )
        
        # 10. News Scanner (Signal 10)
        individual_results["news_scanner"] = self.news_signal.compute(
            events=events,
            current_time=current_time,
            current_iv=current_iv,
            straddle_price=atm_ce_ltp + atm_pe_ltp,
        )
        
        # 12. Greeks Signal (Signal 12)
        individual_results["greeks_signal"] = self.greeks_signal.compute(
            records=records,
            spot=spot,
            dte=dte,
            lot_size=lot_size,
            portfolio_positions=portfolio_positions,
        )
        
        # Check for blackout from news scanner
        news_result = individual_results["news_scanner"]
        blackout = news_result.metadata.get("blackout", False)
        
        # Get weights for current regime
        weights = self.REGIME_WEIGHTS.get(regime, self.REGIME_WEIGHTS[MarketRegime.UNKNOWN])
        
        # Aggregate signals with weights
        composite_score = 0.0
        weighted_confidence = 0.0
        total_weight = 0.0
        
        for signal_name, weight in weights.items():
            if signal_name in individual_results:
                result = individual_results[signal_name]
                composite_score += result.score * weight
                weighted_confidence += result.confidence * weight
                total_weight += weight
        
        # Normalize by total weight to get weighted average
        if total_weight > 0:
            composite_score = composite_score / total_weight
            weighted_confidence = weighted_confidence / total_weight
        
        # Determine if we should trade
        should_trade = (
            not blackout and
            abs(composite_score) >= self.MINIMUM_COMPOSITE_SCORE and
            weighted_confidence >= self.MINIMUM_CONFIDENCE
        )
        
        # Determine signal direction
        if composite_score >= self.MINIMUM_COMPOSITE_SCORE:
            direction = "bullish"
        elif composite_score <= -self.MINIMUM_COMPOSITE_SCORE:
            direction = "bearish"
        else:
            direction = "neutral"
        
        # Get recommended strategy
        strategy_map = self.STRATEGY_MAP.get(regime, self.STRATEGY_MAP[MarketRegime.RANGE_BOUND])
        recommended_strategy = strategy_map.get(direction, "wait")
        
        # If in blackout, override strategy
        if blackout:
            recommended_strategy = "wait_for_event"
        
        # Compile individual scores for output
        individual_scores = {
            name: {
                "score": round(result.score, 4),
                "confidence": round(result.confidence, 4),
                "reason": result.reason,
            }
            for name, result in individual_results.items()
        }
        
        # Compile reasons
        reasons = []
        for name, result in individual_results.items():
            if abs(result.score) >= 0.3 and result.confidence >= 0.5:
                reasons.append(f"{name}: {result.reason}")
        
        return AggregatedSignal(
            composite_score=composite_score,
            confidence=weighted_confidence,
            regime=regime.value,
            recommended_strategy=recommended_strategy,
            individual_scores=individual_scores,
            trade=should_trade,
            blackout=blackout,
            size_multiplier=regime_result.size_multiplier,
            regime_strategies=regime_result.recommended_strategies,
            avoid_strategies=regime_result.avoid_strategies,
            reasons=reasons[:5],  # Top 5 reasons
        )
    
    def _get_ivr(self, current_iv: float, iv_history: list) -> float:
        """Calculate IV Rank from current IV and history."""
        if not iv_history or current_iv <= 0:
            return 50.0
        
        iv_low = min(iv_history)
        iv_high = max(iv_history)
        
        if iv_high == iv_low:
            return 50.0
        
        ivr = (current_iv - iv_low) / (iv_high - iv_low) * 100
        return max(0, min(100, ivr))
    
    def set_thresholds(
        self,
        min_score: float = None,
        min_confidence: float = None
    ):
        """Update trading thresholds."""
        if min_score is not None:
            self.MINIMUM_COMPOSITE_SCORE = min_score
        if min_confidence is not None:
            self.MINIMUM_CONFIDENCE = min_confidence
