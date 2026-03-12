"""
Tests for the 12-Signal Engine modules.

Tests cover:
- Individual signal computations
- Signal aggregation
- Regime classification
- Position sizing
- Trade execution
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, date, timedelta

from signals.base import BaseSignal, SignalResult
from signals.oi_analysis import OiSignal
from signals.iv_analysis import IvSignal
from signals.max_pain import MaxPainSignal
from signals.price_action import PriceActionSignal
from signals.technicals import TechnicalSignal
from signals.global_cues import GlobalCuesSignal
from signals.fii_dii import FiiDiiSignal
from signals.straddle_pricing import StraddleSignal
from signals.news_scanner import NewsSignal
from signals.greeks_signal import GreeksSignal
from signals.engine import MasterSignalEngine, AggregatedSignal
from market.regime import RegimeClassifier, MarketRegime
from watcher.state import OptionsTradeState, TradeLeg, TradeWatcher, TradeStatus
from execution.sizer import OptionsSizer
from execution.executor import OptionsExecutor


# Fixtures
@pytest.fixture
def sample_records():
    """Sample option chain records for testing."""
    return [
        {'strikePrice': 22000, 'CE': {'openInterest': 50000, 'lastPrice': 150, 'delta': 0.7, 'gamma': 0.01}, 'PE': {'openInterest': 80000, 'lastPrice': 30, 'delta': -0.3, 'gamma': 0.01}},
        {'strikePrice': 22100, 'CE': {'openInterest': 70000, 'lastPrice': 100, 'delta': 0.55, 'gamma': 0.02}, 'PE': {'openInterest': 60000, 'lastPrice': 50, 'delta': -0.45, 'gamma': 0.02}},
        {'strikePrice': 22200, 'CE': {'openInterest': 100000, 'lastPrice': 55, 'delta': 0.45, 'gamma': 0.02}, 'PE': {'openInterest': 100000, 'lastPrice': 75, 'delta': -0.55, 'gamma': 0.02}},
        {'strikePrice': 22300, 'CE': {'openInterest': 90000, 'lastPrice': 25, 'delta': 0.3, 'gamma': 0.01}, 'PE': {'openInterest': 70000, 'lastPrice': 120, 'delta': -0.7, 'gamma': 0.01}},
        {'strikePrice': 22400, 'CE': {'openInterest': 60000, 'lastPrice': 10, 'delta': 0.15, 'gamma': 0.005}, 'PE': {'openInterest': 40000, 'lastPrice': 180, 'delta': -0.85, 'gamma': 0.005}},
    ]


@pytest.fixture
def iv_history():
    """Sample IV history for testing."""
    return list(range(15, 25)) * 25  # 250 days of data


@pytest.fixture
def price_data():
    """Sample price data for testing."""
    return [22000 + i * 10 for i in range(50)]


class TestSignalResult:
    """Tests for SignalResult dataclass."""
    
    def test_signal_result_creation(self):
        """Test creating a signal result."""
        result = SignalResult(
            score=0.5,
            confidence=0.8,
            reason="Test reason",
            metadata={"key": "value"}
        )
        
        assert result.score == 0.5
        assert result.confidence == 0.8
        assert result.reason == "Test reason"
        assert result.metadata["key"] == "value"
    
    def test_signal_result_to_dict(self):
        """Test converting signal result to dict."""
        result = SignalResult(score=0.5, confidence=0.8, reason="Test")
        d = result.to_dict()
        
        assert "score" in d
        assert "confidence" in d
        assert "reason" in d


class TestOiSignal:
    """Tests for OI Analysis Signal."""
    
    def test_compute_basic(self, sample_records):
        """Test basic OI signal computation."""
        signal = OiSignal()
        result = signal.compute(
            records=sample_records,
            spot=22150,
            pcr=1.1
        )
        
        assert isinstance(result, SignalResult)
        assert -1.0 <= result.score <= 1.0
        assert result.confidence > 0
    
    def test_compute_no_data(self):
        """Test OI signal with no data."""
        signal = OiSignal()
        result = signal.compute(records=[], spot=22150, pcr=1.0)
        
        assert result.score == 0.0
        assert result.confidence == 0.0
    
    def test_high_pcr_bullish(self, sample_records):
        """Test high PCR triggers contrarian bullish signal."""
        signal = OiSignal()
        result = signal.compute(
            records=sample_records,
            spot=22150,
            pcr=1.8  # High PCR
        )
        
        # High PCR should give positive (bullish) score
        assert result.score > 0


class TestIvSignal:
    """Tests for IV Analysis Signal."""
    
    def test_compute_basic(self, iv_history):
        """Test basic IV signal computation."""
        signal = IvSignal()
        result = signal.compute(
            current_iv=18,
            iv_history=iv_history,
            vix=16
        )
        
        assert isinstance(result, SignalResult)
        assert "iv_rank" in result.metadata
        assert "iv_percentile" in result.metadata
    
    def test_high_ivr(self, iv_history):
        """Test high IV rank detection."""
        signal = IvSignal()
        result = signal.compute(
            current_iv=24,  # Near top of range
            iv_history=iv_history,
            vix=22
        )
        
        assert result.metadata["iv_rank"] > 70


class TestMaxPainSignal:
    """Tests for Max Pain Signal."""
    
    def test_compute_max_pain(self, sample_records):
        """Test max pain calculation."""
        signal = MaxPainSignal()
        result = signal.compute(
            records=sample_records,
            spot=22150,
            dte=5
        )
        
        assert "max_pain" in result.metadata
        assert result.metadata["max_pain"] is not None
    
    def test_gex_calculation(self, sample_records):
        """Test GEX calculation."""
        signal = MaxPainSignal()
        result = signal.compute(
            records=sample_records,
            spot=22150,
            dte=5
        )
        
        assert "net_gex" in result.metadata
        assert "gex_regime" in result.metadata


class TestPriceActionSignal:
    """Tests for Price Action Signal."""
    
    def test_above_vwap_bullish(self):
        """Test price above VWAP gives bullish signal."""
        signal = PriceActionSignal()
        result = signal.compute(
            spot=22200,
            vwap=22100,
            minutes_above_vwap=45,
            prev_close=22000
        )
        
        assert result.score > 0
    
    def test_below_vwap_bearish(self):
        """Test price below VWAP gives bearish signal."""
        signal = PriceActionSignal()
        result = signal.compute(
            spot=22000,
            vwap=22100,
            minutes_below_vwap=45,
            prev_close=22050
        )
        
        assert result.score < 0


class TestTechnicalSignal:
    """Tests for Technical Signal."""
    
    def test_compute_with_data(self, price_data):
        """Test technical signal with price data."""
        signal = TechnicalSignal()
        result = signal.compute(closes=price_data)
        
        assert "rsi" in result.metadata
        assert "bollinger" in result.metadata
        assert "ema" in result.metadata
    
    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        signal = TechnicalSignal()
        result = signal.compute(closes=[100, 101, 102])
        
        assert result.score == 0.0
        assert result.confidence == 0.0


class TestGlobalCuesSignal:
    """Tests for Global Cues Signal."""
    
    def test_gift_premium_bullish(self):
        """Test GIFT Nifty premium gives bullish signal."""
        signal = GlobalCuesSignal()
        result = signal.compute(
            gift_nifty=22300,
            nifty_prev_close=22000,  # +1.36% premium
            spx_change_pct=0.5,
            nasdaq_change_pct=0.8
        )
        
        assert result.score > 0
    
    def test_time_weighting(self):
        """Test time-based signal weighting."""
        signal = GlobalCuesSignal()
        morning_time = datetime.now().replace(hour=9, minute=30)
        
        result = signal.compute(
            gift_nifty=22300,
            nifty_prev_close=22000,
            current_time=morning_time
        )
        
        assert "time_multiplier" in result.metadata


class TestFiiDiiSignal:
    """Tests for FII/DII Signal."""
    
    def test_strong_fii_buying(self):
        """Test strong FII buying gives bullish signal."""
        signal = FiiDiiSignal()
        result = signal.compute(
            fii_net_futures=6000,
            fii_3day_cumulative=15000
        )
        
        assert result.score > 0
    
    def test_strong_fii_selling(self):
        """Test strong FII selling gives bearish signal."""
        signal = FiiDiiSignal()
        result = signal.compute(
            fii_net_futures=-8000,
            fii_3day_cumulative=-20000
        )
        
        assert result.score < 0


class TestStraddleSignal:
    """Tests for Straddle Pricing Signal."""
    
    def test_compute_straddle(self):
        """Test straddle pricing signal."""
        signal = StraddleSignal()
        result = signal.compute(
            spot=22150,
            atm_strike=22200,
            atm_ce_ltp=100,
            atm_pe_ltp=80,
            dte=5,
            hv20=15
        )
        
        assert "straddle_price" in result.metadata
        assert "implied_move_pct" in result.metadata
        assert "upper_breakeven" in result.metadata
        assert "lower_breakeven" in result.metadata


class TestNewsSignal:
    """Tests for News Scanner Signal."""
    
    def test_high_impact_event_blackout(self):
        """Test high impact event triggers blackout."""
        signal = NewsSignal()
        event_time = datetime.now() + timedelta(hours=12)
        
        result = signal.compute(
            events=[{
                "name": "RBI MPC",
                "type": "RBI_MPC",
                "datetime": event_time,
                "impact": "HIGH"
            }],
            current_time=datetime.now()
        )
        
        assert result.metadata.get("blackout") is True
    
    def test_no_events(self):
        """Test no events gives neutral signal."""
        signal = NewsSignal()
        result = signal.compute(events=[], current_time=datetime.now())
        
        assert result.metadata.get("blackout") is False


class TestGreeksSignal:
    """Tests for Greeks Signal."""
    
    def test_compute_greeks(self, sample_records):
        """Test Greeks signal computation."""
        signal = GreeksSignal()
        result = signal.compute(
            records=sample_records,
            spot=22150,
            dte=5
        )
        
        assert "aggregate_delta" in result.metadata


class TestRegimeClassifier:
    """Tests for Market Regime Classifier."""
    
    def test_trending_up(self):
        """Test trending up detection."""
        classifier = RegimeClassifier()
        result = classifier.classify(
            spot=22200,
            ema_20=22100,
            prev_day_high=22150,
            supertrend_bullish=True
        )
        
        assert result.regime == MarketRegime.TRENDING_UP
    
    def test_high_volatility(self):
        """Test high volatility detection."""
        classifier = RegimeClassifier()
        result = classifier.classify(
            spot=22150,
            vix=22,
            vix_open=18,  # +22% spike
            net_gex=-1e9
        )
        
        assert result.regime == MarketRegime.HIGH_VOLATILITY
    
    def test_range_bound(self):
        """Test range bound detection."""
        classifier = RegimeClassifier()
        result = classifier.classify(
            spot=22150,
            vwap=22145,  # Very close to VWAP
            net_gex=1e9,  # Positive GEX
            ivr=65
        )
        
        assert result.regime == MarketRegime.RANGE_BOUND


class TestMasterSignalEngine:
    """Tests for Master Signal Engine."""
    
    def test_compute_all_signals(self, sample_records):
        """Test computing all signals."""
        engine = MasterSignalEngine()
        result = engine.compute_all_signals(
            spot=22150,
            records=sample_records,
            vwap=22100,
            prev_close=22050,
            pcr=1.1,
            dte=5
        )
        
        assert isinstance(result, AggregatedSignal)
        d = result.to_dict()
        assert "composite_score" in d
        assert "regime" in d
        assert "trade" in d
    
    def test_blackout_prevents_trade(self, sample_records):
        """Test blackout prevents trading."""
        engine = MasterSignalEngine()
        event_time = datetime.now() + timedelta(hours=6)
        
        result = engine.compute_all_signals(
            spot=22150,
            records=sample_records,
            events=[{
                "name": "RBI MPC",
                "type": "RBI_MPC",
                "datetime": event_time,
                "impact": "HIGH"
            }]
        )
        
        assert result.blackout is True
        assert result.trade is False


class TestOptionsSizer:
    """Tests for Options Sizer."""
    
    def test_defined_risk_sizing(self):
        """Test sizing for defined risk strategies."""
        sizer = OptionsSizer(bankroll=500000)
        result = sizer.calculate_lots(
            strategy_name="bull_call_spread",
            symbol="NIFTY",
            max_loss_per_lot=5000,
            confidence=0.8,
            signal_score=0.6
        )
        
        assert result.lots > 0
        assert result.lots <= 20  # Max lots for NIFTY
    
    def test_undefined_risk_sizing(self):
        """Test sizing for undefined risk strategies."""
        sizer = OptionsSizer(bankroll=500000)
        result = sizer.calculate_lots(
            strategy_name="short_straddle",
            symbol="NIFTY",
            max_loss_per_lot=10000,
            margin_per_lot=100000,
            confidence=0.8,
            signal_score=0.6
        )
        
        assert result.lots > 0


class TestTradeState:
    """Tests for Options Trade State."""
    
    def test_pnl_calculation(self):
        """Test P&L calculation."""
        trade = OptionsTradeState(
            strategy_name="bull_call_spread",
            underlying="NIFTY",
            underlying_price_at_entry=22150,
            max_profit=5000,
            max_loss=3000,
            lot_size=50
        )
        
        leg = TradeLeg(
            tradingsymbol="NIFTY22DEC22200CE",
            instrument_token=12345,
            transaction_type="BUY",
            qty_lots=2,
            entry_price=100,
            current_price=120
        )
        trade.legs.append(leg)
        
        trade.update_prices({"NIFTY22DEC22200CE": 120})
        
        # (120-100) * 1 * 2 * 50 = 2000
        assert trade.current_pnl == 2000
    
    def test_pnl_percent(self):
        """Test P&L percentage calculation."""
        trade = OptionsTradeState(
            strategy_name="test",
            max_loss=3000
        )
        trade.current_pnl = 1500
        
        pct = trade.pnl_percent()
        assert pct == 50.0
    
    def test_trade_close(self):
        """Test closing a trade."""
        trade = OptionsTradeState(
            strategy_name="test",
            paper_mode=True
        )
        
        trade.close_trade("Target reached")
        
        assert trade.status == TradeStatus.PAPER_CLOSED
        assert trade.exit_reason == "Target reached"


class TestTradeWatcher:
    """Tests for Trade Watcher."""
    
    def test_register_trade(self):
        """Test registering a trade."""
        watcher = TradeWatcher()
        trade = OptionsTradeState(strategy_name="test")
        
        watcher.register(trade)
        
        assert trade.trade_id in watcher.trades
    
    def test_get_open_trades(self):
        """Test getting open trades."""
        watcher = TradeWatcher()
        
        trade1 = OptionsTradeState(strategy_name="test1", status=TradeStatus.PAPER_OPEN)
        trade2 = OptionsTradeState(strategy_name="test2", status=TradeStatus.PAPER_CLOSED)
        
        watcher.register(trade1)
        watcher.register(trade2)
        
        open_trades = watcher.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].strategy_name == "test1"


class TestOptionsExecutor:
    """Tests for Options Executor."""
    
    def test_strategy_definitions(self):
        """Test strategy definitions exist."""
        executor = OptionsExecutor(paper_mode=True)
        
        assert "bull_call_spread" in executor.STRATEGIES
        assert "iron_condor" in executor.STRATEGIES
        assert "short_straddle" in executor.STRATEGIES
    
    def test_iron_condor_legs(self):
        """Test iron condor has 4 legs."""
        executor = OptionsExecutor(paper_mode=True)
        strategy = executor.STRATEGIES["iron_condor"]
        
        assert len(strategy.legs) == 4
