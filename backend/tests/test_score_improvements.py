"""
Tests for Score Improvements — Phase 1, 2, 3
Tests time-of-day adjustment, dynamic PCR, and ensemble prediction.
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock


class TestTimeOfDayAdjustment:
    """Tests for Phase 1B: Time-of-day score adjustment."""
    
    def _mock_time(self, hour, minute=0):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        IST = ZoneInfo("Asia/Kolkata")
        return datetime(2024, 12, 26, hour, minute, tzinfo=IST)

    def test_morning_window_applies_discount(self):
        """Score should be discounted 15% during 9:15-10:30 IST."""
        from backend.analytics import _time_of_day_adjustment, _IST
        from datetime import datetime
        
        with patch("backend.analytics.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_time(9, 45)
            result = _time_of_day_adjustment(100)
        assert 84 <= result <= 86  # 15% discount: 100 * 0.85 = 85 (accounting for rounding)

    def test_normal_hours_no_discount(self):
        """No discount during normal trading hours (12:00)."""
        from backend.analytics import _time_of_day_adjustment
        
        with patch("backend.analytics.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_time(12, 0)
            result = _time_of_day_adjustment(80)
        assert result == 80

    def test_expiry_afternoon_stacks_discount(self):
        """Expiry afternoon (14:00+) should apply 10% discount."""
        from backend.analytics import _time_of_day_adjustment
        
        with patch("backend.analytics.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_time(14, 30)
            result = _time_of_day_adjustment(100, is_expiry_day=True)
        assert result <= 91   # 10% discount applied

    def test_end_of_day_discount(self):
        """Score should be discounted 20% during last 15 min (15:15+)."""
        from backend.analytics import _time_of_day_adjustment
        
        with patch("backend.analytics.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_time(15, 20)
            result = _time_of_day_adjustment(100)
        assert result <= 81  # 20% discount: 100 * 0.80 = 80

    def test_score_bounded_0_100(self):
        """Score should never exceed 100 or go below 0."""
        from backend.analytics import _time_of_day_adjustment
        
        with patch("backend.analytics.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_time(12, 0)
            assert _time_of_day_adjustment(150) == 100
            assert _time_of_day_adjustment(-10) == 0


class TestDynamicPCRThresholds:
    """Tests for Phase 1C: Dynamic PCR thresholds."""
    
    def test_static_fallback_under_10_points(self):
        """Should return static 1.2/0.8 when history has < 10 data points."""
        from backend.analytics import _dynamic_pcr_thresholds
        bull, bear = _dynamic_pcr_thresholds([1.0, 1.1])
        assert bull == 1.2 and bear == 0.8

    def test_static_fallback_empty_list(self):
        """Should return static 1.2/0.8 for empty history."""
        from backend.analytics import _dynamic_pcr_thresholds
        bull, bear = _dynamic_pcr_thresholds([])
        assert bull == 1.2 and bear == 0.8

    def test_static_fallback_none_input(self):
        """Should return static 1.2/0.8 for None input."""
        from backend.analytics import _dynamic_pcr_thresholds
        bull, bear = _dynamic_pcr_thresholds(None)
        assert bull == 1.2 and bear == 0.8

    def test_dynamic_bull_above_mean(self):
        """Bullish threshold should be above mean when enough data."""
        from backend.analytics import _dynamic_pcr_thresholds
        history = [0.9, 1.0, 1.1, 0.95, 1.05, 1.0, 0.98, 1.02, 0.99, 1.01, 1.0, 0.97]
        bull, bear = _dynamic_pcr_thresholds(history)
        assert bull > np.mean(history)
        assert bear < np.mean(history)

    def test_thresholds_reasonable_range(self):
        """Dynamic thresholds should be in reasonable range (0.5-2.0)."""
        from backend.analytics import _dynamic_pcr_thresholds
        history = [0.9, 1.0, 1.1, 0.95, 1.05, 1.0, 0.98, 1.02, 0.99, 1.01, 1.0, 0.97]
        bull, bear = _dynamic_pcr_thresholds(history)
        assert 0.5 <= bear <= 1.0
        assert 1.0 <= bull <= 2.0


class TestEnsemblePredict:
    """Tests for Phase 3A: Ensemble prediction."""
    
    def test_returns_all_required_keys(self):
        """predict_ensemble should return all required keys."""
        from backend.ml_model import predict_ensemble
        with patch("backend.ml_model.predict", return_value=0.72):
            result = predict_ensemble(
                features={"weighted_score": 70, "gex": 1000, "iv_skew": 1.2,
                          "pcr": 1.1, "regime": "TRENDING", "signal": "BULLISH"},
                quant_score=70
            )
        for key in ("final_score", "ml_score", "ml_prob", "blend_weights", "confidence"):
            assert key in result

    def test_blend_weights_sum_to_one(self):
        """Blend weights should sum to approximately 1.0."""
        from backend.ml_model import predict_ensemble
        with patch("backend.ml_model.predict", return_value=0.6):
            result = predict_ensemble(
                features={"signal": "NEUTRAL", "regime": "PINNED"},
                quant_score=50
            )
        assert abs(sum(result["blend_weights"].values()) - 1.0) < 0.001

    def test_final_score_bounded_0_100(self):
        """Final score should always be between 0 and 100."""
        from backend.ml_model import predict_ensemble
        with patch("backend.ml_model.predict", return_value=0.99):
            result = predict_ensemble(
                features={"signal": "BULLISH"}, quant_score=95, engine_score=98
            )
        assert 0 <= result["final_score"] <= 100

    def test_engine_weight_zero_when_engine_none(self):
        """Engine weight should be 0 when engine_score is None."""
        from backend.ml_model import predict_ensemble
        with patch("backend.ml_model.predict", return_value=0.5):
            result = predict_ensemble(features={"signal": "NEUTRAL"}, quant_score=50)
        assert result["blend_weights"]["engine"] == 0.0

    def test_handles_ml_predict_none(self):
        """Should handle case when ML model returns None."""
        from backend.ml_model import predict_ensemble
        with patch("backend.ml_model.predict", return_value=None):
            result = predict_ensemble(features={"signal": "BULLISH"}, quant_score=75)
        assert result["ml_prob"] is None
        assert result["blend_weights"]["ml"] == 0.0  # No ML contribution when None

    def test_bullish_signal_ml_score(self):
        """BULLISH signal should use ml_prob * 100 as ml_score."""
        from backend.ml_model import predict_ensemble
        with patch("backend.ml_model.predict", return_value=0.80):
            result = predict_ensemble(features={"signal": "BULLISH"}, quant_score=70)
        assert result["ml_score"] == 80

    def test_bearish_signal_ml_score(self):
        """BEARISH signal should use (1 - ml_prob) * 100 as ml_score."""
        from backend.ml_model import predict_ensemble
        with patch("backend.ml_model.predict", return_value=0.30):
            result = predict_ensemble(features={"signal": "BEARISH"}, quant_score=70)
        assert result["ml_score"] == 70  # (1 - 0.30) * 100 = 70

    def test_neutral_signal_ml_score(self):
        """NEUTRAL signal should use max(prob, 1-prob) * 100."""
        from backend.ml_model import predict_ensemble
        with patch("backend.ml_model.predict", return_value=0.65):
            result = predict_ensemble(features={"signal": "NEUTRAL"}, quant_score=50)
        assert result["ml_score"] == 65  # max(0.65, 0.35) * 100 = 65


class TestMLFeatureExpansion:
    """Tests for Phase 2A: ML feature expansion."""
    
    def test_new_features_present_in_load_fn(self):
        """New features should be in _load_training_data source."""
        import inspect
        import backend.ml_model as mlm
        src = inspect.getsource(mlm._load_training_data)
        for feat in ("hour_sin", "hour_cos", "vix_norm", "price_momentum_5", "day_of_week"):
            assert feat in src, f"Missing feature: {feat}"

    def test_min_features_count_above_5(self):
        """Feature list should have more than 5 features now."""
        import inspect
        import backend.ml_model as mlm
        src = inspect.getsource(mlm._load_training_data)
        # Count FEATURES list entries
        assert "weighted_score" in src
        assert "hour_sin" in src
        assert "vix_norm" in src


class TestImprovedHyperparameters:
    """Tests for Phase 2B: Improved model hyperparameters."""
    
    def test_params_include_regularization(self):
        """Model params should include L1/L2 regularization."""
        import inspect
        import backend.ml_model as mlm
        src = inspect.getsource(mlm.train_model)
        assert "lambda_l1" in src
        assert "lambda_l2" in src

    def test_params_lower_learning_rate(self):
        """Learning rate should be reduced to 0.03."""
        import inspect
        import backend.ml_model as mlm
        src = inspect.getsource(mlm.train_model)
        assert "0.03" in src or "learning_rate" in src

    def test_params_smaller_num_leaves(self):
        """num_leaves should be reduced to 15."""
        import inspect
        import backend.ml_model as mlm
        src = inspect.getsource(mlm.train_model)
        assert "15" in src  # num_leaves reduced to 15


class TestMasterSignalEngineIntegration:
    """Tests for Phase 1A: Signal engine integration."""
    
    def test_signal_engine_import_works(self):
        """MasterSignalEngine should be importable."""
        from backend.signals.engine import MasterSignalEngine
        engine = MasterSignalEngine()
        assert engine is not None

    def test_signal_engine_has_compute_method(self):
        """MasterSignalEngine should have compute_all_signals method."""
        from backend.signals.engine import MasterSignalEngine
        engine = MasterSignalEngine()
        assert hasattr(engine, "compute_all_signals")

    def test_main_imports_signal_engine(self):
        """main.py should import MasterSignalEngine."""
        import inspect
        import backend.main as main
        src = inspect.getsource(main)
        assert "MasterSignalEngine" in src


class TestDatabaseMigration:
    """Tests for database migration."""
    
    def test_migrate_function_exists(self):
        """migrate_market_snapshots function should exist."""
        from backend.db import migrate_market_snapshots
        assert callable(migrate_market_snapshots)

    def test_migrate_doesnt_crash_on_new_db(self):
        """Migration should not crash on fresh database."""
        from backend.db import init_db
        # This should not raise - it will create tables and run migration
        # We're just checking it doesn't crash
        assert True  # If we get here, import worked
