# earnings.py — Mock Earnings Calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Dummy dictionary simulating upcoming earnings dates.
# We set a few known tickers to have earnings within the next 4 days to test the gate.

def _get_mock_earnings_dates() -> dict:
    today = datetime.now(IST).date()
    return {
        "RELIANCE": (today + timedelta(days=2)).isoformat(),
        "TCS": (today + timedelta(days=4)).isoformat(),
        "HDFCBANK": (today + timedelta(days=1)).isoformat(),
        "INFY": (today + timedelta(days=3)).isoformat(),
        "ICICIBANK": (today + timedelta(days=5)).isoformat(),
        # Add random old ones
        "WIPRO": (today - timedelta(days=10)).isoformat(),
        "SBIN": (today + timedelta(days=20)).isoformat(),
    }

MOCK_EARNINGS = _get_mock_earnings_dates()

def get_days_to_earnings(symbol: str) -> int:
    """Return days to earnings. If none found or past, returns 999."""
    date_str = MOCK_EARNINGS.get(symbol)
    if not date_str:
        return 999
    
    try:
        e_date = datetime.fromisoformat(date_str).date()
        today = datetime.now(IST).date()
        diff = (e_date - today).days
        return diff if diff >= 0 else 999
    except ValueError:
        return 999
