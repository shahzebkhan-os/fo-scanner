"""
watcher/state.py — Options Trade State

Manages the state of options trades (both paper and live).

Fields:
- trade_id: UUID
- strategy_name: str          (e.g. "iron_condor", "bull_call_spread")
- legs: List[TradeLeg]        (each leg = one options contract)
  Each TradeLeg:
  - tradingsymbol: str        (e.g. "NIFTY24DEC24000CE")
  - instrument_token: int
  - transaction_type: str     ("BUY" or "SELL")
  - qty_lots: int
  - entry_price: float        (premium in INR per unit)
  - current_price: float
  - entry_delta: float
  - entry_iv: float
  - entry_theta: float
  - entry_vega: float
- underlying: str             ("NIFTY" or "BANKNIFTY")
- underlying_price_at_entry: float
- expiry: date
- dte_at_entry: int
- max_profit: float           (INR, capped for spreads)
- max_loss: float             (INR, defined for defined-risk strategies)
- current_pnl: float
- target_pnl: float           (take profit in INR)
- stop_loss_pnl: float        (cut loss at this INR loss)
- status: Literal["PAPER_OPEN","PAPER_CLOSED","LIVE_OPEN","LIVE_CLOSED","CANCELLED"]
- regime_at_entry: str
- signal_scores_at_entry: dict
- paper_mode: bool

Methods:
- update_prices(leg_prices: dict) → recalculate current_pnl
- net_greeks() → {"delta": float, "theta": float, "vega": float, "gamma": float}
- is_near_expiry() → bool (DTE <= 1)
- pnl_percent() → float (current_pnl / max_loss * 100)
- to_event_dict() → dict
"""

from __future__ import annotations
import uuid
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class TradeStatus(str, Enum):
    """Trade status enumeration."""
    PAPER_OPEN = "PAPER_OPEN"
    PAPER_CLOSED = "PAPER_CLOSED"
    LIVE_OPEN = "LIVE_OPEN"
    LIVE_CLOSED = "LIVE_CLOSED"
    CANCELLED = "CANCELLED"


@dataclass
class TradeLeg:
    """
    Represents a single leg of an options trade.
    
    Each leg is one options contract with its entry and current state.
    """
    tradingsymbol: str
    instrument_token: int
    transaction_type: Literal["BUY", "SELL"]
    qty_lots: int
    entry_price: float
    current_price: float = 0.0
    strike: float = 0.0
    option_type: Literal["CE", "PE"] = "CE"
    
    # Greeks at entry
    entry_delta: float = 0.0
    entry_iv: float = 0.0
    entry_theta: float = 0.0
    entry_vega: float = 0.0
    entry_gamma: float = 0.0
    
    # Current Greeks
    current_delta: float = 0.0
    current_theta: float = 0.0
    current_vega: float = 0.0
    current_gamma: float = 0.0
    
    def pnl(self, lot_size: int = 1) -> float:
        """Calculate P&L for this leg."""
        price_change = self.current_price - self.entry_price
        direction = 1 if self.transaction_type == "BUY" else -1
        return price_change * direction * self.qty_lots * lot_size
    
    def to_dict(self) -> dict:
        return {
            "tradingsymbol": self.tradingsymbol,
            "instrument_token": self.instrument_token,
            "transaction_type": self.transaction_type,
            "qty_lots": self.qty_lots,
            "entry_price": round(self.entry_price, 2),
            "current_price": round(self.current_price, 2),
            "strike": self.strike,
            "option_type": self.option_type,
            "entry_delta": round(self.entry_delta, 4),
            "entry_iv": round(self.entry_iv, 2),
            "entry_theta": round(self.entry_theta, 4),
            "entry_vega": round(self.entry_vega, 4),
            "entry_gamma": round(self.entry_gamma, 6),
        }


@dataclass
class OptionsTradeState:
    """
    Complete state of an options trade.
    
    Tracks multi-leg strategies with entry, current state, and P&L.
    """
    # Identification
    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strategy_name: str = ""
    
    # Trade legs
    legs: List[TradeLeg] = field(default_factory=list)
    
    # Underlying info
    underlying: str = "NIFTY"
    underlying_price_at_entry: float = 0.0
    current_underlying_price: float = 0.0
    expiry: Optional[date] = None
    dte_at_entry: int = 30
    
    # Lot size (for P&L calculation)
    lot_size: int = 50
    
    # Risk parameters
    max_profit: float = 0.0      # Max profit possible (INR)
    max_loss: float = 0.0        # Max loss possible (INR)
    current_pnl: float = 0.0     # Current P&L (INR)
    target_pnl: float = 0.0      # Take profit level (INR)
    stop_loss_pnl: float = 0.0   # Stop loss level (INR, negative)
    
    # Status
    status: TradeStatus = TradeStatus.PAPER_OPEN
    paper_mode: bool = True
    
    # Entry context
    regime_at_entry: str = ""
    signal_scores_at_entry: Dict = field(default_factory=dict)
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: Optional[datetime] = None
    exit_reason: str = ""
    
    def update_prices(self, leg_prices: Dict[str, float]) -> float:
        """
        Update leg prices and recalculate current P&L.
        
        Args:
            leg_prices: Dict mapping tradingsymbol to current price
            
        Returns:
            Updated current_pnl
        """
        total_pnl = 0.0
        
        for leg in self.legs:
            if leg.tradingsymbol in leg_prices:
                leg.current_price = leg_prices[leg.tradingsymbol]
            
            total_pnl += leg.pnl(self.lot_size)
        
        self.current_pnl = total_pnl
        return self.current_pnl
    
    def update_underlying_price(self, price: float):
        """Update current underlying price."""
        self.current_underlying_price = price
    
    def net_greeks(self) -> Dict[str, float]:
        """
        Calculate net Greeks for the entire position.
        
        Returns:
            Dict with net delta, theta, vega, gamma
        """
        net_delta = 0.0
        net_theta = 0.0
        net_vega = 0.0
        net_gamma = 0.0
        
        for leg in self.legs:
            direction = 1 if leg.transaction_type == "BUY" else -1
            qty = leg.qty_lots * self.lot_size
            
            net_delta += (leg.current_delta or leg.entry_delta) * direction * qty
            net_theta += (leg.current_theta or leg.entry_theta) * direction * qty
            net_vega += (leg.current_vega or leg.entry_vega) * direction * qty
            net_gamma += (leg.current_gamma or leg.entry_gamma) * direction * qty
        
        return {
            "delta": round(net_delta, 4),
            "theta": round(net_theta, 4),
            "vega": round(net_vega, 4),
            "gamma": round(net_gamma, 6),
        }
    
    def is_near_expiry(self) -> bool:
        """Check if trade is near expiry (DTE <= 1)."""
        if self.expiry is None:
            return False
        
        today = date.today()
        dte = (self.expiry - today).days
        return dte <= 1
    
    def current_dte(self) -> int:
        """Get current days to expiry."""
        if self.expiry is None:
            return self.dte_at_entry
        
        today = date.today()
        return max(0, (self.expiry - today).days)
    
    def pnl_percent(self) -> float:
        """
        Calculate P&L as percentage of max loss.
        
        Returns:
            Positive for profit, negative for loss (as % of max loss)
        """
        if self.max_loss == 0:
            return 0.0
        
        return (self.current_pnl / abs(self.max_loss)) * 100
    
    def should_take_profit(self) -> bool:
        """Check if trade has reached take profit target."""
        if self.target_pnl <= 0:
            return False
        return self.current_pnl >= self.target_pnl
    
    def should_stop_loss(self) -> bool:
        """Check if trade has reached stop loss."""
        if self.stop_loss_pnl >= 0:
            return False
        return self.current_pnl <= self.stop_loss_pnl
    
    def close_trade(self, reason: str = ""):
        """Mark trade as closed."""
        if self.paper_mode:
            self.status = TradeStatus.PAPER_CLOSED
        else:
            self.status = TradeStatus.LIVE_CLOSED
        
        self.exit_time = datetime.now()
        self.exit_reason = reason
    
    def cancel_trade(self, reason: str = ""):
        """Mark trade as cancelled."""
        self.status = TradeStatus.CANCELLED
        self.exit_time = datetime.now()
        self.exit_reason = reason
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "trade_id": self.trade_id,
            "strategy_name": self.strategy_name,
            "legs": [leg.to_dict() for leg in self.legs],
            "underlying": self.underlying,
            "underlying_price_at_entry": round(self.underlying_price_at_entry, 2),
            "current_underlying_price": round(self.current_underlying_price, 2),
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "dte_at_entry": self.dte_at_entry,
            "current_dte": self.current_dte(),
            "lot_size": self.lot_size,
            "max_profit": round(self.max_profit, 2),
            "max_loss": round(self.max_loss, 2),
            "current_pnl": round(self.current_pnl, 2),
            "target_pnl": round(self.target_pnl, 2),
            "stop_loss_pnl": round(self.stop_loss_pnl, 2),
            "pnl_percent": round(self.pnl_percent(), 2),
            "status": self.status.value,
            "paper_mode": self.paper_mode,
            "regime_at_entry": self.regime_at_entry,
            "net_greeks": self.net_greeks(),
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_reason": self.exit_reason,
        }
    
    def to_event_dict(self) -> dict:
        """
        Convert to event dictionary for logging/streaming.
        
        Simplified format for real-time updates.
        """
        return {
            "trade_id": self.trade_id,
            "strategy": self.strategy_name,
            "underlying": self.underlying,
            "status": self.status.value,
            "pnl": round(self.current_pnl, 2),
            "pnl_percent": round(self.pnl_percent(), 2),
            "dte": self.current_dte(),
            "net_greeks": self.net_greeks(),
            "timestamp": datetime.now().isoformat(),
        }


class TradeWatcher:
    """
    Manages and monitors multiple OptionsTradeState instances.
    """
    
    def __init__(self):
        self.trades: Dict[str, OptionsTradeState] = {}
    
    def register(self, trade: OptionsTradeState):
        """Register a trade for monitoring."""
        self.trades[trade.trade_id] = trade
    
    def unregister(self, trade_id: str):
        """Remove a trade from monitoring."""
        if trade_id in self.trades:
            del self.trades[trade_id]
    
    def get_open_trades(self) -> List[OptionsTradeState]:
        """Get all open trades."""
        return [
            t for t in self.trades.values()
            if t.status in [TradeStatus.PAPER_OPEN, TradeStatus.LIVE_OPEN]
        ]
    
    def get_trade(self, trade_id: str) -> Optional[OptionsTradeState]:
        """Get trade by ID."""
        return self.trades.get(trade_id)
    
    def update_all_prices(self, prices: Dict[str, float]):
        """Update prices for all open trades."""
        for trade in self.get_open_trades():
            trade.update_prices(prices)
    
    def check_exits(self) -> List[OptionsTradeState]:
        """Check all trades for exit conditions."""
        trades_to_exit = []
        
        for trade in self.get_open_trades():
            if trade.should_take_profit():
                trades_to_exit.append(trade)
            elif trade.should_stop_loss():
                trades_to_exit.append(trade)
            elif trade.is_near_expiry():
                trades_to_exit.append(trade)
        
        return trades_to_exit
    
    def get_portfolio_greeks(self) -> Dict[str, float]:
        """Get aggregate Greeks across all open positions."""
        total = {"delta": 0.0, "theta": 0.0, "vega": 0.0, "gamma": 0.0}
        
        for trade in self.get_open_trades():
            greeks = trade.net_greeks()
            for key in total:
                total[key] += greeks.get(key, 0)
        
        return {k: round(v, 4) for k, v in total.items()}
    
    def get_total_exposure(self) -> Dict[str, float]:
        """Calculate total exposure metrics."""
        total_max_loss = 0.0
        total_current_pnl = 0.0
        
        for trade in self.get_open_trades():
            total_max_loss += abs(trade.max_loss)
            total_current_pnl += trade.current_pnl
        
        return {
            "total_max_loss": round(total_max_loss, 2),
            "total_current_pnl": round(total_current_pnl, 2),
            "open_trades": len(self.get_open_trades()),
        }
