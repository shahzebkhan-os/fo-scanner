"""
Tests for OI Velocity Signal — backend/signals/oi_velocity.py
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from signals.oi_velocity import OiVelocitySignal, VelocityResult

import pytz

IST = pytz.timezone("Asia/Kolkata")


def _make_records(spot, ce_oi=100000, pe_oi=100000):
    """Build a minimal option chain records list with one ATM strike."""
    strike = round(spot / 50) * 50  # Nearest 50
    return [
        {
            "strikePrice": strike,
            "CE": {"openInterest": ce_oi},
            "PE": {"openInterest": pe_oi},
        }
    ]


def _make_records_multi(spot, strikes_data):
    """
    Build records with multiple strikes.
    strikes_data: list of (strike, ce_oi, pe_oi)
    """
    return [
        {
            "strikePrice": s,
            "CE": {"openInterest": ce},
            "PE": {"openInterest": pe},
        }
        for s, ce, pe in strikes_data
    ]


class TestOiVelocitySignal:
    """Tests for OiVelocitySignal."""

    def test_neutral_with_no_history(self):
        """Fresh signal returns score=0.0, confidence=0.0."""
        sig = OiVelocitySignal()
        spot = 24000.0
        records = _make_records(spot)
        result = sig._compute_velocity("NIFTY", records, spot)
        assert result.score == 0.0
        assert result.confidence == 0.0
        assert "insufficient_history" in result.reason

    def test_neutral_with_one_snapshot(self):
        """Single push still returns score=0.0 (need >=2)."""
        sig = OiVelocitySignal()
        spot = 24000.0
        records = _make_records(spot)
        now = datetime.now(IST)
        sig.push_snapshot("NIFTY", records, spot, now)

        result = sig._compute_velocity("NIFTY", records, spot)
        assert result.score == 0.0
        assert result.confidence == 0.0

    def test_bullish_on_ce_spike(self):
        """Push snapshot with CE OI 100k, then 200k over 5 min -> score > 0."""
        sig = OiVelocitySignal()
        spot = 24000.0
        now = datetime.now(IST)

        records1 = _make_records(spot, ce_oi=100000, pe_oi=100000)
        sig.push_snapshot("NIFTY", records1, spot, now - timedelta(minutes=5))

        records2 = _make_records(spot, ce_oi=200000, pe_oi=100000)
        sig.push_snapshot("NIFTY", records2, spot, now)

        result = sig._compute_velocity("NIFTY", records2, spot)
        assert result.score > 0, f"Expected bullish score, got {result.score}"

    def test_bearish_on_pe_spike(self):
        """PE doubles while CE flat -> score < 0."""
        sig = OiVelocitySignal()
        spot = 24000.0
        now = datetime.now(IST)

        records1 = _make_records(spot, ce_oi=100000, pe_oi=100000)
        sig.push_snapshot("NIFTY", records1, spot, now - timedelta(minutes=5))

        records2 = _make_records(spot, ce_oi=100000, pe_oi=200000)
        sig.push_snapshot("NIFTY", records2, spot, now)

        result = sig._compute_velocity("NIFTY", records2, spot)
        assert result.score < 0, f"Expected bearish score, got {result.score}"

    def test_uoa_flagged(self):
        """Push 15 snapshots with +1k OI each, then +400k spike -> is_uoa=True."""
        sig = OiVelocitySignal()
        spot = 24000.0
        base_time = datetime.now(IST) - timedelta(minutes=150)

        # Build 15 snapshots with gradual +1k OI growth
        for i in range(15):
            t = base_time + timedelta(minutes=i * 10)
            records = _make_records(spot, ce_oi=100000 + i * 1000, pe_oi=100000)
            sig.push_snapshot("NIFTY", records, spot, t)

        # Now push a massive spike: +400k CE OI in 10 minutes
        spike_time = base_time + timedelta(minutes=150)
        spike_records = _make_records(spot, ce_oi=100000 + 14 * 1000 + 400000, pe_oi=100000)
        sig.push_snapshot("NIFTY", spike_records, spot, spike_time)

        result = sig._compute_velocity("NIFTY", spike_records, spot)
        assert result.is_uoa, f"Expected UOA to be flagged, reason: {result.reason}"

    def test_score_bounded(self):
        """Any input -> -1.0 <= score <= 1.0."""
        sig = OiVelocitySignal()
        spot = 24000.0
        now = datetime.now(IST)

        # Extreme scenario: massive CE spike
        records1 = _make_records(spot, ce_oi=1, pe_oi=1)
        sig.push_snapshot("NIFTY", records1, spot, now - timedelta(minutes=1))

        records2 = _make_records(spot, ce_oi=10000000, pe_oi=1)
        sig.push_snapshot("NIFTY", records2, spot, now)

        result = sig._compute_velocity("NIFTY", records2, spot)
        assert -1.0 <= result.score <= 1.0, f"Score out of bounds: {result.score}"

    def test_rolling_window_trimmed(self):
        """Push 25 snapshots -> history len stays <= ROLLING_WINDOW."""
        sig = OiVelocitySignal()
        spot = 24000.0
        base_time = datetime.now(IST) - timedelta(minutes=250)

        for i in range(25):
            t = base_time + timedelta(minutes=i * 10)
            records = _make_records(spot, ce_oi=100000 + i * 1000, pe_oi=100000)
            sig.push_snapshot("NIFTY", records, spot, t)

        history = sig._history.get("NIFTY", [])
        assert len(history) <= sig.ROLLING_WINDOW, f"History length {len(history)} exceeds ROLLING_WINDOW {sig.ROLLING_WINDOW}"

    def test_compute_returns_signal_result(self):
        """The compute() method returns a valid SignalResult."""
        sig = OiVelocitySignal()
        spot = 24000.0
        now = datetime.now(IST)

        records1 = _make_records(spot, ce_oi=100000, pe_oi=100000)
        sig.push_snapshot("NIFTY", records1, spot, now - timedelta(minutes=5))

        records2 = _make_records(spot, ce_oi=150000, pe_oi=100000)
        sig.push_snapshot("NIFTY", records2, spot, now)

        result = sig.compute(symbol="NIFTY", records=records2, spot=spot)
        assert hasattr(result, "score")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reason")
        assert -1.0 <= result.score <= 1.0
        assert 0.0 <= result.confidence <= 1.0

    def test_neutral_velocity_when_equal_change(self):
        """Equal CE and PE velocity changes -> near-zero score."""
        sig = OiVelocitySignal()
        spot = 24000.0
        now = datetime.now(IST)

        records1 = _make_records(spot, ce_oi=100000, pe_oi=100000)
        sig.push_snapshot("NIFTY", records1, spot, now - timedelta(minutes=5))

        # Both CE and PE increase equally
        records2 = _make_records(spot, ce_oi=150000, pe_oi=150000)
        sig.push_snapshot("NIFTY", records2, spot, now)

        result = sig._compute_velocity("NIFTY", records2, spot)
        assert abs(result.score) < 0.15, f"Expected near-zero score for equal velocity, got {result.score}"
