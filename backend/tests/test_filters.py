"""
Test suite for the 5 unified evaluation improvements (filter gates):
1. Signal Quality Filter
2. Time of Day Filter
3. Market Regime Override
4. Event Calendar
5. Signal Persistence
"""

import pytest
from datetime import datetime, date, time
import pytz
from backend.filters.signal_quality import SignalQualityFilter, QualityTag
from backend.filters.time_of_day import TimeOfDayFilter, TimeWindow, WindowStatus
from backend.filters.regime_override import RegimeOverrideFilter, RegimeType, TrendDirection
from backend.filters.event_calendar import EventCalendar, EventType, EventAction
from backend.filters.signal_persistence import SignalPersistenceCache, PersistenceStatus

IST = pytz.timezone("Asia/Kolkata")


class TestSignalQualityFilter:
    """Test Signal Quality Filter (Improvement #1)"""

    def test_prime_signal_all_conditions_pass(self):
        """Test PRIME tag when all 6 conditions pass"""
        filter = SignalQualityFilter()

        result = filter.evaluate(
            unified_score=80.0,
            model_agreement_ratio=0.85,
            unified_confidence=0.85,
            risk_reward_ratio=2.0,
            option_volume=1000,
            option_avg_volume=800,
            iv_rank=50.0,
        )

        assert result.tag == QualityTag.PRIME
        assert result.conditions_passed == 6
        assert len(result.failed_conditions) == 0

    def test_qualified_signal_5_of_6_pass(self):
        """Test QUALIFIED tag when 5 of 6 conditions pass"""
        filter = SignalQualityFilter()

        result = filter.evaluate(
            unified_score=80.0,
            model_agreement_ratio=0.75,  # Below threshold (0.80)
            unified_confidence=0.85,
            risk_reward_ratio=2.0,
            option_volume=1000,
            option_avg_volume=800,
            iv_rank=50.0,
        )

        assert result.tag == QualityTag.QUALIFIED
        assert result.conditions_passed == 5
        assert len(result.failed_conditions) == 1

    def test_marginal_signal_4_of_6_pass(self):
        """Test MARGINAL tag when 4 of 6 conditions pass"""
        filter = SignalQualityFilter()

        result = filter.evaluate(
            unified_score=70.0,  # Below threshold (75)
            model_agreement_ratio=0.75,  # Below threshold (0.80)
            unified_confidence=0.85,
            risk_reward_ratio=2.0,
            option_volume=1000,
            option_avg_volume=800,
            iv_rank=50.0,
        )

        assert result.tag == QualityTag.MARGINAL
        assert result.conditions_passed == 4

    def test_blocked_signal_3_or_fewer_pass(self):
        """Test BLOCKED tag when 3 or fewer conditions pass"""
        filter = SignalQualityFilter()

        result = filter.evaluate(
            unified_score=70.0,  # Below threshold
            model_agreement_ratio=0.75,  # Below threshold
            unified_confidence=0.75,  # Below threshold
            risk_reward_ratio=1.2,  # Below threshold
            option_volume=1000,
            option_avg_volume=800,
            iv_rank=50.0,
        )

        assert result.tag == QualityTag.BLOCKED
        assert result.conditions_passed <= 3

    def test_iv_rank_extremes_blocked(self):
        """Test that extreme IV Rank values cause failure"""
        filter = SignalQualityFilter()

        # Too low IV Rank
        result_low = filter.evaluate(
            unified_score=80.0,
            model_agreement_ratio=0.85,
            unified_confidence=0.85,
            risk_reward_ratio=2.0,
            option_volume=1000,
            option_avg_volume=800,
            iv_rank=15.0,  # Below 20%
        )

        assert not result_low.details["iv_rank"]["pass"]

        # Too high IV Rank
        result_high = filter.evaluate(
            unified_score=80.0,
            model_agreement_ratio=0.85,
            unified_confidence=0.85,
            risk_reward_ratio=2.0,
            option_volume=1000,
            option_avg_volume=800,
            iv_rank=85.0,  # Above 80%
        )

        assert not result_high.details["iv_rank"]["pass"]


class TestTimeOfDayFilter:
    """Test Time of Day Filter (Improvement #2)"""

    def test_opening_volatility_blocked(self):
        """Test that signals are blocked during opening volatility (9:15-9:30)"""
        filter = TimeOfDayFilter()

        test_time = IST.localize(datetime(2026, 3, 17, 9, 20))
        window = filter.get_current_window(test_time)

        assert window == TimeWindow.OPENING_VOLATILITY

        result = filter.get_current_filter(current_time=test_time)
        assert result.status == WindowStatus.BLOCKED
        assert result.blocked

    def test_prime_window_open(self):
        """Test that all qualified signals are allowed during prime window (10:15-13:00)"""
        filter = TimeOfDayFilter()

        test_time = IST.localize(datetime(2026, 3, 17, 11, 30))
        window = filter.get_current_window(test_time)

        assert window == TimeWindow.PRIME_WINDOW

        result = filter.get_current_filter(current_time=test_time)
        assert result.status == WindowStatus.OPEN
        assert not result.blocked
        assert "PRIME" in result.allowed_quality_tags
        assert "QUALIFIED" in result.allowed_quality_tags

    def test_caution_window_prime_only(self):
        """Test that only PRIME signals are allowed during caution windows"""
        filter = TimeOfDayFilter()

        # Early morning (9:30-10:15)
        test_time = IST.localize(datetime(2026, 3, 17, 9, 45))
        result = filter.get_current_filter(current_time=test_time)

        assert result.status == WindowStatus.CAUTION
        assert "PRIME" in result.allowed_quality_tags
        assert "QUALIFIED" not in result.allowed_quality_tags

    def test_expiry_day_detection(self):
        """Test that Thursday is correctly detected as expiry day"""
        filter = TimeOfDayFilter()

        # Thursday, March 20, 2026
        thursday = IST.localize(datetime(2026, 3, 19, 11, 0))
        is_expiry = filter.is_expiry_day(thursday)

        assert is_expiry

        # Friday should not be expiry day
        friday = IST.localize(datetime(2026, 3, 20, 11, 0))
        is_expiry_friday = filter.is_expiry_day(friday)

        assert not is_expiry_friday

    def test_expiry_day_otm_blocked(self):
        """Test that OTM options are blocked on expiry day"""
        filter = TimeOfDayFilter()

        # Thursday at 11 AM
        thursday = IST.localize(datetime(2026, 3, 19, 11, 0))

        # OTM option (delta < 0.40)
        result = filter.get_current_filter(
            current_time=thursday,
            quality_tag="PRIME",
            unified_score=85,
            option_delta=0.25,  # OTM
        )

        assert result.is_expiry_day
        assert result.blocked
        assert "OTM" in result.message

    def test_expiry_day_itm_allowed(self):
        """Test that ITM/ATM options are allowed on expiry day with PRIME quality"""
        filter = TimeOfDayFilter()

        # Thursday at 11 AM
        thursday = IST.localize(datetime(2026, 3, 19, 11, 0))

        # ITM/ATM option (delta = 0.50)
        result = filter.get_current_filter(
            current_time=thursday,
            quality_tag="PRIME",
            unified_score=85,
            option_delta=0.50,  # ATM
        )

        assert result.is_expiry_day
        assert not result.blocked
        assert result.min_score_threshold == 85.0


class TestMarketRegimeOverride:
    """Test Market Regime Override (Improvement #3)"""

    def test_pinned_regime_blocks_directional(self):
        """Test that PINNED regime blocks directional trades"""
        filter = RegimeOverrideFilter()

        result = filter.apply_override(
            regime="PINNED",
            signal_direction="BULLISH",
            option_delta=0.45,
            days_to_expiry=5,
        )

        assert not result.allowed
        assert "PINNED" in result.reason

    def test_trending_counter_trend_blocked(self):
        """Test that counter-trend signals are blocked in TRENDING regime"""
        filter = RegimeOverrideFilter()

        # Bearish signal in bullish trend
        result = filter.apply_override(
            regime="TRENDING",
            signal_direction="BEARISH",
            option_delta=0.45,
            days_to_expiry=5,
            spot_price=23000,
            ema_20=22500,  # Price above EMA = bullish trend
        )

        assert not result.allowed
        assert "Counter-trend" in result.reason

    def test_trending_aligned_gets_bonus(self):
        """Test that aligned signals get confidence bonus in TRENDING regime"""
        filter = RegimeOverrideFilter()

        # Bullish signal in bullish trend
        result = filter.apply_override(
            regime="TRENDING",
            signal_direction="BULLISH",
            option_delta=0.45,
            days_to_expiry=5,
            spot_price=23000,
            ema_20=22500,  # Price above EMA = bullish trend
        )

        assert result.allowed
        assert result.confidence_adjustment == 0.05  # +5% bonus

    def test_squeeze_blocks_without_breakout(self):
        """Test that SQUEEZE regime blocks signals without breakout confirmation"""
        filter = RegimeOverrideFilter()

        result = filter.apply_override(
            regime="SQUEEZE",
            signal_direction="BULLISH",
            option_delta=0.45,
            days_to_expiry=5,
            breakout_confirmed=False,
        )

        assert not result.allowed
        assert "SQUEEZE" in result.reason
        assert "breakout" in result.reason.lower()

    def test_expiry_blocks_otm(self):
        """Test that EXPIRY regime blocks OTM options"""
        filter = RegimeOverrideFilter()

        result = filter.apply_override(
            regime="EXPIRY",
            signal_direction="BULLISH",
            option_delta=0.30,  # OTM (< 0.50)
            days_to_expiry=3,
        )

        assert not result.allowed
        assert "OTM" in result.reason

    def test_expiry_blocks_same_day_expiry(self):
        """Test that EXPIRY regime blocks same-day/next-day expiry"""
        filter = RegimeOverrideFilter()

        result = filter.apply_override(
            regime="EXPIRY",
            signal_direction="BULLISH",
            option_delta=0.55,  # ITM
            days_to_expiry=1,  # Same day
        )

        assert not result.allowed
        assert "DTE" in result.reason or "expiry" in result.reason.lower()


class TestEventCalendar:
    """Test Event Calendar (Improvement #4)"""

    @pytest.mark.asyncio
    async def test_fo_ban_list_check(self):
        """Test F&O ban list check (most critical)"""
        calendar = EventCalendar()

        # Mock a banned symbol and set last update to now to avoid refresh
        calendar._fo_ban_list = {"TESTSTOCK"}
        calendar._fo_ban_last_update = datetime.now()

        is_banned = await calendar.is_fo_banned("TESTSTOCK")
        assert is_banned

        is_not_banned = await calendar.is_fo_banned("RELIANCE")
        assert not is_not_banned

    @pytest.mark.asyncio
    async def test_event_blocks_signal(self):
        """Test that events can block signals"""
        from backend.filters.event_calendar import EventInfo

        calendar = EventCalendar()

        # Add a test earnings event
        test_event = EventInfo(
            event_type=EventType.EARNINGS,
            symbol="RELIANCE",
            event_date=date.today(),
            description="RELIANCE Earnings",
            action=EventAction.BLOCK,
            lookback_days=3,
        )

        calendar._corporate_events["RELIANCE"] = [test_event]
        calendar._corporate_events_last_update = datetime.now()
        calendar._fo_ban_last_update = datetime.now()

        result = await calendar.check_events("RELIANCE")

        assert result.has_event
        assert result.blocked
        assert len(result.events) > 0

    @pytest.mark.asyncio
    async def test_event_reduces_confidence(self):
        """Test that some events reduce confidence without blocking"""
        from backend.filters.event_calendar import EventInfo

        calendar = EventCalendar()

        # Add a board meeting event
        test_event = EventInfo(
            event_type=EventType.BOARD_MEETING,
            symbol="TCS",
            event_date=date.today(),
            description="TCS Board Meeting",
            action=EventAction.REDUCE_CONFIDENCE_15,
        )

        calendar._corporate_events["TCS"] = [test_event]
        calendar._corporate_events_last_update = datetime.now()
        calendar._fo_ban_last_update = datetime.now()

        result = await calendar.check_events("TCS")

        assert result.has_event
        assert not result.blocked
        assert result.confidence_adjustment == -0.15


class TestSignalPersistence:
    """Test Signal Persistence (Improvement #5)"""

    def test_new_signal_not_actionable(self):
        """Test that new signals are not immediately actionable"""
        cache = SignalPersistenceCache()
        cache.clear_history()  # Start fresh

        result = cache.update_history(
            symbol="NIFTY",
            unified_score=80.0,
            signal_direction="BULLISH",
            quality_tag="PRIME",
            unified_confidence=0.85,
        )

        assert result.status == PersistenceStatus.BUILDING
        assert result.consecutive_count == 1
        assert not result.is_actionable

    def test_confirmed_after_3_refreshes(self):
        """Test that signals are confirmed after 3 consecutive refreshes"""
        cache = SignalPersistenceCache()
        cache.clear_history()

        # First refresh
        result1 = cache.update_history(
            symbol="NIFTY",
            unified_score=80.0,
            signal_direction="BULLISH",
            quality_tag="PRIME",
            unified_confidence=0.85,
        )
        assert not result1.is_actionable

        # Second refresh
        result2 = cache.update_history(
            symbol="NIFTY",
            unified_score=81.0,
            signal_direction="BULLISH",
            quality_tag="PRIME",
            unified_confidence=0.86,
        )
        assert not result2.is_actionable

        # Third refresh - should be confirmed
        result3 = cache.update_history(
            symbol="NIFTY",
            unified_score=82.0,
            signal_direction="BULLISH",
            quality_tag="PRIME",
            unified_confidence=0.87,
        )

        assert result3.status == PersistenceStatus.CONFIRMED
        assert result3.is_actionable
        assert result3.consecutive_count >= 3

    def test_direction_change_resets(self):
        """Test that direction change resets persistence"""
        cache = SignalPersistenceCache()
        cache.clear_history()

        # Build up to 2 refreshes
        cache.update_history("NIFTY", 80.0, "BULLISH", "PRIME", 0.85)
        cache.update_history("NIFTY", 81.0, "BULLISH", "PRIME", 0.86)

        # Direction changes - should reset
        result = cache.update_history("NIFTY", 45.0, "BEARISH", "PRIME", 0.85)

        assert result.consecutive_count == 1  # Reset to 1

    def test_large_score_drop_resets(self):
        """Test that large score drop resets persistence"""
        cache = SignalPersistenceCache()
        cache.clear_history()

        # Build up to 2 refreshes
        cache.update_history("NIFTY", 80.0, "BULLISH", "PRIME", 0.85)
        cache.update_history("NIFTY", 81.0, "BULLISH", "PRIME", 0.86)

        # Large score drop (> 5 points) - should reset
        result = cache.update_history("NIFTY", 74.0, "BULLISH", "PRIME", 0.85)

        assert result.consecutive_count == 1  # Reset

    def test_quality_degradation_resets(self):
        """Test that quality degradation from PRIME/QUALIFIED to MARGINAL resets"""
        cache = SignalPersistenceCache()
        cache.clear_history()

        # Build up with PRIME
        cache.update_history("NIFTY", 80.0, "BULLISH", "PRIME", 0.85)
        cache.update_history("NIFTY", 81.0, "BULLISH", "PRIME", 0.86)

        # Drop to MARGINAL - should reset
        result = cache.update_history("NIFTY", 80.5, "BULLISH", "MARGINAL", 0.80)

        assert result.consecutive_count == 1  # Reset


class TestFilterIntegration:
    """Test integration of all filters"""

    def test_filters_work_together(self):
        """Test that all filters can be instantiated and used together"""
        quality_filter = SignalQualityFilter()
        time_filter = TimeOfDayFilter()
        regime_filter = RegimeOverrideFilter()
        event_calendar = EventCalendar()
        persistence_cache = SignalPersistenceCache()

        # All filters should be initialized
        assert quality_filter is not None
        assert time_filter is not None
        assert regime_filter is not None
        assert event_calendar is not None
        assert persistence_cache is not None


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])
