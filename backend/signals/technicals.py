"""
signals/technicals.py — Technical Indicators Signal (Signal 6)

Indicators:
1. Supertrend (period=10, multiplier=3) → primary trend direction
2. RSI(14): >70 overbought, <30 oversold. Divergence detection.
3. Bollinger Bands(20,2): squeeze (bandwidth < 1%) → volatility expansion imminent
4. EMA crossover: 9 EMA vs. 21 EMA on 5-min chart
5. Volume: current bar volume vs. 20-bar avg volume
6. ATR(14) → dynamic stop-loss calculation

DO NOT USE: MACD (lagging), Stochastic (unreliable for indices)
"""

from __future__ import annotations
from typing import List, Dict, Optional
import math
from .base import BaseSignal, SignalResult


class TechnicalSignal(BaseSignal):
    """
    Technical Indicators Signal — pure price-based analysis.
    
    Uses Supertrend, RSI, Bollinger Bands, EMA crossover, and Volume.
    """
    
    name = "technicals"
    
    # RSI thresholds
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    
    # Bollinger squeeze threshold
    BB_SQUEEZE_THRESHOLD = 0.01  # 1% bandwidth
    
    # Volume spike threshold
    VOLUME_SPIKE_MULTIPLIER = 2.0
    
    def compute(
        self,
        prices: List[float] = None,
        highs: List[float] = None,
        lows: List[float] = None,
        closes: List[float] = None,
        volumes: List[float] = None,
        current_price: float = 0.0,
        timeframe: str = "5min",
        **kwargs
    ) -> SignalResult:
        """
        Compute technical indicators signal.
        
        Args:
            prices: List of close prices (at least 50 bars for meaningful analysis)
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices
            volumes: List of volume values
            current_price: Current price for validation
            timeframe: Chart timeframe (5min, 15min)
            
        Returns:
            SignalResult with technical analysis score
        """
        # Normalize inputs
        if prices is None:
            prices = closes or []
        if closes is None:
            closes = prices
        if not closes or len(closes) < 20:
            return SignalResult(
                score=0.0,
                confidence=0.0,
                reason="Insufficient price data for technical analysis"
            )
        
        # Ensure we have enough data
        if highs is None:
            highs = closes
        if lows is None:
            lows = closes
        if volumes is None:
            volumes = [0] * len(closes)
        
        scores = []
        reasons = []
        metadata = {}
        
        # 1. Supertrend
        st_score, st_reason, st_data = self._compute_supertrend(
            highs, lows, closes, period=10, multiplier=3.0
        )
        scores.append(st_score * 0.25)  # 25% weight
        if st_reason:
            reasons.append(st_reason)
        metadata["supertrend"] = st_data
        
        # 2. RSI
        rsi_score, rsi_reason, rsi_value = self._compute_rsi(closes, period=14)
        scores.append(rsi_score * 0.20)  # 20% weight
        if rsi_reason:
            reasons.append(rsi_reason)
        metadata["rsi"] = rsi_value
        
        # 3. Bollinger Bands
        bb_score, bb_reason, bb_data = self._compute_bollinger_bands(closes, period=20, std=2.0)
        scores.append(bb_score * 0.15)  # 15% weight
        if bb_reason:
            reasons.append(bb_reason)
        metadata["bollinger"] = bb_data
        
        # 4. EMA Crossover
        ema_score, ema_reason, ema_data = self._compute_ema_crossover(
            closes, fast=9, slow=21
        )
        scores.append(ema_score * 0.20)  # 20% weight
        if ema_reason:
            reasons.append(ema_reason)
        metadata["ema"] = ema_data
        
        # 5. Volume Analysis
        vol_score, vol_reason, vol_data = self._compute_volume_signal(
            volumes, closes, period=20
        )
        scores.append(vol_score * 0.10)  # 10% weight
        if vol_reason:
            reasons.append(vol_reason)
        metadata["volume"] = vol_data
        
        # 6. ATR (for metadata/risk calculation)
        atr = self._compute_atr(highs, lows, closes, period=14)
        metadata["atr"] = round(atr, 2)
        metadata["atr_pct"] = round(atr / closes[-1] * 100, 3) if closes[-1] > 0 else 0
        
        # Composite score
        composite_score = sum(scores)
        
        # Confidence based on signal agreement
        bullish_signals = sum(1 for s in [st_score, rsi_score, ema_score] if s > 0)
        bearish_signals = sum(1 for s in [st_score, rsi_score, ema_score] if s < 0)
        signal_agreement = max(bullish_signals, bearish_signals) / 3
        
        confidence = 0.5 + signal_agreement * 0.3
        if bb_data.get("squeeze", False):
            confidence += 0.1  # Squeeze adds conviction
        confidence = min(1.0, confidence)
        
        combined_reason = " | ".join(reasons) if reasons else "Mixed technical signals"
        
        return SignalResult(
            score=composite_score,
            confidence=confidence,
            reason=combined_reason,
            metadata=metadata
        )
    
    def _compute_supertrend(
        self, highs: List[float], lows: List[float], closes: List[float],
        period: int = 10, multiplier: float = 3.0
    ) -> tuple[float, str, dict]:
        """
        Compute Supertrend indicator.
        
        Supertrend uses ATR to create dynamic support/resistance.
        """
        if len(closes) < period + 1:
            return 0.0, "", {}
        
        # Calculate ATR
        atr = self._compute_atr(highs, lows, closes, period)
        
        # Calculate basic upper and lower bands
        hl2 = (highs[-1] + lows[-1]) / 2
        basic_upper = hl2 + multiplier * atr
        basic_lower = hl2 - multiplier * atr
        
        # Simplified Supertrend logic
        current_close = closes[-1]
        prev_close = closes[-2] if len(closes) >= 2 else current_close
        
        # Determine trend
        is_bullish = current_close > basic_lower
        is_bearish = current_close < basic_upper
        
        # More robust: check if price is trending above/below the bands
        recent_closes = closes[-period:]
        above_lower_count = sum(1 for c in recent_closes if c > basic_lower)
        below_upper_count = sum(1 for c in recent_closes if c < basic_upper)
        
        trend_strength = (above_lower_count - below_upper_count) / period
        
        data = {
            "upper_band": round(basic_upper, 2),
            "lower_band": round(basic_lower, 2),
            "trend": "BULLISH" if trend_strength > 0.3 else ("BEARISH" if trend_strength < -0.3 else "NEUTRAL"),
            "strength": round(abs(trend_strength), 2),
        }
        
        if trend_strength > 0.3:
            score = 0.6 + min(0.4, trend_strength)
            reason = f"Supertrend bullish ({data['trend']})"
        elif trend_strength < -0.3:
            score = -0.6 - min(0.4, abs(trend_strength))
            reason = f"Supertrend bearish ({data['trend']})"
        else:
            score = 0.0
            reason = "Supertrend neutral"
        
        return score, reason, data
    
    def _compute_rsi(
        self, closes: List[float], period: int = 14
    ) -> tuple[float, float, float]:
        """
        Compute RSI (Relative Strength Index).
        
        - RSI > 70 → overbought
        - RSI < 30 → oversold
        """
        if len(closes) < period + 1:
            return 0.0, "", 50.0
        
        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        if len(changes) < period:
            return 0.0, "", 50.0
        
        # Calculate average gains and losses
        gains = [max(0, c) for c in changes[-period:]]
        losses = [abs(min(0, c)) for c in changes[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        # Score based on RSI
        if rsi >= self.RSI_OVERBOUGHT:
            score = -0.5 - min(0.3, (rsi - self.RSI_OVERBOUGHT) / 30)
            reason = f"RSI {rsi:.1f} (overbought)"
        elif rsi <= self.RSI_OVERSOLD:
            score = 0.5 + min(0.3, (self.RSI_OVERSOLD - rsi) / 30)
            reason = f"RSI {rsi:.1f} (oversold)"
        elif rsi > 50:
            score = (rsi - 50) / 40 * 0.3
            reason = f"RSI {rsi:.1f} (bullish)"
        else:
            score = (rsi - 50) / 40 * 0.3
            reason = f"RSI {rsi:.1f} (bearish)"
        
        return score, reason, round(rsi, 1)
    
    def _compute_bollinger_bands(
        self, closes: List[float], period: int = 20, std: float = 2.0
    ) -> tuple[float, str, dict]:
        """
        Compute Bollinger Bands.
        
        - Squeeze (bandwidth < 1%) → volatility expansion imminent
        - Price at upper band → overbought
        - Price at lower band → oversold
        """
        if len(closes) < period:
            return 0.0, "", {}
        
        recent = closes[-period:]
        sma = sum(recent) / period
        
        # Standard deviation
        variance = sum((x - sma) ** 2 for x in recent) / period
        std_dev = math.sqrt(variance)
        
        upper_band = sma + std * std_dev
        lower_band = sma - std * std_dev
        
        # Bandwidth as percentage
        bandwidth = (upper_band - lower_band) / sma * 100 if sma > 0 else 0
        
        current = closes[-1]
        
        # Position within bands (0 = lower band, 1 = upper band)
        band_position = (current - lower_band) / (upper_band - lower_band) if upper_band != lower_band else 0.5
        
        data = {
            "upper": round(upper_band, 2),
            "middle": round(sma, 2),
            "lower": round(lower_band, 2),
            "bandwidth": round(bandwidth, 3),
            "position": round(band_position, 3),
            "squeeze": bandwidth < self.BB_SQUEEZE_THRESHOLD * 100,
        }
        
        # Squeeze detection
        if data["squeeze"]:
            score = 0.0  # Neutral during squeeze, but flag it
            reason = f"BB squeeze (bandwidth {bandwidth:.2f}%)"
        elif band_position > 0.95:
            score = -0.4
            reason = f"At BB upper band"
        elif band_position < 0.05:
            score = 0.4
            reason = f"At BB lower band"
        elif band_position > 0.7:
            score = -0.2
            reason = "Near BB upper"
        elif band_position < 0.3:
            score = 0.2
            reason = "Near BB lower"
        else:
            score = 0.0
            reason = "Within BB range"
        
        return score, reason, data
    
    def _compute_ema_crossover(
        self, closes: List[float], fast: int = 9, slow: int = 21
    ) -> tuple[float, str, dict]:
        """
        Compute EMA crossover signal.
        
        - Fast EMA above slow EMA → bullish
        - Fast EMA below slow EMA → bearish
        - Recent crossover → stronger signal
        """
        if len(closes) < slow + 5:
            return 0.0, "", {}
        
        # Calculate EMAs
        fast_ema = self._ema(closes, fast)
        slow_ema = self._ema(closes, slow)
        
        data = {
            "fast_ema": round(fast_ema, 2),
            "slow_ema": round(slow_ema, 2),
            "crossover": "NONE",
        }
        
        diff_pct = (fast_ema - slow_ema) / slow_ema * 100 if slow_ema > 0 else 0
        
        # Check for recent crossover
        prev_fast = self._ema(closes[:-1], fast) if len(closes) > fast + 1 else fast_ema
        prev_slow = self._ema(closes[:-1], slow) if len(closes) > slow + 1 else slow_ema
        
        if prev_fast <= prev_slow and fast_ema > slow_ema:
            data["crossover"] = "BULLISH"
            score = 0.7
            reason = f"EMA bullish crossover ({fast}/{slow})"
        elif prev_fast >= prev_slow and fast_ema < slow_ema:
            data["crossover"] = "BEARISH"
            score = -0.7
            reason = f"EMA bearish crossover ({fast}/{slow})"
        elif fast_ema > slow_ema:
            score = 0.3 + min(0.3, diff_pct / 2)
            reason = f"EMA bullish ({fast} > {slow})"
        else:
            score = -0.3 - min(0.3, abs(diff_pct) / 2)
            reason = f"EMA bearish ({fast} < {slow})"
        
        return score, reason, data
    
    def _compute_volume_signal(
        self, volumes: List[float], closes: List[float], period: int = 20
    ) -> tuple[float, str, dict]:
        """
        Compute volume analysis.
        
        - Volume > 2x avg on breakout → high conviction move
        - Volume declining with price rise → weak rally
        """
        if not volumes or len(volumes) < period:
            return 0.0, "", {}
        
        current_vol = volumes[-1]
        avg_vol = sum(volumes[-period:]) / period if period > 0 else 0
        
        ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        
        data = {
            "current_volume": current_vol,
            "avg_volume": round(avg_vol, 0),
            "ratio": round(ratio, 2),
        }
        
        # Determine price direction
        price_change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 and closes[-2] > 0 else 0
        
        if ratio >= self.VOLUME_SPIKE_MULTIPLIER:
            if price_change > 0:
                score = 0.4  # Strong buying
                reason = f"Volume spike {ratio:.1f}x with price up"
            else:
                score = -0.4  # Strong selling
                reason = f"Volume spike {ratio:.1f}x with price down"
        elif ratio > 1.2:
            score = 0.1 if price_change > 0 else -0.1
            reason = f"Above avg volume ({ratio:.1f}x)"
        elif ratio < 0.7:
            score = 0.0  # Low volume, neutral
            reason = f"Low volume ({ratio:.1f}x avg)"
        else:
            score = 0.0
            reason = "Normal volume"
        
        return score, reason, data
    
    def _compute_atr(
        self, highs: List[float], lows: List[float], closes: List[float], period: int = 14
    ) -> float:
        """Compute Average True Range."""
        if len(closes) < period + 1:
            return 0.0
        
        tr_values = []
        for i in range(1, len(closes)):
            high = highs[i] if i < len(highs) else closes[i]
            low = lows[i] if i < len(lows) else closes[i]
            prev_close = closes[i - 1]
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
        
        if len(tr_values) < period:
            return sum(tr_values) / len(tr_values) if tr_values else 0
        
        return sum(tr_values[-period:]) / period
    
    def _ema(self, data: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if not data or len(data) < period:
            return 0.0
        
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period  # Start with SMA
        
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
