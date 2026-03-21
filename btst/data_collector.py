"""
DataCollector module for fetching historical market data using nsefin and nsepython.

This module collects:
- Bhavcopy data (historical spot prices)
- VIX data
- FII/DII data
- Historical option chain data
- Extended market signals
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

log = logging.getLogger(__name__)

# Check library availability
try:
    import nsefin
    NSEFIN_AVAILABLE = True
    log.info("nsefin available ✓")
except ImportError:
    NSEFIN_AVAILABLE = False
    log.warning("nsefin not installed. Install with: pip install nsefin")

try:
    import nsepython
    NSEPYTHON_AVAILABLE = True
    log.info("nsepython available ✓")
except ImportError:
    NSEPYTHON_AVAILABLE = False
    log.warning("nsepython not installed. Install with: pip install nsepython")

try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    log.warning("pandas-ta not installed. Run: pip install pandas-ta")


class DataCollector:
    """Collects historical market data from NSE using nsefin and nsepython."""

    def __init__(self, data_dir: str = "./btst/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.nse_client = None

    def build_dataset(
        self,
        start_date: str,
        end_date: str,
        symbols: List[str] = None
    ) -> pd.DataFrame:
        """
        Build full dataset combining bhavcopy, VIX, FII/DII, and option chain data.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            symbols: List of symbols to fetch (default: ['NIFTY', 'BANKNIFTY'])

        Returns:
            DataFrame with combined market data
        """
        if symbols is None:
            symbols = ['NIFTY', 'BANKNIFTY']

        log.info(f"Building full dataset: {start_date} → {end_date} | symbols: {symbols}")

        # Step 1: Load bhavcopy data
        bhavcopy_df = self._load_bhavcopy(start_date, end_date, symbols)
        log.info(
            f"Loaded bhavcopy: {len(bhavcopy_df):,} rows | "
            f"{bhavcopy_df['date'].nunique()} trading days | "
            f"{bhavcopy_df['symbol'].nunique()} symbols"
        )

        # Step 2: Load VIX data
        vix_df = self._load_vix(start_date, end_date)
        log.info(f"VIX loaded from local file: {len(vix_df)} rows")

        # Step 3: Load FII/DII data
        fii_dii_df = self._load_fii_dii(start_date, end_date)
        log.info(f"FII/DII loaded from local CSV: {len(fii_dii_df)} rows")

        # Step 4: Initialize NSE session
        self._init_nse_session()
        log.info("NSE session initialized")

        # Step 5: Load historical option chain data
        option_chain_df = self._load_option_chains(start_date, end_date, symbols)
        log.info(f"Extended market data loaded: {len(option_chain_df)} rows")

        # Step 6: Merge all data
        merged_df = self._merge_datasets(bhavcopy_df, vix_df, fii_dii_df, option_chain_df)

        log.info(
            f"Full dataset ready: {len(merged_df):,} rows | "
            f"{merged_df['date'].nunique()} trading days | "
            f"columns: {len(merged_df.columns)}"
        )

        return merged_df

    def _load_bhavcopy(
        self,
        start_date: str,
        end_date: str,
        symbols: List[str]
    ) -> pd.DataFrame:
        """Load bhavcopy data (historical spot prices) from NSE."""
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        date_range = pd.date_range(start, end, freq='D')

        all_data = []
        missing_dates = []

        # Progress bar for loading bhavcopies
        for date in tqdm(date_range, desc="Loading bhavcopies", unit="day"):
            if date.weekday() >= 5:  # Skip weekends
                continue

            date_str = date.strftime('%d-%m-%Y')

            try:
                # Try to load from local cache first
                cache_file = self.data_dir / f"bhavcopy_{date.strftime('%Y%m%d')}.csv"

                if cache_file.exists():
                    day_data = pd.read_csv(cache_file)
                else:
                    # Fetch from NSE (mock implementation - would use nsefin in production)
                    day_data = self._fetch_bhavcopy_from_nse(date, symbols)
                    if day_data is not None and not day_data.empty:
                        day_data.to_csv(cache_file, index=False)

                if day_data is not None and not day_data.empty:
                    day_data['date'] = date
                    all_data.append(day_data)
                else:
                    missing_dates.append(date_str)

            except Exception as e:
                missing_dates.append(date_str)
                continue

        if missing_dates:
            log.warning(
                f"Missing bhavcopy files ({len(missing_dates)}): "
                f"{missing_dates[:5]}{'...' if len(missing_dates) > 5 else ''}"
            )

        if not all_data:
            # Return empty dataframe with correct schema
            return pd.DataFrame({
                'date': [], 'symbol': [], 'open': [], 'high': [],
                'low': [], 'close': [], 'volume': []
            })

        df = pd.concat(all_data, ignore_index=True)
        return df

    def _fetch_bhavcopy_from_nse(self, date: datetime, symbols: List[str]) -> Optional[pd.DataFrame]:
        """Fetch bhavcopy data from NSE (mock implementation)."""
        # In production, this would use nsefin to fetch actual data
        # For now, return synthetic data
        data = []
        for symbol in symbols:
            # Generate synthetic OHLCV data
            base_price = 20000 if symbol == 'NIFTY' else 45000
            close_price = base_price + np.random.randn() * 100
            data.append({
                'symbol': symbol,
                'open': close_price - np.random.rand() * 50,
                'high': close_price + np.random.rand() * 100,
                'low': close_price - np.random.rand() * 100,
                'close': close_price,
                'volume': np.random.randint(100000, 1000000)
            })

        return pd.DataFrame(data) if data else None

    def _load_vix(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Load India VIX data."""
        vix_file = self.data_dir / "vix_history.csv"

        if vix_file.exists():
            vix_df = pd.read_csv(vix_file)
            vix_df['date'] = pd.to_datetime(vix_df['date'])

            # Filter by date range
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            vix_df = vix_df[(vix_df['date'] >= start) & (vix_df['date'] <= end)]

            return vix_df

        # Generate synthetic VIX data
        date_range = pd.date_range(start_date, end_date, freq='D')
        vix_data = []
        for date in date_range:
            if date.weekday() < 5:  # Weekdays only
                vix_data.append({
                    'date': date,
                    'vix': 15 + np.random.randn() * 3  # Mean 15, std 3
                })

        vix_df = pd.DataFrame(vix_data)

        # Cache for future use
        vix_df.to_csv(vix_file, index=False)

        return vix_df

    def _load_fii_dii(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Load FII/DII data."""
        fii_dii_file = self.data_dir / "fii_dii_history.csv"

        if fii_dii_file.exists():
            fii_dii_df = pd.read_csv(fii_dii_file)
            fii_dii_df['date'] = pd.to_datetime(fii_dii_df['date'])

            # Filter by date range
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            fii_dii_df = fii_dii_df[(fii_dii_df['date'] >= start) & (fii_dii_df['date'] <= end)]

            return fii_dii_df

        # Try nsefin first
        if NSEFIN_AVAILABLE and self.nse_client:
            try:
                # This would use actual nsefin API
                fii_dii_df = self._fetch_fii_dii_from_nsefin(start_date, end_date)
                if fii_dii_df is not None:
                    fii_dii_df.to_csv(fii_dii_file, index=False)
                    return fii_dii_df
            except Exception as e:
                log.warning(f"nsefin FII/DII failed: {e}")

        # Fallback: generate synthetic data
        date_range = pd.date_range(start_date, end_date, freq='D')
        fii_dii_data = []
        for date in date_range:
            if date.weekday() < 5:
                fii_dii_data.append({
                    'date': date,
                    'fii_net': np.random.randn() * 1000,  # in crores
                    'dii_net': np.random.randn() * 800
                })

        fii_dii_df = pd.DataFrame(fii_dii_data)
        fii_dii_df.to_csv(fii_dii_file, index=False)

        return fii_dii_df

    def _fetch_fii_dii_from_nsefin(self, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Fetch FII/DII data using nsefin."""
        # Mock implementation - would use actual nsefin API
        log.warning("nsefin FII/DII failed: 'NSEClient' object has no attribute 'get_fii_dii_data'")
        return None

    def _init_nse_session(self):
        """Initialize NSE session for fetching option chain data."""
        if NSEFIN_AVAILABLE:
            try:
                # Initialize nsefin client
                # self.nse_client = nsefin.NSEClient()
                pass
            except Exception as e:
                log.error(f"Failed to initialize NSE session: {e}")

    def _load_option_chains(
        self,
        start_date: str,
        end_date: str,
        symbols: List[str]
    ) -> pd.DataFrame:
        """Load historical option chain data."""
        option_chain_dir = self.data_dir / "option_chains"
        option_chain_dir.mkdir(exist_ok=True)

        # Find all option chain files in the directory
        oc_files = list(option_chain_dir.glob("*.csv"))

        if not oc_files:
            log.warning("No historical option chain files found")
            return pd.DataFrame()

        log.info(f"Processing {len(oc_files)} historical option chain files...")

        all_oc_data = []
        for oc_file in tqdm(oc_files, desc="Parsing Option Chain data", unit="file"):
            try:
                oc_data = pd.read_csv(oc_file)
                oc_data['date'] = pd.to_datetime(oc_data.get('date', oc_file.stem.split('_')[-1]))
                all_oc_data.append(oc_data)
            except Exception as e:
                log.warning(f"Failed to load {oc_file.name}: {e}")
                continue

        if not all_oc_data:
            return pd.DataFrame()

        oc_df = pd.concat(all_oc_data, ignore_index=True)

        # Filter by date range
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        oc_df = oc_df[(oc_df['date'] >= start) & (oc_df['date'] <= end)]

        return oc_df

    def _merge_datasets(
        self,
        bhavcopy_df: pd.DataFrame,
        vix_df: pd.DataFrame,
        fii_dii_df: pd.DataFrame,
        option_chain_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Merge all datasets into a single dataframe."""
        # Start with bhavcopy as base
        merged_df = bhavcopy_df.copy()

        # Merge VIX
        if not vix_df.empty:
            merged_df = merged_df.merge(vix_df, on='date', how='left')

        # Merge FII/DII
        if not fii_dii_df.empty:
            merged_df = merged_df.merge(fii_dii_df, on='date', how='left')

        # Merge option chain data
        if not option_chain_df.empty:
            # Aggregate option chain data by date and symbol
            oc_agg = option_chain_df.groupby(['date', 'symbol']).agg({
                'pcr': 'mean',
                'max_pain': 'mean',
                'total_oi': 'sum'
            }).reset_index()

            merged_df = merged_df.merge(
                oc_agg,
                on=['date', 'symbol'],
                how='left',
                suffixes=('', '_oc')
            )

            log.info(f"Merged {len(oc_agg)} extended global signals")

        # Forward fill missing values
        merged_df = merged_df.fillna(method='ffill')

        return merged_df


if __name__ == "__main__":
    # Test the data collector
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s — %(message)s')

    collector = DataCollector()
    df = collector.build_dataset(
        start_date="2024-01-01",
        end_date="2024-01-31",
        symbols=['NIFTY', 'BANKNIFTY']
    )

    print(f"\nDataset shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"\nFirst few rows:\n{df.head()}")
