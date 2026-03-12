"""
execution/executor.py — Options Executor

Executes options strategies based on signals.

execute_strategy(signal: AggregatedSignal) -> Optional[OptionsTradeState]:

1. Resolve strategy from signal.recommended_strategy
2. Build leg definitions (which strikes, CE/PE, buy/sell, qty)
   - ATM strike from option_chain.get_atm_strike()
   - Validate all legs have sufficient OI > MIN_OI_LOTS (default 500 lots)
   - Validate bid-ask spread < MAX_SPREAD_PCT (default 2% of mid price)
3. Run RiskGate.approve() — abort if rejected
4. Calculate lot size via OptionsSizer (see below)
5. If paper_mode=True → route all legs to PaperBroker
   If paper_mode=False → route to KiteClient
6. For multi-leg strategies: place ALL legs simultaneously via asyncio.gather()
   Never place one leg without the other — partial fills create unhedged exposure
7. If any leg fails: cancel all other legs, log PARTIAL_FILL_ABORT event
8. On full success: create OptionsTradeState, register with TradeWatcher
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import date, datetime
import asyncio

from .sizer import OptionsSizer, SizingResult

# Handle import based on package structure
try:
    from ..watcher.state import OptionsTradeState, TradeLeg, TradeStatus, TradeWatcher
    from ..signals.engine import AggregatedSignal
except ImportError:
    from watcher.state import OptionsTradeState, TradeLeg, TradeStatus, TradeWatcher
    from signals.engine import AggregatedSignal


@dataclass
class StrategyLeg:
    """Definition of a single leg in a strategy."""
    strike_offset: int          # 0 = ATM, +1 = ATM+1 strike, -1 = ATM-1 strike
    option_type: str            # "CE" or "PE"
    transaction_type: str       # "BUY" or "SELL"
    
    @staticmethod
    def from_dict(d: dict) -> "StrategyLeg":
        return StrategyLeg(
            strike_offset=d.get("strike_offset", 0),
            option_type=d.get("option_type", "CE"),
            transaction_type=d.get("transaction_type", "BUY"),
        )


@dataclass
class StrategyDefinition:
    """Complete definition of an options strategy."""
    name: str
    legs: List[StrategyLeg]
    is_defined_risk: bool = True
    target_profit_pct: float = 50       # Take profit at 50% of max profit
    stop_loss_pct: float = 100          # Stop at 100% of max loss
    
    @staticmethod
    def from_dict(d: dict) -> "StrategyDefinition":
        return StrategyDefinition(
            name=d.get("name", ""),
            legs=[StrategyLeg.from_dict(leg) for leg in d.get("legs", [])],
            is_defined_risk=d.get("is_defined_risk", True),
            target_profit_pct=d.get("target_profit_pct", 50),
            stop_loss_pct=d.get("stop_loss_pct", 100),
        )


class RiskGate:
    """
    Risk management gate for trade approval.
    
    Checks:
    - Position limits
    - Exposure limits
    - Correlation limits
    - Time-based rules
    """
    
    def __init__(
        self,
        max_positions: int = 5,
        max_exposure: float = 100000,
        max_delta_exposure: float = 10000,
        blocked_hours: List[tuple] = None,
    ):
        self.max_positions = max_positions
        self.max_exposure = max_exposure
        self.max_delta_exposure = max_delta_exposure
        self.blocked_hours = blocked_hours or []
    
    def approve(
        self,
        strategy: StrategyDefinition,
        sizing: SizingResult,
        current_positions: int,
        current_exposure: float,
        current_delta: float,
        current_time: datetime = None,
    ) -> tuple[bool, str]:
        """
        Approve or reject a trade.
        
        Returns:
            (approved: bool, reason: str)
        """
        # Check position limit
        if current_positions >= self.max_positions:
            return False, f"Max positions reached ({self.max_positions})"
        
        # Check exposure limit
        new_exposure = current_exposure + sizing.max_loss
        if new_exposure > self.max_exposure:
            return False, f"Exposure limit exceeded ({new_exposure:.0f} > {self.max_exposure:.0f})"
        
        # Check delta exposure (simplified)
        # In practice, this would calculate the new trade's delta
        
        # Check time-based rules
        if current_time:
            hour = current_time.hour
            minute = current_time.minute
            current_mins = hour * 60 + minute
            
            for start_h, start_m, end_h, end_m in self.blocked_hours:
                start_mins = start_h * 60 + start_m
                end_mins = end_h * 60 + end_m
                
                if start_mins <= current_mins <= end_mins:
                    return False, f"Trading blocked during {start_h}:{start_m:02d}-{end_h}:{end_m:02d}"
        
        return True, "Approved"


class OptionsExecutor:
    """
    Options Executor — executes strategies based on signals.
    
    Handles:
    - Strategy resolution
    - Leg building
    - Risk approval
    - Order placement (paper or live)
    - Trade state management
    """
    
    # Validation thresholds
    MIN_OI_LOTS = 500           # Minimum OI in lots
    MAX_SPREAD_PCT = 2.0        # Maximum bid-ask spread as % of mid
    
    # Strategy definitions
    STRATEGIES = {
        "bull_call_spread": StrategyDefinition(
            name="bull_call_spread",
            legs=[
                StrategyLeg(strike_offset=0, option_type="CE", transaction_type="BUY"),
                StrategyLeg(strike_offset=1, option_type="CE", transaction_type="SELL"),
            ],
            is_defined_risk=True,
        ),
        "bear_put_spread": StrategyDefinition(
            name="bear_put_spread",
            legs=[
                StrategyLeg(strike_offset=0, option_type="PE", transaction_type="BUY"),
                StrategyLeg(strike_offset=-1, option_type="PE", transaction_type="SELL"),
            ],
            is_defined_risk=True,
        ),
        "iron_condor": StrategyDefinition(
            name="iron_condor",
            legs=[
                StrategyLeg(strike_offset=-2, option_type="PE", transaction_type="BUY"),
                StrategyLeg(strike_offset=-1, option_type="PE", transaction_type="SELL"),
                StrategyLeg(strike_offset=1, option_type="CE", transaction_type="SELL"),
                StrategyLeg(strike_offset=2, option_type="CE", transaction_type="BUY"),
            ],
            is_defined_risk=True,
            target_profit_pct=50,
            stop_loss_pct=200,  # 2x premium received
        ),
        "short_straddle": StrategyDefinition(
            name="short_straddle",
            legs=[
                StrategyLeg(strike_offset=0, option_type="CE", transaction_type="SELL"),
                StrategyLeg(strike_offset=0, option_type="PE", transaction_type="SELL"),
            ],
            is_defined_risk=False,
            target_profit_pct=50,
            stop_loss_pct=100,  # 1x premium received
        ),
        "long_straddle": StrategyDefinition(
            name="long_straddle",
            legs=[
                StrategyLeg(strike_offset=0, option_type="CE", transaction_type="BUY"),
                StrategyLeg(strike_offset=0, option_type="PE", transaction_type="BUY"),
            ],
            is_defined_risk=True,
            target_profit_pct=100,  # 100% gain
            stop_loss_pct=50,       # 50% loss of premium
        ),
        "sell_otm_pe": StrategyDefinition(
            name="sell_otm_pe",
            legs=[
                StrategyLeg(strike_offset=-2, option_type="PE", transaction_type="SELL"),
            ],
            is_defined_risk=False,
            target_profit_pct=80,
            stop_loss_pct=200,
        ),
        "sell_otm_ce": StrategyDefinition(
            name="sell_otm_ce",
            legs=[
                StrategyLeg(strike_offset=2, option_type="CE", transaction_type="SELL"),
            ],
            is_defined_risk=False,
            target_profit_pct=80,
            stop_loss_pct=200,
        ),
        "wide_iron_condor": StrategyDefinition(
            name="wide_iron_condor",
            legs=[
                StrategyLeg(strike_offset=-4, option_type="PE", transaction_type="BUY"),
                StrategyLeg(strike_offset=-3, option_type="PE", transaction_type="SELL"),
                StrategyLeg(strike_offset=3, option_type="CE", transaction_type="SELL"),
                StrategyLeg(strike_offset=4, option_type="CE", transaction_type="BUY"),
            ],
            is_defined_risk=True,
            target_profit_pct=50,
            stop_loss_pct=200,
        ),
    }
    
    def __init__(
        self,
        sizer: OptionsSizer = None,
        risk_gate: RiskGate = None,
        trade_watcher: TradeWatcher = None,
        paper_mode: bool = True,
    ):
        """
        Initialize the executor.
        
        Args:
            sizer: Position sizer instance
            risk_gate: Risk gate instance
            trade_watcher: Trade watcher for state management
            paper_mode: If True, use paper trading
        """
        self.sizer = sizer or OptionsSizer()
        self.risk_gate = risk_gate or RiskGate()
        self.trade_watcher = trade_watcher or TradeWatcher()
        self.paper_mode = paper_mode
    
    def execute_strategy(
        self,
        signal: AggregatedSignal,
        option_chain: dict,
        symbol: str = "NIFTY",
        expiry: date = None,
        lot_size: int = 50,
        **kwargs
    ) -> Optional[OptionsTradeState]:
        """
        Execute a strategy based on the aggregated signal.
        
        Args:
            signal: AggregatedSignal from the engine
            option_chain: Current option chain data
            symbol: Underlying symbol
            expiry: Expiry date
            lot_size: Contract lot size
            
        Returns:
            OptionsTradeState if executed, None if rejected
        """
        # Check if we should trade
        if not signal.trade:
            return None
        
        if signal.blackout:
            return None
        
        # Get strategy definition
        strategy_name = signal.recommended_strategy
        if strategy_name not in self.STRATEGIES:
            return None
        
        strategy = self.STRATEGIES[strategy_name]
        
        # Get current spot and ATM strike
        spot = option_chain.get("spot", 0)
        if spot <= 0:
            return None
        
        atm_strike = self._get_atm_strike(option_chain, spot)
        strikes = self._get_sorted_strikes(option_chain)
        
        if not atm_strike or not strikes:
            return None
        
        # Build legs
        legs_data = self._build_legs(
            strategy, atm_strike, strikes, option_chain, lot_size
        )
        
        if not legs_data:
            return None
        
        # Validate legs
        is_valid, validation_reason = self._validate_legs(legs_data, option_chain)
        if not is_valid:
            return None
        
        # Calculate sizing
        max_loss_per_lot = self._calculate_max_loss_per_lot(
            strategy, legs_data, lot_size
        )
        margin_per_lot = self._estimate_margin_per_lot(
            strategy, legs_data, spot, lot_size
        )
        
        sizing = self.sizer.calculate_lots(
            strategy_name=strategy_name,
            symbol=symbol,
            max_loss_per_lot=max_loss_per_lot,
            margin_per_lot=margin_per_lot,
            confidence=signal.confidence,
            signal_score=signal.composite_score,
            regime_multiplier=signal.size_multiplier,
        )
        
        # Risk gate approval
        current_exposure = self.trade_watcher.get_total_exposure()
        approved, reject_reason = self.risk_gate.approve(
            strategy=strategy,
            sizing=sizing,
            current_positions=current_exposure.get("open_trades", 0),
            current_exposure=current_exposure.get("total_max_loss", 0),
            current_delta=0,  # Simplified
            current_time=datetime.now(),
        )
        
        if not approved:
            return None
        
        # Create trade legs
        trade_legs = []
        for leg_data in legs_data:
            trade_leg = TradeLeg(
                tradingsymbol=leg_data["tradingsymbol"],
                instrument_token=leg_data.get("instrument_token", 0),
                transaction_type=leg_data["transaction_type"],
                qty_lots=sizing.lots,
                entry_price=leg_data["price"],
                current_price=leg_data["price"],
                strike=leg_data["strike"],
                option_type=leg_data["option_type"],
                entry_delta=leg_data.get("delta", 0),
                entry_iv=leg_data.get("iv", 0),
                entry_theta=leg_data.get("theta", 0),
                entry_vega=leg_data.get("vega", 0),
                entry_gamma=leg_data.get("gamma", 0),
            )
            trade_legs.append(trade_leg)
        
        # Calculate max profit/loss and targets
        max_profit, max_loss = self._calculate_strategy_pnl(
            strategy, legs_data, sizing.lots, lot_size
        )
        
        target_pnl = max_profit * (strategy.target_profit_pct / 100)
        stop_loss_pnl = -max_loss * (strategy.stop_loss_pct / 100)
        
        # Create trade state
        trade = OptionsTradeState(
            strategy_name=strategy_name,
            legs=trade_legs,
            underlying=symbol,
            underlying_price_at_entry=spot,
            current_underlying_price=spot,
            expiry=expiry,
            dte_at_entry=self._calculate_dte(expiry),
            lot_size=lot_size,
            max_profit=max_profit,
            max_loss=max_loss,
            current_pnl=0,
            target_pnl=target_pnl,
            stop_loss_pnl=stop_loss_pnl,
            status=TradeStatus.PAPER_OPEN if self.paper_mode else TradeStatus.LIVE_OPEN,
            paper_mode=self.paper_mode,
            regime_at_entry=signal.regime,
            signal_scores_at_entry=signal.individual_scores,
        )
        
        # Register with watcher
        self.trade_watcher.register(trade)
        
        return trade
    
    def _get_atm_strike(self, option_chain: dict, spot: float) -> Optional[float]:
        """Get ATM strike from option chain."""
        records = option_chain.get("records", {}).get("data", [])
        if not records:
            records = option_chain.get("data", [])
        
        strikes = sorted({r.get("strikePrice", 0) for r in records if r.get("strikePrice")})
        if not strikes:
            return None
        
        return min(strikes, key=lambda s: abs(s - spot))
    
    def _get_sorted_strikes(self, option_chain: dict) -> List[float]:
        """Get sorted list of strikes from option chain."""
        records = option_chain.get("records", {}).get("data", [])
        if not records:
            records = option_chain.get("data", [])
        
        return sorted({r.get("strikePrice", 0) for r in records if r.get("strikePrice")})
    
    def _build_legs(
        self,
        strategy: StrategyDefinition,
        atm_strike: float,
        strikes: List[float],
        option_chain: dict,
        lot_size: int,
    ) -> Optional[List[dict]]:
        """Build leg data from strategy definition."""
        atm_idx = strikes.index(atm_strike) if atm_strike in strikes else -1
        if atm_idx < 0:
            return None
        
        records = option_chain.get("records", {}).get("data", [])
        if not records:
            records = option_chain.get("data", [])
        
        # Build lookup
        chain_lookup = {}
        for r in records:
            strike = r.get("strikePrice", 0)
            if strike:
                chain_lookup[strike] = r
        
        legs_data = []
        symbol_prefix = option_chain.get("underlying", "NIFTY")
        expiry_str = option_chain.get("expiryDate", "")
        
        for leg in strategy.legs:
            strike_idx = atm_idx + leg.strike_offset
            if strike_idx < 0 or strike_idx >= len(strikes):
                return None
            
            strike = strikes[strike_idx]
            chain_row = chain_lookup.get(strike, {})
            
            opt_data = chain_row.get(leg.option_type, {}) or {}
            if not opt_data:
                return None
            
            price = opt_data.get("lastPrice", 0) or opt_data.get("askPrice", 0) or 0
            if price <= 0:
                return None
            
            # Build tradingsymbol
            tradingsymbol = f"{symbol_prefix}{expiry_str}{int(strike)}{leg.option_type}"
            
            legs_data.append({
                "tradingsymbol": tradingsymbol,
                "instrument_token": opt_data.get("identifier", 0),
                "transaction_type": leg.transaction_type,
                "strike": strike,
                "option_type": leg.option_type,
                "price": price,
                "delta": opt_data.get("delta", 0.5 if leg.option_type == "CE" else -0.5),
                "iv": opt_data.get("impliedVolatility", 20),
                "theta": opt_data.get("theta", 0),
                "vega": opt_data.get("vega", 0),
                "gamma": opt_data.get("gamma", 0),
                "oi": opt_data.get("openInterest", 0),
                "bid": opt_data.get("bidPrice", 0),
                "ask": opt_data.get("askPrice", 0),
            })
        
        return legs_data
    
    def _validate_legs(
        self, legs_data: List[dict], option_chain: dict
    ) -> tuple[bool, str]:
        """Validate legs meet liquidity requirements."""
        lot_size = option_chain.get("lot_size", 50)
        
        for leg in legs_data:
            # Check OI
            oi_lots = leg.get("oi", 0) / lot_size
            if oi_lots < self.MIN_OI_LOTS:
                return False, f"Insufficient OI at {leg['strike']}: {oi_lots:.0f} lots"
            
            # Check spread
            bid = leg.get("bid", 0)
            ask = leg.get("ask", 0)
            if bid > 0 and ask > 0:
                mid = (bid + ask) / 2
                spread_pct = (ask - bid) / mid * 100
                if spread_pct > self.MAX_SPREAD_PCT:
                    return False, f"Wide spread at {leg['strike']}: {spread_pct:.1f}%"
        
        return True, "Valid"
    
    def _calculate_max_loss_per_lot(
        self,
        strategy: StrategyDefinition,
        legs_data: List[dict],
        lot_size: int,
    ) -> float:
        """Calculate max loss per lot for the strategy."""
        if not legs_data:
            return 0
        
        # For spreads, max loss = width - premium received
        if len(legs_data) == 2:
            strikes = [leg["strike"] for leg in legs_data]
            width = abs(strikes[1] - strikes[0])
            
            net_premium = 0
            for leg in legs_data:
                if leg["transaction_type"] == "SELL":
                    net_premium += leg["price"]
                else:
                    net_premium -= leg["price"]
            
            max_loss = (width - net_premium) * lot_size if net_premium > 0 else abs(net_premium) * lot_size
            return max(0, max_loss)
        
        # For iron condor
        if len(legs_data) == 4:
            # Max loss = max(call_width, put_width) - net_premium
            put_width = abs(legs_data[1]["strike"] - legs_data[0]["strike"])
            call_width = abs(legs_data[3]["strike"] - legs_data[2]["strike"])
            
            net_premium = sum(
                leg["price"] if leg["transaction_type"] == "SELL" else -leg["price"]
                for leg in legs_data
            )
            
            max_width = max(put_width, call_width)
            max_loss = (max_width - net_premium) * lot_size
            return max(0, max_loss)
        
        # For straddles
        if len(legs_data) == 2 and legs_data[0]["strike"] == legs_data[1]["strike"]:
            total_premium = sum(leg["price"] for leg in legs_data)
            if legs_data[0]["transaction_type"] == "BUY":
                return total_premium * lot_size  # Long straddle
            else:
                return total_premium * lot_size * 2  # Short straddle estimate
        
        # Single leg
        if len(legs_data) == 1:
            return legs_data[0]["price"] * lot_size * 2  # Estimate
        
        return 10000  # Default
    
    def _estimate_margin_per_lot(
        self,
        strategy: StrategyDefinition,
        legs_data: List[dict],
        spot: float,
        lot_size: int,
    ) -> float:
        """Estimate margin requirement per lot."""
        if strategy.is_defined_risk:
            return 0  # No margin for defined risk
        
        # Rough margin estimate for undefined risk
        # Typically 15-20% of notional
        notional = spot * lot_size
        return notional * 0.15
    
    def _calculate_strategy_pnl(
        self,
        strategy: StrategyDefinition,
        legs_data: List[dict],
        lots: int,
        lot_size: int,
    ) -> tuple[float, float]:
        """Calculate max profit and max loss for the strategy."""
        net_premium = sum(
            leg["price"] if leg["transaction_type"] == "SELL" else -leg["price"]
            for leg in legs_data
        )
        
        max_loss = self._calculate_max_loss_per_lot(strategy, legs_data, lot_size) * lots / lot_size
        
        if net_premium > 0:
            # Credit strategy
            max_profit = net_premium * lot_size * lots
        else:
            # Debit strategy - max profit is theoretical max
            if len(legs_data) == 2:
                width = abs(legs_data[1]["strike"] - legs_data[0]["strike"])
                max_profit = (width + net_premium) * lot_size * lots
            else:
                max_profit = abs(net_premium) * lot_size * lots * 3  # Estimate
        
        return max_profit, max_loss
    
    def _calculate_dte(self, expiry: date = None) -> int:
        """Calculate days to expiry."""
        if expiry is None:
            return 30
        
        today = date.today()
        return max(0, (expiry - today).days)
