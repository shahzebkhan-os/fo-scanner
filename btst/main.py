"""
Main training script for the BTST ML model.

Usage:
    python3 main.py --mode train --optimize --start 2024-01-01 --end 2026-03-31

Arguments:
    --mode: Mode of operation ('train', 'predict', 'evaluate')
    --optimize: Enable Optuna hyperparameter optimization
    --start: Start date for data collection (YYYY-MM-DD)
    --end: End date for data collection (YYYY-MM-DD)
    --symbols: Comma-separated list of symbols (default: NIFTY,BANKNIFTY)
    --n_trials: Number of Optuna trials (default: 100)
"""

import logging
import argparse
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

log = logging.getLogger("Main")

# Import modules
try:
    from data_collector import DataCollector
    from feature_engineering import FeatureEngineering
    from training_pipeline import TrainingPipeline
except ImportError:
    # Try relative imports if running as package
    from .data_collector import DataCollector
    from .feature_engineering import FeatureEngineering
    from .training_pipeline import TrainingPipeline


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='BTST ML Training Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--mode',
        type=str,
        choices=['train', 'predict', 'evaluate'],
        default='train',
        help='Mode of operation'
    )

    parser.add_argument(
        '--optimize',
        action='store_true',
        help='Enable Optuna hyperparameter optimization'
    )

    parser.add_argument(
        '--start',
        type=str,
        required=True,
        help='Start date for data collection (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--end',
        type=str,
        required=True,
        help='End date for data collection (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--symbols',
        type=str,
        default='NIFTY,BANKNIFTY',
        help='Comma-separated list of symbols'
    )

    parser.add_argument(
        '--n_trials',
        type=int,
        default=100,
        help='Number of Optuna trials for optimization'
    )

    parser.add_argument(
        '--data_dir',
        type=str,
        default='./btst/data',
        help='Directory for data storage'
    )

    return parser.parse_args()


def train_mode(args):
    """Run training mode."""
    log.info("=" * 80)
    log.info("MODE: TRAIN")
    log.info("=" * 80)

    # Parse symbols
    symbols = [s.strip() for s in args.symbols.split(',')]

    # Step 1: Collect data
    log.info("Step 1: Collecting data...")
    collector = DataCollector(data_dir=args.data_dir)
    data = collector.build_dataset(
        start_date=args.start,
        end_date=args.end,
        symbols=symbols
    )
    log.info(f"Collected {len(data)} rows")

    # Step 2: Engineer features
    log.info("Step 2: Engineering features...")
    fe = FeatureEngineering()
    data_with_features = fe.compute_features(data)
    log.info(f"Features computed: {len(data_with_features.columns)} columns")

    # Step 3: Save processed data (optional)
    output_dir = Path(args.data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / f"processed_data_{datetime.now().strftime('%Y%m%d')}.csv"
    # data_with_features.to_csv(data_path, index=False)
    # log.info(f"Processed data saved: {data_path}")

    # Step 4: Train model
    log.info("Step 4: Training model...")
    pipeline = TrainingPipeline(
        data=data_with_features,
        optimize=args.optimize,
        n_trials=args.n_trials
    )
    model, metrics = pipeline.run()

    log.info("Training complete ✓")

    return model, metrics


def predict_mode(args):
    """Run prediction mode."""
    log.info("=" * 80)
    log.info("MODE: PREDICT")
    log.info("=" * 80)

    log.warning("Prediction mode not yet implemented")

    return None


def evaluate_mode(args):
    """Run evaluation mode."""
    log.info("=" * 80)
    log.info("MODE: EVALUATE")
    log.info("=" * 80)

    log.warning("Evaluation mode not yet implemented")

    return None


def main():
    """Main entry point."""
    args = parse_args()

    try:
        if args.mode == 'train':
            train_mode(args)
        elif args.mode == 'predict':
            predict_mode(args)
        elif args.mode == 'evaluate':
            evaluate_mode(args)
        else:
            log.error(f"Unknown mode: {args.mode}")
            return 1

        return 0

    except KeyboardInterrupt:
        log.info("\nInterrupted by user")
        return 130

    except Exception as e:
        log.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
