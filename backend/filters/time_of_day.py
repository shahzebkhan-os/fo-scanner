"""
Time of Day Filter (Improvement #2)

Defines allowed and blocked trading windows based on IST market timing.

Time Windows (IST):
- Opening Volatility (9:15-9:30): BLOCKED - All signals suppressed
- Early Morning (9:30-10:15): CAUTION - Show only PRIME signals
- Prime Window (10:15-13:00): OPEN - All qualified signals shown
- Lunch Lull (13:00-14:00): CAUTION - Show only PRIME signals
- Afternoon Prime (14:00-15:00): OPEN - All qualified signals shown
- Power Hour (15:00-15:15): CAUTION - Show only PRIME signals
- Close Risk (15:15-15:30): BLOCKED - All signals suppressed

Expiry Day (Thursday) Special Rules:
- Block all OTM option buys (only ITM/ATM allowed)
- Raise score threshold to 85
- Force PRIME quality only
- Show expiry warning banner
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, time, timedelta
import pytz
import logging

log = logging.getLogger(__name__)

# IST timezone
IST = pytz.timezone("Asia/Kolkata")


class TimeWindow(str, Enum):
    """Market time windows."""
    OPENING_VOLATILITY = "OPENING_VOLATILITY"  # 9:15-9:30 BLOCKED
    EARLY_MORNING = "EARLY_MORNING"            # 9:30-10:15 CAUTION
    PRIME_WINDOW = "PRIME_WINDOW"              # 10:15-13:00 OPEN
    LUNCH_LULL = "LUNCH_LULL"                  # 13:00-14:00 CAUTION
    AFTERNOON_PRIME = "AFTERNOON_PRIME"        # 14:00-15:00 OPEN
    POWER_HOUR = "POWER_HOUR"                  # 15:00-15:15 CAUTION
    CLOSE_RISK = "CLOSE_RISK"                  # 15:15-15:30 BLOCKED
    MARKET_CLOSED = "MARKET_CLOSED"            # Outside hours


class WindowStatus(str, Enum):
    """Signal visibility status for time window."""
    OPEN = "OPEN"              # All qualified signals shown
    CAUTION = "CAUTION"        # Only PRIME signals shown
    BLOCKED = "BLOCKED"        # All signals suppressed


@dataclass
class TimeFilterResult:
    """Result of time-based filtering."""
    window: TimeWindow
    status: WindowStatus
    is_expiry_day: bool
    allowed_quality_tags: list[str]
    min_score_threshold: float
    blocked: bool
    message: Optional[str]

    def to_dict(self) -> dict:
        return {
            "time_window": self.window.value,
            "status": self.status.value,
            "is_expiry_day": self.is_expiry_day,
            "allowed_quality_tags": self.allowed_quality_tags,
            "min_score_threshold": self.min_score_threshold,
            "blocked": self.blocked,
            "message": self.message,
        }


class TimeOfDayFilter:
    """
    Time of Day Filter - Controls signal visibility based on market timing.

    Usage:
        filter = TimeOfDayFilter()
        result = filter.get_current_filter()
        if not result.blocked:
            # Check quality tag
            if signal_quality in result.allowed_quality_tags:
                # Signal is allowed
    """

    # Window definitions (hour, minute)
    WINDOWS = {
        TimeWindow.OPENING_VOLATILITY: ((9, 15), (9, 30)),
        TimeWindow.EARLY_MORNING: ((9, 30), (10, 15)),
        TimeWindow.PRIME_WINDOW: ((10, 15), (13, 0)),
        TimeWindow.LUNCH_LULL: ((13, 0), (14, 0)),
        TimeWindow.AFTERNOON_PRIME: ((14, 0), (15, 0)),
        TimeWindow.POWER_HOUR: ((15, 0), (15, 15)),
        TimeWindow.CLOSE_RISK: ((15, 15), (15, 30)),
    }

    # Status mapping
    WINDOW_STATUS = {
        TimeWindow.OPENING_VOLATILITY: WindowStatus.BLOCKED,
        TimeWindow.EARLY_MORNING: WindowStatus.CAUTION,
        TimeWindow.PRIME_WINDOW: WindowStatus.OPEN,
        TimeWindow.LUNCH_LULL: WindowStatus.CAUTION,
        TimeWindow.AFTERNOON_PRIME: WindowStatus.OPEN,
        TimeWindow.POWER_HOUR: WindowStatus.CAUTION,
        TimeWindow.CLOSE_RISK: WindowStatus.BLOCKED,
        TimeWindow.MARKET_CLOSED: WindowStatus.BLOCKED,
    }

    # Normal score threshold
    NORMAL_SCORE_THRESHOLD = 75.0
    EXPIRY_SCORE_THRESHOLD = 85.0

    def get_current_window(self, current_time: Optional[datetime] = None) -> TimeWindow:
        """
        Determine current time window.

        Args:
            current_time: Optional datetime (defaults to now in IST)

        Returns:
            TimeWindow enum
        """
        if current_time is None:
            current_time = datetime.now(IST)
        elif current_time.tzinfo is None:
            # Localize naive datetime to IST
            current_time = IST.localize(current_time)
        else:
            # Convert to IST
            current_time = current_time.astimezone(IST)

        current_time_obj = current_time.time()

        # Check each window
        for window, ((start_h, start_m), (end_h, end_m)) in self.WINDOWS.items():
            start = time(start_h, start_m)
            end = time(end_h, end_m)

            if start <= current_time_obj < end:
                return window

        # Outside market hours
        return TimeWindow.MARKET_CLOSED

    def is_expiry_day(self, current_time: Optional[datetime] = None) -> bool:
        """
        Check if today is weekly expiry day (Thursday).

        Note: NSE weekly options expire on Thursday. If Thursday is a market holiday,
        expiry shifts to Wednesday, but we detect by checking if today's weekday is
        Thursday AND market is open.

        Args:
            current_time: Optional datetime (defaults to now in IST)

        Returns:
            True if today is expiry day
        """
        if current_time is None:
            current_time = datetime.now(IST)
        elif current_time.tzinfo is None:
            current_time = IST.localize(current_time)
        else:
            current_time = current_time.astimezone(IST)

        # Check if Thursday (weekday 3)
        return current_time.weekday() == 3

    def get_current_filter(
        self,
        current_time: Optional[datetime] = None,
        quality_tag: Optional[str] = None,
        unified_score: Optional[float] = None,
        option_delta: Optional[float] = None,
    ) -> TimeFilterResult:
        """
        Get current time-based filter result.

        Args:
            current_time: Optional datetime (defaults to now in IST)
            quality_tag: Signal quality tag (PRIME, QUALIFIED, etc.)
            unified_score: Unified score (for threshold check)
            option_delta: Option delta (for expiry day OTM check)

        Returns:
            TimeFilterResult with filtering decision
        """
        window = self.get_current_window(current_time)
        status = self.WINDOW_STATUS[window]
        is_expiry = self.is_expiry_day(current_time)

        # Default values
        allowed_tags = []
        min_score = self.NORMAL_SCORE_THRESHOLD
        blocked = False
        message = None

        # Apply window rules
        if status == WindowStatus.BLOCKED:
            blocked = True
            message = f"Signals blocked during {window.value.replace('_', ' ').title()}"
        elif status == WindowStatus.CAUTION:
            allowed_tags = ["PRIME"]
            message = f"Only PRIME signals allowed during {window.value.replace('_', ' ').title()}"
        elif status == WindowStatus.OPEN:
            allowed_tags = ["PRIME", "QUALIFIED"]
            message = None

        # Apply expiry day special rules
        if is_expiry:
            min_score = self.EXPIRY_SCORE_THRESHOLD
            allowed_tags = ["PRIME"]  # Force PRIME only

            # Check if OTM option (delta < 0.40 or > 0.60 means more than 1 strike away)
            if option_delta is not None:
                is_otm = option_delta < 0.40 or option_delta > 0.60
                if is_otm:
                    blocked = True
                    message = "OTM options blocked on expiry day (Thursday)"
                else:
                    message = "⚠️ EXPIRY DAY - Only ITM/ATM PRIME signals allowed, threshold 85"
            else:
                message = "⚠️ EXPIRY DAY - Only PRIME signals allowed, threshold 85"

        # Check quality tag if provided
        if quality_tag and not blocked:
            if quality_tag not in allowed_tags:
                blocked = True
                if not message:
                    message = f"{quality_tag} signals not allowed in {window.value}"

        # Check score threshold if provided
        if unified_score is not None and not blocked:
            if unified_score < min_score:
                blocked = True
                if not message:
                    message = f"Score {unified_score:.1f} below threshold {min_score:.1f}"

        return TimeFilterResult(
            window=window,
            status=status,
            is_expiry_day=is_expiry,
            allowed_quality_tags=allowed_tags,
            min_score_threshold=min_score,
            blocked=blocked,
            message=message,
        )

    def check_signal(
        self,
        quality_tag: str,
        unified_score: float,
        option_delta: Optional[float] = None,
        current_time: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        """
        Check if a signal should be shown based on time-of-day rules.

        Args:
            quality_tag: Signal quality tag (PRIME, QUALIFIED, etc.)
            unified_score: Unified score
            option_delta: Option delta (for expiry day OTM check)
            current_time: Optional datetime (defaults to now in IST)

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        result = self.get_current_filter(
            current_time=current_time,
            quality_tag=quality_tag,
            unified_score=unified_score,
            option_delta=option_delta,
        )

        if result.blocked:
            return False, result.message or "Signal blocked by time filter"

        return True, "Signal allowed"


# Singleton instance
_time_filter = TimeOfDayFilter()


def get_time_of_day_filter() -> TimeOfDayFilter:
    """Get the singleton time-of-day filter instance."""
    return _time_filter
