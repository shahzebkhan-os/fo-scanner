"""
Test suite for unified evaluation improvements:
- Optimized model weights
- Risk-reward calculation
- Target/stoploss logic
"""

import pytest
from backend.unified_evaluation import UnifiedEvaluation


class TestOptimizedWeights:
    """Test that model weights are properly optimized and sum to 1.0"""

    def test_weights_sum_to_one(self):
        """Weights must sum to exactly 1.0 for proper ensemble"""
        evaluator = UnifiedEvaluation()
        total = sum(evaluator.WEIGHTS.values())
        assert abs(total - 1.0) < 0.0001, f"Weights sum to {total}, expected 1.0"

    def test_weights_distribution(self):
        """Verify optimized weight distribution"""
        evaluator = UnifiedEvaluation()
        weights = evaluator.WEIGHTS

        # ML and OI should have highest weights (30% each)
        assert weights["ml_ensemble"] == 0.30, "ML ensemble should be 30%"
        assert weights["oi_based"] == 0.30, "OI-based should be 30%"

        # Technical should be third highest (25%)
        assert weights["technical"] == 0.25, "Technical should be 25%"

        # OI velocity and global cues should be lowest
        assert weights["oi_velocity"] == 0.08, "OI velocity should be 8%"
        assert weights["global_cues"] == 0.07, "Global cues should be 7%"

    def test_all_weights_positive(self):
        """All weights must be positive"""
        evaluator = UnifiedEvaluation()
        for model, weight in evaluator.WEIGHTS.items():
            assert weight > 0, f"{model} weight must be positive, got {weight}"


class TestRiskRewardCalculation:
    """Test risk-reward calculation logic"""

    def test_basic_calculation(self):
        """Test basic risk-reward calculation"""
        evaluator = UnifiedEvaluation()

        result = evaluator.calculate_risk_reward(
            option_ltp=100.0,
            lot_size=100,
            profit_target_pct=20.0,
            stop_loss_pct=15.0,
        )

        # Verify target price (100 * 1.20 = 120)
        assert result["target_price"] == 120.0, f"Expected 120, got {result['target_price']}"

        # Verify stop loss (100 * 0.85 = 85)
        assert result["stoploss_price"] == 85.0, f"Expected 85, got {result['stoploss_price']}"

        # Verify potential profit ((120 - 100) * 100 = 2000)
        assert result["potential_profit"] == 2000.0, f"Expected 2000, got {result['potential_profit']}"

        # Verify potential loss ((100 - 85) * 100 = 1500)
        assert result["potential_loss"] == 1500.0, f"Expected 1500, got {result['potential_loss']}"

        # Verify risk-reward ratio (2000 / 1500 = 1.33)
        assert abs(result["risk_reward_ratio"] - 1.33) < 0.01, f"Expected ~1.33, got {result['risk_reward_ratio']}"

    def test_default_parameters(self):
        """Test that default parameters are used when not provided"""
        evaluator = UnifiedEvaluation()

        result = evaluator.calculate_risk_reward(
            option_ltp=50.0,
            lot_size=250,
        )

        # Should use default 20% target and 15% stop
        assert result["target_pct"] == 20.0, "Default target should be 20%"
        assert result["stoploss_pct"] == 15.0, "Default stop should be 15%"

        # Verify calculations with defaults
        assert result["target_price"] == 60.0, f"Expected 60, got {result['target_price']}"
        assert result["stoploss_price"] == 42.5, f"Expected 42.5, got {result['stoploss_price']}"

    def test_lot_size_integration(self):
        """Test that lot size affects capital and P/L correctly"""
        evaluator = UnifiedEvaluation()

        # Small lot
        small_lot = evaluator.calculate_risk_reward(
            option_ltp=100.0,
            lot_size=50,
        )

        # Large lot
        large_lot = evaluator.calculate_risk_reward(
            option_ltp=100.0,
            lot_size=500,
        )

        # Capital should scale with lot size
        assert small_lot["capital_required"] == 5000.0
        assert large_lot["capital_required"] == 50000.0

        # P/L should scale with lot size
        assert large_lot["potential_profit"] == small_lot["potential_profit"] * 10
        assert large_lot["potential_loss"] == small_lot["potential_loss"] * 10

        # But R:R ratio should be the same
        assert small_lot["risk_reward_ratio"] == large_lot["risk_reward_ratio"]

    def test_custom_risk_parameters(self):
        """Test custom risk management parameters"""
        evaluator = UnifiedEvaluation()

        # Aggressive: 30% target, 10% stop
        aggressive = evaluator.calculate_risk_reward(
            option_ltp=100.0,
            lot_size=100,
            profit_target_pct=30.0,
            stop_loss_pct=10.0,
        )

        assert aggressive["target_price"] == 130.0
        assert aggressive["stoploss_price"] == 90.0
        assert aggressive["risk_reward_ratio"] == 3.0  # 30/10

        # Conservative: 15% target, 20% stop
        conservative = evaluator.calculate_risk_reward(
            option_ltp=100.0,
            lot_size=100,
            profit_target_pct=15.0,
            stop_loss_pct=20.0,
        )

        assert conservative["target_price"] == 115.0
        assert conservative["stoploss_price"] == 80.0
        assert conservative["risk_reward_ratio"] == 0.75  # 15/20

    def test_edge_cases(self):
        """Test edge cases and boundary conditions"""
        evaluator = UnifiedEvaluation()

        # Very low LTP
        low_ltp = evaluator.calculate_risk_reward(
            option_ltp=1.0,
            lot_size=1000,
        )
        assert low_ltp["target_price"] == 1.2
        assert low_ltp["stoploss_price"] == 0.85

        # Very high LTP
        high_ltp = evaluator.calculate_risk_reward(
            option_ltp=500.0,
            lot_size=10,
        )
        assert high_ltp["target_price"] == 600.0
        assert high_ltp["stoploss_price"] == 425.0

    def test_rounding(self):
        """Test that values are properly rounded"""
        evaluator = UnifiedEvaluation()

        result = evaluator.calculate_risk_reward(
            option_ltp=33.33,
            lot_size=75,
        )

        # All prices should be rounded to 2 decimals
        assert isinstance(result["target_price"], float)
        assert isinstance(result["stoploss_price"], float)
        assert len(str(result["target_price"]).split(".")[-1]) <= 2
        assert len(str(result["stoploss_price"]).split(".")[-1]) <= 2


class TestUnifiedScoreCalculation:
    """Test unified score calculation with optimized weights"""

    def test_all_bullish_scenario(self):
        """When all models are bullish, unified score should be high"""
        evaluator = UnifiedEvaluation()

        unified = evaluator.compute_unified_score(
            oi_score=85,
            oi_signal="BULLISH",
            oi_confidence=0.8,
            technical_score=80,
            technical_signal="BULLISH",
            technical_confidence=0.75,
            ml_bullish_prob=0.85,
            oi_velocity_score=0.6,
            global_cues_score=0.4,
        )

        # All models bullish, should have high score
        assert unified["unified_score"] > 70, "All bullish should give high score"
        assert unified["unified_signal"] == "BULLISH"
        assert unified["unified_confidence"] > 0.7, "High agreement should give high confidence"

    def test_weight_contribution(self):
        """Test that weights properly contribute to final score"""
        evaluator = UnifiedEvaluation()

        # Only ML bullish (30% weight)
        ml_only = evaluator.compute_unified_score(
            oi_score=50,  # neutral
            oi_signal="NEUTRAL",
            oi_confidence=0.5,
            technical_score=50,  # neutral
            technical_signal="NEUTRAL",
            technical_confidence=0.5,
            ml_bullish_prob=1.0,  # 100% bullish
            oi_velocity_score=0.0,  # neutral
            global_cues_score=0.0,  # neutral
        )

        # Score should be: 50*0.3 + 50*0.25 + 100*0.3 + 50*0.08 + 50*0.07
        # = 15 + 12.5 + 30 + 4 + 3.5 = 65
        expected = 65.0
        assert abs(ml_only["unified_score"] - expected) < 1.0, \
            f"Expected ~{expected}, got {ml_only['unified_score']}"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
