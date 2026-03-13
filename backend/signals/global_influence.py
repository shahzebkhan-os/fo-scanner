"""
Global Market Influence Signal

Aggregates signals from markets that consistently move NIFTY:
- GIFT Nifty futures (direct pre-market proxy)
- US equity futures (risk-on/off)
- Dollar Index (FII flow proxy)
- Crude oil (India macro impact)
- USD/INR currency (FII proxy)
- Asian equity indices (regional sentiment)
- CBOE VIX (global fear gauge)

All data from yfinance (free, no API key needed).
Cached aggressively — most of these change slowly intraday.

Score: -1.0 (all global signals bearish) to +1.0 (all bullish)
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
import pytz

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.UTC

# Tickers (yfinance symbols)
TICKERS = {
    "gift_nifty": "^NSEI",       # Fallback - NIFTY index as proxy
    "sp500_fut": "ES=F",
    "nasdaq_fut": "NQ=F",
    "dow_fut": "YM=F",
    "dxy": "DX-Y.NYB",
    "crude_wti": "CL=F",
    "brent": "BZ=F",
    "usdinr": "INR=X",
    "hang_seng": "^HSI",
    "nikkei": "^N225",
    "shanghai": "000001.SS",
    "vix_cboe": "^VIX",
}

# Weights: pre-market = GIFT Nifty + US futures dominate; intraday = macro + Asia
WEIGHTS_PREMARKET = {
    "gift_nifty": 0.30,
    "sp500_fut": 0.20,
    "nasdaq_fut": 0.10,
    "dxy": 0.15,
    "crude_wti": 0.10,
    "usdinr": 0.10,
    "vix_cboe": 0.05,
}
WEIGHTS_INTRADAY = {
    "sp500_fut": 0.20,
    "dxy": 0.20,
    "crude_wti": 0.15,
    "usdinr": 0.15,
    "vix_cboe": 0.15,
    "hang_seng": 0.10,
    "nikkei": 0.05,
}

# Directional: positive = same direction as NIFTY, negative = inverse
# DXY/-0.8: strong dollar = FII outflows; crude/-0.5: India is importer; VIX/-0.9: fear = EM selling
DIRECTIONAL_MULTIPLIER = {
    "gift_nifty": +1.0,
    "sp500_fut": +0.7,
    "nasdaq_fut": +0.6,
    "dow_fut": +0.5,
    "dxy": -0.8,
    "crude_wti": -0.5,
    "brent": -0.5,
    "usdinr": -0.7,
    "hang_seng": +0.4,
    "nikkei": +0.3,
    "shanghai": +0.2,
    "vix_cboe": -0.9,
}

# Cache TTL seconds per ticker
CACHE_TTL = {
    "gift_nifty": 30,
    "sp500_fut": 60,
    "nasdaq_fut": 60,
    "dxy": 120,
    "crude_wti": 120,
    "usdinr": 90,
    "vix_cboe": 60,
    "hang_seng": 180,
    "nikkei": 180,
    "shanghai": 180,
}


@dataclass
class MarketSnapshot:
    name: str
    pct_change: float
    current: float
    signal_contribution: float   # After directional multiplier
    timestamp: datetime


@dataclass
class GlobalInfluenceResult:
    score: float                 # -1.0 to +1.0
    confidence: float            # 0.0 to 1.0
    reason: str
    markets: list = field(default_factory=list)
    is_premarket: bool = False
    dominant_driver: Optional[str] = None   # Biggest single contributor


class GlobalInfluenceSignal:
    """
    Fetches and aggregates global market signals.
    Uses yfinance with aggressive caching to avoid rate limits.
    Falls back gracefully when individual tickers are unavailable.
    """

    def __init__(self):
        self._cache: dict[str, tuple[float, float, datetime]] = {}
        # {ticker: (pct_change, current_price, fetched_at)}

    def _is_premarket(self) -> bool:
        now = datetime.now(IST)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        return now < market_open

    def _cache_valid(self, name: str) -> bool:
        if name not in self._cache:
            return False
        _, _, fetched_at = self._cache[name]
        ttl = CACHE_TTL.get(name, 120)
        return (datetime.now(IST) - fetched_at).total_seconds() < ttl

    async def _fetch_pct_change(self, name: str, ticker_sym: str) -> Optional[float]:
        """
        Fetch % change for one ticker via yfinance.
        Returns None on failure — caller handles missing data gracefully.
        """
        if self._cache_valid(name):
            pct, price, _ = self._cache[name]
            return pct

        if not YF_AVAILABLE:
            return None

        try:
            def _fetch():
                t = yf.Ticker(ticker_sym)
                try:
                    info = t.fast_info    # Lightweight — no full info dict
                    prev_close = info.previous_close
                    current = info.last_price
                except Exception:
                    # Fallback to history if fast_info fails
                    hist = t.history(period="2d")
                    if len(hist) >= 2:
                        prev_close = hist["Close"].iloc[-2]
                        current = hist["Close"].iloc[-1]
                    else:
                        return None, None
                
                if prev_close and current and prev_close > 0:
                    return ((current - prev_close) / prev_close) * 100, current
                return None, None

            pct, price = await asyncio.to_thread(_fetch)
            if pct is not None:
                self._cache[name] = (pct, price, datetime.now(IST))
                return pct

        except Exception:
            pass

        return None

    async def compute(self) -> GlobalInfluenceResult:
        """
        Compute the composite global influence score.
        Fetches all configured tickers concurrently.
        """
        is_pre = self._is_premarket()
        weights = WEIGHTS_PREMARKET if is_pre else WEIGHTS_INTRADAY

        # Fetch all tickers concurrently with timeout
        results = {}
        for name in weights.keys():
            if name not in TICKERS:
                continue
            try:
                pct = await asyncio.wait_for(
                    self._fetch_pct_change(name, TICKERS[name]),
                    timeout=5.0
                )
                results[name] = pct
            except asyncio.TimeoutError:
                results[name] = None
            except Exception:
                results[name] = None

        # Compute weighted score
        total_weight = 0.0
        weighted_sum = 0.0
        markets = []
        contributions = {}

        for name, pct in results.items():
            if pct is None:
                continue

            weight = weights.get(name, 0.0)
            multiplier = DIRECTIONAL_MULTIPLIER.get(name, 1.0)

            # Normalize pct change to -1..+1 using tanh (3% move = ~0.9 score)
            normalized = np.tanh(pct * multiplier / 2.0)
            contribution = normalized * weight

            weighted_sum += contribution
            total_weight  += weight
            contributions[name] = contribution

            cached = self._cache.get(name, (0, 0, None))
            markets.append(MarketSnapshot(
                name=name,
                pct_change=round(pct, 3),
                current=cached[1] if cached[1] else 0,
                signal_contribution=round(contribution, 4),
                timestamp=datetime.now(IST),
            ))

        if total_weight < 0.1:
            return GlobalInfluenceResult(
                score=0.0, confidence=0.0,
                reason="insufficient_data: no global markets available",
                is_premarket=is_pre,
            )

        # Normalize by actual weight collected (handles missing tickers gracefully)
        raw_score = weighted_sum / total_weight
        score     = round(max(-1.0, min(1.0, raw_score)), 4)

        # Confidence = fraction of expected weight that was actually fetched
        expected_weight = sum(weights.values())
        confidence = round(min(0.95, total_weight / expected_weight), 4)

        # Dominant driver (largest absolute contributor)
        dominant = max(contributions, key=lambda k: abs(contributions[k])) \
            if contributions else None

        # Build reason string
        top_3 = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        reason_parts = [f"{n}:{'+' if v > 0 else ''}{v:.2f}" for n, v in top_3]
        sentiment = "bullish" if score > 0.2 else ("bearish" if score < -0.2 else "neutral")
        reason = f"global_{sentiment} [{', '.join(reason_parts)}]"

        return GlobalInfluenceResult(
            score=score,
            confidence=confidence,
            reason=reason,
            markets=sorted(markets, key=lambda m: abs(m.signal_contribution), reverse=True),
            is_premarket=is_pre,
            dominant_driver=dominant,
        )


# Module-level singleton for use in scan endpoint
_global_signal = GlobalInfluenceSignal()


async def get_global_influence() -> GlobalInfluenceResult:
    """
    Convenience function to get global influence from singleton.
    Use this from main.py scan endpoint.
    """
    return await _global_signal.compute()
