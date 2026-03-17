"""
Signal Quality Filter (Improvement #1)

Enforces 6 hard conditions that ALL must be true for a signal to be tradeable:
1. Unified Score ≥ 75 (raised from 60)
2. Model Agreement Ratio ≥ 0.80 (at least 4 of 5 models agree)
3. Unified Confidence ≥ 0.80
4. Risk-Reward Ratio ≥ 1.5
5. Option Volume ≥ 20-day average volume for that strike
6. IV Percentile (IV Rank) between 20% and 80% (avoid extremes)

Quality Tags:
- PRIME: All 6 conditions pass → Full position
- QUALIFIED: 5 of 6 conditions pass → Half position
- MARGINAL: 4 of 6 conditions pass → Monitor only
- BLOCKED: 3 or fewer pass → Hidden from main list
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass
import logging

log = logging.getLogger(__name__)


class QualityTag(str, Enum):
    """Signal quality classification."""
    PRIME = "PRIME"              # All 6 conditions pass - highest confidence
    QUALIFIED = "QUALIFIED"      # 5 of 6 pass - acceptable risk
    MARGINAL = "MARGINAL"        # 4 of 6 pass - monitor only
    BLOCKED = "BLOCKED"          # 3 or fewer pass - do not trade


@dataclass
class QualityResult:
    """Result of signal quality evaluation."""
    tag: QualityTag
    conditions_passed: int
    total_conditions: int
    failed_conditions: list[str]
    details: dict

    def to_dict(self) -> dict:
        return {
            "quality_tag": self.tag.value,
            "conditions_passed": self.conditions_passed,
            "total_conditions": self.total_conditions,
            "failed_conditions": self.failed_conditions,
            "details": self.details,
        }


class SignalQualityFilter:
    """
    Signal Quality Filter - Enforces hard quality conditions on signals.

    Usage:
        filter = SignalQualityFilter()
        result = filter.evaluate(unified_result)
        if result.tag in [QualityTag.PRIME, QualityTag.QUALIFIED]:
            # Signal is tradeable
    """

    # Threshold values
    MIN_UNIFIED_SCORE = 75.0
    MIN_MODEL_AGREEMENT = 0.80
    MIN_UNIFIED_CONFIDENCE = 0.80
    MIN_RISK_REWARD_RATIO = 1.5
    MIN_VOLUME_RATIO = 1.0  # Volume must be >= average volume
    IV_RANK_MIN = 20.0
    IV_RANK_MAX = 80.0

    def evaluate(
        self,
        unified_score: float,
        model_agreement_ratio: float,
        unified_confidence: float,
        risk_reward_ratio: Optional[float],
        option_volume: Optional[float],
        option_avg_volume: Optional[float],
        iv_rank: Optional[float],
    ) -> QualityResult:
        """
        Evaluate signal quality based on 6 hard conditions.

        Args:
            unified_score: Unified score (0-100)
            model_agreement_ratio: Ratio of models agreeing (0-1)
            unified_confidence: Unified confidence (0-1)
            risk_reward_ratio: Risk-reward ratio (potential_profit / potential_loss)
            option_volume: Current option volume
            option_avg_volume: 20-day average volume for the strike
            iv_rank: IV percentile (0-100)

        Returns:
            QualityResult with tag and detailed breakdown
        """
        conditions = []
        failed = []
        details = {}

        # Condition 1: Unified Score ≥ 75
        score_pass = unified_score >= self.MIN_UNIFIED_SCORE
        conditions.append(score_pass)
        details["unified_score"] = {
            "value": unified_score,
            "threshold": self.MIN_UNIFIED_SCORE,
            "pass": score_pass,
        }
        if not score_pass:
            failed.append(f"Unified Score {unified_score:.1f} < {self.MIN_UNIFIED_SCORE}")

        # Condition 2: Model Agreement Ratio ≥ 0.80
        agreement_pass = model_agreement_ratio >= self.MIN_MODEL_AGREEMENT
        conditions.append(agreement_pass)
        details["model_agreement"] = {
            "value": model_agreement_ratio,
            "threshold": self.MIN_MODEL_AGREEMENT,
            "pass": agreement_pass,
        }
        if not agreement_pass:
            failed.append(f"Model Agreement {model_agreement_ratio:.2f} < {self.MIN_MODEL_AGREEMENT}")

        # Condition 3: Unified Confidence ≥ 0.80
        confidence_pass = unified_confidence >= self.MIN_UNIFIED_CONFIDENCE
        conditions.append(confidence_pass)
        details["unified_confidence"] = {
            "value": unified_confidence,
            "threshold": self.MIN_UNIFIED_CONFIDENCE,
            "pass": confidence_pass,
        }
        if not confidence_pass:
            failed.append(f"Unified Confidence {unified_confidence:.2f} < {self.MIN_UNIFIED_CONFIDENCE}")

        # Condition 4: Risk-Reward Ratio ≥ 1.5
        if risk_reward_ratio is not None:
            rr_pass = risk_reward_ratio >= self.MIN_RISK_REWARD_RATIO
            conditions.append(rr_pass)
            details["risk_reward_ratio"] = {
                "value": risk_reward_ratio,
                "threshold": self.MIN_RISK_REWARD_RATIO,
                "pass": rr_pass,
            }
            if not rr_pass:
                failed.append(f"Risk-Reward {risk_reward_ratio:.2f} < {self.MIN_RISK_REWARD_RATIO}")
        else:
            # If R:R not available, consider it as failed
            conditions.append(False)
            details["risk_reward_ratio"] = {
                "value": None,
                "threshold": self.MIN_RISK_REWARD_RATIO,
                "pass": False,
            }
            failed.append("Risk-Reward ratio not available")

        # Condition 5: Option Volume ≥ 20-day average
        if option_volume is not None and option_avg_volume is not None and option_avg_volume > 0:
            volume_ratio = option_volume / option_avg_volume
            volume_pass = volume_ratio >= self.MIN_VOLUME_RATIO
            conditions.append(volume_pass)
            details["option_volume"] = {
                "current": option_volume,
                "average": option_avg_volume,
                "ratio": volume_ratio,
                "threshold": self.MIN_VOLUME_RATIO,
                "pass": volume_pass,
            }
            if not volume_pass:
                failed.append(f"Volume ratio {volume_ratio:.2f}x < {self.MIN_VOLUME_RATIO}x avg")
        else:
            # If volume data not available, be lenient and pass this condition
            conditions.append(True)
            details["option_volume"] = {
                "current": option_volume,
                "average": option_avg_volume,
                "ratio": None,
                "threshold": self.MIN_VOLUME_RATIO,
                "pass": True,
                "note": "Volume data not available, condition passed by default",
            }

        # Condition 6: IV Rank between 20% and 80%
        if iv_rank is not None:
            iv_pass = self.IV_RANK_MIN <= iv_rank <= self.IV_RANK_MAX
            conditions.append(iv_pass)
            details["iv_rank"] = {
                "value": iv_rank,
                "min": self.IV_RANK_MIN,
                "max": self.IV_RANK_MAX,
                "pass": iv_pass,
            }
            if not iv_pass:
                if iv_rank < self.IV_RANK_MIN:
                    failed.append(f"IV Rank {iv_rank:.1f}% too low (< {self.IV_RANK_MIN}%)")
                else:
                    failed.append(f"IV Rank {iv_rank:.1f}% too high (> {self.IV_RANK_MAX}%)")
        else:
            # If IV rank not available, be lenient
            conditions.append(True)
            details["iv_rank"] = {
                "value": None,
                "min": self.IV_RANK_MIN,
                "max": self.IV_RANK_MAX,
                "pass": True,
                "note": "IV Rank not available, condition passed by default",
            }

        # Count passed conditions
        passed_count = sum(conditions)
        total_count = len(conditions)

        # Determine quality tag
        if passed_count == total_count:
            tag = QualityTag.PRIME
        elif passed_count >= 5:
            tag = QualityTag.QUALIFIED
        elif passed_count >= 4:
            tag = QualityTag.MARGINAL
        else:
            tag = QualityTag.BLOCKED

        return QualityResult(
            tag=tag,
            conditions_passed=passed_count,
            total_conditions=total_count,
            failed_conditions=failed,
            details=details,
        )

    def evaluate_from_unified_result(self, unified_result: dict) -> QualityResult:
        """
        Convenience method to evaluate from a unified evaluation result dict.

        Args:
            unified_result: Result dict from UnifiedEvaluation.select_best_fo_option()

        Returns:
            QualityResult
        """
        # Extract values from unified result
        unified_score = unified_result.get("unified_score", 0)
        model_agreement = unified_result.get("model_agreement", {})
        agreement_ratio = model_agreement.get("agreement_ratio", 0)
        unified_confidence = unified_result.get("unified_confidence", 0)

        # Risk-reward
        risk_reward = unified_result.get("risk_reward", {})
        rr_ratio = risk_reward.get("risk_reward_ratio") if risk_reward else None

        # Option volume (from best_option)
        best_option = unified_result.get("best_option", {})
        option_volume = best_option.get("volume")
        option_avg_volume = best_option.get("avg_volume_20d")

        # IV Rank
        iv_rank = unified_result.get("iv_rank")

        return self.evaluate(
            unified_score=unified_score,
            model_agreement_ratio=agreement_ratio,
            unified_confidence=unified_confidence,
            risk_reward_ratio=rr_ratio,
            option_volume=option_volume,
            option_avg_volume=option_avg_volume,
            iv_rank=iv_rank,
        )


# Singleton instance
_quality_filter = SignalQualityFilter()


def get_signal_quality_filter() -> SignalQualityFilter:
    """Get the singleton signal quality filter instance."""
    return _quality_filter
