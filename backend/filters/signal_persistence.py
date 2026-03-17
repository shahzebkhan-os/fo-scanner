"""
Signal Persistence Check (Improvement #5)

A signal must be consistently present across multiple consecutive evaluation cycles
before being shown as actionable. Only persistent signals are valid.

Persistence Rules:
- Minimum 3 consecutive refreshes
- Score drop ≤ 5 points between any two consecutive refreshes
- Direction must not flip even once
- Quality tag must remain same (PRIME/QUALIFIED) across all 3 refreshes
- If 4th refresh shows different direction → reset counter

Persistence Status:
- CONFIRMED: 3+ consecutive refreshes passed
- BUILDING (2/3): 2 refreshes passed so far
- BUILDING (1/3): 1 refresh passed so far
- RESET: Direction flipped or score dropped significantly
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import logging

log = logging.getLogger(__name__)


class PersistenceStatus(str, Enum):
    """Signal persistence status."""
    CONFIRMED = "CONFIRMED"        # 3+ consecutive refreshes passed
    BUILDING = "BUILDING"          # 1-2 refreshes so far
    RESET = "RESET"                # Direction flipped or score dropped
    NEW = "NEW"                    # First time seeing this signal


@dataclass
class SignalSnapshot:
    """A snapshot of a signal at a specific time."""
    timestamp: datetime
    unified_score: float
    signal_direction: str
    quality_tag: str
    unified_confidence: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "unified_score": self.unified_score,
            "signal_direction": self.signal_direction,
            "quality_tag": self.quality_tag,
            "unified_confidence": self.unified_confidence,
        }


@dataclass
class SignalHistory:
    """Rolling history of signal snapshots for a symbol."""
    symbol: str
    snapshots: deque[SignalSnapshot] = field(default_factory=lambda: deque(maxlen=10))
    consecutive_count: int = 0
    is_persistent: bool = False
    first_confirmed_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "consecutive_count": self.consecutive_count,
            "is_persistent": self.is_persistent,
            "first_confirmed_at": self.first_confirmed_at.isoformat() if self.first_confirmed_at else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class PersistenceResult:
    """Result of persistence check."""
    status: PersistenceStatus
    consecutive_count: int
    required_count: int
    first_confirmed_at: Optional[datetime]
    message: str
    is_actionable: bool

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "consecutive_count": self.consecutive_count,
            "required_count": self.required_count,
            "first_confirmed_at": self.first_confirmed_at.isoformat() if self.first_confirmed_at else None,
            "message": self.message,
            "is_actionable": self.is_actionable,
        }


class SignalPersistenceCache:
    """
    Signal Persistence Cache - Maintains rolling history per symbol.

    Tracks signals across multiple refresh cycles to ensure stability.
    """

    # Configuration
    MIN_CONSECUTIVE_REFRESHES = 3
    MAX_SCORE_DROP = 5.0
    MAX_HISTORY_SIZE = 100  # symbols
    MAX_CACHE_AGE_HOURS = 2

    def __init__(self):
        self._history: Dict[str, SignalHistory] = {}

    def update_history(
        self,
        symbol: str,
        unified_score: float,
        signal_direction: str,
        quality_tag: str,
        unified_confidence: float,
        timestamp: Optional[datetime] = None,
    ) -> PersistenceResult:
        """
        Update signal history and check persistence.

        Args:
            symbol: Stock/index symbol
            unified_score: Current unified score
            signal_direction: BULLISH/BEARISH/NEUTRAL
            quality_tag: PRIME/QUALIFIED/MARGINAL/BLOCKED
            unified_confidence: Unified confidence
            timestamp: Optional timestamp (defaults to now)

        Returns:
            PersistenceResult with current status
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Create new snapshot
        snapshot = SignalSnapshot(
            timestamp=timestamp,
            unified_score=unified_score,
            signal_direction=signal_direction,
            quality_tag=quality_tag,
            unified_confidence=unified_confidence,
        )

        # Get or create history
        if symbol not in self._history:
            history = SignalHistory(symbol=symbol)
            self._history[symbol] = history
        else:
            history = self._history[symbol]

        # Check if we need to reset
        should_reset = False
        reset_reason = None

        if history.snapshots:
            last_snapshot = history.snapshots[-1]

            # Check direction consistency
            if signal_direction != last_snapshot.signal_direction:
                should_reset = True
                reset_reason = f"Direction changed from {last_snapshot.signal_direction} to {signal_direction}"

            # Check score drop
            elif abs(unified_score - last_snapshot.unified_score) > self.MAX_SCORE_DROP:
                score_diff = unified_score - last_snapshot.unified_score
                should_reset = True
                reset_reason = f"Score changed by {score_diff:+.1f} (> ±{self.MAX_SCORE_DROP})"

            # Check quality tag consistency (must stay at PRIME/QUALIFIED level)
            elif quality_tag != last_snapshot.quality_tag:
                if not self._is_quality_tag_consistent(last_snapshot.quality_tag, quality_tag):
                    should_reset = True
                    reset_reason = f"Quality tag changed from {last_snapshot.quality_tag} to {quality_tag}"

        # Reset if needed
        if should_reset:
            log.debug(f"{symbol}: Persistence RESET - {reset_reason}")
            history.snapshots.clear()
            history.consecutive_count = 0
            history.is_persistent = False
            history.first_confirmed_at = None

        # Add new snapshot
        history.snapshots.append(snapshot)
        history.last_updated = timestamp

        # Update consecutive count
        if not should_reset:
            history.consecutive_count += 1
        else:
            history.consecutive_count = 1

        # Check if confirmed
        if history.consecutive_count >= self.MIN_CONSECUTIVE_REFRESHES:
            if not history.is_persistent:
                history.first_confirmed_at = timestamp
                log.info(f"{symbol}: Persistence CONFIRMED after {history.consecutive_count} consecutive refreshes")

            history.is_persistent = True
            status = PersistenceStatus.CONFIRMED
            message = f"✅ Confirmed ({history.consecutive_count}/{self.MIN_CONSECUTIVE_REFRESHES})"
            is_actionable = True

        else:
            history.is_persistent = False
            status = PersistenceStatus.BUILDING
            message = f"🕐 Building ({history.consecutive_count}/{self.MIN_CONSECUTIVE_REFRESHES})"
            is_actionable = False

        # Clean up old entries
        self._cleanup_stale_entries()

        return PersistenceResult(
            status=status,
            consecutive_count=history.consecutive_count,
            required_count=self.MIN_CONSECUTIVE_REFRESHES,
            first_confirmed_at=history.first_confirmed_at,
            message=message,
            is_actionable=is_actionable,
        )

    def get_persistence_status(self, symbol: str) -> PersistenceResult:
        """
        Get current persistence status for a symbol without updating.

        Args:
            symbol: Stock/index symbol

        Returns:
            PersistenceResult
        """
        history = self._history.get(symbol)

        if not history or not history.snapshots:
            return PersistenceResult(
                status=PersistenceStatus.NEW,
                consecutive_count=0,
                required_count=self.MIN_CONSECUTIVE_REFRESHES,
                first_confirmed_at=None,
                message="New signal - No history",
                is_actionable=False,
            )

        if history.is_persistent:
            status = PersistenceStatus.CONFIRMED
            message = f"✅ Confirmed ({history.consecutive_count}/{self.MIN_CONSECUTIVE_REFRESHES})"
            is_actionable = True
        else:
            status = PersistenceStatus.BUILDING
            message = f"🕐 Building ({history.consecutive_count}/{self.MIN_CONSECUTIVE_REFRESHES})"
            is_actionable = False

        return PersistenceResult(
            status=status,
            consecutive_count=history.consecutive_count,
            required_count=self.MIN_CONSECUTIVE_REFRESHES,
            first_confirmed_at=history.first_confirmed_at,
            message=message,
            is_actionable=is_actionable,
        )

    def get_history(self, symbol: str) -> Optional[SignalHistory]:
        """Get full history for a symbol."""
        return self._history.get(symbol)

    def clear_history(self, symbol: Optional[str] = None):
        """
        Clear history.

        Args:
            symbol: If provided, clear only this symbol. Otherwise clear all.
        """
        if symbol:
            if symbol in self._history:
                del self._history[symbol]
        else:
            self._history.clear()

    def _is_quality_tag_consistent(self, prev_tag: str, new_tag: str) -> bool:
        """
        Check if quality tag transition is acceptable.

        PRIME -> PRIME: OK
        PRIME -> QUALIFIED: OK (minor degradation allowed)
        QUALIFIED -> PRIME: OK (improvement)
        QUALIFIED -> QUALIFIED: OK
        Anything else: NOT OK (reset)
        """
        acceptable_tags = {"PRIME", "QUALIFIED"}
        return prev_tag in acceptable_tags and new_tag in acceptable_tags

    def _cleanup_stale_entries(self):
        """Remove stale entries to prevent memory leak."""
        now = datetime.now()
        max_age = self.MAX_CACHE_AGE_HOURS * 3600  # seconds

        stale_symbols = []
        for symbol, history in self._history.items():
            if history.last_updated:
                age = (now - history.last_updated).total_seconds()
                if age > max_age:
                    stale_symbols.append(symbol)

        for symbol in stale_symbols:
            del self._history[symbol]
            log.debug(f"Removed stale persistence history for {symbol}")

        # Also enforce max size
        if len(self._history) > self.MAX_HISTORY_SIZE:
            # Remove oldest entries
            sorted_symbols = sorted(
                self._history.items(),
                key=lambda x: x[1].last_updated or datetime.min,
            )
            to_remove = len(self._history) - self.MAX_HISTORY_SIZE
            for symbol, _ in sorted_symbols[:to_remove]:
                del self._history[symbol]
                log.debug(f"Removed history for {symbol} to enforce max size")


# Singleton instance
_persistence_cache = SignalPersistenceCache()


def get_signal_persistence_cache() -> SignalPersistenceCache:
    """Get the singleton signal persistence cache instance."""
    return _persistence_cache
