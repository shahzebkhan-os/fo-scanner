"""
Market Regime Override Filter (Improvement #3)

Enforces regime-specific rules - certain trade types are unsuitable for certain regimes.

Regime Rules:
- TRENDING: Directional CE/PE buys ALLOWED, counter-trend BLOCKED
- PINNED: Directional buys BLOCKED, only option selling strategies allowed
- SQUEEZE: Immediate entry BLOCKED until breakout confirmation
- EXPIRY: OTM options BLOCKED, only ITM/ATM with DTE ≥ 2

Regime alignment: BULLISH signal in BULLISH_TREND gets +5 confidence bonus.
Counter-trend signals are blocked.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass
import logging

log = logging.getLogger(__name__)


class RegimeType(str, Enum):
    """Market regime types (as detected by analytics.py)."""
    TRENDING = "TRENDING"
    PINNED = "PINNED"
    SQUEEZE = "SQUEEZE"
    EXPIRY = "EXPIRY"
    UNKNOWN = "UNKNOWN"


class TrendDirection(str, Enum):
    """Trend direction for TRENDING regime."""
    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeOverrideResult:
    """Result of regime-based filtering."""
    allowed: bool
    reason: str
    score_adjustment: float  # Bonus or penalty to apply
    confidence_adjustment: float  # Adjustment to confidence
    details: dict

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "score_adjustment": self.score_adjustment,
            "confidence_adjustment": self.confidence_adjustment,
            "details": self.details,
        }


class RegimeOverrideFilter:
    """
    Market Regime Override Filter - Blocks signals unsuitable for current regime.

    Usage:
        filter = RegimeOverrideFilter()
        result = filter.apply_override(
            regime="PINNED",
            signal_direction="BULLISH",
            option_delta=0.45,
            ...
        )
        if not result.allowed:
            # Signal is blocked for this regime
    """

    # Score thresholds by regime
    REGIME_SCORE_THRESHOLDS = {
        RegimeType.TRENDING: 75.0,
        RegimeType.PINNED: 999.0,  # Effectively blocks directional signals
        RegimeType.SQUEEZE: 82.0,
        RegimeType.EXPIRY: 80.0,
        RegimeType.UNKNOWN: 75.0,
    }

    def infer_trend_direction(
        self,
        regime: str,
        spot_price: float,
        ema_20: Optional[float] = None,
        prev_close: Optional[float] = None,
    ) -> TrendDirection:
        """
        Infer trend direction from price action when regime is TRENDING.

        Args:
            regime: Market regime string
            spot_price: Current spot price
            ema_20: 20-period EMA
            prev_close: Previous day close

        Returns:
            TrendDirection enum
        """
        if regime != RegimeType.TRENDING.value:
            return TrendDirection.UNKNOWN

        # Use EMA if available
        if ema_20 is not None and ema_20 > 0:
            if spot_price > ema_20:
                return TrendDirection.BULLISH_TREND
            else:
                return TrendDirection.BEARISH_TREND

        # Fallback to previous close
        if prev_close is not None and prev_close > 0:
            if spot_price > prev_close:
                return TrendDirection.BULLISH_TREND
            else:
                return TrendDirection.BEARISH_TREND

        return TrendDirection.UNKNOWN

    def apply_override(
        self,
        regime: str,
        signal_direction: str,
        option_delta: Optional[float],
        days_to_expiry: Optional[int],
        spot_price: Optional[float] = None,
        ema_20: Optional[float] = None,
        prev_close: Optional[float] = None,
        breakout_confirmed: bool = False,
    ) -> RegimeOverrideResult:
        """
        Apply regime-based override rules.

        Args:
            regime: Market regime (TRENDING, PINNED, SQUEEZE, EXPIRY)
            signal_direction: Signal direction (BULLISH, BEARISH, NEUTRAL)
            option_delta: Option delta (for OTM/ITM check)
            days_to_expiry: Days to expiry
            spot_price: Current spot price (for trend detection)
            ema_20: 20-period EMA (for trend detection)
            prev_close: Previous close (for trend detection)
            breakout_confirmed: Whether breakout has been confirmed (for SQUEEZE)

        Returns:
            RegimeOverrideResult with decision
        """
        # Normalize regime string
        regime_normalized = regime.upper() if regime else "UNKNOWN"

        try:
            regime_type = RegimeType(regime_normalized)
        except ValueError:
            regime_type = RegimeType.UNKNOWN

        details = {
            "regime": regime_normalized,
            "signal_direction": signal_direction,
            "option_delta": option_delta,
            "days_to_expiry": days_to_expiry,
        }

        # TRENDING Regime
        if regime_type == RegimeType.TRENDING:
            return self._handle_trending_regime(
                signal_direction,
                spot_price,
                ema_20,
                prev_close,
                details,
            )

        # PINNED Regime
        elif regime_type == RegimeType.PINNED:
            return RegimeOverrideResult(
                allowed=False,
                reason="Market is PINNED - Avoid directional trades. Consider option selling strategies (straddles, strangles).",
                score_adjustment=0.0,
                confidence_adjustment=0.0,
                details=details,
            )

        # SQUEEZE Regime
        elif regime_type == RegimeType.SQUEEZE:
            if not breakout_confirmed:
                return RegimeOverrideResult(
                    allowed=False,
                    reason="SQUEEZE detected - Wait for breakout confirmation (2 candles closing outside squeeze range)",
                    score_adjustment=0.0,
                    confidence_adjustment=0.0,
                    details=details,
                )
            else:
                # After breakout, raise threshold
                return RegimeOverrideResult(
                    allowed=True,
                    reason="SQUEEZE breakout confirmed - Proceed with caution",
                    score_adjustment=0.0,
                    confidence_adjustment=0.0,
                    details={**details, "threshold": self.REGIME_SCORE_THRESHOLDS[RegimeType.SQUEEZE]},
                )

        # EXPIRY Regime
        elif regime_type == RegimeType.EXPIRY:
            return self._handle_expiry_regime(
                option_delta,
                days_to_expiry,
                details,
            )

        # UNKNOWN or default
        else:
            return RegimeOverrideResult(
                allowed=True,
                reason="Regime unknown - Proceed with normal filters",
                score_adjustment=0.0,
                confidence_adjustment=0.0,
                details=details,
            )

    def _handle_trending_regime(
        self,
        signal_direction: str,
        spot_price: Optional[float],
        ema_20: Optional[float],
        prev_close: Optional[float],
        details: dict,
    ) -> RegimeOverrideResult:
        """Handle TRENDING regime logic."""
        # Infer trend direction
        trend_dir = self.infer_trend_direction(
            RegimeType.TRENDING.value,
            spot_price or 0,
            ema_20,
            prev_close,
        )

        details["trend_direction"] = trend_dir.value

        # Check alignment
        if trend_dir == TrendDirection.BULLISH_TREND:
            if signal_direction == "BULLISH":
                # Aligned - give bonus
                return RegimeOverrideResult(
                    allowed=True,
                    reason="Signal aligns with bullish trend",
                    score_adjustment=0.0,
                    confidence_adjustment=0.05,  # +5% confidence boost
                    details=details,
                )
            elif signal_direction == "BEARISH":
                # Counter-trend - block
                return RegimeOverrideResult(
                    allowed=False,
                    reason="Counter-trend signal blocked (Bearish signal in Bullish trend)",
                    score_adjustment=0.0,
                    confidence_adjustment=0.0,
                    details=details,
                )

        elif trend_dir == TrendDirection.BEARISH_TREND:
            if signal_direction == "BEARISH":
                # Aligned - give bonus
                return RegimeOverrideResult(
                    allowed=True,
                    reason="Signal aligns with bearish trend",
                    score_adjustment=0.0,
                    confidence_adjustment=0.05,  # +5% confidence boost
                    details=details,
                )
            elif signal_direction == "BULLISH":
                # Counter-trend - block
                return RegimeOverrideResult(
                    allowed=False,
                    reason="Counter-trend signal blocked (Bullish signal in Bearish trend)",
                    score_adjustment=0.0,
                    confidence_adjustment=0.0,
                    details=details,
                )

        # Trend direction unknown or neutral signal - allow
        return RegimeOverrideResult(
            allowed=True,
            reason="Trend direction unclear - Proceed with caution",
            score_adjustment=0.0,
            confidence_adjustment=0.0,
            details=details,
        )

    def _handle_expiry_regime(
        self,
        option_delta: Optional[float],
        days_to_expiry: Optional[int],
        details: dict,
    ) -> RegimeOverrideResult:
        """Handle EXPIRY regime logic."""
        # Check DTE
        if days_to_expiry is not None and days_to_expiry < 2:
            return RegimeOverrideResult(
                allowed=False,
                reason=f"Same-day/next-day expiry blocked (DTE={days_to_expiry}). Only trades with DTE ≥ 2 allowed.",
                score_adjustment=0.0,
                confidence_adjustment=0.0,
                details=details,
            )

        # Check if OTM (delta < 0.50)
        if option_delta is not None:
            if option_delta < 0.50:
                return RegimeOverrideResult(
                    allowed=False,
                    reason=f"OTM options blocked in EXPIRY regime (delta={option_delta:.2f}). Prefer delta > 0.50.",
                    score_adjustment=0.0,
                    confidence_adjustment=0.0,
                    details=details,
                )

        # ITM/ATM with DTE ≥ 2 - allowed
        return RegimeOverrideResult(
            allowed=True,
            reason="ITM/ATM option with sufficient DTE - Proceed with elevated threshold (80)",
            score_adjustment=0.0,
            confidence_adjustment=0.0,
            details={**details, "threshold": self.REGIME_SCORE_THRESHOLDS[RegimeType.EXPIRY]},
        )


# Singleton instance
_regime_filter = RegimeOverrideFilter()


def get_regime_override_filter() -> RegimeOverrideFilter:
    """Get the singleton regime override filter instance."""
    return _regime_filter
