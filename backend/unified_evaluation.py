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
import asyncio
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


class UnifiedEvaluation:
    """
    Unified evaluation combining all scoring models for comprehensive F&O analysis.
    """

    # Model weights for ensemble scoring - Optimized for best performance
    # Based on backtesting and accuracy metrics, these weights provide optimal balance
    WEIGHTS = {
        "oi_based": 0.30,       # Primary quantitative model (reduced from 0.35)
        "technical": 0.25,      # Technical indicators (increased from 0.20)
        "ml_ensemble": 0.30,    # LightGBM + LSTM (increased from 0.25)
        "oi_velocity": 0.08,    # UOA detection (reduced from 0.10)
        "global_cues": 0.07,    # Macro sentiment (reduced from 0.10)
    }

    # Risk management parameters
    DEFAULT_PROFIT_TARGET_PCT = 20.0  # 20% profit target
    DEFAULT_STOP_LOSS_PCT = 15.0      # 15% stop loss (tighter risk management)

    def __init__(self):
        self.last_evaluation_time = None
        self.cached_evaluations = {}
        self._technical_cache = {}  # {symbol: (TechnicalScore, timestamp)}
        self._technical_cache_ttl_minutes = 30

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
            "normalized_scores": normalized_scores,  # Alias for backward compatibility
            "model_agreement": {
                "signals": model_signals,
                "agreement_ratio": round(agreement_ratio, 3),
            },
        }

    def calculate_risk_reward(
        self,
        option_ltp: float,
        lot_size: int,
        profit_target_pct: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
    ) -> Dict:
        """
        Calculate target and stoploss prices with risk-reward metrics.

        Args:
            option_ltp: Current LTP of the option
            lot_size: Lot size for the symbol
            profit_target_pct: Target profit percentage (default from DEFAULT_PROFIT_TARGET_PCT)
            stop_loss_pct: Stop loss percentage (default from DEFAULT_STOP_LOSS_PCT)

        Returns:
            Dict with target_price, stoploss_price, lot_size, potential_profit, potential_loss, risk_reward_ratio
        """
        if profit_target_pct is None:
            profit_target_pct = self.DEFAULT_PROFIT_TARGET_PCT
        if stop_loss_pct is None:
            stop_loss_pct = self.DEFAULT_STOP_LOSS_PCT

        # Calculate target and stoploss prices
        target_price = option_ltp * (1 + profit_target_pct / 100)
        stoploss_price = option_ltp * (1 - stop_loss_pct / 100)

        # Calculate potential profit and loss
        potential_profit = (target_price - option_ltp) * lot_size
        potential_loss = (option_ltp - stoploss_price) * lot_size

        # Calculate risk-reward ratio
        risk_reward_ratio = potential_profit / potential_loss if potential_loss > 0 else 0

        return {
            "target_price": round(target_price, 2),
            "stoploss_price": round(stoploss_price, 2),
            "target_pct": profit_target_pct,
            "stoploss_pct": stop_loss_pct,
            "lot_size": lot_size,
            "potential_profit": round(potential_profit, 2),
            "potential_loss": round(potential_loss, 2),
            "risk_reward_ratio": round(risk_reward_ratio, 2),
            "capital_required": round(option_ltp * lot_size, 2),
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
            "regime": scan_result.get("regime") or "NEUTRAL",
            "iv_rank": scan_result.get("iv_rank") or 0.0,
            "pcr": scan_result.get("pcr") or 1.0,
            "spot_price": scan_result.get("ltp") or 0.0,
            "days_to_expiry": scan_result.get("days_to_expiry") or 0,
            "signal_reasons": scan_result.get("signal_reasons", []),
        }

        # Add risk-reward metrics if we have LTP and can get lot size
        option_ltp = best_option.get("ltp")
        if option_ltp and option_ltp > 0:
            from .constants import LOT_SIZES
            lot_size = LOT_SIZES.get(symbol, 1)
            risk_reward = self.calculate_risk_reward(
                option_ltp=option_ltp,
                lot_size=lot_size,
            )
            result["risk_reward"] = risk_reward

        return result

    async def evaluate_market(
        self,
        scan_data: List[Dict],
        include_technical: bool = True,
        apply_filters: bool = True,
    ) -> List[Dict]:
        """
        Evaluate entire market and return best F&O option per stock with unified scoring.

        Now includes 5 filter gates for improved win rate:
        1. F&O Ban Check (Gate 1)
        2. Time of Day Filter (Gate 2)
        3. Market Regime Override (Gate 3)
        4. Event Blackout (Gate 4)
        5. Signal Quality (Gate 5)
        6. Signal Persistence (Gate 6)

        Args:
            scan_data: List of scan results from /api/scan
            include_technical: Whether to include technical scoring (slower)
            apply_filters: Whether to apply the 5 filter gates (default True)

        Returns:
            List of unified evaluation results, sorted by unified_score descending
        """

        results = []

        # Import filter modules
        if apply_filters:
            from .filters.signal_quality import get_signal_quality_filter
            from .filters.time_of_day import get_time_of_day_filter
            from .filters.regime_override import get_regime_override_filter
            from .filters.event_calendar import get_event_calendar
            from .filters.signal_persistence import get_signal_persistence_cache

            quality_filter = get_signal_quality_filter()
            time_filter = get_time_of_day_filter()
            regime_filter = get_regime_override_filter()
            event_calendar = get_event_calendar()
            persistence_cache = get_signal_persistence_cache()

        for stock in scan_data:
            symbol = stock.get("symbol")
            if not symbol:
                continue

            # Check technical cache first if enabled
            technical_result = None
            if include_technical:
                now = datetime.now()
                cached_tech, ts = self._technical_cache.get(symbol, (None, None))
                if cached_tech and (now - ts).total_seconds() < self._technical_cache_ttl_minutes * 60:
                    technical_result = cached_tech
                else:
                    try:
                        tech_obj = await self._fetch_and_compute_technical(symbol)
                        if tech_obj:
                            technical_result = tech_obj.to_dict()
                            self._technical_cache[symbol] = (technical_result, now)
                    except Exception as e:
                        log.warning(f"Failed to compute technical score for {symbol}: {e}")

            # GATE 1: F&O Ban Check (CRITICAL - runs first)
            if apply_filters:
                is_banned = await event_calendar.is_fo_banned(symbol)
                if is_banned:
                    log.info(f"{symbol} on F&O ban list - skipping")
                    # Add to results as blocked for transparency
                    results.append({
                        "symbol": symbol,
                        "unified_score": 0,
                        "unified_signal": "BLOCKED",
                        "unified_confidence": 0,
                        "blocked": True,
                        "blocked_reason": "F&O Ban List",
                        "fo_ban": True,
                    })
                    continue

            # (Technical result fetched above via cache/helper)

            # Select best option with unified scoring
            evaluation = self.select_best_fo_option(stock, technical_result)

            if not evaluation:
                continue

            # Apply filter gates if enabled
            if apply_filters:
                evaluation = await self._apply_filter_gates(
                    evaluation=evaluation,
                    quality_filter=quality_filter,
                    time_filter=time_filter,
                    regime_filter=regime_filter,
                    event_calendar=event_calendar,
                    persistence_cache=persistence_cache,
                )

            results.append(evaluation)

        # Sort by unified score descending
        results.sort(key=lambda x: x["unified_score"], reverse=True)

        self.last_evaluation_time = datetime.now()

        return results

    async def _fetch_and_compute_technical(self, symbol: str):
        """Fetch price data and compute technical score for a symbol."""
        try:
            import yfinance as yf
            from .constants import YFINANCE_TICKER_MAP
            from .scoring_technical import compute_technical_score

            ticker = YFINANCE_TICKER_MAP.get(symbol, f"{symbol}.NS")
            
            # Fetch 15m bars for 5 days (consistent with /api/score-technical)
            df = await asyncio.to_thread(
                lambda: yf.download(ticker, period="5d", interval="15m", progress=False)
            )

            if df is None or df.empty:
                return None

            # Flatten columns if MultiIndex
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = df.columns.get_level_values(0)

            def _to_list(series_or_df):
                if hasattr(series_or_df, "tolist"):
                    return series_or_df.tolist()
                if hasattr(series_or_df, "iloc"):
                    return series_or_df.iloc[:, 0].tolist()
                return list(series_or_df)

            closes = _to_list(df["Close"].dropna())
            highs = _to_list(df["High"].dropna())
            lows = _to_list(df["Low"].dropna())
            volumes = _to_list(df["Volume"].dropna())

            def _flatten(lst):
                if lst and isinstance(lst[0], (list, tuple, np.ndarray)):
                    return [x[0] if hasattr(x, "__len__") and len(x) > 0 else x for x in lst]
                return lst

            closes = _flatten(closes)
            highs = _flatten(highs)
            lows = _flatten(lows)
            volumes = _flatten(volumes)

            return compute_technical_score(closes, highs, lows, volumes)

        except Exception as e:
            log.warning(f"Technical fetch failed for {symbol}: {e}")
            return None

    async def _apply_filter_gates(
        self,
        evaluation: Dict,
        quality_filter,
        time_filter,
        regime_filter,
        event_calendar,
        persistence_cache,
    ) -> Dict:
        """
        Apply all 6 filter gates to an evaluation result.

        Gates are applied in order:
        1. F&O Ban (already checked in evaluate_market)
        2. Time of Day
        3. Market Regime Override
        4. Event Blackout
        5. Signal Quality
        6. Signal Persistence

        Args:
            evaluation: Unified evaluation result dict
            quality_filter: SignalQualityFilter instance
            time_filter: TimeOfDayFilter instance
            regime_filter: RegimeOverrideFilter instance
            event_calendar: EventCalendar instance
            persistence_cache: SignalPersistenceCache instance

        Returns:
            Updated evaluation dict with filter results
        """
        symbol = evaluation.get("symbol")
        unified_score = evaluation.get("unified_score")
        unified_signal = evaluation.get("unified_signal")
        unified_confidence = evaluation.get("unified_confidence")
        best_option = evaluation.get("best_option", {})
        option_delta = best_option.get("delta")
        days_to_expiry = evaluation.get("days_to_expiry")
        regime = evaluation.get("regime")
        spot_price = evaluation.get("spot_price")

        # Track if signal passes all gates
        blocked = False
        blocked_reasons = []

        # GATE 2: Time of Day Filter
        time_result = None
        quality_tag = None  # Will be set by Gate 5

        # We'll check time filter after quality filter since it needs quality_tag
        # For now, get current window info
        current_time_info = time_filter.get_current_filter(
            unified_score=unified_score,
            option_delta=option_delta,
        )

        # GATE 3: Market Regime Override
        regime_result = regime_filter.apply_override(
            regime=regime or "UNKNOWN",
            signal_direction=unified_signal,
            option_delta=option_delta,
            days_to_expiry=days_to_expiry,
            spot_price=spot_price,
        )

        if not regime_result.allowed:
            blocked = True
            blocked_reasons.append(regime_result.reason)

        # Apply confidence adjustment from regime
        unified_confidence = min(0.99, max(0.01, unified_confidence + regime_result.confidence_adjustment))

        # GATE 4: Event Blackout
        event_result = await event_calendar.check_events(symbol)

        if event_result.blocked:
            blocked = True
            blocked_reasons.append(event_result.message)

        # Apply confidence adjustment from events
        unified_confidence = min(0.99, max(0.01, unified_confidence + event_result.confidence_adjustment))

        # GATE 5: Signal Quality
        risk_reward = evaluation.get("risk_reward", {})
        model_agreement = evaluation.get("model_agreement", {})

        quality_result = quality_filter.evaluate(
            unified_score=unified_score,
            model_agreement_ratio=model_agreement.get("agreement_ratio", 0),
            unified_confidence=unified_confidence,
            risk_reward_ratio=risk_reward.get("risk_reward_ratio"),
            option_volume=best_option.get("volume"),
            option_avg_volume=best_option.get("avg_volume_20d"),
            iv_rank=evaluation.get("iv_rank"),
        )

        quality_tag = quality_result.tag.value

        # BLOCKED or MARGINAL signals are not shown by default
        if quality_tag in ["BLOCKED", "MARGINAL"]:
            blocked = True
            blocked_reasons.append(f"Quality: {quality_tag} ({quality_result.conditions_passed}/{quality_result.total_conditions} conditions passed)")

        # Now check time filter with quality tag
        time_allowed, time_reason = time_filter.check_signal(
            quality_tag=quality_tag,
            unified_score=unified_score,
            option_delta=option_delta,
        )

        if not time_allowed:
            blocked = True
            blocked_reasons.append(time_reason)

        # GATE 6: Signal Persistence
        persistence_result = persistence_cache.update_history(
            symbol=symbol,
            unified_score=unified_score,
            signal_direction=unified_signal,
            quality_tag=quality_tag,
            unified_confidence=unified_confidence,
        )

        if not persistence_result.is_actionable:
            # Building signals are shown but marked as not actionable
            pass  # Don't block, just mark

        # Update evaluation with filter results
        evaluation.update({
            # Original confidence before adjustments
            "unified_confidence_original": evaluation.get("unified_confidence"),
            # Updated confidence after regime/event adjustments
            "unified_confidence": round(unified_confidence, 3),
            # Filter results
            "quality_filter": quality_result.to_dict(),
            "time_filter": current_time_info.to_dict(),
            "regime_override": regime_result.to_dict(),
            "event_flag": event_result.to_dict(),
            "persistence": persistence_result.to_dict(),
            # Blocking status
            "blocked": blocked,
            "blocked_reasons": blocked_reasons,
            # Quick access fields
            "quality_tag": quality_tag,
            "is_actionable": not blocked and persistence_result.is_actionable,
        })

        return evaluation


# Singleton instance
_unified_evaluator = UnifiedEvaluation()


def get_unified_evaluator() -> UnifiedEvaluation:
    """Get the singleton unified evaluator instance."""
    return _unified_evaluator
