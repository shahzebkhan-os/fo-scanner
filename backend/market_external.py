"""
market_external.py — External Market Data Fetcher

Fetches and caches global market indicators used for sentiment analysis:
  - US markets (S&P 500, NASDAQ) overnight % changes
  - Dollar Index (DXY) level and direction
  - Crude Oil (WTI) level and direction
  - USD/INR exchange rate
  - India VIX (CBOE VIX proxy, used as general volatility gauge)
  - NIFTY 50 previous close (for gap computation)

Results are cached for 30 minutes to avoid excessive API calls during scan cycles.

Uses yfinance (already in requirements.txt) for all data.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

# ── In-memory cache ────────────────────────────────────────────────────────────
_market_cache: dict = {}
_cache_timestamp: Optional[datetime] = None
CACHE_TTL_SECONDS = 1800  # 30 minutes


async def fetch_external_market_data(force_refresh: bool = False) -> dict:
    """
    Fetch global market data with 30-minute in-memory caching.

    Returns a dict with keys:
      spx_change_pct     — S&P 500 previous-day % change
      nasdaq_change_pct  — NASDAQ previous-day % change
      spx_current        — S&P 500 latest close
      nasdaq_current     — NASDAQ latest close
      dxy                — Dollar Index (current)
      dxy_prev           — Dollar Index (previous day)
      crude_oil          — WTI crude price (current)
      crude_prev         — WTI crude price (previous day)
      usdinr             — USD/INR rate (current)
      usdinr_prev        — USD/INR rate (previous day)
      india_vix          — CBOE VIX (US volatility, proxy for global risk)
      nifty_prev_close   — NIFTY 50 previous close (for gap estimate)
      last_updated       — ISO timestamp of the last successful fetch
      source             — data source label
      cached             — True if returned from cache
      stale              — True if returning old data due to fetch failure
    """
    global _market_cache, _cache_timestamp

    now = datetime.now(IST)
    if (
        not force_refresh
        and _cache_timestamp
        and (now - _cache_timestamp).total_seconds() < CACHE_TTL_SECONDS
        and _market_cache
    ):
        return {**_market_cache, "cached": True, "stale": False}

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, _fetch_yfinance_sync)
    except Exception as e:
        log.error(f"External market data fetch failed: {e}")
        data = {}

    if data:
        _market_cache = data
        _cache_timestamp = now
        return {**data, "cached": False, "stale": False}

    if _market_cache:
        log.warning("Returning stale external market data cache due to fetch failure")
        return {**_market_cache, "cached": True, "stale": True}

    return _default_data()


def _fetch_yfinance_sync() -> dict:
    """
    Synchronous yfinance fetch — runs inside a thread executor.

    Downloads 5 days of daily OHLCV data for all tickers and extracts
    the two most-recent closes to compute percentage changes.
    """
    import yfinance as yf

    tickers = ["^GSPC", "^IXIC", "DX-Y.NYB", "CL=F", "INR=X", "^VIX", "^NSEI"]

    try:
        raw = yf.download(
            tickers,
            period="5d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        log.error(f"yfinance.download failed: {e}")
        return {}

    # Handle both single and multi-level column DataFrames
    if hasattr(raw.columns, "levels"):
        closes = raw["Close"]
    else:
        closes = raw

    def _prev_curr(ticker: str) -> tuple[float, float]:
        """Return (prev_close, curr_close) for a ticker."""
        try:
            series = closes[ticker].dropna()
            if len(series) >= 2:
                return float(series.iloc[-2]), float(series.iloc[-1])
            elif len(series) == 1:
                v = float(series.iloc[-1])
                return v, v
        except Exception:
            pass
        return 0.0, 0.0

    spx_prev, spx_curr = _prev_curr("^GSPC")
    nq_prev, nq_curr = _prev_curr("^IXIC")
    dxy_prev, dxy_curr = _prev_curr("DX-Y.NYB")
    crude_prev, crude_curr = _prev_curr("CL=F")
    inr_prev, inr_curr = _prev_curr("INR=X")
    vix_prev, vix_curr = _prev_curr("^VIX")
    nifty_prev, _nifty_curr = _prev_curr("^NSEI")

    spx_change = round((spx_curr - spx_prev) / spx_prev * 100, 2) if spx_prev > 0 else 0.0
    nasdaq_change = round((nq_curr - nq_prev) / nq_prev * 100, 2) if nq_prev > 0 else 0.0

    return {
        "spx_change_pct": spx_change,
        "nasdaq_change_pct": nasdaq_change,
        "spx_current": round(spx_curr, 2),
        "nasdaq_current": round(nq_curr, 2),
        "dxy": round(dxy_curr, 3),
        "dxy_prev": round(dxy_prev, 3),
        "crude_oil": round(crude_curr, 2),
        "crude_prev": round(crude_prev, 2),
        "usdinr": round(inr_curr, 2),
        "usdinr_prev": round(inr_prev, 2),
        "india_vix": round(vix_curr, 2),
        "nifty_prev_close": round(nifty_prev, 2),
        "last_updated": datetime.now(IST).isoformat(),
        "source": "Yahoo Finance",
    }


def _default_data() -> dict:
    """Return zero-value defaults when no data is available."""
    return {
        "spx_change_pct": 0.0,
        "nasdaq_change_pct": 0.0,
        "spx_current": 0.0,
        "nasdaq_current": 0.0,
        "dxy": 0.0,
        "dxy_prev": 0.0,
        "crude_oil": 0.0,
        "crude_prev": 0.0,
        "usdinr": 0.0,
        "usdinr_prev": 0.0,
        "india_vix": 0.0,
        "nifty_prev_close": 0.0,
        "last_updated": None,
        "source": "unavailable",
        "cached": False,
        "stale": False,
    }


def get_cached_data() -> dict:
    """Return current cached data without triggering a fetch. Useful for sync contexts."""
    return {**_market_cache} if _market_cache else _default_data()
