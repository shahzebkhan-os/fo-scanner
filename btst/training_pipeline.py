"""
TrainingPipeline module with Optuna hyperparameter optimization.

This module orchestrates the entire training process:
- Data preparation and feature selection
- Optuna hyperparameter optimization
- Model training with best parameters
- Evaluation and metrics reporting
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional
from pathlib import Path
import json
from datetime import datetime

log = logging.getLogger(__name__)

try:
    import optuna
    from optuna.pruners import MedianPruner
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    log.warning("Optuna not available")

try:
    from sklearn.metrics import accuracy_score, f1_score, classification_report
    from sklearn.model_selection import train_test_split
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from .model_architecture import EnsemblePredictor


class TrainingPipeline:
    """Training pipeline with Optuna optimization."""

    def __init__(self, data: pd.DataFrame, optimize: bool = False, n_trials: int = 100):
        self.data = data
        self.optimize = optimize
        self.n_trials = n_trials
        self.best_params = None
        self.model = None

        log.info("=" * 80)
        log.info("TRAINING PIPELINE STARTED")
        log.info("=" * 80)

    def run(self) -> Tuple[EnsemblePredictor, Dict]:
        """Run the training pipeline."""
        # Step 1: Prepare data
        log.info("Preparing data...")
        X_train, X_val, X_test, y_train, y_val, y_test = self._prepare_data()
        log.info(f"Using {X_train.shape[1]} features for training.")

        # Step 2: Optuna optimization (if enabled)
        if self.optimize and OPTUNA_AVAILABLE:
            log.info("Running Optuna optimization...")
            self.best_params = self._optimize_hyperparameters(X_train, y_train, X_val, y_val)
        else:
            # Default parameters
            self.best_params = {
                'lookback': 44,
                'lstm_units': 256,
                'attn_heads': 2,
                'dropout': 0.3,
                'lr': 0.0001,
                'focal_gamma': 1.5,
                'temp': 1.7,
                'batch_size': 32
            }

        # Step 3: Build ensemble predictor
        log.info("Building ensemble predictor...")
        self.model = EnsemblePredictor(
            params=self.best_params,
            n_features=X_train.shape[1],
            lookback=self.best_params['lookback']
        )

        # Step 4: Train model
        log.info("Training model...")
        self.model.train(X_train, y_train, X_val, y_val)

        # Step 5: Evaluate
        log.info("Evaluating ensemble...")
        metrics = self._evaluate(X_val, y_val)

        log.info(f"Validation Accuracy: {metrics['accuracy']:.4f}")
        log.info(f"Validation F1 Score: {metrics['f1_score']:.4f}")
        log.info(f"\nClassification Report:\n{metrics['classification_report']}")

        # Step 6: Save model and params
        self._save_artifacts(metrics)

        log.info("=" * 80)
        log.info("TRAINING PIPELINE COMPLETE")
        log.info("=" * 80)

        return self.model, metrics

    def _prepare_data(self) -> Tuple:
        """Prepare training, validation, and test sets."""
        # Extract features and target
        feature_cols = [col for col in self.data.columns if col not in ['date', 'symbol', 'target']]

        # Create target variable (3-class)
        # This should be computed from price movements: DOWN (0), FLAT (1), UP (2)
        if 'target' not in self.data.columns:
            # Compute target from future returns
            self.data['future_return'] = self.data.groupby('symbol')['close'].pct_change(1).shift(-1)

            # Classify into 3 categories
            self.data['target'] = 1  # FLAT (default)
            self.data.loc[self.data['future_return'] < -0.005, 'target'] = 0  # DOWN (-0.5%)
            self.data.loc[self.data['future_return'] > 0.005, 'target'] = 2   # UP (+0.5%)

        # Remove rows with NaN target
        self.data = self.data.dropna(subset=['target'])

        X = self.data[feature_cols].values
        y = self.data['target'].values

        # Train/val/test split (60/20/20)
        X_train, X_temp, y_train, y_temp = train_test_split(
            X, y, test_size=0.4, random_state=42, stratify=y
        )
        X_val, X_test, y_val, y_test = train_test_split(
            X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp
        )

        # Handle NaN and Inf
        X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
        X_val = np.nan_to_num(X_val, nan=0.0, posinf=0.0, neginf=0.0)
        X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

        return X_train, X_val, X_test, y_train, y_val, y_test

    def _optimize_hyperparameters(self, X_train, y_train, X_val, y_val) -> Dict:
        """Run Optuna hyperparameter optimization."""

        def objective(trial):
            """Optuna objective function."""
            params = {
                'lookback': trial.suggest_int('lookback', 16, 60),
                'lstm_units': trial.suggest_categorical('lstm_units', [64, 128, 256]),
                'attn_heads': trial.suggest_categorical('attn_heads', [2, 4, 8]),
                'dropout': trial.suggest_float('dropout', 0.15, 0.4),
                'lr': trial.suggest_float('lr', 1e-4, 0.01, log=True),
                'focal_gamma': trial.suggest_float('focal_gamma', 1.0, 3.0),
                'temp': trial.suggest_float('temp', 0.9, 3.0),
                'batch_size': trial.suggest_categorical('batch_size', [32, 64, 128])
            }

            try:
                # Quick evaluation with subset of data
                subset_size = min(len(X_train), 500)
                X_sub = X_train[:subset_size]
                y_sub = y_train[:subset_size]

                # Create simple model (just LGBM for speed)
                ensemble = EnsemblePredictor(params, n_features=X_train.shape[1])

                # Quick training
                import lightgbm as lgb
                train_data = lgb.Dataset(X_sub, label=y_sub)

                lgb_params = {
                    'objective': 'multiclass',
                    'num_class': 3,
                    'metric': 'multi_logloss',
                    'learning_rate': params['lr'],
                    'num_leaves': 31,
                    'verbose': -1
                }

                model = lgb.train(
                    lgb_params,
                    train_data,
                    num_boost_round=50,
                    valid_sets=[train_data],
                    callbacks=[lgb.early_stopping(stopping_rounds=10), lgb.log_evaluation(0)]
                )

                # Evaluate on validation set
                val_preds = model.predict(X_val, num_iteration=model.best_iteration)
                val_pred_labels = np.argmax(val_preds, axis=1)

                # Compute F1 score (macro)
                from sklearn.metrics import f1_score
                score = f1_score(y_val, val_pred_labels, average='macro')

                # Pruning for non-promising trials
                trial.report(score, step=1)
                if trial.should_prune():
                    raise optuna.TrialPruned()

                return score

            except optuna.TrialPruned:
                raise
            except Exception as e:
                log.warning(f"Trial failed: {e}")
                return 0.0

        # Create study
        study = optuna.create_study(
            direction='maximize',
            pruner=MedianPruner(n_startup_trials=5, n_warmup_steps=5)
        )

        # Run optimization
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)

        best_params = study.best_params
        log.info(f"Best parameters: {best_params}")
        log.info(f"Best F1 score: {study.best_value:.4f}")

        return best_params

    def _evaluate(self, X_val, y_val) -> Dict:
        """Evaluate the model."""
        # Predict
        y_pred = self.model.predict(X_val)
        y_proba = self.model.predict_proba(X_val)

        # Compute metrics
        accuracy = accuracy_score(y_val, y_pred)
        f1 = f1_score(y_val, y_pred, average='macro')
        report = classification_report(
            y_val,
            y_pred,
            target_names=['DOWN', 'FLAT', 'UP'],
            digits=2
        )

        metrics = {
            'accuracy': accuracy,
            'f1_score': f1,
            'classification_report': report
        }

        return metrics

    def _save_artifacts(self, metrics: Dict):
        """Save model and parameters."""
        output_dir = Path("./btst/models")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save model
        model_path = output_dir / f"ensemble_model_{timestamp}.pkl"
        self.model.save(str(model_path))
        log.info(f"Model saved: {model_path}")

        # Save parameters
        params_path = output_dir / f"best_params_{timestamp}.json"
        with open(params_path, 'w') as f:
            json.dump(self.best_params, f, indent=2)
        log.info(f"Best params saved: {params_path}")

        # Save metrics
        metrics_path = output_dir / f"training_status_{timestamp}.json"
        metrics_dict = {
            'accuracy': float(metrics['accuracy']),
            'f1_score': float(metrics['f1_score']),
            'timestamp': timestamp,
            'best_params': self.best_params
        }
        with open(metrics_path, 'w') as f:
            json.dump(metrics_dict, f, indent=2)
        log.info("Dashboard status updated ✓")


if __name__ == "__main__":
    # Test the training pipeline
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s — %(message)s')

    # Create synthetic data
    n_samples = 1000
    n_features = 100

    dates = pd.date_range('2024-01-01', periods=n_samples, freq='H')
    data = pd.DataFrame({
        'date': dates,
        'symbol': ['NIFTY'] * n_samples,
        'close': 20000 + np.cumsum(np.random.randn(n_samples) * 10)
    })

    # Add random features
    for i in range(n_features):
        data[f'feature_{i}'] = np.random.randn(n_samples)

    # Run pipeline
    pipeline = TrainingPipeline(data, optimize=False)
    model, metrics = pipeline.run()

    print(f"\nTraining complete!")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"F1 Score: {metrics['f1_score']:.4f}")
