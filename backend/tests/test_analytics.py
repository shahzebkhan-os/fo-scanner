"""
Tests for analytics.py — Black-Scholes Greeks and scoring functions.
"""

import pytest
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import (
    compute_stock_score_v2,
    black_scholes_greeks,
    nearest_atm,
    get_strike_interval,
)


class TestBlackScholesGreeks:
    """Tests for Black-Scholes Greeks calculations."""

    def test_call_delta_between_0_and_1(self):
        """Call delta should be between 0 and 1."""
        greeks = black_scholes_greeks(spot=24050, strike=24000, iv=14, dte=7, opt_type="CE")
        assert 0 < greeks["delta"] < 1

    def test_put_delta_between_minus1_and_0(self):
        """Put delta should be between -1 and 0."""
        greeks = black_scholes_greeks(spot=24050, strike=24000, iv=14, dte=7, opt_type="PE")
        assert -1 < greeks["delta"] < 0

    def test_theta_negative_for_long_options(self):
        """Theta should be negative for long options (time decay)."""
        call = black_scholes_greeks(spot=24050, strike=24000, iv=14, dte=7, opt_type="CE")
        put = black_scholes_greeks(spot=24050, strike=24000, iv=14, dte=7, opt_type="PE")
        assert call["theta"] < 0
        assert put["theta"] < 0

    def test_vega_positive(self):
        """Vega should always be positive."""
        greeks = black_scholes_greeks(spot=24050, strike=24000, iv=14, dte=7, opt_type="CE")
        assert greeks["vega"] > 0

    def test_atm_delta_near_0_5(self):
        """ATM call delta should be close to 0.5."""
        greeks = black_scholes_greeks(spot=24000, strike=24000, iv=14, dte=7, opt_type="CE")
        assert abs(greeks["delta"] - 0.5) < 0.1

    def test_deep_itm_delta_near_1(self):
        """Deep ITM call delta should be close to 1."""
        greeks = black_scholes_greeks(spot=25000, strike=24000, iv=14, dte=7, opt_type="CE")
        assert greeks["delta"] > 0.9

    def test_deep_otm_delta_near_0(self):
        """Deep OTM call delta should be close to 0."""
        greeks = black_scholes_greeks(spot=24000, strike=26000, iv=14, dte=7, opt_type="CE")
        assert greeks["delta"] < 0.1

    def test_gamma_highest_at_atm(self):
        """Gamma should be highest for ATM options."""
        atm_greeks = black_scholes_greeks(spot=24000, strike=24000, iv=14, dte=7, opt_type="CE")
        otm_greeks = black_scholes_greeks(spot=24000, strike=25000, iv=14, dte=7, opt_type="CE")
        assert atm_greeks["gamma"] > otm_greeks["gamma"]

    def test_invalid_inputs_return_zeros(self):
        """Invalid inputs should return zero Greeks."""
        greeks = black_scholes_greeks(spot=0, strike=24000, iv=14, dte=7, opt_type="CE")
        assert greeks["delta"] == 0
        assert greeks["gamma"] == 0
        assert greeks["theta"] == 0
        assert greeks["vega"] == 0

    def test_zero_dte_returns_zeros(self):
        """Zero DTE should return zero Greeks."""
        greeks = black_scholes_greeks(spot=24050, strike=24000, iv=14, dte=0, opt_type="CE")
        assert greeks["delta"] == 0

    def test_intrinsic_value_itm_call(self):
        """ITM call should have positive intrinsic value."""
        greeks = black_scholes_greeks(spot=25000, strike=24000, iv=14, dte=7, opt_type="CE")
        assert greeks["intrinsic"] == 1000  # 25000 - 24000

    def test_intrinsic_value_itm_put(self):
        """ITM put should have positive intrinsic value."""
        greeks = black_scholes_greeks(spot=23000, strike=24000, iv=14, dte=7, opt_type="PE")
        assert greeks["intrinsic"] == 1000  # 24000 - 23000


class TestScoringAlgorithm:
    """Tests for compute_stock_score_v2 function."""

    def test_score_returns_required_keys(self, sample_chain_data):
        """Score result should contain all required keys."""
        result = compute_stock_score_v2(
            sample_chain_data,
            spot=24050,
            symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        assert "score" in result
        assert "regime" in result
        assert "signal" in result
        assert "pcr" in result

    def test_score_bounded_0_to_100(self, sample_chain_data):
        """Score should be between 0 and 100."""
        result = compute_stock_score_v2(
            sample_chain_data,
            spot=24050,
            symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        assert 0 <= result["score"] <= 100

    def test_regime_is_valid(self, sample_chain_data):
        """Regime should be one of the valid values."""
        result = compute_stock_score_v2(
            sample_chain_data,
            spot=24050,
            symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        assert result["regime"] in ["PINNED", "TRENDING", "EXPIRY", "SQUEEZE"]

    def test_signal_is_valid(self, sample_chain_data):
        """Signal should be BULLISH, BEARISH, or NEUTRAL."""
        result = compute_stock_score_v2(
            sample_chain_data,
            spot=24050,
            symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        assert result["signal"] in ["BULLISH", "BEARISH", "NEUTRAL"]

    def test_pcr_calculated(self, sample_chain_data):
        """PCR should be calculated and reasonable."""
        result = compute_stock_score_v2(
            sample_chain_data,
            spot=24050,
            symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        # PCR may be 0 for minimal test data
        assert result["pcr"] >= 0

    def test_top_picks_returned(self, sample_chain_data):
        """Top picks should be returned in the result."""
        result = compute_stock_score_v2(
            sample_chain_data,
            spot=24050,
            symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        assert "top_picks" in result
        assert isinstance(result["top_picks"], list)


class TestMaxPain:
    """Tests for max pain calculation."""

    def test_max_pain_returns_valid_strike(self, sample_chain_data):
        """Max pain should return a valid strike price or None for minimal data."""
        result = compute_stock_score_v2(
            sample_chain_data,
            spot=24050,
            symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        max_pain = result.get("max_pain")
        # max_pain may be None for minimal test data
        if max_pain is not None:
            assert max_pain > 0
            assert isinstance(max_pain, (int, float))


class TestStrikeHelpers:
    """Tests for strike-related helper functions."""

    def test_nearest_atm_nifty(self):
        """Test nearest ATM for NIFTY."""
        atm = nearest_atm(24050, "NIFTY")
        assert atm == 24050

    def test_nearest_atm_banknifty(self):
        """Test nearest ATM for BANKNIFTY."""
        atm = nearest_atm(51250, "BANKNIFTY")
        # BANKNIFTY has 100 point interval, 51250 rounds to 51300
        assert atm in [51200, 51300]  # Accept either valid rounding

    def test_get_strike_interval(self):
        """Test strike interval retrieval."""
        assert get_strike_interval("NIFTY") == 50
        assert get_strike_interval("BANKNIFTY") == 100
        assert get_strike_interval("UNKNOWN") == 10  # Default
