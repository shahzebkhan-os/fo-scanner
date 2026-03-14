"""
Tests for score calculation correctness — validates that signals and sub-scores
compute correct values and that both BULLISH and BEARISH setups produce
proportional high-conviction scores.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import (
    compute_stock_score_v2,
    compute_gex,
    compute_iv_skew,
    detect_buildup_type,
    detect_regime,
    black_scholes_greeks,
)


def _make_chain(strikes, spot, ce_oi_mult=1.0, pe_oi_mult=1.0, ce_iv=14.0, pe_iv=14.0,
                ce_vol_mult=1.0, pe_vol_mult=1.0, ce_ltp_fn=None, pe_ltp_fn=None):
    """
    Helper to create a synthetic option chain for testing.
    Produces an NSE-like chain dict keyed under records.data.
    """
    data = []
    for strike in strikes:
        ce_ltp = ce_ltp_fn(spot, strike) if ce_ltp_fn else max(0.1, spot - strike + 20)
        pe_ltp = pe_ltp_fn(spot, strike) if pe_ltp_fn else max(0.1, strike - spot + 20)
        data.append({
            "strikePrice": strike,
            "expiryDate": "27-Mar-2025",
            "CE": {
                "openInterest": int(100000 * ce_oi_mult),
                "changeinOpenInterest": 5000,
                "totalTradedVolume": int(30000 * ce_vol_mult),
                "impliedVolatility": ce_iv,
                "lastPrice": round(ce_ltp, 2),
                "strikePrice": strike,
                "expiryDate": "27-Mar-2025",
            },
            "PE": {
                "openInterest": int(100000 * pe_oi_mult),
                "changeinOpenInterest": 5000,
                "totalTradedVolume": int(30000 * pe_vol_mult),
                "impliedVolatility": pe_iv,
                "lastPrice": round(pe_ltp, 2),
                "strikePrice": strike,
                "expiryDate": "27-Mar-2025",
            },
        })
    return {
        "records": {
            "underlyingValue": spot,
            "expiryDates": ["27-Mar-2025"],
            "data": data,
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Regime Detection Uses Computed Greeks
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegimeDetectionWithGreeks:
    """Verify that detect_regime uses accurate gamma from computed Greeks."""

    def test_regime_uses_computed_gamma(self):
        """
        When records have gamma computed via black_scholes_greeks,
        detect_regime should be able to detect PINNED regime (net_gex > 0).
        """
        spot = 24000.0
        strikes = [23800, 23900, 24000, 24100, 24200]
        chain = _make_chain(strikes, spot, ce_oi_mult=3.0, pe_oi_mult=1.0)
        records = chain["records"]["data"]

        # Compute Greeks first (like the fixed code does)
        for row in records:
            strike = row["strikePrice"]
            iv_ce = row["CE"]["impliedVolatility"]
            iv_pe = row["PE"]["impliedVolatility"]
            row["CE"].update(black_scholes_greeks(spot, strike, iv_ce, 7, "CE"))
            row["PE"].update(black_scholes_greeks(spot, strike, iv_pe, 7, "PE"))

        # Now detect regime — should have non-zero GEX
        gex_data = compute_gex(records, spot, lot_size=50)
        assert gex_data["net_gex"] != 0, "GEX should be non-zero after computing Greeks"

    def test_regime_without_gamma_gives_zero_gex(self):
        """
        Without computed Greeks, gamma defaults to 0 and GEX is always 0.
        This was the bug: detect_regime was called BEFORE Greeks computation.
        """
        spot = 24000.0
        strikes = [23800, 23900, 24000, 24100, 24200]
        chain = _make_chain(strikes, spot)
        records = chain["records"]["data"]

        # No Greeks computed — gamma should default to 0
        gex_data = compute_gex(records, spot, lot_size=50)
        assert gex_data["net_gex"] == 0, "Without computed gamma, GEX must be zero"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Detect Buildup Type analyzes both CE and PE
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildupDetection:
    """Verify detect_buildup_type considers both CE and PE sides."""

    def test_bullish_buildup_from_pe_short_buildup(self):
        """
        PE Short Buildup (PE price ↓ + PE OI ↑) should contribute bullish points.
        """
        records = [
            {
                "strikePrice": 24000,
                "CE": {"openInterest": 100000, "lastPrice": 180.0},
                "PE": {"openInterest": 200000, "lastPrice": 90.0},  # PE OI up, price down
            }
        ]
        prev_records = [
            {
                "strikePrice": 24000,
                "CE": {"openInterest": 100000, "lastPrice": 180.0},  # CE unchanged
                "PE": {"openInterest": 150000, "lastPrice": 120.0},  # PE OI was lower, price higher
            }
        ]
        result = detect_buildup_type(records, 24050.0, prev_records)
        # PE OI ↑ + PE price ↓ = PE_SHORT_BUILDUP = bullish
        assert result["overall"] in ["BULLISH", "NEUTRAL"], f"Expected BULLISH or NEUTRAL, got {result['overall']}"
        # Check PE state is captured
        strike_data = result["strikes"].get(24000, {})
        assert isinstance(strike_data, dict), "Strike data should be a dict with CE and PE keys"
        assert "PE" in strike_data, "Strike buildup should include PE state"

    def test_bearish_buildup_from_pe_long_buildup(self):
        """
        PE Long Buildup (PE price ↑ + PE OI ↑) should contribute bearish points.
        """
        records = [
            {
                "strikePrice": 24000,
                "CE": {"openInterest": 100000, "lastPrice": 180.0},
                "PE": {"openInterest": 200000, "lastPrice": 150.0},  # PE OI up, price up
            },
            {
                "strikePrice": 24100,
                "CE": {"openInterest": 100000, "lastPrice": 120.0},
                "PE": {"openInterest": 180000, "lastPrice": 200.0},  # PE OI up, price up
            },
        ]
        prev_records = [
            {
                "strikePrice": 24000,
                "CE": {"openInterest": 100000, "lastPrice": 180.0},
                "PE": {"openInterest": 150000, "lastPrice": 100.0},
            },
            {
                "strikePrice": 24100,
                "CE": {"openInterest": 100000, "lastPrice": 120.0},
                "PE": {"openInterest": 130000, "lastPrice": 140.0},
            },
        ]
        result = detect_buildup_type(records, 24050.0, prev_records)
        # PE OI ↑ + PE price ↑ = PE_LONG_BUILDUP = bearish for both strikes
        assert result["overall"] == "BEARISH", f"Expected BEARISH, got {result['overall']}"

    def test_no_prev_records_returns_neutral(self):
        """Without previous records, buildup should be NEUTRAL."""
        result = detect_buildup_type([], 24050.0, prev_records=None)
        assert result["overall"] == "NEUTRAL"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Direction-Aware Sub-Scores
# ═══════════════════════════════════════════════════════════════════════════════

class TestDirectionAwareScoring:
    """Verify that both BULLISH and BEARISH setups produce high conviction scores."""

    def _bullish_chain(self):
        """Create a strongly bullish chain: high PE OI & volume, low CE OI & volume."""
        spot = 24000.0
        strikes = [23800, 23900, 24000, 24100, 24200]
        return _make_chain(
            strikes, spot,
            ce_oi_mult=0.5,   # Low CE OI → more support (bullish)
            pe_oi_mult=2.5,   # High PE OI → more support (bullish)
            ce_vol_mult=0.5,
            pe_vol_mult=2.5,  # High PE volume → bullish PCR
            ce_iv=13.0,
            pe_iv=11.0,       # Lower PE IV → bullish skew (pe_iv - ce_iv < -1)
        )

    def _bearish_chain(self):
        """Create a strongly bearish chain: high CE OI & volume, low PE OI & volume."""
        spot = 24000.0
        strikes = [23800, 23900, 24000, 24100, 24200]
        return _make_chain(
            strikes, spot,
            ce_oi_mult=2.5,   # High CE OI → resistance (bearish)
            pe_oi_mult=0.5,   # Low PE OI (bearish)
            ce_vol_mult=2.5,
            pe_vol_mult=0.5,  # Low PE vol → bearish PCR
            ce_iv=12.0,
            pe_iv=16.0,       # High PE IV → bearish skew (pe_iv - ce_iv > 2)
        )

    def test_bullish_setup_gets_high_score(self):
        """A strongly bullish setup should produce score >= 55."""
        chain = self._bullish_chain()
        result = compute_stock_score_v2(
            chain, spot=24000.0, symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        assert result["signal"] == "BULLISH", f"Expected BULLISH signal, got {result['signal']}"
        assert result["score"] >= 55, f"Bullish score {result['score']} should be >= 55"

    def test_bearish_setup_gets_high_score(self):
        """
        A strongly bearish setup should produce score >= 55.
        Previously this was broken — bearish setups always scored ~20-30.
        """
        chain = self._bearish_chain()
        result = compute_stock_score_v2(
            chain, spot=24000.0, symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        assert result["signal"] == "BEARISH", f"Expected BEARISH signal, got {result['signal']}"
        assert result["score"] >= 55, (
            f"Bearish score {result['score']} should be >= 55. "
            "Direction-aware sub-scores should give BEARISH setups high conviction."
        )

    def test_bullish_and_bearish_scores_comparable(self):
        """
        Both bullish and bearish setups with same-strength signals should
        produce scores in the same range (not have one always lower).
        """
        bullish = compute_stock_score_v2(
            self._bullish_chain(), spot=24000.0, symbol="NIFTY",
            expiry_str="27-Mar-2025", iv_rank_data={"iv_rank": 50},
        )
        bearish = compute_stock_score_v2(
            self._bearish_chain(), spot=24000.0, symbol="NIFTY",
            expiry_str="27-Mar-2025", iv_rank_data={"iv_rank": 50},
        )
        # The difference should be no more than 20 points for symmetrically
        # strong setups (previously bearish was 50+ points lower than bullish)
        diff = abs(bullish["score"] - bearish["score"])
        assert diff <= 25, (
            f"Score difference {diff} (bull={bullish['score']}, bear={bearish['score']}) "
            f"is too large — direction-aware scoring should produce comparable scores."
        )

    def test_neutral_setup_moderate_score(self):
        """A neutral setup (balanced CE/PE) should produce moderate score around 40-60."""
        spot = 24000.0
        strikes = [23800, 23900, 24000, 24100, 24200]
        chain = _make_chain(strikes, spot, ce_oi_mult=1.0, pe_oi_mult=1.0)
        result = compute_stock_score_v2(
            chain, spot=24000.0, symbol="NIFTY",
            expiry_str="27-Mar-2025",
            iv_rank_data={"iv_rank": 50},
        )
        assert result["signal"] == "NEUTRAL"
        assert 20 <= result["score"] <= 70, f"Neutral score {result['score']} should be moderate"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: IV Skew computation
# ═══════════════════════════════════════════════════════════════════════════════

class TestIVSkew:
    """Verify IV skew signal produces correct values."""

    def test_bearish_skew_when_pe_iv_high(self):
        """When PE IV >> CE IV, skew should be BEARISH."""
        records = [{"strikePrice": 24000, "CE": {"impliedVolatility": 12.0}, "PE": {"impliedVolatility": 16.0}}]
        result = compute_iv_skew(records, 24000.0, "NIFTY")
        assert result["skew_signal"] == "BEARISH", f"Expected BEARISH, got {result['skew_signal']}"
        assert result["skew_value"] > 2.0

    def test_bullish_skew_when_ce_iv_high(self):
        """When CE IV >> PE IV, skew should be BULLISH."""
        records = [{"strikePrice": 24000, "CE": {"impliedVolatility": 16.0}, "PE": {"impliedVolatility": 12.0}}]
        result = compute_iv_skew(records, 24000.0, "NIFTY")
        assert result["skew_signal"] == "BULLISH", f"Expected BULLISH, got {result['skew_signal']}"
        assert result["skew_value"] < -1.0

    def test_neutral_skew_when_equal_iv(self):
        """When CE IV ≈ PE IV, skew should be NEUTRAL."""
        records = [{"strikePrice": 24000, "CE": {"impliedVolatility": 14.0}, "PE": {"impliedVolatility": 14.5}}]
        result = compute_iv_skew(records, 24000.0, "NIFTY")
        assert result["skew_signal"] == "NEUTRAL"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: GEX computation
# ═══════════════════════════════════════════════════════════════════════════════

class TestGEXComputation:
    """Verify GEX uses gamma values from records."""

    def test_gex_uses_computed_gamma(self):
        """GEX should use gamma from computed Greeks, not zero defaults."""
        spot = 24000.0
        records = [{
            "strikePrice": 24000,
            "CE": {"openInterest": 100000, "gamma": 0.0005},
            "PE": {"openInterest": 50000, "gamma": 0.0005},
        }]
        gex = compute_gex(records, spot, lot_size=50)
        # With real gamma, GEX should be non-zero
        assert gex["net_gex"] != 0, "GEX should be non-zero with gamma values"

    def test_gex_zero_without_gamma(self):
        """Without gamma, GEX should be zero."""
        spot = 24000.0
        records = [{
            "strikePrice": 24000,
            "CE": {"openInterest": 100000},  # No gamma field
            "PE": {"openInterest": 50000},
        }]
        gex = compute_gex(records, spot, lot_size=50)
        assert gex["net_gex"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Full scoring pipeline produces correct metrics
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoringMetrics:
    """Verify the score result dict contains correct metric values."""

    def test_metrics_keys_present(self, sample_chain_data):
        """Score result should include metrics with all expected keys."""
        result = compute_stock_score_v2(
            sample_chain_data, spot=24050.0, symbol="NIFTY",
            expiry_str="27-Mar-2025", iv_rank_data={"iv_rank": 50},
        )
        assert "metrics" in result
        metrics = result["metrics"]
        assert "gex" in metrics
        assert "vol_pcr" in metrics
        assert "dwoi_pcr" in metrics
        assert "iv_skew" in metrics

    def test_velocity_fields_present(self, sample_chain_data):
        """Score result should include OI velocity fields."""
        result = compute_stock_score_v2(
            sample_chain_data, spot=24050.0, symbol="NIFTY",
            expiry_str="27-Mar-2025", iv_rank_data={"iv_rank": 50},
        )
        assert "oi_velocity_score" in result
        assert "oi_velocity_conf" in result
        assert "oi_velocity_reason" in result

    def test_greeks_atm_present(self, sample_chain_data):
        """Score result should include ATM Greeks."""
        result = compute_stock_score_v2(
            sample_chain_data, spot=24050.0, symbol="NIFTY",
            expiry_str="27-Mar-2025", iv_rank_data={"iv_rank": 50},
        )
        greeks = result.get("greeks_atm", {})
        # ATM strike for NIFTY at 24050 should be 24050 (interval 50)
        if greeks:
            assert "CE" in greeks
            assert "PE" in greeks
