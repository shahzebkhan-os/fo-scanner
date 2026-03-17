"""
Test suite for unified market evaluation feature
"""

import pytest
from backend.unified_evaluation import UnifiedEvaluation


def test_unified_evaluation_initialization():
    """Test that unified evaluator can be initialized"""
    evaluator = UnifiedEvaluation()
    assert evaluator is not None
    assert evaluator.WEIGHTS is not None
    assert sum(evaluator.WEIGHTS.values()) == 1.0  # Weights should sum to 1


def test_compute_unified_score_all_bullish():
    """Test unified score calculation when all models are bullish"""
    evaluator = UnifiedEvaluation()

    result = evaluator.compute_unified_score(
        oi_score=85,
        oi_signal="BULLISH",
        oi_confidence=0.8,
        technical_score=80,
        technical_signal="BULLISH",
        technical_confidence=0.75,
        ml_bullish_prob=0.75,  # 75 on 0-100 scale
        oi_velocity_score=0.6,  # 80 on 0-100 scale
        global_cues_score=0.4,  # 70 on 0-100 scale
    )

    assert result["unified_signal"] == "BULLISH"
    assert result["unified_score"] > 60
    assert result["unified_confidence"] > 0.7  # High confidence when all agree
    assert result["model_agreement"]["agreement_ratio"] == 1.0  # All agree


def test_compute_unified_score_all_bearish():
    """Test unified score calculation when all models are bearish"""
    evaluator = UnifiedEvaluation()

    result = evaluator.compute_unified_score(
        oi_score=25,
        oi_signal="BEARISH",
        oi_confidence=0.75,
        technical_score=20,
        technical_signal="BEARISH",
        technical_confidence=0.7,
        ml_bullish_prob=0.25,  # 25 on 0-100 scale
        oi_velocity_score=-0.5,  # 25 on 0-100 scale
        global_cues_score=-0.6,  # 20 on 0-100 scale
    )

    assert result["unified_signal"] == "BEARISH"
    assert result["unified_score"] < 40
    assert result["unified_confidence"] > 0.7  # High confidence when all agree
    assert result["model_agreement"]["agreement_ratio"] == 1.0  # All agree


def test_compute_unified_score_mixed_signals():
    """Test unified score calculation with mixed signals"""
    evaluator = UnifiedEvaluation()

    result = evaluator.compute_unified_score(
        oi_score=75,  # BULLISH
        oi_signal="BULLISH",
        oi_confidence=0.6,
        technical_score=40,  # NEUTRAL
        technical_signal="NEUTRAL",
        technical_confidence=0.5,
        ml_bullish_prob=0.55,  # NEUTRAL
        oi_velocity_score=0.1,  # NEUTRAL
        global_cues_score=-0.2,  # BEARISH
    )

    # Score should be in NEUTRAL or BULLISH range
    assert 40 <= result["unified_score"] <= 80
    # Confidence should be lower due to disagreement
    assert result["unified_confidence"] < 0.7
    # Agreement ratio should be less than 1.0
    assert result["model_agreement"]["agreement_ratio"] < 1.0


def test_compute_unified_score_with_missing_technical():
    """Test unified score calculation when technical data is missing"""
    evaluator = UnifiedEvaluation()

    result = evaluator.compute_unified_score(
        oi_score=80,
        oi_signal="BULLISH",
        oi_confidence=0.8,
        technical_score=None,  # Missing
        technical_signal=None,
        technical_confidence=None,
        ml_bullish_prob=0.7,
        oi_velocity_score=0.5,
        global_cues_score=0.3,
    )

    # Should still work with missing technical data
    assert result["unified_score"] > 0
    assert result["unified_signal"] in ["BULLISH", "BEARISH", "NEUTRAL"]
    assert 0 < result["unified_confidence"] < 1


def test_compute_unified_score_with_missing_ml():
    """Test unified score calculation when ML data is missing"""
    evaluator = UnifiedEvaluation()

    result = evaluator.compute_unified_score(
        oi_score=75,
        oi_signal="BULLISH",
        oi_confidence=0.7,
        technical_score=72,
        technical_signal="BULLISH",
        technical_confidence=0.65,
        ml_bullish_prob=None,  # Missing
        oi_velocity_score=0.4,
        global_cues_score=0.2,
    )

    # Should still work with missing ML data (falls back to neutral 50)
    assert result["unified_score"] > 0
    assert result["unified_signal"] in ["BULLISH", "BEARISH", "NEUTRAL"]


def test_select_best_fo_option():
    """Test selection of best F&O option from scan results"""
    evaluator = UnifiedEvaluation()

    scan_result = {
        "symbol": "RELIANCE",
        "score": 82,
        "signal": "BULLISH",
        "confidence": 0.75,
        "ml_bullish_probability": 0.72,
        "top_picks": [
            {
                "strike": 2800,
                "type": "CE",
                "ltp": 45.50,
                "iv": 18.5,
                "delta": 0.45,
                "score": 85,
            }
        ],
        "metrics": {"oi_velocity_score": 0.35},
        "global_cues_score": 0.25,
        "regime": "TRENDING",
        "iv_rank": 45.2,
        "pcr": 1.15,
        "ltp": 2785.50,
        "days_to_expiry": 7,
        "signal_reasons": ["High Score", "AI Confirmed"],
    }

    technical_result = {
        "score": 75,
        "direction": "BULLISH",
        "confidence": 0.68,
    }

    result = evaluator.select_best_fo_option(scan_result, technical_result)

    assert result is not None
    assert result["symbol"] == "RELIANCE"
    assert result["best_option"]["strike"] == 2800
    assert result["best_option"]["type"] == "CE"
    assert result["unified_score"] > 0
    assert result["unified_signal"] == "BULLISH"
    assert result["unified_confidence"] > 0


def test_select_best_fo_option_no_picks():
    """Test selection when no top picks are available"""
    evaluator = UnifiedEvaluation()

    scan_result = {
        "symbol": "RELIANCE",
        "score": 82,
        "signal": "BULLISH",
        "confidence": 0.75,
        "top_picks": [],  # No picks
    }

    result = evaluator.select_best_fo_option(scan_result, None)

    # Should return None when no picks available
    assert result is None


def test_model_weights_sum_to_one():
    """Ensure model weights sum to 1.0 for proper ensemble"""
    evaluator = UnifiedEvaluation()
    total_weight = sum(evaluator.WEIGHTS.values())
    assert abs(total_weight - 1.0) < 0.0001  # Allow for floating point precision


def test_score_normalization_ranges():
    """Test that normalized scores are within 0-100 range"""
    evaluator = UnifiedEvaluation()

    result = evaluator.compute_unified_score(
        oi_score=100,
        oi_signal="BULLISH",
        oi_confidence=1.0,
        technical_score=100,
        technical_signal="BULLISH",
        technical_confidence=1.0,
        ml_bullish_prob=1.0,
        oi_velocity_score=1.0,
        global_cues_score=1.0,
    )

    # Check all normalized scores are in valid range
    for score in result["normalized_scores"].values():
        assert 0 <= score <= 100

    # Unified score should also be in valid range
    assert 0 <= result["unified_score"] <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
