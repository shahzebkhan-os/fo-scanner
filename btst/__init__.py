"""
BTST (Buy Today, Sell Tomorrow) ML Training Package.

This package provides advanced ML training infrastructure with:
- DataCollector: nsefin/nsepython integration for historical data
- FeatureEngineering: 400+ technical and market features
- ModelArchitecture: TFT + LGBM + XGB + LR ensemble with meta-learner
- TrainingPipeline: Optuna hyperparameter optimization
- Main: CLI for training/prediction/evaluation

Usage:
    cd btst
    python3 main.py --mode train --optimize --start 2024-01-01 --end 2026-03-31
"""

__version__ = "1.0.0"
__author__ = "FO Scanner Team"

from .data_collector import DataCollector
from .feature_engineering import FeatureEngineering
from .model_architecture import EnsemblePredictor
from .training_pipeline import TrainingPipeline

__all__ = [
    'DataCollector',
    'FeatureEngineering',
    'EnsemblePredictor',
    'TrainingPipeline'
]
