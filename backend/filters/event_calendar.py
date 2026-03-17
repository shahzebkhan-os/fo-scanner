"""
Event Calendar and Blackout Filter (Improvement #4)

Automatically reduces or suppresses signal confidence when high-impact events are imminent.

Event Types:
- RBI Monetary Policy: Suppress all Nifty/BankNifty signals on announcement day
- US Fed Meeting: Reduce confidence by 20% on same day
- US CPI/NFP Data: Add CAUTION tag, raise threshold to 82
- India Union Budget: Suppress all signals on budget day
- Stock Earnings: Block 3 days before and on day
- Stock AGM/Board Meeting: Reduce confidence by 15%
- Stock Ex-Dividend: Block - price gap risk
- NSE F&O Ban: Block entirely - no fresh positions allowed

Data Sources:
- Macro events: NSE economic calendar API or hardcoded dates
- Corporate events: NSE corporate actions API
- F&O Ban: NSE F&O ban list API (CRITICAL - refresh every 30 min)
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, date
import logging
import asyncio
from collections import defaultdict

log = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of events that affect trading."""
    # Macro events
    RBI_POLICY = "RBI_POLICY"
    FED_MEETING = "FED_MEETING"
    US_CPI = "US_CPI"
    US_NFP = "US_NFP"
    INDIA_BUDGET = "INDIA_BUDGET"

    # Corporate events
    EARNINGS = "EARNINGS"
    AGM = "AGM"
    BOARD_MEETING = "BOARD_MEETING"
    EX_DIVIDEND = "EX_DIVIDEND"

    # F&O specific
    FO_BAN = "FO_BAN"


class EventAction(str, Enum):
    """Actions to take when event is detected."""
    BLOCK = "BLOCK"                      # Block signal entirely
    REDUCE_CONFIDENCE_20 = "REDUCE_20"   # Reduce confidence by 20%
    REDUCE_CONFIDENCE_15 = "REDUCE_15"   # Reduce confidence by 15%
    CAUTION = "CAUTION"                  # Add caution tag, raise threshold to 82


@dataclass
class EventInfo:
    """Information about an event."""
    event_type: EventType
    symbol: Optional[str]  # None for market-wide events
    event_date: date
    description: str
    action: EventAction
    lookback_days: int = 0  # How many days before to start blocking


@dataclass
class EventFilterResult:
    """Result of event filtering."""
    has_event: bool
    events: List[EventInfo]
    action: Optional[EventAction]
    confidence_adjustment: float  # Negative adjustment
    blocked: bool
    message: Optional[str]

    def to_dict(self) -> dict:
        return {
            "has_event": self.has_event,
            "event_count": len(self.events),
            "events": [
                {
                    "type": e.event_type.value,
                    "symbol": e.symbol,
                    "date": e.event_date.isoformat(),
                    "description": e.description,
                    "action": e.action.value,
                }
                for e in self.events
            ],
            "action": self.action.value if getattr(self, "action", None) else None,
            "confidence_adjustment": self.confidence_adjustment,
            "blocked": self.blocked,
            "message": self.message,
        }


class EventCalendar:
    """
    Event Calendar - Tracks macro and corporate events affecting trading.

    F&O Ban List Check runs FIRST before any other evaluation.
    """

    def __init__(self):
        # In-memory caches
        self._fo_ban_list: set[str] = set()
        self._fo_ban_last_update = datetime(2000, 1, 1)
        self._corporate_events: Dict[str, List[EventInfo]] = defaultdict(list)
        self._corporate_events_last_update = datetime(2000, 1, 1)
        self._macro_events: List[EventInfo] = []
        self._macro_events_last_update = datetime(2000, 1, 1)

        # Cache TTLs
        self.FO_BAN_TTL_MINUTES = 30
        self.CORPORATE_TTL_HOURS = 24
        self.MACRO_TTL_DAYS = 7

    async def is_fo_banned(self, symbol: str) -> bool:
        """
        Check if a symbol is on the F&O ban list.

        This is the CRITICAL check that must run FIRST.

        Args:
            symbol: Stock symbol (e.g., "RELIANCE")

        Returns:
            True if symbol is banned
        """
        # Refresh cache if stale
        await self._refresh_fo_ban_list_if_needed()

        return symbol.upper() in self._fo_ban_list

    async def check_events(
        self,
        symbol: str,
        check_date: Optional[date] = None,
    ) -> EventFilterResult:
        """
        Check for events affecting a symbol.

        Args:
            symbol: Stock symbol (e.g., "RELIANCE", "NIFTY")
            check_date: Date to check (defaults to today)

        Returns:
            EventFilterResult with all applicable events and recommended action
        """
        if check_date is None:
            check_date = date.today()

        # F&O Ban Check (FIRST)
        if await self.is_fo_banned(symbol):
            ban_event = EventInfo(
                event_type=EventType.FO_BAN,
                symbol=symbol,
                event_date=check_date,
                description=f"{symbol} is on NSE F&O ban list",
                action=EventAction.BLOCK,
            )
            return EventFilterResult(
                has_event=True,
                events=[ban_event],
                action=EventAction.BLOCK,
                confidence_adjustment=0.0,
                blocked=True,
                message=f"⛔ {symbol} on F&O ban list - No fresh positions allowed",
            )

        # Refresh event caches
        await self._refresh_events_if_needed()

        # Collect all applicable events
        events: List[EventInfo] = []

        # Check macro events (for indices)
        if symbol in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]:
            for event in self._macro_events:
                if self._is_event_applicable(event, check_date):
                    events.append(event)

        # Check corporate events (for stocks)
        else:
            for event in self._corporate_events.get(symbol.upper(), []):
                if self._is_event_applicable(event, check_date):
                    events.append(event)

        if not events:
            return EventFilterResult(
                has_event=False,
                events=[],
                action=None,
                confidence_adjustment=0.0,
                blocked=False,
                message=None,
            )

        # Determine strictest action
        strictest_action = self._get_strictest_action(events)

        # Calculate adjustments
        if strictest_action == EventAction.BLOCK:
            blocked = True
            confidence_adj = 0.0
            message = self._format_event_message(events, blocked=True)
        elif strictest_action == EventAction.REDUCE_CONFIDENCE_20:
            blocked = False
            confidence_adj = -0.20
            message = self._format_event_message(events, blocked=False)
        elif strictest_action == EventAction.REDUCE_CONFIDENCE_15:
            blocked = False
            confidence_adj = -0.15
            message = self._format_event_message(events, blocked=False)
        elif strictest_action == EventAction.CAUTION:
            blocked = False
            confidence_adj = 0.0
            message = self._format_event_message(events, blocked=False) + " (Threshold raised to 82)"
        else:
            blocked = False
            confidence_adj = 0.0
            message = self._format_event_message(events, blocked=False)

        return EventFilterResult(
            has_event=True,
            events=events,
            action=strictest_action,
            confidence_adjustment=confidence_adj,
            blocked=blocked,
            message=message,
        )

    def _is_event_applicable(self, event: EventInfo, check_date: date) -> bool:
        """Check if an event is applicable for the given date."""
        lookback_start = event.event_date - timedelta(days=event.lookback_days)
        return lookback_start <= check_date <= event.event_date

    def _get_strictest_action(self, events: List[EventInfo]) -> EventAction:
        """Get the strictest action from a list of events."""
        # Priority: BLOCK > REDUCE_20 > REDUCE_15 > CAUTION
        priority = {
            EventAction.BLOCK: 4,
            EventAction.REDUCE_CONFIDENCE_20: 3,
            EventAction.REDUCE_CONFIDENCE_15: 2,
            EventAction.CAUTION: 1,
        }

        strictest = max(events, key=lambda e: priority.get(e.action, 0))
        return strictest.action

    def _format_event_message(self, events: List[EventInfo], blocked: bool) -> str:
        """Format event message for display."""
        if blocked:
            event_desc = events[0].description  # Show first blocking event
            return f"📅 Signal blocked - {event_desc}"
        else:
            event_count = len(events)
            if event_count == 1:
                return f"📅 {events[0].description}"
            else:
                return f"📅 {event_count} events detected - Proceed with caution"

    async def _refresh_fo_ban_list_if_needed(self):
        """Refresh F&O ban list cache if stale."""
        now = datetime.now()

        if (now - self._fo_ban_last_update).total_seconds() > self.FO_BAN_TTL_MINUTES * 60:
            await self._fetch_fo_ban_list()

    async def _refresh_events_if_needed(self):
        """Refresh event caches if stale."""
        now = datetime.now()

        # Corporate events (daily refresh)
        if (now - self._corporate_events_last_update).total_seconds() > self.CORPORATE_TTL_HOURS * 3600:
            await self._fetch_corporate_events()

        # Macro events (weekly refresh)
        if (now - self._macro_events_last_update).total_seconds() > self.MACRO_TTL_DAYS * 86400:
            await self._fetch_macro_events()

    async def _fetch_fo_ban_list(self):
        """
        Fetch F&O ban list from NSE API.

        NSE API: https://www.nseindia.com/api/fo-secban
        """
        try:
            # Import here to avoid circular dependency
            from ..constants import NSE_BASE, NSE_HEADERS
            import httpx

            url = f"{NSE_BASE}/api/fo-secban"

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                # First, visit the main page to get cookies
                await client.get(f"{NSE_BASE}/option-chain", headers=NSE_HEADERS)

                # Now fetch the ban list
                response = await client.get(url, headers=NSE_HEADERS)
                
                if response.status_code == 404:
                    log.info("F&O ban list is currently empty (404 Not Found)")
                    self._fo_ban_list = set()
                    self._fo_ban_last_update = datetime.now()
                    return

                response.raise_for_status()
                data = response.json()
                securities = data.get("secban", [])

                # Extract symbols
                ban_symbols = set()
                for sec in securities:
                    symbol = sec.get("symbol")
                    if symbol:
                        ban_symbols.add(symbol.upper())

                self._fo_ban_list = ban_symbols
                self._fo_ban_last_update = datetime.now()

                log.info(f"Updated F&O ban list: {len(ban_symbols)} symbols")

        except Exception as e:
            log.warning(f"Failed to fetch F&O ban list: {e}")
            # Keep existing cache if fetch fails

    async def _fetch_corporate_events(self):
        """
        Fetch corporate events from NSE API.

        NSE API: https://www.nseindia.com/api/corporates-corporateActions
        """
        try:
            # Import here to avoid circular dependency
            from ..constants import NSE_BASE, NSE_HEADERS
            import httpx

            # Fetch for next 30 days
            today = date.today()
            from_date = today.strftime("%d-%m-%Y")
            to_date = (today + timedelta(days=30)).strftime("%d-%m-%Y")

            url = f"{NSE_BASE}/api/corporates-corporateActions?index=equities&from_date={from_date}&to_date={to_date}"

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                # Visit landing page first for cookies - using the correct one for corporate actions
                landing_url = f"{NSE_BASE}/companies-listing/corporate-filings-actions"
                await client.get(landing_url, headers=NSE_HEADERS)

                # Fetch actions
                response = await client.get(url, headers=NSE_HEADERS)
                response.raise_for_status()

                try:
                    data = response.json()
                except Exception as json_err:
                    log.error(f"Failed to decode corporate actions JSON: {json_err}. Raw content starts with: {response.text[:100]}")
                    return

                actions = data if isinstance(data, list) else []

                # Parse events
                events_by_symbol = defaultdict(list)

                for action in actions:
                    symbol = action.get("symbol", "").upper()
                    subject = action.get("subject", "").lower()
                    ex_date_str = action.get("exDate")

                    if not symbol or not ex_date_str:
                        continue

                    # Parse date
                    try:
                        ex_date = datetime.strptime(ex_date_str, "%d-%b-%Y").date()
                    except ValueError:
                        continue

                    # Classify event type
                    if "dividend" in subject:
                        event = EventInfo(
                            event_type=EventType.EX_DIVIDEND,
                            symbol=symbol,
                            event_date=ex_date,
                            description=f"{symbol} Ex-Dividend on {ex_date}",
                            action=EventAction.BLOCK,
                        )
                        events_by_symbol[symbol].append(event)

                    elif "result" in subject or "earnings" in subject:
                        event = EventInfo(
                            event_type=EventType.EARNINGS,
                            symbol=symbol,
                            event_date=ex_date,
                            description=f"{symbol} Earnings on {ex_date}",
                            action=EventAction.BLOCK,
                            lookback_days=3,  # Block 3 days before
                        )
                        events_by_symbol[symbol].append(event)

                    elif "agm" in subject or "egm" in subject:
                        event = EventInfo(
                            event_type=EventType.AGM,
                            symbol=symbol,
                            event_date=ex_date,
                            description=f"{symbol} AGM on {ex_date}",
                            action=EventAction.REDUCE_CONFIDENCE_15,
                        )
                        events_by_symbol[symbol].append(event)

                    elif "board" in subject:
                        event = EventInfo(
                            event_type=EventType.BOARD_MEETING,
                            symbol=symbol,
                            event_date=ex_date,
                            description=f"{symbol} Board Meeting on {ex_date}",
                            action=EventAction.REDUCE_CONFIDENCE_15,
                        )
                        events_by_symbol[symbol].append(event)

                self._corporate_events = dict(events_by_symbol)
                self._corporate_events_last_update = datetime.now()

                log.info(f"Updated corporate events: {sum(len(v) for v in events_by_symbol.values())} events across {len(events_by_symbol)} symbols")

        except Exception as e:
            log.warning(f"Failed to fetch corporate events: {e}")
            # Keep existing cache if fetch fails

    async def _fetch_macro_events(self):
        """
        Fetch macro events (hardcoded for now, can be enhanced with API later).

        Typical events:
        - RBI Monetary Policy: Every 2 months (Feb, Apr, Jun, Aug, Oct, Dec)
        - US Fed Meeting: 8 times per year
        - US CPI: First half of every month
        - US NFP: First Friday of every month
        - India Budget: Feb 1st
        """
        try:
            today = date.today()
            macro_events = []

            # India Budget (Feb 1)
            if today.month <= 2:
                budget_date = date(today.year, 2, 1)
                if budget_date >= today:
                    macro_events.append(
                        EventInfo(
                            event_type=EventType.INDIA_BUDGET,
                            symbol=None,
                            event_date=budget_date,
                            description="India Union Budget",
                            action=EventAction.BLOCK,
                        )
                    )

            # RBI Policy (approximate dates - typically every 2 months)
            rbi_months = [2, 4, 6, 8, 10, 12]
            for month in rbi_months:
                if month >= today.month:
                    # RBI typically meets in the first week
                    rbi_date = date(today.year, month, 8)
                    if rbi_date >= today:
                        macro_events.append(
                            EventInfo(
                                event_type=EventType.RBI_POLICY,
                                symbol=None,
                                event_date=rbi_date,
                                description=f"RBI Monetary Policy Meeting",
                                action=EventAction.BLOCK,
                            )
                        )

            # US CPI (around 10th-15th of each month)
            for month_offset in range(0, 3):
                cpi_month = (today.month + month_offset - 1) % 12 + 1
                cpi_year = today.year if today.month + month_offset <= 12 else today.year + 1
                cpi_date = date(cpi_year, cpi_month, 13)

                if cpi_date >= today:
                    macro_events.append(
                        EventInfo(
                            event_type=EventType.US_CPI,
                            symbol=None,
                            event_date=cpi_date,
                            description="US CPI Data Release",
                            action=EventAction.CAUTION,
                        )
                    )

            # US NFP (first Friday of each month)
            for month_offset in range(0, 3):
                nfp_month = (today.month + month_offset - 1) % 12 + 1
                nfp_year = today.year if today.month + month_offset <= 12 else today.year + 1

                # Find first Friday
                first_day = date(nfp_year, nfp_month, 1)
                days_until_friday = (4 - first_day.weekday()) % 7
                nfp_date = first_day + timedelta(days=days_until_friday)

                if nfp_date >= today:
                    macro_events.append(
                        EventInfo(
                            event_type=EventType.US_NFP,
                            symbol=None,
                            event_date=nfp_date,
                            description="US Non-Farm Payrolls (NFP) Release",
                            action=EventAction.REDUCE_CONFIDENCE_20,
                        )
                    )

            self._macro_events = macro_events
            self._macro_events_last_update = datetime.now()

            log.info(f"Updated macro events: {len(macro_events)} events")

        except Exception as e:
            log.warning(f"Failed to fetch macro events: {e}")
            # Keep existing cache if fetch fails


# Singleton instance
_event_calendar = EventCalendar()


def get_event_calendar() -> EventCalendar:
    """Get the singleton event calendar instance."""
    return _event_calendar
