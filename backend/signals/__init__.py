"""
signals/ — 12-Signal Engine (Accuracy Core)

These signals are computed on every scan cycle and fed to the strategy selector.
Each signal returns a score from -1.0 (strongly bearish) to +1.0 (strongly bullish),
plus a confidence (0–1) and a reason string.
"""

from .base import BaseSignal, SignalResult
from .oi_analysis import OiSignal
from .iv_analysis import IvSignal
from .max_pain import MaxPainSignal
from .price_action import PriceActionSignal
from .technicals import TechnicalSignal
from .global_cues import GlobalCuesSignal
from .fii_dii import FiiDiiSignal
from .straddle_pricing import StraddleSignal
from .news_scanner import NewsSignal
from .greeks_signal import GreeksSignal
from .oi_velocity import OiVelocitySignal
from .engine import MasterSignalEngine

__all__ = [
    "BaseSignal",
    "SignalResult",
    "OiSignal",
    "IvSignal",
    "MaxPainSignal",
    "PriceActionSignal",
    "TechnicalSignal",
    "GlobalCuesSignal",
    "FiiDiiSignal",
    "StraddleSignal",
    "NewsSignal",
    "GreeksSignal",
    "OiVelocitySignal",
    "MasterSignalEngine",
]
