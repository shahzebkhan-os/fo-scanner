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
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Result container
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TechnicalScore:
    """Output of the technical scoring model."""

    score: int  # 0-100
    direction: str  # BULLISH / BEARISH / NEUTRAL
    direction_strength: str = "UNKNOWN"  # STRONG / WEAK / SIDEWAYS
    directional_edge: float = 0.0  # Net weighted directional bias (-1.0 to +1.0)
    agreement_pct: float = 0.0  # % of weight committed to direction (0.0 to 1.0)
    confidence: float = 0.0  # 0.0-1.0
    indicators: Dict[str, dict] = field(default_factory=dict)
    sub_scores: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "direction": self.direction,
            "direction_strength": self.direction_strength,
            "directional_edge": round(self.directional_edge, 4),
            "agreement_pct": round(self.agreement_pct, 4),
            "confidence": round(self.confidence, 4),
            "indicators": self.indicators,
            "sub_scores": {k: round(v, 4) for k, v in self.sub_scores.items()},
            "reasons": self.reasons,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Indicator weights — now include divergence + supertrend (must sum to 1.0)
# ──────────────────────────────────────────────────────────────────────────────

DIRECTION_THRESHOLD = 0.05          # min |raw_score| to count as directional
MIN_INDICATOR_AGREEMENT = 4         # minimum indicators in same direction (legacy, not used in weighted)
STRONG_DIRECTION_THRESHOLD = 0.15   # 15% weighted edge = STRONG direction
WEAK_DIRECTION_THRESHOLD = 0.05     # 5% weighted edge = WEAK direction
BASE_CONFIDENCE = 0.3               # baseline confidence before agreement
AGREEMENT_WEIGHT = 0.5              # scaling for indicator agreement ratio
STRONG_TREND_ADX = 25               # ADX above this boosts confidence
ADX_CONFIDENCE_BOOST = 0.1          # extra confidence when ADX is strong
DIVERGENCE_CONFIDENCE_BOOST = 0.12  # extra confidence when dual divergence detected

# Default (balanced) weights — 11 indicators, sum = 1.0
WEIGHTS: Dict[str, float] = {
    "rsi": 0.11,
    "macd": 0.15,
    "adx": 0.11,
    "stochastic": 0.07,
    "ema_alignment": 0.11,
    "bollinger": 0.07,
    "volume": 0.08,
    "vwap": 0.04,
    "supertrend": 0.09,
    "divergence": 0.10,
    "ichimoku": 0.07,
}

# Adaptive weight profiles selected by ADX regime
WEIGHTS_TRENDING: Dict[str, float] = {
    "rsi": 0.07,
    "macd": 0.18,
    "adx": 0.11,
    "stochastic": 0.04,
    "ema_alignment": 0.14,
    "bollinger": 0.03,
    "volume": 0.07,
    "vwap": 0.04,
    "supertrend": 0.12,
    "divergence": 0.12,
    "ichimoku": 0.08,
}

WEIGHTS_RANGING: Dict[str, float] = {
    "rsi": 0.15,
    "macd": 0.09,
    "adx": 0.07,
    "stochastic": 0.13,
    "ema_alignment": 0.07,
    "bollinger": 0.13,
    "volume": 0.08,
    "vwap": 0.05,
    "supertrend": 0.05,
    "divergence": 0.12,
    "ichimoku": 0.06,
}


def _get_adaptive_weights(adx_val: float) -> Dict[str, float]:
    """Select weight profile based on ADX trend strength.

    ADX > 30  → strong trend  → favour trend-following indicators
    ADX < 20  → ranging       → favour mean-reversion indicators
    Otherwise → balanced default weights
    """
    if adx_val > 30:
        return WEIGHTS_TRENDING
    if adx_val < 20:
        return WEIGHTS_RANGING
    return WEIGHTS


# ──────────────────────────────────────────────────────────────────────────────
# Direction determination logic
# ──────────────────────────────────────────────────────────────────────────────

def _determine_direction_weighted(
    raw_scores: Dict[str, float],
    weights: Dict[str, float]
) -> tuple:
    """Determine direction using weighted consensus instead of simple voting.

    This addresses the issue where all indicators get equal votes despite having
    different weights (e.g., MACD=20% vs VWAP=5%).

    Returns:
        (direction, strength, agreement_pct, net_edge)
        - direction: "BULLISH", "BEARISH", or "NEUTRAL"
        - strength: "STRONG", "WEAK", or "SIDEWAYS"
        - agreement_pct: Total weighted commitment to direction (0.0-1.0)
        - net_edge: Net directional bias (-1.0 to +1.0)
    """
    # Calculate weighted contributions for bullish and bearish signals
    weighted_bull = sum(
        max(0, raw_scores[k]) * weights[k]
        for k in weights
        if raw_scores.get(k, 0) > DIRECTION_THRESHOLD
    )

    weighted_bear = sum(
        abs(min(0, raw_scores[k])) * weights[k]
        for k in weights
        if raw_scores.get(k, 0) < -DIRECTION_THRESHOLD
    )

    # Net directional edge (range: -1.0 to +1.0)
    net_edge = weighted_bull - weighted_bear

    # Total committed weight (how much is directional vs neutral)
    total_committed = weighted_bull + weighted_bear

    # Determine direction and strength based on net edge
    if net_edge > STRONG_DIRECTION_THRESHOLD:
        direction = "BULLISH"
        strength = "STRONG"
    elif net_edge > WEAK_DIRECTION_THRESHOLD:
        direction = "BULLISH"
        strength = "WEAK"
    elif net_edge < -STRONG_DIRECTION_THRESHOLD:
        direction = "BEARISH"
        strength = "STRONG"
    elif net_edge < -WEAK_DIRECTION_THRESHOLD:
        direction = "BEARISH"
        strength = "WEAK"
    else:
        direction = "NEUTRAL"
        strength = "SIDEWAYS"

    return direction, strength, total_committed, net_edge


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
        log.warning(f"  ⚠️ Insufficient price data for technical score (need ≥20 bars, got {len(closes) if closes else 0})")
        return TechnicalScore(
            score=0,
            direction="NEUTRAL",
            confidence=0.0,
            reasons=[f"Insufficient price data (need ≥20 bars, got {len(closes) if closes else 0})"],
        )

    highs = highs if highs and len(highs) == len(closes) else closes
    lows = lows if lows and len(lows) == len(closes) else closes
    volumes = volumes if volumes and len(volumes) == len(closes) else [0.0] * len(closes)

    # ── Compute individual indicators ────────────────────────────────────
    rsi_val = _rsi(closes, 14)
    rsi_series = _rsi_series(closes, 14)
    macd_line, signal_line, histogram = _macd(closes, 12, 26, 9)
    macd_hist_series = _macd_histogram_series(closes, 12, 26, 9)
    adx_val, plus_di, minus_di = _adx(highs, lows, closes, 14)
    stoch_k, stoch_d = _stochastic(highs, lows, closes, 14, 3)
    ema9, ema21, ema50 = _ema(closes, 9), _ema(closes, 21), _ema(closes, 50)
    bb_upper, bb_middle, bb_lower, bb_pctb = _bollinger(closes, 20, 2.0)
    vol_ratio = _volume_ratio(volumes, 20)
    vwap_dev = _vwap_deviation(closes, volumes)
    st_direction, st_value = _supertrend(highs, lows, closes, 10, 3.0)
    div_score_val, div_type = _detect_divergence(closes, rsi_series, macd_hist_series)
    obv_slope = _obv_slope(closes, volumes, 20)
    cmf_val = _chaikin_money_flow(highs, lows, closes, volumes, 20)
    sr_proximity = _sr_proximity(highs, lows, closes)
    ichi = _ichimoku(highs, lows, closes)

    # ── Select adaptive weights based on ADX regime ──────────────────────
    active_weights = _get_adaptive_weights(adx_val)
    regime = "TRENDING" if adx_val > 30 else "RANGING" if adx_val < 20 else "BALANCED"

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

    # 7. Volume flow (OBV + CMF composite) ---------------------------------
    vol_flow_score, vol_flow_reason = _score_volume_flow(obv_slope, cmf_val, vol_ratio, closes)
    raw_scores["volume"] = vol_flow_score
    indicators["volume"] = {
        "ratio": round(vol_ratio, 2),
        "obv_slope": round(obv_slope, 4),
        "cmf": round(cmf_val, 4),
    }
    if vol_flow_reason:
        reasons.append(vol_flow_reason)

    # 8. VWAP deviation ----------------------------------------------------
    vwap_score, vwap_reason = _score_vwap(vwap_dev)
    raw_scores["vwap"] = vwap_score
    indicators["vwap"] = {"deviation_pct": round(vwap_dev, 4)}
    if vwap_reason:
        reasons.append(vwap_reason)

    # 9. Supertrend --------------------------------------------------------
    st_score, st_reason = _score_supertrend(st_direction, closes[-1], st_value)
    raw_scores["supertrend"] = st_score
    indicators["supertrend"] = {
        "direction": "BULLISH" if st_direction == 1 else "BEARISH",
        "value": round(st_value, 2),
    }
    if st_reason:
        reasons.append(st_reason)

    # 10. Divergence -------------------------------------------------------
    raw_scores["divergence"] = div_score_val
    indicators["divergence"] = {"type": div_type}
    if div_type != "none":
        reasons.append(f"⚡ {div_type.replace('_', ' ').title()} detected")

    # 11. Ichimoku Cloud ---------------------------------------------------
    ichi_score, ichi_reason = _score_ichimoku(ichi, closes[-1])
    raw_scores["ichimoku"] = ichi_score
    indicators["ichimoku"] = {
        "tenkan": round(ichi["tenkan"], 2),
        "kijun": round(ichi["kijun"], 2),
        "senkou_a": round(ichi["senkou_a"], 2),
        "senkou_b": round(ichi["senkou_b"], 2),
        "cloud": ichi["cloud"],
        "position": ichi["position"],
    }
    if ichi_reason:
        reasons.append(ichi_reason)

    # ── Determine direction using ADAPTIVE weighted consensus ────────────
    direction, direction_strength, agreement_pct, net_edge = _determine_direction_weighted(
        raw_scores, active_weights
    )

    # ── Direction-aware sub-scores (0-100) ───────────────────────────────
    sub_scores: Dict[str, float] = {}
    for name, raw in raw_scores.items():
        if direction == "BEARISH":
            # Invert: bearish-aligned (negative raw) → high sub-score
            sub_scores[name] = max(0.0, min(100.0, 50 - raw * 50))
        else:
            # Bullish / neutral: positive raw → high sub-score
            sub_scores[name] = max(0.0, min(100.0, 50 + raw * 50))

    # ── Weighted composite → 0-100 (using adaptive weights) ─────────────
    weighted = sum(sub_scores[k] * active_weights[k] for k in active_weights if k in sub_scores)
    final_score = int(max(0, min(100, weighted)))

    # ── Confidence ───────────────────────────────────────────────────────
    # Base confidence + agreement boost + ADX boost + divergence boost
    confidence = BASE_CONFIDENCE + agreement_pct * AGREEMENT_WEIGHT
    if adx_val > STRONG_TREND_ADX:
        confidence += ADX_CONFIDENCE_BOOST
    # Boost confidence when dual divergence (RSI+MACD) is detected
    if div_type in ("bullish_dual_divergence", "bearish_dual_divergence"):
        confidence += DIVERGENCE_CONFIDENCE_BOOST
    # S/R proximity confidence modifier
    if sr_proximity["near_level"]:
        sr_type = sr_proximity["type"]  # "support" or "resistance"
        if (direction == "BULLISH" and sr_type == "support") or (direction == "BEARISH" and sr_type == "resistance"):
            confidence += 0.12  # Direction aligns with nearby level
            reasons.append(f"📍 Near {sr_type} @ {sr_proximity['level']:.1f} (confirms {direction})")
        elif (direction == "BULLISH" and sr_type == "resistance") or (direction == "BEARISH" and sr_type == "support"):
            confidence -= 0.08  # Direction opposes nearby level
            reasons.append(f"⚠️ Near {sr_type} @ {sr_proximity['level']:.1f} (caution — against {direction})")
    confidence = max(0.0, min(1.0, confidence))

    return TechnicalScore(
        score=final_score,
        direction=direction,
        direction_strength=direction_strength,
        directional_edge=net_edge,
        agreement_pct=agreement_pct,
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


# ──────────────────────────────────────────────────────────────────────────────
# Phase A: New indicator helpers (Supertrend, Divergence, RSI/MACD series)
# ──────────────────────────────────────────────────────────────────────────────

def _rsi_series(closes: List[float], period: int = 14) -> List[float]:
    """Return full RSI series (same length as closes, padded with 50.0)."""
    if len(closes) < period + 1:
        return [50.0] * len(closes)
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(0, c) for c in changes]
    losses = [abs(min(0, c)) for c in changes]
    result = [50.0] * period  # pad first `period` values with neutral
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))
    # `changes` is len(closes)-1, so result will be len(closes)-1.
    # Prepend one 50.0 to match len(closes).
    result.insert(0, 50.0)
    return result[:len(closes)]


def _macd_histogram_series(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> List[float]:
    """Return MACD histogram series (same length as closes, padded with 0.0)."""
    fast_series = _ema_series(closes, fast)
    slow_series = _ema_series(closes, slow)
    macd_series = [
        f - s if f != 0 and s != 0 else 0.0
        for f, s in zip(fast_series, slow_series)
    ]
    valid_macd = [m for m in macd_series if m != 0.0]
    if len(valid_macd) < signal_period:
        return [0.0] * len(closes)
    signal_series = _ema_series(valid_macd, signal_period)
    # Align signal_series back to the full length
    pad_len = len(macd_series) - len(signal_series)
    signal_padded = [0.0] * pad_len + signal_series
    histogram = [m - s for m, s in zip(macd_series, signal_padded)]
    return histogram


def _supertrend(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    atr_period: int = 10,
    multiplier: float = 3.0,
) -> tuple:
    """Supertrend indicator.  Returns (direction, value) for the latest bar.

    direction = +1 (bullish), -1 (bearish)
    value = the supertrend line value
    """
    n = len(closes)
    if n < atr_period + 1:
        return 1, closes[-1] if closes else 0.0

    # Calculate ATR series
    tr_list: List[float] = [0.0]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)

    # Simple ATR via rolling average
    atr_series = [0.0] * n
    if n > atr_period:
        atr_series[atr_period] = sum(tr_list[1:atr_period + 1]) / atr_period
        for i in range(atr_period + 1, n):
            atr_series[i] = (atr_series[i - 1] * (atr_period - 1) + tr_list[i]) / atr_period

    # Compute bands and direction
    upper_band = [0.0] * n
    lower_band = [0.0] * n
    direction = [1] * n
    supertrend = [0.0] * n

    for i in range(atr_period, n):
        hl2 = (highs[i] + lows[i]) / 2
        upper_band[i] = hl2 + multiplier * atr_series[i]
        lower_band[i] = hl2 - multiplier * atr_series[i]

        # Narrow bands (carry forward)
        if i > atr_period:
            if lower_band[i] < lower_band[i - 1] and closes[i - 1] > lower_band[i - 1]:
                lower_band[i] = lower_band[i - 1]
            if upper_band[i] > upper_band[i - 1] and closes[i - 1] < upper_band[i - 1]:
                upper_band[i] = upper_band[i - 1]

        # Direction flip
        if i > atr_period:
            if direction[i - 1] == 1:
                direction[i] = 1 if closes[i] >= lower_band[i] else -1
            else:
                direction[i] = -1 if closes[i] <= upper_band[i] else 1
        else:
            direction[i] = 1 if closes[i] >= lower_band[i] else -1

        supertrend[i] = lower_band[i] if direction[i] == 1 else upper_band[i]

    return direction[-1], supertrend[-1]


def _score_supertrend(direction: int, price: float, st_value: float) -> tuple:
    """Score the Supertrend indicator (−1.0 to +1.0).

    direction +1 = bullish, −1 = bearish.
    Stronger score when price is further from the supertrend line.
    """
    if st_value == 0 or price == 0:
        return 0.0, ""
    dist_pct = abs(price - st_value) / price * 100
    strength = min(1.0, dist_pct / 2.0)  # 2% away = max strength
    if direction == 1:
        score = 0.4 + strength * 0.5  # range: 0.4 — 0.9
        return min(1.0, score), f"Supertrend BULLISH (price {dist_pct:.1f}% above line)"
    else:
        score = -(0.4 + strength * 0.5)
        return max(-1.0, score), f"Supertrend BEARISH (price {dist_pct:.1f}% below line)"


def _find_swing_points(data: List[float], lookback: int = 5) -> tuple:
    """Find the two most recent swing highs and swing lows in a series.

    Returns (swing_highs, swing_lows) where each is a list of
    (index, value) tuples, most recent first.
    """
    highs: List[tuple] = []
    lows: List[tuple] = []
    n = len(data)
    for i in range(lookback, n - 1):
        window_before = data[max(0, i - lookback):i]
        window_after = data[i + 1:min(n, i + lookback + 1)]
        if not window_before or not window_after:
            continue
        # Swing high: higher than both neighbours
        if data[i] >= max(window_before) and data[i] >= max(window_after):
            highs.append((i, data[i]))
        # Swing low: lower than both neighbours
        if data[i] <= min(window_before) and data[i] <= min(window_after):
            lows.append((i, data[i]))

    # Return most recent first
    return highs[-3:] if len(highs) >= 2 else highs, lows[-3:] if len(lows) >= 2 else lows


def _detect_divergence(
    closes: List[float],
    rsi_series: List[float],
    macd_hist_series: List[float],
    lookback: int = 5,
) -> tuple:
    """Detect bullish/bearish divergence between price and RSI/MACD.

    Returns (score, divergence_type) where:
      score: −1.0 to +1.0
      divergence_type: one of
        'bullish_dual_divergence', 'bearish_dual_divergence',
        'bullish_rsi_divergence', 'bearish_rsi_divergence',
        'bullish_macd_divergence', 'bearish_macd_divergence',
        'none'
    """
    n = len(closes)
    if n < 30 or len(rsi_series) < n or len(macd_hist_series) < n:
        return 0.0, "none"

    price_highs, price_lows = _find_swing_points(closes, lookback)
    rsi_highs, rsi_lows = _find_swing_points(rsi_series, lookback)
    macd_highs, macd_lows = _find_swing_points(macd_hist_series, lookback)

    rsi_bull = False
    rsi_bear = False
    macd_bull = False
    macd_bear = False

    # ── Bullish divergence: price LOWER low, indicator HIGHER low ──────
    if len(price_lows) >= 2 and len(rsi_lows) >= 2:
        # Compare the two most recent lows
        p1_idx, p1_val = price_lows[-1]
        p2_idx, p2_val = price_lows[-2]
        r1 = rsi_series[p1_idx] if p1_idx < len(rsi_series) else 50
        r2 = rsi_series[p2_idx] if p2_idx < len(rsi_series) else 50
        if p1_val < p2_val and r1 > r2:
            rsi_bull = True

    if len(price_lows) >= 2:
        p1_idx, p1_val = price_lows[-1]
        p2_idx, p2_val = price_lows[-2]
        m1 = macd_hist_series[p1_idx] if p1_idx < len(macd_hist_series) else 0
        m2 = macd_hist_series[p2_idx] if p2_idx < len(macd_hist_series) else 0
        if p1_val < p2_val and m1 > m2:
            macd_bull = True

    # ── Bearish divergence: price HIGHER high, indicator LOWER high ──
    if len(price_highs) >= 2 and len(rsi_highs) >= 2:
        p1_idx, p1_val = price_highs[-1]
        p2_idx, p2_val = price_highs[-2]
        r1 = rsi_series[p1_idx] if p1_idx < len(rsi_series) else 50
        r2 = rsi_series[p2_idx] if p2_idx < len(rsi_series) else 50
        if p1_val > p2_val and r1 < r2:
            rsi_bear = True

    if len(price_highs) >= 2:
        p1_idx, p1_val = price_highs[-1]
        p2_idx, p2_val = price_highs[-2]
        m1 = macd_hist_series[p1_idx] if p1_idx < len(macd_hist_series) else 0
        m2 = macd_hist_series[p2_idx] if p2_idx < len(macd_hist_series) else 0
        if p1_val > p2_val and m1 < m2:
            macd_bear = True

    # ── Score: dual divergence is strongest ────────────────────────────
    if rsi_bull and macd_bull:
        return 0.9, "bullish_dual_divergence"
    if rsi_bear and macd_bear:
        return -0.9, "bearish_dual_divergence"
    if rsi_bull:
        return 0.5, "bullish_rsi_divergence"
    if rsi_bear:
        return -0.5, "bearish_rsi_divergence"
    if macd_bull:
        return 0.4, "bullish_macd_divergence"
    if macd_bear:
        return -0.4, "bearish_macd_divergence"
    return 0.0, "none"


# ──────────────────────────────────────────────────────────────────────────────
# Phase B: OBV, CMF, Volume Flow Scoring, S/R Proximity
# ──────────────────────────────────────────────────────────────────────────────

def _obv_slope(closes: List[float], volumes: List[float], period: int = 20) -> float:
    """On-Balance Volume slope over the last *period* bars.

    Returns a normalised slope: positive = accumulation, negative = distribution.
    The value is OBV change / (average volume * period) to keep it scale-free.
    """
    n = len(closes)
    if n < period + 1 or len(volumes) < n:
        return 0.0
    # Build OBV for the last `period + 1` bars
    start = n - period - 1
    obv = 0.0
    obv_start = 0.0
    for i in range(start + 1, n):
        if closes[i] > closes[i - 1]:
            obv += volumes[i]
        elif closes[i] < closes[i - 1]:
            obv -= volumes[i]
        if i == start + 1:
            obv_start = obv
    obv_change = obv - obv_start
    avg_vol = sum(volumes[-period:]) / period if period > 0 else 1
    if avg_vol == 0:
        return 0.0
    return obv_change / (avg_vol * period)


def _chaikin_money_flow(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    period: int = 20,
) -> float:
    """Chaikin Money Flow over the last *period* bars.

    CMF = Σ(MF Multiplier × Volume) / Σ(Volume)
    MF Multiplier = ((Close − Low) − (High − Close)) / (High − Low)

    Range: −1.0 to +1.0.  Positive = buying pressure, negative = selling.
    """
    n = len(closes)
    if n < period or len(highs) < n or len(lows) < n or len(volumes) < n:
        return 0.0
    mf_volume_sum = 0.0
    volume_sum = 0.0
    for i in range(n - period, n):
        hl_range = highs[i] - lows[i]
        if hl_range == 0:
            mf_mult = 0.0
        else:
            mf_mult = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / hl_range
        mf_volume_sum += mf_mult * volumes[i]
        volume_sum += volumes[i]
    return mf_volume_sum / volume_sum if volume_sum > 0 else 0.0


def _score_volume_flow(
    obv_slope: float,
    cmf: float,
    vol_ratio: float,
    closes: List[float],
) -> tuple:
    """Composite volume flow score using OBV slope + CMF + volume ratio.

    This replaces the simple _score_volume() with a richer signal.
    """
    score = 0.0
    parts: List[str] = []

    # OBV slope contribution (accumulation / distribution)
    if obv_slope > 0.05:
        score += min(0.35, obv_slope * 3)
        parts.append(f"OBV accumulation ({obv_slope:+.3f})")
    elif obv_slope < -0.05:
        score += max(-0.35, obv_slope * 3)
        parts.append(f"OBV distribution ({obv_slope:+.3f})")

    # CMF contribution (buying / selling pressure)
    if cmf > 0.1:
        score += min(0.35, cmf)
        parts.append(f"CMF buying pressure ({cmf:+.3f})")
    elif cmf < -0.1:
        score += max(-0.35, cmf)
        parts.append(f"CMF selling pressure ({cmf:+.3f})")

    # Volume spike amplifier (from old scorer, but now just an amplifier)
    if vol_ratio >= 2.0 and len(closes) >= 2:
        price_chg = (closes[-1] - closes[-2]) / closes[-2] if closes[-2] > 0 else 0
        if price_chg > 0:
            score += 0.15
        else:
            score -= 0.15
        parts.append(f"Vol spike {vol_ratio:.1f}x")

    score = max(-1.0, min(1.0, score))
    return score, " | ".join(parts) if parts else ""


def _sr_proximity(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    pivot_lookback: int = 50,
    proximity_pct: float = 0.5,
) -> dict:
    """Detect if current price is near a significant support or resistance level.

    Uses two methods:
    1. Classic Pivot Point from the recent high/low/close
    2. Swing High/Low levels over the lookback window

    Returns dict with:
      near_level: bool — True if price is within proximity_pct% of a key level
      type: "support" | "resistance" | None
      level: float — the key level value
      distance_pct: float — how far price is from the level (%)
    """
    n = len(closes)
    result: dict = {"near_level": False, "type": None, "level": 0.0, "distance_pct": 0.0}
    if n < 20:
        return result

    price = closes[-1]
    window = min(pivot_lookback, n)

    # --- Pivot Points (from prior session high/low/close) ---
    recent_high = max(highs[-window:])
    recent_low = min(lows[-window:])
    recent_close = closes[-2] if n >= 2 else price
    pivot = (recent_high + recent_low + recent_close) / 3
    s1 = 2 * pivot - recent_high    # Support 1
    r1 = 2 * pivot - recent_low     # Resistance 1
    s2 = pivot - (recent_high - recent_low)  # Support 2
    r2 = pivot + (recent_high - recent_low)  # Resistance 2

    # --- Swing levels (last N bars highest high, lowest low) ---
    swing_high = max(highs[-window:])
    swing_low = min(lows[-window:])

    # Collect all candidate levels
    levels = [
        ("support", s1),
        ("support", s2),
        ("support", swing_low),
        ("resistance", r1),
        ("resistance", r2),
        ("resistance", swing_high),
        ("support", pivot),
    ]

    # Find the closest level within the proximity threshold
    best_dist = float("inf")
    for level_type, level_val in levels:
        if level_val <= 0:
            continue
        dist_pct = abs(price - level_val) / price * 100
        if dist_pct < proximity_pct and dist_pct < best_dist:
            best_dist = dist_pct
            result["near_level"] = True
            result["type"] = level_type
            result["level"] = level_val
            result["distance_pct"] = round(dist_pct, 3)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Phase C: Ichimoku Cloud
# ──────────────────────────────────────────────────────────────────────────────

def _ichimoku(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
) -> dict:
    """Compute Ichimoku Cloud components.

    Returns a dict with:
      tenkan:    Tenkan-sen (Conversion Line) — (9-period high + low) / 2
      kijun:     Kijun-sen (Base Line) — (26-period high + low) / 2
      senkou_a:  Senkou Span A — (Tenkan + Kijun) / 2
      senkou_b:  Senkou Span B — (52-period high + low) / 2
      cloud:     "green" if senkou_a >= senkou_b, else "red"
      position:  "above" if price > cloud top, "below" if price < cloud bottom, "inside"
    """
    n = len(closes)
    result = {
        "tenkan": 0.0, "kijun": 0.0,
        "senkou_a": 0.0, "senkou_b": 0.0,
        "cloud": "neutral", "position": "inside",
    }
    if n < senkou_b_period:
        # Not enough data — return defaults with current price as tenkan/kijun
        if closes:
            result["tenkan"] = closes[-1]
            result["kijun"] = closes[-1]
            result["senkou_a"] = closes[-1]
            result["senkou_b"] = closes[-1]
        return result

    # Tenkan-sen: (highest high + lowest low) / 2 over tenkan_period
    tenkan_high = max(highs[-tenkan_period:])
    tenkan_low = min(lows[-tenkan_period:])
    tenkan = (tenkan_high + tenkan_low) / 2

    # Kijun-sen: (highest high + lowest low) / 2 over kijun_period
    kijun_high = max(highs[-kijun_period:])
    kijun_low = min(lows[-kijun_period:])
    kijun = (kijun_high + kijun_low) / 2

    # Senkou Span A: (Tenkan + Kijun) / 2
    senkou_a = (tenkan + kijun) / 2

    # Senkou Span B: (highest high + lowest low) / 2 over senkou_b_period
    senkou_b_high = max(highs[-senkou_b_period:])
    senkou_b_low = min(lows[-senkou_b_period:])
    senkou_b = (senkou_b_high + senkou_b_low) / 2

    # Cloud color
    cloud = "green" if senkou_a >= senkou_b else "red"

    # Price position relative to cloud
    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)
    price = closes[-1]
    if price > cloud_top:
        position = "above"
    elif price < cloud_bottom:
        position = "below"
    else:
        position = "inside"

    result["tenkan"] = tenkan
    result["kijun"] = kijun
    result["senkou_a"] = senkou_a
    result["senkou_b"] = senkou_b
    result["cloud"] = cloud
    result["position"] = position
    return result


def _score_ichimoku(ichi: dict, price: float) -> tuple:
    """Score the Ichimoku Cloud with a 5-factor system.

    Factors:
    1. Price vs Cloud position (+/- 0.3)
    2. Cloud color (+/- 0.15)
    3. Tenkan-Kijun cross (+/- 0.2)
    4. Chikou span proxy — price vs 26 bars ago (via kijun) (+/- 0.15)
    5. Distance from cloud — intensity scaling (+/- 0.2)
    """
    tenkan = ichi.get("tenkan", 0)
    kijun = ichi.get("kijun", 0)
    senkou_a = ichi.get("senkou_a", 0)
    senkou_b = ichi.get("senkou_b", 0)
    cloud_color = ichi.get("cloud", "neutral")
    position = ichi.get("position", "inside")

    if tenkan == 0 or kijun == 0:
        return 0.0, ""

    score = 0.0
    parts: List[str] = []

    # 1. Price vs Cloud
    if position == "above":
        score += 0.3
        parts.append("Price above cloud")
    elif position == "below":
        score -= 0.3
        parts.append("Price below cloud")
    else:
        parts.append("Price inside cloud (indecision)")

    # 2. Cloud color (future sentiment)
    if cloud_color == "green":
        score += 0.15
    elif cloud_color == "red":
        score -= 0.15

    # 3. Tenkan-Kijun cross (short-term momentum)
    if tenkan > kijun:
        score += 0.2
        parts.append("TK bullish cross")
    elif tenkan < kijun:
        score -= 0.2
        parts.append("TK bearish cross")

    # 4. Chikou span proxy — price above kijun = bullish lagging confirmation
    if price > kijun * 1.005:
        score += 0.15
    elif price < kijun * 0.995:
        score -= 0.15

    # 5. Distance from cloud — further away = stronger conviction
    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)
    if price > cloud_top and cloud_top > 0:
        dist_pct = (price - cloud_top) / cloud_top * 100
        score += min(0.2, dist_pct * 0.1)
    elif price < cloud_bottom and cloud_bottom > 0:
        dist_pct = (cloud_bottom - price) / cloud_bottom * 100
        score -= min(0.2, dist_pct * 0.1)

    score = max(-1.0, min(1.0, score))
    cloud_emoji = "🟢" if cloud_color == "green" else "🔴" if cloud_color == "red" else "⚪"
    reason = f"Ichimoku {cloud_emoji} {position} cloud | {' | '.join(parts)}"
    return score, reason
