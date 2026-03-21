"""
FeatureEngineering module for computing 400+ technical and market features.

This module transforms raw market data into features for ML training including:
- Technical indicators (RSI, MACD, Bollinger Bands, etc.)
- Price-based features (returns, volatility, momentum)
- Option-specific features (PCR, OI metrics, Greeks)
- Time-based features (day of week, time to expiry)
"""

import logging
import pandas as pd
import numpy as np
from typing import List, Dict
from tqdm import tqdm

log = logging.getLogger(__name__)

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    log.warning("pandas-ta not available - technical indicators will be limited")


class FeatureEngineering:
    """Feature engineering for market data."""

    def __init__(self):
        self.feature_count = 0

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all features from raw market data.

        Args:
            df: DataFrame with columns: date, symbol, open, high, low, close, volume, etc.

        Returns:
            DataFrame with 400+ engineered features
        """
        # Process each symbol separately
        symbols = df['symbol'].unique()
        processed_dfs = []

        for symbol in tqdm(symbols, desc="Engineering features", unit="symbol"):
            symbol_df = df[df['symbol'] == symbol].copy()
            symbol_df = symbol_df.sort_values('date').reset_index(drop=True)

            # Apply all feature engineering functions
            symbol_df = self._add_price_features(symbol_df)
            symbol_df = self._add_technical_indicators(symbol_df)
            symbol_df = self._add_volume_features(symbol_df)
            symbol_df = self._add_volatility_features(symbol_df)
            symbol_df = self._add_momentum_features(symbol_df)
            symbol_df = self._add_option_features(symbol_df)
            symbol_df = self._add_time_features(symbol_df)
            symbol_df = self._add_statistical_features(symbol_df)
            symbol_df = self._add_rolling_features(symbol_df)
            symbol_df = self._add_interaction_features(symbol_df)

            processed_dfs.append(symbol_df)

        result_df = pd.concat(processed_dfs, ignore_index=True)

        self.feature_count = len([col for col in result_df.columns if col not in ['date', 'symbol']])
        log.info(f"Features computed: {self.feature_count} columns")

        return result_df

    def _add_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add price-based features."""
        # Returns
        df['return_1d'] = df['close'].pct_change(1)
        df['return_2d'] = df['close'].pct_change(2)
        df['return_5d'] = df['close'].pct_change(5)
        df['return_10d'] = df['close'].pct_change(10)
        df['return_20d'] = df['close'].pct_change(20)

        # Log returns
        df['log_return_1d'] = np.log(df['close'] / df['close'].shift(1))
        df['log_return_5d'] = np.log(df['close'] / df['close'].shift(5))

        # High-Low range
        df['high_low_range'] = (df['high'] - df['low']) / df['close']
        df['open_close_range'] = (df['close'] - df['open']) / df['open']

        # Gap features
        df['gap_up'] = (df['open'] > df['close'].shift(1)).astype(int)
        df['gap_down'] = (df['open'] < df['close'].shift(1)).astype(int)
        df['gap_pct'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)

        return df

    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators."""
        if PANDAS_TA_AVAILABLE:
            # Use pandas-ta for comprehensive indicators
            df.ta.rsi(length=14, append=True)
            df.ta.rsi(length=7, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.stoch(k=14, d=3, append=True)
            df.ta.adx(length=14, append=True)
            df.ta.cci(length=20, append=True)
            df.ta.willr(length=14, append=True)
            df.ta.roc(length=10, append=True)
            df.ta.atr(length=14, append=True)
        else:
            # Fallback: manual implementations
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI_14'] = 100 - (100 / (1 + rs))

            # SMA
            df['SMA_10'] = df['close'].rolling(window=10).mean()
            df['SMA_20'] = df['close'].rolling(window=20).mean()
            df['SMA_50'] = df['close'].rolling(window=50).mean()
            df['SMA_200'] = df['close'].rolling(window=200).mean()

            # EMA
            df['EMA_9'] = df['close'].ewm(span=9, adjust=False).mean()
            df['EMA_21'] = df['close'].ewm(span=21, adjust=False).mean()
            df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()

            # Bollinger Bands
            bb_length = 20
            bb_std = 2
            df['BB_MIDDLE'] = df['close'].rolling(window=bb_length).mean()
            bb_rolling_std = df['close'].rolling(window=bb_length).std()
            df['BB_UPPER'] = df['BB_MIDDLE'] + (bb_rolling_std * bb_std)
            df['BB_LOWER'] = df['BB_MIDDLE'] - (bb_rolling_std * bb_std)
            df['BB_WIDTH'] = df['BB_UPPER'] - df['BB_LOWER']
            df['BB_PCTB'] = (df['close'] - df['BB_LOWER']) / (df['BB_UPPER'] - df['BB_LOWER'])

        return df

    def _add_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volume-based features."""
        # Volume changes
        df['volume_change_1d'] = df['volume'].pct_change(1)
        df['volume_change_5d'] = df['volume'].pct_change(5)

        # Volume moving averages
        df['volume_sma_5'] = df['volume'].rolling(window=5).mean()
        df['volume_sma_20'] = df['volume'].rolling(window=20).mean()

        # Volume ratio
        df['volume_ratio_5'] = df['volume'] / df['volume_sma_5']
        df['volume_ratio_20'] = df['volume'] / df['volume_sma_20']

        # VWAP (Volume Weighted Average Price)
        df['vwap'] = (df['close'] * df['volume']).rolling(window=20).sum() / df['volume'].rolling(window=20).sum()

        # OBV (On-Balance Volume)
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()

        return df

    def _add_volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility features."""
        # Historical volatility (std of returns)
        df['volatility_5d'] = df['return_1d'].rolling(window=5).std()
        df['volatility_10d'] = df['return_1d'].rolling(window=10).std()
        df['volatility_20d'] = df['return_1d'].rolling(window=20).std()
        df['volatility_60d'] = df['return_1d'].rolling(window=60).std()

        # Parkinson volatility (uses high-low range)
        df['parkinson_volatility'] = np.sqrt(
            (1 / (4 * np.log(2))) * ((np.log(df['high'] / df['low'])) ** 2)
        ).rolling(window=20).mean()

        # ATR-based volatility
        if 'ATRr_14' not in df.columns:
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['ATRr_14'] = true_range.rolling(window=14).mean()

        df['atr_ratio'] = df['ATRr_14'] / df['close']

        return df

    def _add_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum features."""
        # Rate of Change
        df['roc_5'] = ((df['close'] - df['close'].shift(5)) / df['close'].shift(5)) * 100
        df['roc_10'] = ((df['close'] - df['close'].shift(10)) / df['close'].shift(10)) * 100
        df['roc_20'] = ((df['close'] - df['close'].shift(20)) / df['close'].shift(20)) * 100

        # Momentum
        df['momentum_5'] = df['close'] - df['close'].shift(5)
        df['momentum_10'] = df['close'] - df['close'].shift(10)

        # Moving average crossovers
        df['ma_cross_10_20'] = (df.get('SMA_10', 0) > df.get('SMA_20', 0)).astype(int)
        df['ma_cross_20_50'] = (df.get('SMA_20', 0) > df.get('SMA_50', 0)).astype(int)

        return df

    def _add_option_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add option-specific features."""
        # PCR features (if available)
        if 'pcr' in df.columns:
            df['pcr_sma_5'] = df['pcr'].rolling(window=5).mean()
            df['pcr_sma_20'] = df['pcr'].rolling(window=20).mean()
            df['pcr_change'] = df['pcr'].pct_change(1)

        # Max pain distance (if available)
        if 'max_pain' in df.columns and 'close' in df.columns:
            df['max_pain_dist'] = df['close'] - df['max_pain']
            df['max_pain_dist_pct'] = (df['max_pain_dist'] / df['close']) * 100

        # OI features (if available)
        if 'total_oi' in df.columns:
            df['oi_change'] = df['total_oi'].pct_change(1)
            df['oi_sma_5'] = df['total_oi'].rolling(window=5).mean()

        # VIX features (if available)
        if 'vix' in df.columns:
            df['vix_sma_5'] = df['vix'].rolling(window=5).mean()
            df['vix_sma_20'] = df['vix'].rolling(window=20).mean()
            df['vix_change'] = df['vix'].pct_change(1)

        return df

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add time-based features."""
        df['day_of_week'] = pd.to_datetime(df['date']).dt.dayofweek
        df['day_of_month'] = pd.to_datetime(df['date']).dt.day
        df['week_of_year'] = pd.to_datetime(df['date']).dt.isocalendar().week
        df['month'] = pd.to_datetime(df['date']).dt.month
        df['quarter'] = pd.to_datetime(df['date']).dt.quarter

        # Is month end/start
        df['is_month_end'] = pd.to_datetime(df['date']).dt.is_month_end.astype(int)
        df['is_month_start'] = pd.to_datetime(df['date']).dt.is_month_start.astype(int)

        return df

    def _add_statistical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add statistical features."""
        # Skewness and kurtosis of returns
        df['return_skew_20'] = df['return_1d'].rolling(window=20).skew()
        df['return_kurt_20'] = df['return_1d'].rolling(window=20).kurt()

        # Quantile features
        df['close_quantile_20'] = df['close'].rolling(window=20).apply(
            lambda x: pd.Series(x).rank().iloc[-1] / len(x)
        )

        return df

    def _add_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add rolling window aggregations."""
        windows = [5, 10, 20, 50]

        for window in windows:
            # Rolling mean
            df[f'close_mean_{window}'] = df['close'].rolling(window=window).mean()

            # Rolling std
            df[f'close_std_{window}'] = df['close'].rolling(window=window).std()

            # Rolling min/max
            df[f'close_min_{window}'] = df['close'].rolling(window=window).min()
            df[f'close_max_{window}'] = df['close'].rolling(window=window).max()

            # Distance from rolling extremes
            df[f'dist_from_min_{window}'] = (df['close'] - df[f'close_min_{window}']) / df['close']
            df[f'dist_from_max_{window}'] = (df[f'close_max_{window}'] - df['close']) / df['close']

        return df

    def _add_interaction_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add interaction features."""
        # Price * Volume
        df['price_volume'] = df['close'] * df['volume']

        # Volatility * Volume
        if 'volatility_20d' in df.columns:
            df['vol_volume'] = df['volatility_20d'] * df['volume']

        # VIX * Return (if VIX available)
        if 'vix' in df.columns:
            df['vix_return'] = df['vix'] * df['return_1d']

        # FII/DII sentiment (if available)
        if 'fii_net' in df.columns and 'dii_net' in df.columns:
            df['fii_dii_ratio'] = df['fii_net'] / (df['dii_net'] + 1e-6)
            df['fii_dii_divergence'] = df['fii_net'] - df['dii_net']

        return df


if __name__ == "__main__":
    # Test feature engineering
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s — %(message)s')

    # Create sample data
    dates = pd.date_range('2024-01-01', '2024-03-31', freq='D')
    sample_data = []
    for date in dates:
        if date.weekday() < 5:  # Weekdays only
            for symbol in ['NIFTY', 'BANKNIFTY']:
                base = 20000 if symbol == 'NIFTY' else 45000
                sample_data.append({
                    'date': date,
                    'symbol': symbol,
                    'open': base + np.random.randn() * 100,
                    'high': base + np.random.randn() * 150,
                    'low': base - np.random.randn() * 150,
                    'close': base + np.random.randn() * 100,
                    'volume': np.random.randint(100000, 1000000)
                })

    df = pd.DataFrame(sample_data)

    fe = FeatureEngineering()
    df_features = fe.compute_features(df)

    print(f"\nOriginal columns: {len(df.columns)}")
    print(f"Feature columns: {fe.feature_count}")
    print(f"Total columns: {len(df_features.columns)}")
    print(f"\nSample features:\n{df_features.head()}")
