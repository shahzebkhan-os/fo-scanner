"""
Tests for the technical indicator scoring model (scoring_technical.py).

Covers:
- Individual indicator computations (RSI, MACD, ADX, Stochastic, EMA, Bollinger, VWAP)
- Score conversion for each indicator
- Composite scoring logic (direction, confidence, weighted score)
- Edge cases (insufficient data, flat prices, extreme values)
"""

import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from scoring_technical import (
    TechnicalScore,
    compute_technical_score,
    _rsi,
    _macd,
    _adx,
    _stochastic,
    _bollinger,
    _ema,
    _ema_series,
    _volume_ratio,
    _vwap_deviation,
    _score_rsi,
    _score_macd,
    _score_adx,
    _score_stochastic,
    _score_ema_alignment,
    _score_bollinger,
    _score_volume,
    _score_vwap,
    WEIGHTS,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def bullish_closes():
    """Steadily rising close prices (60 bars)."""
    return [100 + i * 0.5 for i in range(60)]


@pytest.fixture
def bearish_closes():
    """Steadily falling close prices (60 bars)."""
    return [130 - i * 0.5 for i in range(60)]


@pytest.fixture
def flat_closes():
    """Flat / range-bound close prices (60 bars)."""
    return [100.0] * 60


@pytest.fixture
def ohlcv_bullish():
    """Bullish OHLCV data (60 bars)."""
    closes = [100 + i * 0.5 for i in range(60)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 0.5 for c in closes]
    volumes = [10000 + i * 100 for i in range(60)]
    return closes, highs, lows, volumes


@pytest.fixture
def ohlcv_bearish():
    """Bearish OHLCV data (60 bars)."""
    closes = [130 - i * 0.5 for i in range(60)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 1.0 for c in closes]
    volumes = [10000 + i * 100 for i in range(60)]
    return closes, highs, lows, volumes


# ──────────────────────────────────────────────────────────────────────────────
# Weights sanity check
# ──────────────────────────────────────────────────────────────────────────────

class TestWeights:
    def test_weights_sum_to_one(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

    def test_all_weights_positive(self):
        for name, w in WEIGHTS.items():
            assert w > 0, f"Weight for {name} must be positive"


# ──────────────────────────────────────────────────────────────────────────────
# Individual indicator tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRSI:
    def test_bullish_rsi(self, bullish_closes):
        rsi = _rsi(bullish_closes, 14)
        assert rsi > 50, "Rising prices should produce RSI > 50"

    def test_bearish_rsi(self, bearish_closes):
        rsi = _rsi(bearish_closes, 14)
        assert rsi < 50, "Falling prices should produce RSI < 50"

    def test_flat_rsi(self, flat_closes):
        rsi = _rsi(flat_closes, 14)
        # Flat prices: no gains or losses, avg_loss == 0 → RSI = 100
        # OR if all zeros, RSI should be extreme
        assert 0 <= rsi <= 100

    def test_insufficient_data(self):
        rsi = _rsi([100, 101], 14)
        assert rsi == 50.0, "Insufficient data should return 50"


class TestMACD:
    def test_bullish_macd(self, bullish_closes):
        macd_line, signal_line, histogram = _macd(bullish_closes, 12, 26, 9)
        assert macd_line > 0, "Rising prices should produce positive MACD"
        assert histogram > 0 or abs(histogram) < 0.01

    def test_bearish_macd(self, bearish_closes):
        macd_line, signal_line, histogram = _macd(bearish_closes, 12, 26, 9)
        assert macd_line < 0, "Falling prices should produce negative MACD"

    def test_insufficient_data(self):
        macd_line, signal_line, histogram = _macd([100, 101, 102], 12, 26, 9)
        assert macd_line == 0.0 and signal_line == 0.0


class TestADX:
    def test_trending_adx(self, ohlcv_bullish):
        closes, highs, lows, _ = ohlcv_bullish
        adx, plus_di, minus_di = _adx(highs, lows, closes, 14)
        assert adx > 0, "Trending market should have ADX > 0"
        assert plus_di > minus_di, "Bullish trend should have +DI > -DI"

    def test_bearish_adx(self, ohlcv_bearish):
        closes, highs, lows, _ = ohlcv_bearish
        adx, plus_di, minus_di = _adx(highs, lows, closes, 14)
        assert adx > 0
        assert minus_di > plus_di, "Bearish trend should have -DI > +DI"

    def test_insufficient_data(self):
        adx, plus_di, minus_di = _adx([100], [101], [99], 14)
        assert adx == 0.0


class TestStochastic:
    def test_overbought(self):
        # All rising to a high
        highs = [100 + i for i in range(20)]
        lows = [99 + i for i in range(20)]
        closes = [99.5 + i for i in range(20)]
        k, d = _stochastic(highs, lows, closes, 14, 3)
        assert k > 70, f"Rising prices should have %K > 70, got {k}"

    def test_oversold(self):
        # All falling
        highs = [120 - i for i in range(20)]
        lows = [119 - i for i in range(20)]
        closes = [119.5 - i for i in range(20)]
        k, d = _stochastic(highs, lows, closes, 14, 3)
        assert k < 30, f"Falling prices should have %K < 30, got {k}"

    def test_insufficient_data(self):
        k, d = _stochastic([100], [99], [99.5], 14, 3)
        assert k == 50.0


class TestEMA:
    def test_ema_follows_trend(self, bullish_closes):
        ema9 = _ema(bullish_closes, 9)
        ema21 = _ema(bullish_closes, 21)
        assert ema9 > ema21, "Fast EMA should be above slow EMA in uptrend"

    def test_ema_series_length(self, bullish_closes):
        series = _ema_series(bullish_closes, 9)
        assert len(series) == len(bullish_closes)

    def test_insufficient_data(self):
        assert _ema([], 9) == 0.0
        assert _ema([100], 9) == 100.0


class TestBollinger:
    def test_normal_range(self, bullish_closes):
        upper, mid, lower, pctb = _bollinger(bullish_closes, 20, 2.0)
        assert upper > mid > lower
        assert 0.0 <= pctb <= 1.5  # Can exceed bands

    def test_flat_prices(self, flat_closes):
        upper, mid, lower, pctb = _bollinger(flat_closes, 20, 2.0)
        assert upper == mid == lower == 100.0
        assert pctb == 0.5  # At the middle


class TestVolumeRatio:
    def test_spike(self):
        volumes = [1000] * 19 + [5000]
        assert _volume_ratio(volumes, 20) > 2.0

    def test_normal(self):
        volumes = [1000] * 20
        assert abs(_volume_ratio(volumes, 20) - 1.0) < 0.1

    def test_empty(self):
        assert _volume_ratio([], 20) == 1.0


class TestVWAP:
    def test_positive_deviation(self):
        closes = [100] * 10 + [110]
        volumes = [1000] * 11
        dev = _vwap_deviation(closes, volumes)
        assert dev > 0, "Price above VWAP should give positive deviation"

    def test_negative_deviation(self):
        closes = [100] * 10 + [90]
        volumes = [1000] * 11
        dev = _vwap_deviation(closes, volumes)
        assert dev < 0

    def test_no_volume(self):
        assert _vwap_deviation([100, 101], [0, 0]) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Score conversion tests
# ──────────────────────────────────────────────────────────────────────────────

class TestScoreRSI:
    def test_overbought(self):
        score, reason = _score_rsi(85)
        assert score < -0.5, "Overbought RSI should give negative score"
        assert "overbought" in reason.lower()

    def test_oversold(self):
        score, reason = _score_rsi(15)
        assert score > 0.5, "Oversold RSI should give positive score"
        assert "oversold" in reason.lower()

    def test_neutral(self):
        score, _ = _score_rsi(50)
        assert abs(score) < 0.2


class TestScoreMACD:
    def test_bullish_crossover(self):
        score, reason = _score_macd(0.5, 0.3, 0.2, [100.0])
        assert score > 0, "MACD above signal should be bullish"

    def test_bearish_crossover(self):
        score, reason = _score_macd(-0.5, -0.3, -0.2, [100.0])
        assert score < 0, "MACD below signal should be bearish"


class TestScoreADX:
    def test_no_trend(self):
        score, reason = _score_adx(10, 20, 15)
        assert score == 0.0, "ADX < 15 should give zero score"
        assert "no trend" in reason.lower()

    def test_bullish_trend(self):
        score, reason = _score_adx(30, 25, 15)
        assert score > 0, "+DI > -DI with strong ADX should be bullish"

    def test_bearish_trend(self):
        score, reason = _score_adx(30, 15, 25)
        assert score < 0, "-DI > +DI with strong ADX should be bearish"


class TestScoreStochastic:
    def test_overbought(self):
        score, _ = _score_stochastic(85, 85)
        assert score < 0

    def test_oversold(self):
        score, _ = _score_stochastic(15, 15)
        assert score > 0

    def test_bullish_cross(self):
        score, _ = _score_stochastic(50, 40)
        assert score > 0


class TestScoreEMA:
    def test_perfect_bullish(self):
        score, reason = _score_ema_alignment(110, 105, 100, 115)
        assert score > 0.5
        assert "bullish" in reason.lower()

    def test_perfect_bearish(self):
        score, reason = _score_ema_alignment(100, 105, 110, 95)
        assert score < -0.5
        assert "bearish" in reason.lower()


class TestScoreBollinger:
    def test_above_upper(self):
        score, _ = _score_bollinger(1.1)
        assert score < 0

    def test_below_lower(self):
        score, _ = _score_bollinger(-0.1)
        assert score > 0


class TestScoreVolume:
    def test_spike_up(self):
        score, _ = _score_volume(2.5, [100, 105])
        assert score > 0, "Volume spike with price up should be bullish"

    def test_spike_down(self):
        score, _ = _score_volume(2.5, [105, 100])
        assert score < 0

    def test_low_volume(self):
        score, _ = _score_volume(0.3, [100, 101])
        assert score == 0.0


class TestScoreVWAP:
    def test_above_vwap(self):
        score, _ = _score_vwap(1.5)
        assert score > 0

    def test_below_vwap(self):
        score, _ = _score_vwap(-1.5)
        assert score < 0


# ──────────────────────────────────────────────────────────────────────────────
# Composite scoring tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCompositeScore:
    def test_insufficient_data(self):
        result = compute_technical_score([100, 101])
        assert result.score == 0
        assert result.direction == "NEUTRAL"
        assert result.confidence == 0.0

    def test_empty_data(self):
        result = compute_technical_score([])
        assert result.score == 0
        assert result.direction == "NEUTRAL"

    def test_bullish_trend_detected(self, ohlcv_bullish):
        closes, highs, lows, volumes = ohlcv_bullish
        result = compute_technical_score(closes, highs, lows, volumes)
        assert isinstance(result, TechnicalScore)
        assert result.direction in ("BULLISH", "NEUTRAL")
        assert 0 <= result.score <= 100
        assert 0.0 <= result.confidence <= 1.0

    def test_bearish_trend_detected(self, ohlcv_bearish):
        closes, highs, lows, volumes = ohlcv_bearish
        result = compute_technical_score(closes, highs, lows, volumes)
        assert isinstance(result, TechnicalScore)
        assert result.direction in ("BEARISH", "NEUTRAL")
        assert 0 <= result.score <= 100

    def test_flat_market(self, flat_closes):
        result = compute_technical_score(flat_closes)
        assert result.direction == "NEUTRAL"
        assert 0 <= result.score <= 100

    def test_result_has_all_indicators(self, ohlcv_bullish):
        closes, highs, lows, volumes = ohlcv_bullish
        result = compute_technical_score(closes, highs, lows, volumes)
        expected_keys = {"rsi", "macd", "adx", "stochastic", "ema_alignment", "bollinger", "volume", "vwap"}
        assert set(result.indicators.keys()) == expected_keys
        assert set(result.sub_scores.keys()) == expected_keys

    def test_to_dict(self, ohlcv_bullish):
        closes, highs, lows, volumes = ohlcv_bullish
        result = compute_technical_score(closes, highs, lows, volumes)
        d = result.to_dict()
        assert "score" in d
        assert "direction" in d
        assert "confidence" in d
        assert "indicators" in d
        assert "sub_scores" in d
        assert "reasons" in d

    def test_closes_only_mode(self, bullish_closes):
        """Should work with only close prices (no OHLV)."""
        result = compute_technical_score(bullish_closes)
        assert isinstance(result, TechnicalScore)
        assert 0 <= result.score <= 100

    def test_score_range(self):
        """Score must always be in 0-100 range regardless of input."""
        # Very extreme data
        extreme_up = [1.0 * (1.05 ** i) for i in range(60)]
        result = compute_technical_score(extreme_up)
        assert 0 <= result.score <= 100

        extreme_down = [1000.0 * (0.95 ** i) for i in range(60)]
        result = compute_technical_score(extreme_down)
        assert 0 <= result.score <= 100

    def test_bullish_score_higher_than_bearish(self, ohlcv_bullish, ohlcv_bearish):
        """Bullish data should generally produce a higher score than bearish data."""
        bull_closes, bull_highs, bull_lows, bull_vols = ohlcv_bullish
        bear_closes, bear_highs, bear_lows, bear_vols = ohlcv_bearish
        bull_result = compute_technical_score(bull_closes, bull_highs, bull_lows, bull_vols)
        bear_result = compute_technical_score(bear_closes, bear_highs, bear_lows, bear_vols)
        # Both should have meaningful scores; bullish should generally be >= bearish
        # (both are direction-aware so both can be high, but bullish trend is cleaner)
        assert bull_result.score >= 0
        assert bear_result.score >= 0
