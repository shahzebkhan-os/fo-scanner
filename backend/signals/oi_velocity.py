"""
OI Change Velocity Signal

Measures the rate of OI change per minute at each strike.
A velocity spike (> 2x rolling average) at an ATM or near-ATM strike
indicates unusual options activity — likely institutional positioning.

Score: -1.0 (heavy put velocity) to +1.0 (heavy call velocity)
Confidence: scales with how extreme the spike is vs rolling mean.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pytz

from .base import BaseSignal, SignalResult

IST = pytz.timezone("Asia/Kolkata")


@dataclass
class VelocityResult:
    score: float  # -1.0 to +1.0
    confidence: float  # 0.0 to 1.0
    reason: str
    top_strike: Optional[int] = None
    top_ce_velocity: float = 0.0
    top_pe_velocity: float = 0.0
    is_uoa: bool = False  # True if spike > UOA_THRESHOLD x rolling avg


UOA_THRESHOLD = 2.0  # Velocity must be 2x rolling average to flag UOA
ATM_BAND_PCT = 0.015  # Only measure velocity within +/-1.5% of spot


class OiVelocitySignal(BaseSignal):
    """
    Requires at least 2 snapshots to compute velocity.
    Maintains a rolling window of per-strike OI snapshots.
    """

    name = "oi_velocity"
    ROLLING_WINDOW = 20  # Number of snapshots for rolling average

    def __init__(self):
        # Per-symbol rolling history: {symbol: [(timestamp, {strike: {ce, pe}}, spot), ...]}
        self._history: dict[str, list] = {}

    def push_snapshot(self, symbol: str, records: list, spot: float, timestamp: datetime):
        """
        Call this every time a fresh option chain arrives.
        Stores per-strike OI keyed by timestamp.
        """
        oi_map = {}
        for row in records:
            strike = row.get("strikePrice", 0)
            # Only store strikes within ATM_BAND_PCT * 3 of spot (reduces memory)
            if spot <= 0:
                continue
            if abs(strike - spot) / spot > ATM_BAND_PCT * 3:
                continue
            oi_map[strike] = {
                "ce": (row.get("CE") or {}).get("openInterest", 0) or 0,
                "pe": (row.get("PE") or {}).get("openInterest", 0) or 0,
            }

        if symbol not in self._history:
            self._history[symbol] = []

        self._history[symbol].append((timestamp, oi_map, spot))

        # Keep only last ROLLING_WINDOW snapshots
        if len(self._history[symbol]) > self.ROLLING_WINDOW:
            self._history[symbol].pop(0)

    def compute(self, symbol: str = "", records: list = None, spot: float = 0.0, **kwargs) -> SignalResult:
        """
        Compute OI velocity signal from stored history.
        Returns neutral result if insufficient history (< 2 snapshots).
        """
        velocity = self._compute_velocity(symbol, records, spot)

        return SignalResult(
            score=velocity.score,
            confidence=velocity.confidence,
            reason=velocity.reason,
            metadata={
                "top_strike": velocity.top_strike,
                "top_ce_velocity": velocity.top_ce_velocity,
                "top_pe_velocity": velocity.top_pe_velocity,
                "is_uoa": velocity.is_uoa,
            },
        )

    def _compute_velocity(self, symbol: str, records: list, spot: float) -> VelocityResult:
        """
        Core velocity computation returning VelocityResult.
        """
        history = self._history.get(symbol, [])

        if len(history) < 2:
            return VelocityResult(
                score=0.0,
                confidence=0.0,
                reason="insufficient_history (need >=2 snapshots)",
            )

        # Current and previous snapshots
        curr_ts, curr_oi, curr_spot = history[-1]
        prev_ts, prev_oi, _ = history[-2]

        elapsed_minutes = max((curr_ts - prev_ts).total_seconds() / 60, 0.1)

        # ATM strikes = within +/-1.5% of current spot
        atm_strikes = [s for s in curr_oi if spot > 0 and abs(s - spot) / spot <= ATM_BAND_PCT]

        if not atm_strikes:
            return VelocityResult(
                score=0.0,
                confidence=0.0,
                reason="no_atm_strikes_in_band",
            )

        # Compute per-strike velocity (OI change / minute)
        ce_velocities = {}
        pe_velocities = {}

        for strike in atm_strikes:
            curr = curr_oi.get(strike, {"ce": 0, "pe": 0})
            prev = prev_oi.get(strike, {"ce": 0, "pe": 0})

            ce_velocities[strike] = (curr["ce"] - prev["ce"]) / elapsed_minutes
            pe_velocities[strike] = (curr["pe"] - prev["pe"]) / elapsed_minutes

        # Rolling average velocity across all history
        all_ce_v, all_pe_v = [], []
        for i in range(1, len(history)):
            t1, oi1, _ = history[i]
            t0, oi0, _ = history[i - 1]
            dt = max((t1 - t0).total_seconds() / 60, 0.1)
            for s in atm_strikes:
                if s in oi1 and s in oi0:
                    all_ce_v.append(abs(oi1[s]["ce"] - oi0[s]["ce"]) / dt)
                    all_pe_v.append(abs(oi1[s]["pe"] - oi0[s]["pe"]) / dt)

        rolling_ce_mean = float(np.mean(all_ce_v)) if all_ce_v else 0.0
        rolling_pe_mean = float(np.mean(all_pe_v)) if all_pe_v else 0.0

        # Need meaningful rolling history to compute spike ratios
        if rolling_ce_mean == 0.0 and rolling_pe_mean == 0.0:
            return VelocityResult(
                score=0.0,
                confidence=0.0,
                reason="insufficient_rolling_history",
            )

        # Find strike with maximum velocity
        top_ce_strike = max(ce_velocities, key=lambda s: abs(ce_velocities[s]))
        top_pe_strike = max(pe_velocities, key=lambda s: abs(pe_velocities[s]))

        top_ce_v = ce_velocities[top_ce_strike]
        top_pe_v = pe_velocities[top_pe_strike]

        # Spike ratios (how many x rolling average is current velocity)
        ce_spike = abs(top_ce_v) / max(rolling_ce_mean, 1.0)
        pe_spike = abs(top_pe_v) / max(rolling_pe_mean, 1.0)

        is_uoa = max(ce_spike, pe_spike) >= UOA_THRESHOLD
        max_spike = max(ce_spike, pe_spike, 0.001)

        # Score: positive = call velocity dominant (bullish), negative = put (bearish)
        # Use rolling mean as scaling factor so tanh spreads across the velocity range
        net_velocity = top_ce_v - top_pe_v
        scaling_factor = max(rolling_ce_mean, rolling_pe_mean, 1.0)
        spike_factor = max(1.0, min(max_spike, 5.0))  # amplify sharp spikes but keep bounded
        raw_score = float(np.tanh((net_velocity / scaling_factor) * spike_factor))

        # Confidence: scales with spike extremity, capped at 0.95
        confidence = min(0.95, (max_spike - 1.0) / 4.0) if max_spike > 1.0 else 0.1

        # Build reason string
        if is_uoa:
            side = "CE" if ce_spike > pe_spike else "PE"
            strike = top_ce_strike if side == "CE" else top_pe_strike
            reason = f"UOA_DETECTED: {side} velocity {max_spike:.1f}x avg at strike {strike}"
        elif abs(raw_score) < 0.15:
            reason = f"velocity_neutral: ce={top_ce_v:.0f}/min pe={top_pe_v:.0f}/min"
        else:
            direction = "bullish" if raw_score > 0 else "bearish"
            reason = f"velocity_{direction}: ce={top_ce_v:.0f}/min pe={top_pe_v:.0f}/min over {elapsed_minutes:.1f}min"

        return VelocityResult(
            score=round(raw_score, 4),
            confidence=round(confidence, 4),
            reason=reason,
            top_strike=top_ce_strike if ce_spike > pe_spike else top_pe_strike,
            top_ce_velocity=round(top_ce_v, 1),
            top_pe_velocity=round(top_pe_v, 1),
            is_uoa=is_uoa,
        )
