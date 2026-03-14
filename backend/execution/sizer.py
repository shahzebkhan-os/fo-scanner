"""
execution/sizer.py — Options Position Sizer

Calculates appropriate lot sizes based on:
- Signal strength and confidence
- Max loss per trade
- Bankroll size
- Strategy risk profile

Size calculation:
- Defined-risk strategies (spreads, condors): max_loss_per_trade = max_loss_inr * lots
  lots = floor(MAX_LOSS_PER_TRADE_INR / strategy.max_loss_per_lot)
- Undefined-risk strategies (short straddle): use margin requirement
  lots = floor(bankroll * MAX_UNDEFINED_RISK_PCT / margin_per_lot)
- Never exceed MAX_LOTS_PER_TRADE (NIFTY: 20, BANKNIFTY: 15 — configurable)
- Apply Kelly fraction: lots = lots * KELLY_FRACTION (default 0.5)
"""

from __future__ import annotations
from typing import Dict, Optional
from dataclasses import dataclass
import math


@dataclass
class SizingResult:
    """Result of position sizing calculation."""
    lots: int
    max_loss: float
    margin_required: float
    reason: str
    kelly_adjusted: bool
    
    def to_dict(self) -> dict:
        return {
            "lots": self.lots,
            "max_loss": round(self.max_loss, 2),
            "margin_required": round(self.margin_required, 2),
            "reason": self.reason,
            "kelly_adjusted": self.kelly_adjusted,
        }


class OptionsSizer:
    """
    Options Position Sizer — calculates appropriate lot sizes.
    
    Considers:
    - Strategy risk profile (defined vs. undefined risk)
    - Signal confidence
    - Bankroll and risk limits
    - Kelly criterion adjustment
    """
    
    # Maximum lots per trade by symbol
    MAX_LOTS = {
        "NIFTY": 20,
        "BANKNIFTY": 15,
        "FINNIFTY": 20,
    }
    
    # Default lot sizes
    LOT_SIZES = {
        "NIFTY": 75,
        "BANKNIFTY": 35,
        "FINNIFTY": 65,
    }
    
    # Default risk parameters (can be overridden in constructor)
    DEFAULT_MAX_LOSS_PER_TRADE_PCT = 0.02     # 2% of bankroll per trade
    DEFAULT_MAX_UNDEFINED_RISK_PCT = 0.10     # 10% of bankroll for undefined risk
    DEFAULT_KELLY_FRACTION = 0.5              # Half-Kelly for conservative sizing
    
    # Defined risk strategies
    DEFINED_RISK_STRATEGIES = [
        "bull_call_spread",
        "bear_put_spread",
        "iron_condor",
        "iron_butterfly",
        "credit_spread",
        "debit_spread",
        "butterfly",
        "long_call",
        "long_put",
        "long_straddle",
        "long_strangle",
    ]
    
    # Undefined risk strategies
    UNDEFINED_RISK_STRATEGIES = [
        "short_straddle",
        "short_strangle",
        "naked_call",
        "naked_put",
        "ratio_spread",
    ]
    
    def __init__(
        self,
        bankroll: float = 500000,      # Default 5 lakh
        max_loss_per_trade: float = None,
        max_loss_per_trade_pct: float = None,
        max_undefined_risk_pct: float = None,
        kelly_fraction: float = None,
    ):
        """
        Initialize the sizer.
        
        Args:
            bankroll: Total available capital (INR)
            max_loss_per_trade: Maximum loss per trade (INR), overrides percentage
            max_loss_per_trade_pct: Max loss as percentage of bankroll (0-1), default 0.02
            max_undefined_risk_pct: Max undefined risk as percentage (0-1), default 0.10
            kelly_fraction: Kelly criterion fraction (0-1), defaults to 0.5
        """
        self.bankroll = bankroll
        self.max_loss_pct = max_loss_per_trade_pct or self.DEFAULT_MAX_LOSS_PER_TRADE_PCT
        self.max_undefined_risk_pct = max_undefined_risk_pct or self.DEFAULT_MAX_UNDEFINED_RISK_PCT
        self.kelly_fraction = kelly_fraction or self.DEFAULT_KELLY_FRACTION
        self.max_loss_per_trade = max_loss_per_trade or (bankroll * self.max_loss_pct)
    
    def calculate_lots(
        self,
        strategy_name: str,
        symbol: str,
        max_loss_per_lot: float,
        margin_per_lot: float = 0.0,
        confidence: float = 0.7,
        signal_score: float = 0.5,
        regime_multiplier: float = 1.0,
        **kwargs
    ) -> SizingResult:
        """
        Calculate appropriate lot size for a trade.
        
        Args:
            strategy_name: Name of the strategy
            symbol: Underlying symbol (NIFTY, BANKNIFTY)
            max_loss_per_lot: Maximum loss per lot for this strategy (INR)
            margin_per_lot: Margin required per lot (for undefined risk)
            confidence: Signal confidence (0-1)
            signal_score: Signal score magnitude (0-1)
            regime_multiplier: Size multiplier from regime (0.4-1.0)
            
        Returns:
            SizingResult with calculated lots and details
        """
        # Get max lots for symbol
        max_lots = self.MAX_LOTS.get(symbol, 10)
        lot_size = self.LOT_SIZES.get(symbol, 50)
        
        # Determine if defined or undefined risk
        is_defined_risk = strategy_name.lower() in [s.lower() for s in self.DEFINED_RISK_STRATEGIES]
        
        if is_defined_risk:
            lots, reason = self._size_defined_risk(
                max_loss_per_lot, max_lots
            )
        else:
            lots, reason = self._size_undefined_risk(
                margin_per_lot, max_lots
            )
        
        # Apply Kelly fraction based on edge (confidence × score)
        edge = confidence * abs(signal_score)
        kelly_lots = self._apply_kelly(lots, edge)
        kelly_adjusted = kelly_lots < lots
        
        if kelly_adjusted:
            reason += f" (Kelly adjusted: {lots}→{kelly_lots})"
            lots = kelly_lots
        
        # Apply regime multiplier
        regime_lots = max(1, int(lots * regime_multiplier))
        if regime_lots < lots:
            reason += f" (Regime: ×{regime_multiplier})"
            lots = regime_lots
        
        # Never exceed max lots
        lots = min(lots, max_lots)
        
        # Ensure at least 1 lot
        lots = max(1, lots)
        
        # Calculate actual max loss and margin
        actual_max_loss = lots * max_loss_per_lot
        actual_margin = lots * margin_per_lot if margin_per_lot > 0 else 0
        
        return SizingResult(
            lots=lots,
            max_loss=actual_max_loss,
            margin_required=actual_margin,
            reason=reason,
            kelly_adjusted=kelly_adjusted,
        )
    
    def _size_defined_risk(
        self, max_loss_per_lot: float, max_lots: int
    ) -> tuple[int, str]:
        """
        Size for defined risk strategies.
        
        lots = floor(MAX_LOSS_PER_TRADE / max_loss_per_lot)
        """
        if max_loss_per_lot <= 0:
            return 1, "Default 1 lot (no max loss data)"
        
        lots = math.floor(self.max_loss_per_trade / max_loss_per_lot)
        lots = min(lots, max_lots)
        lots = max(1, lots)
        
        reason = f"Defined risk: {self.max_loss_per_trade:.0f} / {max_loss_per_lot:.0f} = {lots} lots"
        return lots, reason
    
    def _size_undefined_risk(
        self, margin_per_lot: float, max_lots: int
    ) -> tuple[int, str]:
        """
        Size for undefined risk strategies.
        
        lots = floor(bankroll × max_undefined_risk_pct / margin_per_lot)
        """
        if margin_per_lot <= 0:
            return 1, "Default 1 lot (no margin data)"
        
        max_margin = self.bankroll * self.max_undefined_risk_pct
        lots = math.floor(max_margin / margin_per_lot)
        lots = min(lots, max_lots)
        lots = max(1, lots)
        
        reason = f"Undefined risk: {max_margin:.0f} / {margin_per_lot:.0f} = {lots} lots"
        return lots, reason
    
    def _apply_kelly(self, lots: int, edge: float) -> int:
        """
        Apply Kelly criterion adjustment.
        
        Full Kelly would be: f* = p - q/b = edge
        We use half-Kelly for safety: f = edge × KELLY_FRACTION
        """
        if edge <= 0:
            return 1  # Minimum lot
        
        # Kelly fraction scales position by edge
        adjusted = lots * edge * self.kelly_fraction
        return max(1, int(adjusted))
    
    def calculate_spread_max_loss(
        self,
        long_strike: float,
        short_strike: float,
        premium_paid: float,
        premium_received: float,
        lot_size: int = 50,
    ) -> float:
        """
        Calculate max loss for a vertical spread.
        
        For credit spread: max_loss = (strike_width - net_premium) × lot_size
        For debit spread: max_loss = net_premium_paid × lot_size
        """
        strike_width = abs(long_strike - short_strike)
        net_premium = premium_received - premium_paid
        
        if net_premium > 0:
            # Credit spread
            max_loss = (strike_width - net_premium) * lot_size
        else:
            # Debit spread
            max_loss = abs(net_premium) * lot_size
        
        return max_loss
    
    def calculate_iron_condor_max_loss(
        self,
        call_spread_width: float,
        put_spread_width: float,
        net_premium: float,
        lot_size: int = 50,
    ) -> float:
        """
        Calculate max loss for an iron condor.
        
        max_loss = max(call_spread_width, put_spread_width) - net_premium
        """
        max_width = max(call_spread_width, put_spread_width)
        max_loss = (max_width - net_premium) * lot_size
        return max(0, max_loss)
    
    def calculate_straddle_max_loss(
        self,
        straddle_price: float,
        lot_size: int = 50,
        is_long: bool = True,
    ) -> float:
        """
        Calculate max loss for a straddle.
        
        Long straddle: max_loss = premium_paid (limited)
        Short straddle: max_loss = unlimited (use margin)
        """
        if is_long:
            return straddle_price * lot_size
        else:
            # Short straddle - return theoretical max (2x premium as approximation)
            return straddle_price * lot_size * 2
    
    def update_bankroll(self, new_bankroll: float):
        """Update bankroll and recalculate max loss per trade."""
        self.bankroll = new_bankroll
        self.max_loss_per_trade = new_bankroll * self.max_loss_pct
    
    def set_max_loss_per_trade(self, max_loss: float):
        """Set fixed max loss per trade."""
        self.max_loss_per_trade = max_loss
    
    def to_dict(self) -> dict:
        """Return current configuration."""
        return {
            "bankroll": self.bankroll,
            "max_loss_per_trade": self.max_loss_per_trade,
            "max_loss_pct": self.max_loss_pct,
            "max_undefined_risk_pct": self.max_undefined_risk_pct,
            "kelly_fraction": self.kelly_fraction,
            "max_lots": self.MAX_LOTS,
            "lot_sizes": self.LOT_SIZES,
        }
