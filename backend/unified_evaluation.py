"""
Unified Market Evaluation - Combines all available models for best F&O suggestion

This module integrates:
1. OI-Based Quantitative Scoring (compute_stock_score_v2)
2. Technical Indicators (scoring_technical)
3. ML Ensemble (LightGBM + LSTM)
4. OI Velocity (UOA detection)
5. Global Market Cues

It produces a single best F&O suggestion per stock with a unified confidence score.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from datetime import datetime

log = logging.getLogger(__name__)


class UnifiedEvaluation:
    """
    Unified evaluation combining all scoring models for comprehensive F&O analysis.
    """

    # Model weights for ensemble scoring
    WEIGHTS = {
        "oi_based": 0.35,      # Primary quantitative model
        "technical": 0.20,      # Technical indicators
        "ml_ensemble": 0.25,    # LightGBM + LSTM
        "oi_velocity": 0.10,    # UOA detection
        "global_cues": 0.10,    # Macro sentiment
    }

    def __init__(self):
        self.last_evaluation_time = None
        self.cached_evaluations = {}

    def compute_unified_score(
        self,
        oi_score: float,
        oi_signal: str,
        oi_confidence: float,
        technical_score: Optional[float],
        technical_signal: Optional[str],
        technical_confidence: Optional[float],
        ml_bullish_prob: Optional[float],
        oi_velocity_score: Optional[float],
        global_cues_score: Optional[float],
    ) -> Dict:
        """
        Compute a unified score combining all models with weighted ensemble.

        Args:
            oi_score: OI-based quantitative score (0-100)
            oi_signal: BULLISH/BEARISH/NEUTRAL
            oi_confidence: Confidence from OI model (0-1)
            technical_score: Technical indicator score (0-100)
            technical_signal: Technical signal direction
            technical_confidence: Technical confidence (0-1)
            ml_bullish_prob: ML ensemble probability (0-1)
            oi_velocity_score: OI velocity score (-1 to 1)
            global_cues_score: Global cues score (-1 to 1)

        Returns:
            Dict with unified_score, unified_signal, unified_confidence, component_scores
        """

        # Normalize all scores to 0-100 scale
        normalized_scores = {}

        # 1. OI-Based Score (already 0-100)
        normalized_scores["oi_based"] = oi_score

        # 2. Technical Score (0-100 if available)
        if technical_score is not None:
            normalized_scores["technical"] = technical_score
        else:
            # If technical not available, redistribute weight
            normalized_scores["technical"] = oi_score  # fallback to OI

        # 3. ML Ensemble (convert probability to directional score)
        if ml_bullish_prob is not None:
            # Convert probability to 0-100 score
            # 0.5 = neutral (50), >0.5 = bullish (up to 100), <0.5 = bearish (down to 0)
            ml_score = ml_bullish_prob * 100
            normalized_scores["ml_ensemble"] = ml_score
        else:
            normalized_scores["ml_ensemble"] = 50  # neutral if unavailable

        # 4. OI Velocity (convert -1 to 1 to 0-100 scale)
        if oi_velocity_score is not None:
            # -1 = 0 (bearish), 0 = 50 (neutral), +1 = 100 (bullish)
            velocity_normalized = (oi_velocity_score + 1) * 50
            normalized_scores["oi_velocity"] = velocity_normalized
        else:
            normalized_scores["oi_velocity"] = 50  # neutral

        # 5. Global Cues (convert -1 to 1 to 0-100 scale)
        if global_cues_score is not None:
            gc_normalized = (global_cues_score + 1) * 50
            normalized_scores["global_cues"] = gc_normalized
        else:
            normalized_scores["global_cues"] = 50  # neutral

        # Compute weighted average
        unified_score = sum(
            normalized_scores[model] * self.WEIGHTS[model]
            for model in self.WEIGHTS.keys()
        )

        # Determine unified signal based on score thresholds
        if unified_score >= 60:
            unified_signal = "BULLISH"
        elif unified_score <= 40:
            unified_signal = "BEARISH"
        else:
            unified_signal = "NEUTRAL"

        # Compute unified confidence
        # Higher confidence when models agree
        model_signals = []

        # OI signal
        if oi_signal == "BULLISH":
            model_signals.append(1)
        elif oi_signal == "BEARISH":
            model_signals.append(-1)
        else:
            model_signals.append(0)

        # Technical signal
        if technical_signal == "BULLISH":
            model_signals.append(1)
        elif technical_signal == "BEARISH":
            model_signals.append(-1)
        else:
            model_signals.append(0)

        # ML signal
        if ml_bullish_prob is not None:
            if ml_bullish_prob > 0.6:
                model_signals.append(1)
            elif ml_bullish_prob < 0.4:
                model_signals.append(-1)
            else:
                model_signals.append(0)
        else:
            model_signals.append(0)

        # OI velocity signal
        if oi_velocity_score is not None:
            if oi_velocity_score > 0.3:
                model_signals.append(1)
            elif oi_velocity_score < -0.3:
                model_signals.append(-1)
            else:
                model_signals.append(0)
        else:
            model_signals.append(0)

        # Global cues signal
        if global_cues_score is not None:
            if global_cues_score > 0.3:
                model_signals.append(1)
            elif global_cues_score < -0.3:
                model_signals.append(-1)
            else:
                model_signals.append(0)
        else:
            model_signals.append(0)

        # Calculate agreement (how many models agree with majority)
        from collections import Counter
        signal_counts = Counter(model_signals)
        most_common = signal_counts.most_common(1)[0]
        agreement_count = most_common[1]
        total_models = len(model_signals)
        agreement_ratio = agreement_count / total_models

        # Base confidence from individual model confidences
        confidences = [oi_confidence]
        if technical_confidence is not None:
            confidences.append(technical_confidence)
        if ml_bullish_prob is not None:
            # Convert ML probability to confidence (distance from 0.5)
            ml_conf = abs(ml_bullish_prob - 0.5) * 2
            confidences.append(ml_conf)

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        # Unified confidence combines average confidence with agreement ratio
        unified_confidence = (avg_confidence * 0.6) + (agreement_ratio * 0.4)
        unified_confidence = min(0.99, max(0.01, unified_confidence))

        return {
            "unified_score": round(unified_score, 2),
            "unified_signal": unified_signal,
            "unified_confidence": round(unified_confidence, 3),
            "component_scores": normalized_scores,
            "model_agreement": {
                "signals": model_signals,
                "agreement_ratio": round(agreement_ratio, 3),
            },
        }

    def select_best_fo_option(
        self,
        scan_result: Dict,
        technical_result: Optional[Dict],
    ) -> Optional[Dict]:
        """
        Select the single best F&O option from a stock's scan result.

        Args:
            scan_result: Result from compute_stock_score_v2 (via /api/scan)
            technical_result: Result from compute_technical_score (optional)

        Returns:
            Dict with the best option details and unified scoring
        """

        symbol = scan_result.get("symbol")
        top_picks = scan_result.get("top_picks", [])

        if not top_picks:
            return None

        # Get the best pick (highest scored option)
        best_option = top_picks[0]

        # Extract model scores
        oi_score = scan_result.get("score", 0)
        oi_signal = scan_result.get("signal", "NEUTRAL")
        oi_confidence = scan_result.get("confidence", 0.5)

        technical_score = None
        technical_signal = None
        technical_confidence = None
        if technical_result:
            technical_score = technical_result.get("score", 0)
            technical_signal = technical_result.get("direction", "NEUTRAL")
            technical_confidence = technical_result.get("confidence", 0.5)

        ml_bullish_prob = scan_result.get("ml_bullish_probability")

        # OI velocity score (from UOA detection)
        metrics = scan_result.get("metrics", {})
        oi_velocity_score = metrics.get("oi_velocity_score")

        # Global cues
        global_cues_score = scan_result.get("global_cues_score")

        # Compute unified evaluation
        unified = self.compute_unified_score(
            oi_score=oi_score,
            oi_signal=oi_signal,
            oi_confidence=oi_confidence,
            technical_score=technical_score,
            technical_signal=technical_signal,
            technical_confidence=technical_confidence,
            ml_bullish_prob=ml_bullish_prob,
            oi_velocity_score=oi_velocity_score,
            global_cues_score=global_cues_score,
        )

        # Build comprehensive result
        result = {
            "symbol": symbol,
            "best_option": {
                "strike": best_option.get("strike"),
                "type": best_option.get("type"),
                "ltp": best_option.get("ltp"),
                "iv": best_option.get("iv"),
                "delta": best_option.get("delta"),
                "option_score": best_option.get("score"),
            },
            "unified_score": unified["unified_score"],
            "unified_signal": unified["unified_signal"],
            "unified_confidence": unified["unified_confidence"],
            "component_scores": {
                "oi_based": {
                    "score": oi_score,
                    "signal": oi_signal,
                    "confidence": oi_confidence,
                },
                "technical": {
                    "score": technical_score,
                    "signal": technical_signal,
                    "confidence": technical_confidence,
                } if technical_result else None,
                "ml_ensemble": {
                    "bullish_probability": ml_bullish_prob,
                    "lgb_prob": scan_result.get("ml_lgb_prob"),
                    "nn_prob": scan_result.get("ml_nn_prob"),
                } if ml_bullish_prob is not None else None,
                "oi_velocity": {
                    "score": oi_velocity_score,
                    "uoa_detected": scan_result.get("uoa_detected", False),
                } if oi_velocity_score is not None else None,
                "global_cues": {
                    "score": global_cues_score,
                    "adjustment": scan_result.get("global_cues_adjustment", 0),
                } if global_cues_score is not None else None,
            },
            "normalized_scores": unified["component_scores"],
            "model_agreement": unified["model_agreement"],
            "regime": scan_result.get("regime"),
            "iv_rank": scan_result.get("iv_rank"),
            "pcr": scan_result.get("pcr"),
            "spot_price": scan_result.get("ltp"),
            "days_to_expiry": scan_result.get("days_to_expiry"),
            "signal_reasons": scan_result.get("signal_reasons", []),
        }

        return result

    async def evaluate_market(
        self,
        scan_data: List[Dict],
        include_technical: bool = True,
    ) -> List[Dict]:
        """
        Evaluate entire market and return best F&O option per stock with unified scoring.

        Args:
            scan_data: List of scan results from /api/scan
            include_technical: Whether to include technical scoring (slower)

        Returns:
            List of unified evaluation results, sorted by unified_score descending
        """

        results = []

        for stock in scan_data:
            symbol = stock.get("symbol")

            # Get technical score if requested
            technical_result = None
            if include_technical:
                try:
                    from .scoring_technical import compute_technical_score
                    technical_result = await compute_technical_score(symbol)
                except Exception as e:
                    log.warning(f"Failed to compute technical score for {symbol}: {e}")

            # Select best option with unified scoring
            evaluation = self.select_best_fo_option(stock, technical_result)

            if evaluation:
                results.append(evaluation)

        # Sort by unified score descending
        results.sort(key=lambda x: x["unified_score"], reverse=True)

        self.last_evaluation_time = datetime.now()

        return results


# Singleton instance
_unified_evaluator = UnifiedEvaluation()


def get_unified_evaluator() -> UnifiedEvaluation:
    """Get the singleton unified evaluator instance."""
    return _unified_evaluator
