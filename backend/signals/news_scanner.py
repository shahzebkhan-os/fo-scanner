"""
signals/news_scanner.py — News & Event Scanner (Signal 10)

Sources:
1. NSE website announcements API (corporate actions, results calendar)
2. RBI website (policy announcements)
3. Economic calendar (India CPI, WPI, GDP, IIP releases)
4. Optional: NewsAPI.org for headline sentiment

Behavior:
- If HIGH-impact event detected within 24 hours:
  a. Block new premium-selling strategies (short straddle, iron condor)
  b. Flag as potential long straddle/strangle opportunity
  c. Tighten stop losses on all open positions to 30% of max loss
- Post-event (within 2 hours of release):
  a. Detect IV crush — if IV drops > 20% from pre-event level → exit all long vega positions
  b. Detect large move — if index moves > 0.8x straddle price → trend-follow with puts/calls
"""

from __future__ import annotations
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from .base import BaseSignal, SignalResult


class NewsSignal(BaseSignal):
    """
    News & Event Scanner Signal — event risk detection.
    
    Detects high-impact events and adjusts trading behavior.
    Returns blackout flag when events are imminent.
    """
    
    name = "news_scanner"
    
    # Event impact levels
    IMPACT_HIGH = "HIGH"
    IMPACT_MEDIUM = "MEDIUM"
    IMPACT_LOW = "LOW"
    
    # Time thresholds
    BLACKOUT_HOURS = 24      # Block trading before high-impact events
    POST_EVENT_HOURS = 2     # Post-event analysis window
    IV_CRUSH_THRESHOLD = 20  # % IV drop for crush detection
    
    # Known high-impact events
    HIGH_IMPACT_EVENTS = [
        "RBI_MPC",
        "US_FED",
        "EARNINGS",
        "CPI",
        "GDP",
        "IIP",
        "WPI",
        "BUDGET",
        "ELECTION",
    ]
    
    def compute(
        self,
        events: List[dict] = None,
        current_time: datetime = None,
        pre_event_iv: float = 0.0,
        current_iv: float = 0.0,
        straddle_price: float = 0.0,
        index_move: float = 0.0,
        **kwargs
    ) -> SignalResult:
        """
        Compute news/event signal.
        
        Args:
            events: List of upcoming/recent events with structure:
                {
                    "name": str,
                    "type": str (RBI_MPC, EARNINGS, etc.),
                    "datetime": datetime or str,
                    "impact": str (HIGH, MEDIUM, LOW),
                    "symbol": str (optional, for stock-specific events)
                }
            current_time: Current datetime for event proximity calculation
            pre_event_iv: IV level before the event
            current_iv: Current IV level
            straddle_price: ATM straddle price
            index_move: Index move since event (in points or %)
            
        Returns:
            SignalResult with event analysis and blackout flag
        """
        events = events or []
        current_time = current_time or datetime.now()
        
        # Analyze events
        high_impact_upcoming = []
        recent_events = []
        
        for event in events:
            event_time = self._parse_event_time(event.get("datetime"))
            if event_time is None:
                continue
            
            hours_until = (event_time - current_time).total_seconds() / 3600
            hours_since = -hours_until
            
            impact = event.get("impact", self.IMPACT_LOW)
            is_high_impact = (
                impact == self.IMPACT_HIGH or
                event.get("type") in self.HIGH_IMPACT_EVENTS
            )
            
            if 0 < hours_until <= self.BLACKOUT_HOURS and is_high_impact:
                high_impact_upcoming.append({
                    **event,
                    "hours_until": round(hours_until, 1),
                })
            elif 0 < hours_since <= self.POST_EVENT_HOURS:
                recent_events.append({
                    **event,
                    "hours_since": round(hours_since, 1),
                })
        
        # Determine blackout status
        blackout = len(high_impact_upcoming) > 0
        
        # Score and reason
        score = 0.0
        reasons = []
        flags = {
            "blackout": blackout,
            "high_impact_upcoming": high_impact_upcoming,
            "recent_events": recent_events,
            "iv_crush_detected": False,
            "large_move_detected": False,
            "block_premium_selling": blackout,
            "tighten_stops": blackout,
            "long_straddle_opportunity": blackout,
        }
        
        # Pre-event analysis
        if high_impact_upcoming:
            event_names = [e["name"] for e in high_impact_upcoming[:3]]
            reasons.append(f"BLACKOUT: {', '.join(event_names)} within {min(e['hours_until'] for e in high_impact_upcoming):.0f}h")
            score = -0.3  # Cautious / reduce exposure
        
        # Post-event analysis
        if recent_events:
            # IV crush detection
            if pre_event_iv > 0 and current_iv > 0:
                iv_change_pct = (pre_event_iv - current_iv) / pre_event_iv * 100
                if iv_change_pct >= self.IV_CRUSH_THRESHOLD:
                    flags["iv_crush_detected"] = True
                    reasons.append(f"IV crush detected ({iv_change_pct:.1f}%)")
                    score += 0.2  # Post-crush, favorable for new trades
            
            # Large move detection
            if straddle_price > 0 and abs(index_move) > 0:
                move_ratio = abs(index_move) / straddle_price
                if move_ratio > 0.8:
                    flags["large_move_detected"] = True
                    if index_move > 0:
                        reasons.append(f"Large bullish move ({move_ratio:.1f}x straddle)")
                        score += 0.4
                    else:
                        reasons.append(f"Large bearish move ({move_ratio:.1f}x straddle)")
                        score -= 0.4
        
        # Confidence
        confidence = 0.7 if events else 0.3
        if blackout:
            confidence = 0.9  # High confidence in blackout decision
        if flags["iv_crush_detected"] or flags["large_move_detected"]:
            confidence = 0.85
        
        combined_reason = " | ".join(reasons) if reasons else "No significant events"
        
        return SignalResult(
            score=score,
            confidence=confidence,
            reason=combined_reason,
            metadata=flags
        )
    
    def _parse_event_time(self, dt_value) -> Optional[datetime]:
        """Parse event datetime from various formats."""
        if isinstance(dt_value, datetime):
            return dt_value
        
        if isinstance(dt_value, str):
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(dt_value, fmt)
                except ValueError:
                    continue
        
        return None
    
    def get_event_calendar(
        self, symbol: str = None, days_ahead: int = 7
    ) -> List[dict]:
        """
        Get upcoming events for a symbol or the market.
        
        This is a placeholder - actual implementation would fetch from:
        - NSE corporate actions API
        - RBI announcements
        - Economic calendar
        """
        # Placeholder - would be implemented with actual API calls
        return []
    
    def detect_earnings_proximity(
        self, symbol: str, current_time: datetime = None
    ) -> Optional[dict]:
        """
        Detect if a stock's earnings are imminent.
        
        Returns event info if earnings are within 7 days.
        """
        # Placeholder for earnings calendar integration
        return None
