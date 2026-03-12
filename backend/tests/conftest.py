"""
pytest configuration and fixtures for NSE F&O Scanner tests.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_chain_data():
    """
    Provide minimal valid NSE option chain structure with one strike, CE+PE.
    Contains OI, IV, LTP, volume fields.
    """
    return {
        "records": {
            "underlyingValue": 24050.0,
            "expiryDates": ["27-Mar-2025", "03-Apr-2025", "10-Apr-2025"],
            "data": [
                {
                    "strikePrice": 23800,
                    "expiryDate": "27-Mar-2025",
                    "CE": {
                        "openInterest": 150000,
                        "changeinOpenInterest": 5000,
                        "totalTradedVolume": 25000,
                        "impliedVolatility": 14.5,
                        "lastPrice": 312.50,
                        "strikePrice": 23800,
                        "expiryDate": "27-Mar-2025",
                    },
                    "PE": {
                        "openInterest": 120000,
                        "changeinOpenInterest": -2000,
                        "totalTradedVolume": 18000,
                        "impliedVolatility": 15.2,
                        "lastPrice": 62.75,
                        "strikePrice": 23800,
                        "expiryDate": "27-Mar-2025",
                    },
                },
                {
                    "strikePrice": 24000,
                    "expiryDate": "27-Mar-2025",
                    "CE": {
                        "openInterest": 280000,
                        "changeinOpenInterest": 15000,
                        "totalTradedVolume": 45000,
                        "impliedVolatility": 13.8,
                        "lastPrice": 185.25,
                        "strikePrice": 24000,
                        "expiryDate": "27-Mar-2025",
                    },
                    "PE": {
                        "openInterest": 320000,
                        "changeinOpenInterest": 8000,
                        "totalTradedVolume": 52000,
                        "impliedVolatility": 14.1,
                        "lastPrice": 135.00,
                        "strikePrice": 24000,
                        "expiryDate": "27-Mar-2025",
                    },
                },
                {
                    "strikePrice": 24200,
                    "expiryDate": "27-Mar-2025",
                    "CE": {
                        "openInterest": 200000,
                        "changeinOpenInterest": 10000,
                        "totalTradedVolume": 35000,
                        "impliedVolatility": 14.2,
                        "lastPrice": 95.50,
                        "strikePrice": 24200,
                        "expiryDate": "27-Mar-2025",
                    },
                    "PE": {
                        "openInterest": 180000,
                        "changeinOpenInterest": 3000,
                        "totalTradedVolume": 28000,
                        "impliedVolatility": 15.5,
                        "lastPrice": 245.75,
                        "strikePrice": 24200,
                        "expiryDate": "27-Mar-2025",
                    },
                },
            ],
            "timestamp": "12-Mar-2026 15:30:00",
            "strikePrices": [23800, 24000, 24200],
        },
        "filtered": {
            "data": [],
        },
    }


@pytest.fixture
def mock_nse_session():
    """
    Provide a mock NSE session with preset fetch return value.
    No real network calls.
    """
    mock_session = AsyncMock()
    mock_session.get = AsyncMock()
    
    # Mock response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "records": {
            "underlyingValue": 24050.0,
            "expiryDates": ["27-Mar-2025"],
            "data": [
                {
                    "strikePrice": 24000,
                    "CE": {"openInterest": 280000, "lastPrice": 185.25},
                    "PE": {"openInterest": 320000, "lastPrice": 135.00},
                }
            ],
        }
    }
    mock_response.status_code = 200
    mock_response.text = '{"records": {}}'
    mock_response.raise_for_status = MagicMock()
    
    mock_session.get.return_value = mock_response
    
    return mock_session


@pytest.fixture
def sample_historical_snapshot():
    """Sample historical snapshot data for backtest testing."""
    return {
        "id": 1,
        "symbol": "NIFTY",
        "snapshot_time": "2025-03-12 15:30:00",
        "spot_price": 24050.0,
        "total_ce_oi": 5000000,
        "total_pe_oi": 5500000,
        "pcr_oi": 1.1,
        "atm_ce_iv": 14.5,
        "atm_pe_iv": 15.2,
        "iv_skew": 0.7,
        "score": 75,
        "signal": "BULLISH",
        "regime": "TRENDING",
        "confidence": 0.65,
    }


@pytest.fixture
def mock_db():
    """Mock database functions."""
    mock = MagicMock()
    mock.get_iv_rank.return_value = {
        "iv_rank": 45,
        "current_iv": 14.5,
        "iv_high_52w": 25.0,
        "iv_low_52w": 10.0,
        "days_available": 252,
    }
    return mock
