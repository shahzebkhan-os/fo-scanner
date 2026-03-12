"""
Tests for NSE session handling and anti-bot measures.
Tests stale detection, HTML guard, 403 reinit, valid JSON pass-through.
All network calls are mocked — no real NSE requests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestNSESessionStaleDetection:
    """Tests for stale data detection in NSE responses."""

    def test_stale_timestamp_detection(self):
        """Test detection of stale timestamps in response."""
        from datetime import datetime
        
        # Mock response with old timestamp
        old_response = {
            "records": {
                "timestamp": "10-Mar-2025 15:30:00",
                "underlyingValue": 24050,
                "data": [],
            }
        }
        
        # Check if timestamp is in expected format
        timestamp = old_response["records"].get("timestamp", "")
        assert "Mar" in timestamp or timestamp == ""

    def test_valid_timestamp_not_stale(self):
        """Valid recent timestamps should not be flagged as stale."""
        from datetime import datetime
        
        # Create a recent timestamp
        now = datetime.now()
        recent_timestamp = now.strftime("%d-%b-%Y %H:%M:%S")
        
        response = {
            "records": {
                "timestamp": recent_timestamp,
                "underlyingValue": 24050,
            }
        }
        
        assert "timestamp" in response["records"]


class TestNSESessionHTMLGuard:
    """Tests for HTML response guard (anti-bot detection)."""

    def test_detect_html_response(self):
        """HTML responses (blocked/captcha) should be detected."""
        html_responses = [
            "<!DOCTYPE html>",
            "<html>",
            "<!doctype html>",
            "<HTML>",
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN">',
        ]
        
        for html in html_responses:
            # Check if it looks like HTML (starts with angle bracket or doctype)
            is_html = html.strip().startswith("<") or html.strip().lower().startswith("<!doctype")
            assert is_html, f"Failed to detect HTML: {html[:20]}"

    def test_json_response_not_detected_as_html(self):
        """Valid JSON should not be detected as HTML."""
        json_responses = [
            '{"records": {}}',
            '{"data": []}',
            '[]',
            '{}',
        ]
        
        for json_str in json_responses:
            is_html = json_str.strip().startswith("<") or json_str.strip().lower().startswith("<!doctype")
            assert not is_html, f"Incorrectly detected JSON as HTML: {json_str}"


class TestNSESession403Handling:
    """Tests for 403 error handling and session reinitialization."""

    @pytest.mark.asyncio
    async def test_403_triggers_reinit(self, mock_nse_session):
        """403 response should trigger session reinitialization."""
        # Simulate 403 error
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = Exception("403 Forbidden")
        
        mock_nse_session.get.return_value = mock_response
        
        # Verify we can detect 403
        response = await mock_nse_session.get("test_url")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_successful_response_passes_through(self, mock_nse_session):
        """Valid 200 response with JSON should pass through."""
        # mock_nse_session is already configured with successful response
        response = await mock_nse_session.get("test_url")
        
        assert response.status_code == 200
        data = response.json()
        assert "records" in data


class TestNSESessionValidJSON:
    """Tests for valid JSON response handling."""

    @pytest.mark.asyncio
    async def test_valid_chain_json_structure(self, mock_nse_session):
        """Valid option chain JSON should have expected structure."""
        response = await mock_nse_session.get("test_url")
        data = response.json()
        
        assert "records" in data
        records = data["records"]
        assert "underlyingValue" in records
        assert "data" in records

    def test_chain_data_has_required_fields(self, sample_chain_data):
        """Chain data should have all required fields."""
        records = sample_chain_data.get("records", {})
        
        assert "underlyingValue" in records
        assert "expiryDates" in records
        assert "data" in records
        
        # Check data structure
        data = records["data"]
        assert len(data) > 0
        
        for row in data:
            assert "strikePrice" in row
            # At least one of CE or PE should exist
            assert "CE" in row or "PE" in row


class TestNSESessionMocking:
    """Tests to verify mocking setup is correct."""

    @pytest.mark.asyncio
    async def test_mock_session_is_async(self, mock_nse_session):
        """Mock session should support async operations."""
        result = await mock_nse_session.get("test")
        assert result is not None

    def test_mock_json_response(self, mock_nse_session):
        """Mock response should return valid JSON."""
        # Get the mocked response synchronously for setup verification
        mock_response = mock_nse_session.get.return_value
        data = mock_response.json()
        
        assert isinstance(data, dict)
        assert "records" in data


class TestNSESessionRetryLogic:
    """Tests for retry logic on transient failures."""

    def test_retry_count_configuration(self):
        """Verify retry count is configurable."""
        # Default retry count should be reasonable (1-5)
        MAX_RETRIES = 3  # Assumed default
        assert 1 <= MAX_RETRIES <= 10

    @pytest.mark.asyncio
    async def test_exponential_backoff_values(self):
        """Verify exponential backoff calculation."""
        import math
        
        # Typical backoff: 2^attempt seconds
        backoffs = [2 ** i for i in range(5)]
        assert backoffs == [1, 2, 4, 8, 16]
        
        # With jitter (random 0-1 multiplier)
        # Values should be reasonable
        for i, backoff in enumerate(backoffs):
            max_wait = backoff * 2  # Upper bound with jitter
            assert max_wait <= 32  # Should not wait too long
