# BTST ML Training Infrastructure

Advanced machine learning training infrastructure for Buy Today, Sell Tomorrow (BTST) trading strategies.

## Overview

This package provides a complete ML pipeline for training ensemble models on NSE options data:

- **DataCollector**: Fetches historical data using nsefin and nsepython
- **FeatureEngineering**: Computes 400+ technical and market features
- **ModelArchitecture**: Ensemble predictor with TFT, LGBM, XGB, LR + meta-learner
- **TrainingPipeline**: Optuna hyperparameter optimization with curriculum learning

## Key Features

### 1. Data Collection
- Bhavcopy data (historical spot prices)
- India VIX data
- FII/DII flows
- Historical option chain data
- Automatic caching for faster re-runs

### 2. Feature Engineering
- **Price features**: Returns, gaps, ranges
- **Technical indicators**: RSI, MACD, Bollinger Bands, Stoch, ADX, CCI
- **Volume features**: OBV, VWAP, volume ratios
- **Volatility**: Historical, Parkinson, ATR-based
- **Momentum**: ROC, MA crossovers
- **Option-specific**: PCR, max pain distance, OI changes
- **Time features**: Day of week, month, quarter, expiry proximity
- **Statistical**: Skewness, kurtosis, quantiles
- **Rolling aggregations**: 5, 10, 20, 50-period windows

### 3. Model Architecture

**Ensemble Components**:
1. **Temporal Fusion Transformer (TFT)** - Deep learning for time-series
2. **LightGBM** - Gradient boosting for feature interactions
3. **XGBoost** - Alternative gradient boosting
4. **Logistic Regression** - Linear baseline

**Meta-Learning**: Logistic regression stacking of base model predictions

**Calibration**: Temperature scaling for probability calibration

**Target**: 3-class classification (DOWN, FLAT, UP)

### 4. Training Pipeline

- **Data splitting**: 60% train, 20% validation, 20% test
- **Hyperparameter optimization**: Optuna with 100 trials
- **Curriculum learning**: Phase 1 (easy examples), Phase 2 (all examples)
- **Cross-validation**: 5-fold stratified CV for out-of-fold predictions
- **Early stopping**: Prevents overfitting
- **Metrics**: Accuracy, F1 score, classification report

## Installation

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Or install specific ML libraries
pip install nsefin nsepython optuna xgboost pytorch-forecasting pandas-ta tqdm
```

## Usage

### Basic Training

```bash
cd btst
python3 main.py --mode train --start 2024-01-01 --end 2026-03-31
```

### Training with Optimization

```bash
python3 main.py --mode train --optimize --start 2024-01-01 --end 2026-03-31 --n_trials 100
```

### Custom Symbols

```bash
python3 main.py --mode train --start 2024-01-01 --end 2024-12-31 --symbols NIFTY,BANKNIFTY,FINNIFTY
```

## Command-Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--mode` | str | train | Mode: train, predict, evaluate |
| `--optimize` | flag | False | Enable Optuna optimization |
| `--start` | str | required | Start date (YYYY-MM-DD) |
| `--end` | str | required | End date (YYYY-MM-DD) |
| `--symbols` | str | NIFTY,BANKNIFTY | Comma-separated symbols |
| `--n_trials` | int | 100 | Number of Optuna trials |
| `--data_dir` | str | ./btst/data | Data storage directory |

## Output

### Model Files
- `btst/models/ensemble_model_YYYYMMDD_HHMMSS.pkl` - Trained ensemble model
- `btst/models/best_params_YYYYMMDD_HHMMSS.json` - Best hyperparameters
- `btst/models/training_status_YYYYMMDD_HHMMSS.json` - Training metrics

### Logs
Training progress is logged with timestamps showing:
- Data collection progress
- Feature engineering progress
- Optuna optimization trials
- Cross-validation fold progress
- Final metrics

## Architecture Details

### TFT (Temporal Fusion Transformer)

**Current Status**: TFT training is currently disabled because the data is in tabular format (not time-series structured).

TFT requires:
- `time_idx`: Sequential integer index for each observation
- `group_ids`: Identifiers for different time series (e.g., symbol names)
- Proper separation of static vs time-varying features
- Data reshaped into sequences (e.g., daily observations grouped by symbol)

**Fallback**: The ensemble works effectively with LGBM, XGB, and LR models when TFT is not available.

**Future Enhancement**: To enable TFT, the DataCollector would need to be modified to structure data as time-series (e.g., rolling windows of daily observations per symbol).

### Hyperparameter Search Space

```python
{
    'lookback': [16, 60],           # Sequence length
    'lstm_units': [64, 128, 256],   # LSTM hidden units
    'attn_heads': [2, 4, 8],        # Attention heads
    'dropout': [0.15, 0.4],         # Dropout rate
    'lr': [1e-4, 0.01],             # Learning rate (log scale)
    'focal_gamma': [1.0, 3.0],      # Focal loss gamma
    'temp': [0.9, 3.0],             # Temperature scaling
    'batch_size': [32, 64, 128]     # Batch size
}
```

## Known Issues and Limitations

1. **TFT Training**: Currently disabled because data is in tabular format (not time-series structured). The ensemble works effectively with LGBM+XGB+LR models. See "TFT (Temporal Fusion Transformer)" section above for details.

2. **nsefin/nsepython**: These libraries may not be available on PyPI. The DataCollector includes fallback to synthetic data for testing.

3. **Memory Usage**: Feature engineering with 400+ features can be memory-intensive for large datasets.

4. **Training Time**: Full optimization with 100 trials can take 30-60 minutes depending on hardware.

## Performance Expectations

From the reference logs:
- **Validation Accuracy**: ~55-60% (3-class is harder than binary)
- **F1 Score**: ~28-35% (macro average)
- **Class Imbalance**: FLAT class dominates (recall=0.99), UP/DOWN underrepresented

## Improvements

To improve model performance:

1. **Class Balancing**: Use SMOTE or class weights
2. **Feature Selection**: Remove highly correlated features
3. **Target Engineering**: Adjust threshold for UP/DOWN classification
4. **More Data**: Collect more historical data, especially for UP/DOWN moves
5. **Ensemble Tuning**: Optimize ensemble weights
6. **TFT Integration**: Fix TFT data format to enable temporal modeling

## Directory Structure

```
btst/
├── __init__.py              # Package initialization
├── main.py                  # CLI entry point
├── data_collector.py        # Data fetching module
├── feature_engineering.py   # Feature computation
├── model_architecture.py    # Ensemble predictor
├── training_pipeline.py     # Training orchestration
├── data/                    # Data storage
│   ├── bhavcopy_*.csv
│   ├── vix_history.csv
│   ├── fii_dii_history.csv
│   └── option_chains/
└── models/                  # Trained models
    ├── ensemble_model_*.pkl
    ├── best_params_*.json
    └── training_status_*.json
```

## License

MIT License - See main repository LICENSE file

## Contributing

This package is part of the fo-scanner repository. Please follow the main repository's contributing guidelines.

## Support

For issues and questions, please open a GitHub issue in the main fo-scanner repository.
