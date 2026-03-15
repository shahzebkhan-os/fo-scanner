"""
scoring_technical.py — Technical Indicator Scoring Model (Experimental)

A separate scoring model using classical technical indicators (RSI, MACD, ADX,
Stochastic, EMA alignment, Bollinger %B, Volume, VWAP) to generate a directional
conviction score for F&O stocks.

This model is kept independent from the primary OI/IV/Greeks scoring model in
analytics.py.  The goal is side-by-side comparison — NOT integration with the
existing ranking pipeline.

Score range  : 0 – 100  (same scale as compute_stock_score_v2)
Direction    : BULLISH / BEARISH / NEUTRAL
Confidence   : 0.0 – 1.0

Required input: OHLCV price bars (at least 60 bars for all indicators to warm up).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Result container
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TechnicalScore:
    """Output of the technical scoring model."""

    score: int  # 0-100
    direction: str  # BULLISH / BEARISH / NEUTRAL
    confidence: float  # 0.0-1.0
    indicators: Dict[str, dict] = field(default_factory=dict)
    sub_scores: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "indicators": self.indicators,
            "sub_scores": {k: round(v, 4) for k, v in self.sub_scores.items()},
            "reasons": self.reasons,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Indicator weights (must sum to 1.0)
# ──────────────────────────────────────────────────────────────────────────────

# Weights are assigned based on each indicator's predictive reliability:
#   MACD (0.20)         — strongest trend-following + momentum confirmation
#   RSI (0.15)          — proven mean-reversion & momentum oscillator
#   ADX (0.15)          — essential trend-strength filter
#   EMA alignment (0.15)— multi-timeframe trend consensus
#   Stochastic (0.10)   — complementary overbought/oversold oscillator
#   Bollinger (0.10)    — volatility + mean-reversion context
#   Volume (0.10)       — confirmation of price moves
#   VWAP (0.05)         — intraday institutional-interest proxy (least weight
#                         because it is most meaningful on intraday data only)
WEIGHTS: Dict[str, float] = {
    "rsi": 0.15,
    "macd": 0.20,
    "adx": 0.15,
    "stochastic": 0.10,
    "ema_alignment": 0.15,
    "bollinger": 0.10,
    "volume": 0.10,
    "vwap": 0.05,
}


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def compute_technical_score(
    closes: List[float],
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
    volumes: Optional[List[float]] = None,
) -> TechnicalScore:
    """Compute the technical indicator score from OHLCV data.

    Parameters
    ----------
    closes : list[float]
        Close prices (oldest → newest).  At least 60 bars recommended.
    highs : list[float] | None
        High prices.  Falls back to *closes* if not provided.
    lows : list[float] | None
        Low prices.  Falls back to *closes* if not provided.
    volumes : list[float] | None
        Volume per bar.  Falls back to zeros if not provided.

    Returns
    -------
    TechnicalScore
    """
    if not closes or len(closes) < 20:
        return TechnicalScore(
            score=0,
            direction="NEUTRAL",
            confidence=0.0,
            reasons=["Insufficient price data (need ≥20 bars)"],
        )

    highs = highs if highs and len(highs) == len(closes) else closes
    lows = lows if lows and len(lows) == len(closes) else closes
    volumes = volumes if volumes and len(volumes) == len(closes) else [0.0] * len(closes)

    # ── Compute individual indicators ────────────────────────────────────
    rsi_val = _rsi(closes, 14)
    macd_line, signal_line, histogram = _macd(closes, 12, 26, 9)
    adx_val, plus_di, minus_di = _adx(highs, lows, closes, 14)
    stoch_k, stoch_d = _stochastic(highs, lows, closes, 14, 3)
    ema9, ema21, ema50 = _ema(closes, 9), _ema(closes, 21), _ema(closes, 50)
    bb_upper, bb_middle, bb_lower, bb_pctb = _bollinger(closes, 20, 2.0)
    vol_ratio = _volume_ratio(volumes, 20)
    vwap_dev = _vwap_deviation(closes, volumes)

    # ── Convert each indicator to a normalised score (−1 … +1) ──────────
    raw_scores: Dict[str, float] = {}
    reasons: List[str] = []
    indicators: Dict[str, dict] = {}

    # 1. RSI ---------------------------------------------------------------
    rsi_score, rsi_reason = _score_rsi(rsi_val)
    raw_scores["rsi"] = rsi_score
    indicators["rsi"] = {"value": round(rsi_val, 2)}
    if rsi_reason:
        reasons.append(rsi_reason)

    # 2. MACD --------------------------------------------------------------
    macd_score, macd_reason = _score_macd(macd_line, signal_line, histogram, closes)
    raw_scores["macd"] = macd_score
    indicators["macd"] = {
        "macd_line": round(macd_line, 4),
        "signal_line": round(signal_line, 4),
        "histogram": round(histogram, 4),
    }
    if macd_reason:
        reasons.append(macd_reason)

    # 3. ADX ---------------------------------------------------------------
    adx_score, adx_reason = _score_adx(adx_val, plus_di, minus_di)
    raw_scores["adx"] = adx_score
    indicators["adx"] = {
        "adx": round(adx_val, 2),
        "plus_di": round(plus_di, 2),
        "minus_di": round(minus_di, 2),
    }
    if adx_reason:
        reasons.append(adx_reason)

    # 4. Stochastic --------------------------------------------------------
    stoch_score, stoch_reason = _score_stochastic(stoch_k, stoch_d)
    raw_scores["stochastic"] = stoch_score
    indicators["stochastic"] = {
        "k": round(stoch_k, 2),
        "d": round(stoch_d, 2),
    }
    if stoch_reason:
        reasons.append(stoch_reason)

    # 5. EMA alignment -----------------------------------------------------
    ema_score, ema_reason = _score_ema_alignment(ema9, ema21, ema50, closes[-1])
    raw_scores["ema_alignment"] = ema_score
    indicators["ema_alignment"] = {
        "ema9": round(ema9, 2),
        "ema21": round(ema21, 2),
        "ema50": round(ema50, 2),
    }
    if ema_reason:
        reasons.append(ema_reason)

    # 6. Bollinger %B ------------------------------------------------------
    bb_score, bb_reason = _score_bollinger(bb_pctb)
    raw_scores["bollinger"] = bb_score
    indicators["bollinger"] = {
        "upper": round(bb_upper, 2),
        "middle": round(bb_middle, 2),
        "lower": round(bb_lower, 2),
        "pctb": round(bb_pctb, 4),
    }
    if bb_reason:
        reasons.append(bb_reason)

    # 7. Volume ratio ------------------------------------------------------
    vol_score, vol_reason = _score_volume(vol_ratio, closes)
    raw_scores["volume"] = vol_score
    indicators["volume"] = {"ratio": round(vol_ratio, 2)}
    if vol_reason:
        reasons.append(vol_reason)

    # 8. VWAP deviation ----------------------------------------------------
    vwap_score, vwap_reason = _score_vwap(vwap_dev)
    raw_scores["vwap"] = vwap_score
    indicators["vwap"] = {"deviation_pct": round(vwap_dev, 4)}
    if vwap_reason:
        reasons.append(vwap_reason)

    # ── Determine direction by majority vote ─────────────────────────────
    bull_count = sum(1 for s in raw_scores.values() if s > 0.05)
    bear_count = sum(1 for s in raw_scores.values() if s < -0.05)

    if bull_count >= 4 and bull_count > bear_count:
        direction = "BULLISH"
    elif bear_count >= 4 and bear_count > bull_count:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    # ── Direction-aware sub-scores (0-100) ───────────────────────────────
    sub_scores: Dict[str, float] = {}
    for name, raw in raw_scores.items():
        if direction == "BEARISH":
            # Invert: bearish-aligned (negative raw) → high sub-score
            sub_scores[name] = max(0.0, min(100.0, 50 - raw * 50))
        else:
            # Bullish / neutral: positive raw → high sub-score
            sub_scores[name] = max(0.0, min(100.0, 50 + raw * 50))

    # ── Weighted composite → 0-100 ──────────────────────────────────────
    weighted = sum(sub_scores[k] * WEIGHTS[k] for k in WEIGHTS)
    final_score = int(max(0, min(100, weighted)))

    # ── Confidence ───────────────────────────────────────────────────────
    total_indicators = len(raw_scores)
    aligned = max(bull_count, bear_count)
    agreement = aligned / total_indicators if total_indicators else 0
    confidence = 0.3 + agreement * 0.5
    # Boost confidence when ADX shows strong trend
    if adx_val > 25:
        confidence += 0.1
    confidence = max(0.0, min(1.0, confidence))

    return TechnicalScore(
        score=final_score,
        direction=direction,
        confidence=confidence,
        indicators=indicators,
        sub_scores=sub_scores,
        reasons=reasons,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Indicator computation helpers (pure math, no external libraries)
# ──────────────────────────────────────────────────────────────────────────────

def _ema(data: List[float], period: int) -> float:
    """Exponential Moving Average of the full series, return latest value."""
    if not data or len(data) < period:
        return data[-1] if data else 0.0
    multiplier = 2 / (period + 1)
    ema = sum(data[:period]) / period
    for price in data[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def _ema_series(data: List[float], period: int) -> List[float]:
    """Return full EMA series (same length as input, padded with 0.0)."""
    if not data or len(data) < period:
        return [0.0] * len(data)
    result = [0.0] * (period - 1)
    sma = sum(data[:period]) / period
    result.append(sma)
    multiplier = 2 / (period + 1)
    ema = sma
    for price in data[period:]:
        ema = (price - ema) * multiplier + ema
        result.append(ema)
    return result


def _rsi(closes: List[float], period: int = 14) -> float:
    """Wilder's RSI."""
    if len(closes) < period + 1:
        return 50.0
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(0, c) for c in changes]
    losses = [abs(min(0, c)) for c in changes]
    # Wilder's smoothing (exponential)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple:
    """MACD line, signal line, histogram (latest values)."""
    fast_series = _ema_series(closes, fast)
    slow_series = _ema_series(closes, slow)
    macd_series = [
        f - s if f != 0 and s != 0 else 0.0
        for f, s in zip(fast_series, slow_series)
    ]
    # Signal line is EMA of MACD series (use only valid portion)
    valid_macd = [m for m in macd_series if m != 0.0]
    if len(valid_macd) < signal_period:
        return 0.0, 0.0, 0.0
    signal_series = _ema_series(valid_macd, signal_period)
    macd_line = macd_series[-1]
    signal_line = signal_series[-1] if signal_series else 0.0
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> tuple:
    """ADX, +DI, −DI (latest values).  Returns (0, 0, 0) on insufficient data."""
    n = len(closes)
    if n < period + 1:
        return 0.0, 0.0, 0.0

    plus_dm_list: List[float] = []
    minus_dm_list: List[float] = []
    tr_list: List[float] = []

    for i in range(1, n):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]
        plus_dm_list.append(max(high_diff, 0) if high_diff > low_diff else 0)
        minus_dm_list.append(max(low_diff, 0) if low_diff > high_diff else 0)
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)

    if len(tr_list) < period:
        return 0.0, 0.0, 0.0

    # Wilder's smoothing for TR, +DM, −DM
    atr = sum(tr_list[:period]) / period
    plus_dm_smooth = sum(plus_dm_list[:period]) / period
    minus_dm_smooth = sum(minus_dm_list[:period]) / period

    dx_values: List[float] = []
    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        plus_dm_smooth = (plus_dm_smooth * (period - 1) + plus_dm_list[i]) / period
        minus_dm_smooth = (minus_dm_smooth * (period - 1) + minus_dm_list[i]) / period

        plus_di = (plus_dm_smooth / atr * 100) if atr > 0 else 0
        minus_di = (minus_dm_smooth / atr * 100) if atr > 0 else 0
        di_sum = plus_di + minus_di
        dx = abs(plus_di - minus_di) / di_sum * 100 if di_sum > 0 else 0
        dx_values.append(dx)

    if not dx_values:
        return 0.0, 0.0, 0.0

    # ADX = smoothed average of DX
    if len(dx_values) >= period:
        adx = sum(dx_values[:period]) / period
        for dx in dx_values[period:]:
            adx = (adx * (period - 1) + dx) / period
    else:
        adx = sum(dx_values) / len(dx_values)

    # Final +DI / −DI
    final_plus_di = (plus_dm_smooth / atr * 100) if atr > 0 else 0
    final_minus_di = (minus_dm_smooth / atr * 100) if atr > 0 else 0

    return adx, final_plus_di, final_minus_di


def _stochastic(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple:
    """%K and %D values."""
    if len(closes) < k_period:
        return 50.0, 50.0

    k_values: List[float] = []
    for i in range(k_period - 1, len(closes)):
        window_high = max(highs[i - k_period + 1: i + 1])
        window_low = min(lows[i - k_period + 1: i + 1])
        if window_high == window_low:
            k_values.append(50.0)
        else:
            k_values.append((closes[i] - window_low) / (window_high - window_low) * 100)

    if len(k_values) < d_period:
        return k_values[-1] if k_values else 50.0, 50.0

    # %D = SMA of %K
    d_value = sum(k_values[-d_period:]) / d_period
    return k_values[-1], d_value


def _bollinger(
    closes: List[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple:
    """Upper band, middle (SMA), lower band, %B."""
    if len(closes) < period:
        mid = closes[-1] if closes else 0
        return mid, mid, mid, 0.5

    recent = closes[-period:]
    sma = sum(recent) / period
    variance = sum((x - sma) ** 2 for x in recent) / period
    std = math.sqrt(variance)
    upper = sma + num_std * std
    lower = sma - num_std * std
    pctb = (closes[-1] - lower) / (upper - lower) if upper != lower else 0.5
    return upper, sma, lower, pctb


def _volume_ratio(volumes: List[float], period: int = 20) -> float:
    """Current volume / average volume over *period* bars."""
    if not volumes or len(volumes) < 2:
        return 1.0
    avg = sum(volumes[-period:]) / min(period, len(volumes)) if volumes else 1
    return volumes[-1] / avg if avg > 0 else 1.0


def _vwap_deviation(closes: List[float], volumes: List[float]) -> float:
    """Percent deviation of last close from session VWAP."""
    if not closes or not volumes or len(closes) != len(volumes):
        return 0.0
    cum_pv = 0.0
    cum_vol = 0.0
    for c, v in zip(closes, volumes):
        cum_pv += c * v
        cum_vol += v
    vwap = cum_pv / cum_vol if cum_vol > 0 else closes[-1]
    return ((closes[-1] - vwap) / vwap * 100) if vwap > 0 else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Indicator → raw score mapping  (−1.0 to +1.0)
# ──────────────────────────────────────────────────────────────────────────────

def _score_rsi(rsi: float) -> tuple:
    """Convert RSI value to a directional score.

    * >70  overbought → bearish
    * <30  oversold   → bullish
    * 40-60  neutral zone
    """
    if rsi >= 80:
        return -0.8, f"RSI {rsi:.1f} (strongly overbought)"
    if rsi >= 70:
        return -0.5 - (rsi - 70) / 20, f"RSI {rsi:.1f} (overbought)"
    if rsi <= 20:
        return 0.8, f"RSI {rsi:.1f} (strongly oversold)"
    if rsi <= 30:
        return 0.5 + (30 - rsi) / 20, f"RSI {rsi:.1f} (oversold)"
    if rsi > 55:
        return (rsi - 55) / 30, f"RSI {rsi:.1f} (bullish momentum)"
    if rsi < 45:
        return (rsi - 45) / 30, f"RSI {rsi:.1f} (bearish momentum)"
    return 0.0, ""


def _score_macd(macd_line: float, signal_line: float, histogram: float, closes: List[float]) -> tuple:
    """Score MACD based on crossover, histogram slope, and divergence."""
    if macd_line == 0 and signal_line == 0:
        return 0.0, ""
    # Normalise histogram relative to recent price
    price = closes[-1] if closes else 1
    norm_hist = histogram / price * 100 if price > 0 else 0

    score = 0.0
    parts: List[str] = []

    # Crossover direction
    if macd_line > signal_line:
        score += 0.4
        parts.append("MACD above signal")
    elif macd_line < signal_line:
        score -= 0.4
        parts.append("MACD below signal")

    # Histogram momentum (rising / falling)
    if norm_hist > 0:
        score += min(0.3, norm_hist * 2)
        parts.append(f"histogram +{norm_hist:.3f}%")
    elif norm_hist < 0:
        score += max(-0.3, norm_hist * 2)
        parts.append(f"histogram {norm_hist:.3f}%")

    # Zero-line cross
    if macd_line > 0 and signal_line > 0:
        score += 0.2
    elif macd_line < 0 and signal_line < 0:
        score -= 0.2

    score = max(-1.0, min(1.0, score))
    return score, " | ".join(parts) if parts else ""


def _score_adx(adx: float, plus_di: float, minus_di: float) -> tuple:
    """ADX measures trend strength; DI lines give direction."""
    if adx < 15:
        return 0.0, f"ADX {adx:.0f} (no trend)"
    direction_factor = 1 if plus_di > minus_di else -1
    strength = min(1.0, (adx - 15) / 35)  # 15→0, 50→1
    score = direction_factor * strength * 0.8
    label = "bullish" if direction_factor > 0 else "bearish"
    return score, f"ADX {adx:.0f} ({label}, +DI {plus_di:.0f} / −DI {minus_di:.0f})"


def _score_stochastic(k: float, d: float) -> tuple:
    """Stochastic %K/%D scoring with crossover detection."""
    if k > 80 and d > 80:
        return -0.5, f"Stoch overbought (%K {k:.0f})"
    if k < 20 and d < 20:
        return 0.5, f"Stoch oversold (%K {k:.0f})"
    # Crossover signal
    if k > d and k < 80:
        return 0.3, f"Stoch bullish cross (%K {k:.0f} > %D {d:.0f})"
    if k < d and k > 20:
        return -0.3, f"Stoch bearish cross (%K {k:.0f} < %D {d:.0f})"
    return 0.0, ""


def _score_ema_alignment(ema9: float, ema21: float, ema50: float, price: float) -> tuple:
    """Score based on EMA stack order and price position."""
    if ema9 == 0 or ema21 == 0 or ema50 == 0:
        return 0.0, ""
    # Perfect bullish alignment: price > EMA9 > EMA21 > EMA50
    if price > ema9 > ema21 > ema50:
        return 0.8, "Perfect bullish EMA alignment"
    # Perfect bearish alignment: price < EMA9 < EMA21 < EMA50
    if price < ema9 < ema21 < ema50:
        return -0.8, "Perfect bearish EMA alignment"
    # Partial bullish
    if ema9 > ema21:
        return 0.3, "EMA9 > EMA21 (bullish)"
    # Partial bearish
    if ema9 < ema21:
        return -0.3, "EMA9 < EMA21 (bearish)"
    return 0.0, "EMAs converging"


def _score_bollinger(pctb: float) -> tuple:
    """Score Bollinger %B — contrarian at extremes, trend-following mid-range."""
    if pctb > 1.0:
        return -0.4, f"BB %B {pctb:.2f} (above upper band)"
    if pctb < 0.0:
        return 0.4, f"BB %B {pctb:.2f} (below lower band)"
    if pctb > 0.8:
        return -0.2, f"BB %B {pctb:.2f} (near upper)"
    if pctb < 0.2:
        return 0.2, f"BB %B {pctb:.2f} (near lower)"
    if pctb > 0.5:
        return 0.1, f"BB %B {pctb:.2f} (upper half)"
    return -0.1, f"BB %B {pctb:.2f} (lower half)"


def _score_volume(ratio: float, closes: List[float]) -> tuple:
    """Volume confirmation scoring."""
    if ratio < 0.5:
        return 0.0, f"Low volume ({ratio:.1f}x avg)"
    price_change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 and closes[-2] > 0 else 0
    if ratio >= 2.0:
        if price_change > 0:
            return 0.5, f"Volume spike {ratio:.1f}x with price up"
        return -0.5, f"Volume spike {ratio:.1f}x with price down"
    if ratio >= 1.3:
        if price_change > 0:
            return 0.2, f"Above avg volume ({ratio:.1f}x), price up"
        return -0.2, f"Above avg volume ({ratio:.1f}x), price down"
    return 0.0, ""


def _score_vwap(deviation_pct: float) -> tuple:
    """VWAP deviation scoring — price above VWAP is bullish."""
    if deviation_pct > 1.0:
        return 0.5, f"Price {deviation_pct:.2f}% above VWAP"
    if deviation_pct > 0.3:
        return 0.2, f"Price {deviation_pct:.2f}% above VWAP"
    if deviation_pct < -1.0:
        return -0.5, f"Price {deviation_pct:.2f}% below VWAP"
    if deviation_pct < -0.3:
        return -0.2, f"Price {deviation_pct:.2f}% below VWAP"
    return 0.0, ""
