"""
signals/base.py — Base Signal class and SignalResult dataclass

All signals inherit from BaseSignal and return SignalResult objects.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class SignalResult:
    """
    Standard output for all signal computations.
    
    Attributes:
        score: Float from -1.0 (strongly bearish) to +1.0 (strongly bullish)
        confidence: Float from 0.0 to 1.0 indicating signal reliability
        reason: Human-readable explanation of the signal
        metadata: Optional dict with additional signal-specific data
    """
    score: float
    confidence: float
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate and clamp values to valid ranges."""
        self.score = max(-1.0, min(1.0, self.score))
        self.confidence = max(0.0, min(1.0, self.confidence))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "metadata": self.metadata,
        }


class BaseSignal(ABC):
    """
    Abstract base class for all signal implementations.
    
    Each signal must implement the compute() method that returns a SignalResult.
    """
    
    name: str = "base"
    
    @abstractmethod
    def compute(self, **kwargs) -> SignalResult:
        """
        Compute the signal based on input data.
        
        Args:
            **kwargs: Signal-specific input parameters
            
        Returns:
            SignalResult with score, confidence, reason, and optional metadata
        """
        raise NotImplementedError
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
