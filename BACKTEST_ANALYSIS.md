# Backtest Data Processing Analysis & Improvement Recommendations

## Executive Summary

This document provides a comprehensive analysis of the backtest system's data processing pipeline in the NSE F&O Scanner application, along with actionable recommendations for improvement.

---

## 1. Current Data Processing Architecture

### 1.1 Overview

The backtest system consists of three main components:

1. **Historical Data Loader** (`historical_loader.py`) - Downloads and preprocesses historical data
2. **EOD Backtester** (`backtest_runner.py`) - Runs simulations on end-of-day data
3. **Live Backtester** (`backtest.py`) - Tests live signals or replays paper trades

### 1.2 Data Processing Pipeline

```
┌─────────────────────────────────────────────────────────┐
│ STAGE 1: DATA ACQUISITION                               │
├─────────────────────────────────────────────────────────┤
│ • Downloads NSE F&O Bhavcopy files (jugaad_data/NSE API)│
│ • Fetches spot prices from yfinance                     │
│ • Handles API changes (pre/post July 2024)             │
│ • Rate limiting: 1.5s between requests, max 3 retries  │
│ • Batch size: 30 files with 5s pauses                  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 2: DATA MERGE & CLEANING                         │
├─────────────────────────────────────────────────────────┤
│ • Standardizes column names (legacy vs new NSE format) │
│ • Filters: OPTIDX, OPTSTK instruments only             │
│ • Filters: CE/PE options only, OI > 0 or Close > 0     │
│ • Deduplication on [date, symbol, expiry, strike, type]│
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 3: FEATURE RECONSTRUCTION                         │
├─────────────────────────────────────────────────────────┤
│ • Calculates IV using Newton-Raphson (100 iterations)  │
│ • Computes Greeks via Black-Scholes model              │
│ • Aggregates chain metrics (PCR, OI concentration)     │
│ • Calculates Max Pain, GEX, IV Skew                    │
│ • Scores using compute_stock_score_v2()                │
│ • Labels next-day outcomes (WIN/LOSS/NEUTRAL)          │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 4: DATABASE STORAGE                              │
├─────────────────────────────────────────────────────────┤
│ • Inserts into market_snapshots (60+ columns)          │
│ • Populates iv_history for IV Rank calculation         │
│ • SQLite with no indexing optimization                 │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ STAGE 5: BACKTEST SIMULATION                           │
├─────────────────────────────────────────────────────────┤
│ • Queries market_snapshots with filters                │
│ • Simulates trades with TP/SL logic                    │
│ • Position sizing based on risk percentage             │
│ • Tracks capital curve and metrics                     │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Data Processing Details

### 2.1 Historical Data Acquisition (Lines 163-228 in historical_loader.py)

**Current Process:**
- Downloads NSE F&O bhavcopy files sequentially
- Handles two different NSE API formats (pre/post July 8, 2024)
- Uses rate limiting (1.5s delay) and retries (max 3)
- Processes in batches of 30 with 5s pauses

**Performance Characteristics:**
- Time per file: ~1.5-3 seconds
- For 1 year (250 trading days): ~6-12 minutes
- For 2 years: ~12-24 minutes

### 2.2 IV Calculation (Lines 334-350 in historical_loader.py)

**Current Algorithm:**
```python
def compute_implied_volatility(market_price, spot, strike, dte, opt_type,
                               r=0.065, max_iter=100, tol=1e-6):
    # Newton-Raphson method
    iv = 0.3  # Initial guess
    for _ in range(max_iter):
        price = _bs_price(spot, strike, T, r, iv, opt_type)
        vega = _bs_vega(spot, strike, T, r, iv)
        if vega == 0: break

        diff = price - market_price
        if abs(diff) < tol: return max(0.01, min(iv * 100, 500.0))
        iv -= diff / vega
```

**Issues:**
- Calculated for EVERY option in EVERY snapshot
- No caching or vectorization
- Fixed initial guess (could be smarter)
- No early termination for out-of-money options

### 2.3 Feature Reconstruction (Lines 354-517 in historical_loader.py)

**Current Process:**
```python
def reconstruct_features(raw_df: pd.DataFrame, spot_prices: dict):
    # Groups by (trade_date, symbol)
    grouped_days = raw_df.groupby(["trade_date", "symbol"])

    for i, ((tdate, sym), day_df) in enumerate(grouped_days):
        # For EACH snapshot:
        # 1. Filter to nearest expiry
        # 2. Calculate ATM strike
        # 3. Aggregate OI/Volume (CE/PE totals, PCR)
        # 4. Calculate Max Pain (nested loops over strikes)
        # 5. Reconstruct IV for every option
        # 6. Build pseudo-chain for scoring
        # 7. Call compute_stock_score_v2()
        # 8. Label next-day outcome
```

**Computational Complexity:**
- Max Pain: O(n²) where n = number of strikes
- IV calculation: O(n × 100) where n = number of options
- Total per snapshot: O(n²) + O(n × 100)

### 2.4 Database Operations

**Current Schema:**
```sql
market_snapshots (60+ columns)
- No explicit indexes besides primary key
- Queries filter on: data_source, snapshot_time, signal, regime, symbol, score
```

**Query Pattern (Lines 48-65 in backtest_runner.py):**
```python
base_q = """
    SELECT * FROM market_snapshots
    WHERE data_source='EOD_HISTORICAL'
    AND trade_result IS NOT NULL
    AND snapshot_time >= ? AND snapshot_time <= ?
"""
# Additional filters for signal, regime, symbols
df = pd.read_sql(base_q, conn)
```

---

## 3. Performance Bottlenecks

### 3.1 Data Download
| Issue | Impact | Location |
|-------|--------|----------|
| Sequential downloads | High | historical_loader.py:180-228 |
| No concurrent requests | High | historical_loader.py:163-228 |
| Fixed rate limiting (1.5s) | Medium | historical_loader.py:215 |
| No local cache validation | Medium | historical_loader.py:190-192 |

### 3.2 IV Calculation
| Issue | Impact | Location |
|-------|--------|----------|
| Per-option calculation | High | historical_loader.py:334-350 |
| No vectorization | High | Throughout |
| No parallel processing | High | historical_loader.py:354-517 |
| Fixed 100 iterations | Low | historical_loader.py:334 |

### 3.3 Max Pain Calculation
| Issue | Impact | Location |
|-------|--------|----------|
| O(n²) nested loops | High | historical_loader.py:411-419 |
| Recalculated for every snapshot | High | historical_loader.py:411-419 |
| No memoization | Medium | N/A |

### 3.4 Database Performance
| Issue | Impact | Location |
|-------|--------|----------|
| No indexes on filter columns | High | db.py |
| SELECT * queries | Medium | backtest_runner.py:54 |
| No query result caching | Medium | backtest_runner.py:48-65 |

### 3.5 Memory Usage
| Issue | Impact | Location |
|-------|--------|----------|
| Loads entire result set into memory | High | backtest_runner.py:54 |
| No streaming/chunking | High | historical_loader.py:354-517 |
| Duplicate data in pseudo-chain | Medium | historical_loader.py:428-440 |

---

## 4. Improvement Recommendations

### 4.1 CRITICAL - High Impact, High Priority

#### 4.1.1 Parallelize Data Downloads
**Current:** Sequential downloads with 1.5s delays = ~6-12 min for 1 year

**Improved:**
```python
import asyncio
import aiohttp

async def download_bhavcopy_concurrent(dates: list, max_concurrent: int = 5):
    """Download multiple bhavcopy files concurrently"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(date):
        async with semaphore:
            # Download logic here
            pass

    tasks = [fetch_one(d) for d in dates]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

**Expected Improvement:** 5-10x faster (60-120 seconds for 1 year)

#### 4.1.2 Add Database Indexes
**Current:** Full table scans on every query

**Improved:**
```sql
CREATE INDEX idx_snapshots_source_time ON market_snapshots(data_source, snapshot_time);
CREATE INDEX idx_snapshots_symbol_time ON market_snapshots(symbol, snapshot_time);
CREATE INDEX idx_snapshots_score ON market_snapshots(score, confidence);
CREATE INDEX idx_snapshots_signal_regime ON market_snapshots(signal, regime);
CREATE INDEX idx_snapshots_trade_result ON market_snapshots(trade_result);
```

**Expected Improvement:** 10-100x faster queries (especially for date range filters)

#### 4.1.3 Vectorize IV Calculations
**Current:** Loop-based per-option calculation

**Improved:**
```python
import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

def compute_iv_vectorized(market_prices, spots, strikes, dtes, opt_types, r=0.065):
    """Vectorized IV calculation using NumPy"""
    T = np.maximum(dtes, 0.5) / 365.0

    def objective(iv, market_price, spot, strike, T, opt_type):
        return bs_price_vectorized(spot, strike, T, r, iv, opt_type) - market_price

    ivs = np.zeros(len(market_prices))
    for i in range(len(market_prices)):
        try:
            ivs[i] = brentq(objective, 0.01, 5.0,
                           args=(market_prices[i], spots[i], strikes[i], T[i], opt_types[i]))
        except:
            ivs[i] = 0.3

    return ivs * 100
```

**Expected Improvement:** 10-20x faster IV calculations

#### 4.1.4 Optimize Max Pain Calculation
**Current:** O(n²) nested loops

**Improved:**
```python
def calculate_max_pain_optimized(chain_df):
    """Optimized Max Pain calculation using vectorization"""
    strikes = chain_df['strike'].unique()

    # Vectorized approach
    ce_data = chain_df[chain_df['opt_type'] == 'CE'][['strike', 'open_interest']].values
    pe_data = chain_df[chain_df['opt_type'] == 'PE'][['strike', 'open_interest']].values

    losses = []
    for strike in strikes:
        # CE losses: sum((s - strike) * oi) for all s > strike
        ce_loss = np.sum(np.maximum(ce_data[:, 0] - strike, 0) * ce_data[:, 1])

        # PE losses: sum((strike - s) * oi) for all s < strike
        pe_loss = np.sum(np.maximum(strike - pe_data[:, 0], 0) * pe_data[:, 1])

        losses.append(ce_loss + pe_loss)

    return strikes[np.argmin(losses)]
```

**Expected Improvement:** 5-10x faster Max Pain calculations

### 4.2 HIGH PRIORITY - High Impact, Medium Effort

#### 4.2.1 Implement Data Chunking/Streaming
**Problem:** Loading entire result sets exhausts memory

**Solution:**
```python
def reconstruct_features_chunked(raw_df: pd.DataFrame, spot_prices: dict,
                                 chunk_size: int = 1000):
    """Process data in chunks to reduce memory usage"""
    grouped_days = raw_df.groupby(["trade_date", "symbol"])

    for chunk_start in range(0, len(grouped_days), chunk_size):
        chunk = list(grouped_days)[chunk_start:chunk_start + chunk_size]

        # Process chunk
        snapshots = process_chunk(chunk, spot_prices)

        # Yield or save incrementally
        yield snapshots
```

**Benefits:**
- Reduces peak memory usage by 90%+
- Enables processing of much larger datasets
- Better progress tracking

#### 4.2.2 Add Query Result Caching
**Problem:** Repeated queries fetch same data

**Solution:**
```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def get_snapshots_cached(db_path, start_date, end_date, filters_hash):
    """Cache query results for repeated use"""
    conn = sqlite3.connect(db_path)
    # ... query logic
    return df

def run_with_cache(self, start_date, end_date, **kwargs):
    filters_hash = hashlib.md5(
        f"{kwargs.get('signal_filter')}-{kwargs.get('regime_filter')}".encode()
    ).hexdigest()

    df = get_snapshots_cached(self.db_path, start_date, end_date, filters_hash)
    # ... rest of logic
```

**Benefits:**
- Eliminates redundant database queries
- Speeds up parameter optimization by 10-50x

#### 4.2.3 Parallel Feature Reconstruction
**Problem:** Sequential processing of snapshots

**Solution:**
```python
from multiprocessing import Pool
import multiprocessing as mp

def reconstruct_features_parallel(raw_df: pd.DataFrame, spot_prices: dict,
                                   n_workers: int = None):
    """Use multiprocessing for feature reconstruction"""
    if n_workers is None:
        n_workers = mp.cpu_count() - 1

    grouped_days = list(raw_df.groupby(["trade_date", "symbol"]))

    with Pool(n_workers) as pool:
        results = pool.starmap(
            process_single_snapshot,
            [(grp, spot_prices) for _, grp in grouped_days]
        )

    return pd.concat(results, ignore_index=True)
```

**Expected Improvement:** 4-8x faster (on 8-core CPU)

### 4.3 MEDIUM PRIORITY - Incremental Improvements

#### 4.3.1 Smart IV Initial Guess
**Current:** Fixed 0.3 (30%) initial guess

**Improved:**
```python
def smart_iv_initial_guess(spot, strike, opt_type):
    """Better initial guess based on moneyness"""
    moneyness = spot / strike

    if opt_type == "CE":
        if moneyness > 1.05:  # ITM
            return 0.25
        elif moneyness < 0.95:  # OTM
            return 0.40
        else:  # ATM
            return 0.30
    else:  # PE
        if moneyness < 0.95:  # ITM
            return 0.25
        elif moneyness > 1.05:  # OTM
            return 0.40
        else:  # ATM
            return 0.30
```

**Benefits:**
- Faster IV convergence (20-30% fewer iterations)
- More accurate results

#### 4.3.2 Optimize Query Selectivity
**Current:** SELECT * FROM market_snapshots

**Improved:**
```python
def run(self, start_date, end_date, ...):
    # Select only needed columns
    columns = [
        "snapshot_time", "symbol", "score", "confidence", "signal", "regime",
        "top_pick_type", "top_pick_strike", "top_pick_ltp",
        "pick_pnl_pct_next", "dte", "iv_rank"
    ]

    base_q = f"SELECT {','.join(columns)} FROM market_snapshots WHERE ..."
```

**Benefits:**
- Reduces data transfer by 70-80%
- Faster query execution

#### 4.3.3 Add Progress Logging
**Current:** Limited progress visibility (only every 500 snapshots)

**Improved:**
```python
from tqdm import tqdm

def reconstruct_features(raw_df, spot_prices):
    grouped_days = raw_df.groupby(["trade_date", "symbol"])

    with tqdm(total=len(grouped_days), desc="Reconstructing features") as pbar:
        for (tdate, sym), day_df in grouped_days:
            # ... processing
            pbar.update(1)
            pbar.set_postfix({"symbol": sym, "date": tdate})
```

**Benefits:**
- Better user experience
- Easier to estimate completion time

### 4.4 LOW PRIORITY - Nice to Have

#### 4.4.1 Data Validation & Quality Checks
```python
def validate_snapshot(snapshot: dict) -> bool:
    """Validate reconstructed snapshot data"""
    checks = [
        snapshot['spot_price'] > 0,
        0 <= snapshot['pcr_oi'] <= 10,
        0 <= snapshot['atm_ce_iv'] <= 500,
        0 <= snapshot['score'] <= 100,
        0 <= snapshot['confidence'] <= 1,
    ]
    return all(checks)
```

#### 4.4.2 Compression for Historical Data
```python
# Store compressed CSV files
df.to_csv('reconstructed.csv.gz', compression='gzip', index=False)

# Or use Parquet format
df.to_parquet('reconstructed.parquet', compression='snappy')
```

**Benefits:**
- 50-70% reduction in disk space
- Faster I/O operations

#### 4.4.3 Configuration Management
```python
# config.yaml
data_pipeline:
  batch_size: 30
  rate_limit_seconds: 1.5
  max_retries: 3
  parallel_workers: 8
  chunk_size: 1000

backtest:
  default_capital: 100000
  default_risk_pct: 2.0
  max_simultaneous_trades: 3
```

---

## 5. Implementation Roadmap

### Phase 1 (Week 1) - Critical Performance Fixes
- [ ] Add database indexes (4.1.2)
- [ ] Optimize query selectivity (4.3.2)
- [ ] Add progress logging (4.3.3)

**Expected Impact:** 10-50x faster backtests

### Phase 2 (Week 2-3) - Data Pipeline Optimization
- [ ] Parallelize data downloads (4.1.1)
- [ ] Vectorize IV calculations (4.1.3)
- [ ] Optimize Max Pain calculation (4.1.4)

**Expected Impact:** 10-20x faster data loading

### Phase 3 (Week 4-5) - Scalability Improvements
- [ ] Implement data chunking (4.2.1)
- [ ] Add query result caching (4.2.2)
- [ ] Parallel feature reconstruction (4.2.3)

**Expected Impact:** Handle 10x larger datasets

### Phase 4 (Week 6+) - Polish & Enhancements
- [ ] Smart IV initial guess (4.3.1)
- [ ] Data validation (4.4.1)
- [ ] Compression (4.4.2)
- [ ] Configuration management (4.4.3)

---

## 6. Performance Benchmarks (Estimated)

### Current Performance
| Operation | Current Time | Current Memory |
|-----------|-------------|----------------|
| Download 1 year data | 6-12 minutes | 100 MB |
| Reconstruct features | 30-60 minutes | 2-4 GB |
| Load to database | 5-10 minutes | 1 GB |
| Run backtest query | 2-5 seconds | 500 MB |
| **Total Pipeline** | **45-85 minutes** | **4-6 GB peak** |

### After Phase 1 (Critical Fixes)
| Operation | Improved Time | Improved Memory |
|-----------|--------------|----------------|
| Run backtest query | 0.1-0.5 seconds | 100 MB |
| **Total Pipeline** | **40-80 minutes** | **4-6 GB peak** |

### After Phase 2 (Pipeline Optimization)
| Operation | Improved Time | Improved Memory |
|-----------|--------------|----------------|
| Download 1 year data | 1-2 minutes | 100 MB |
| Reconstruct features | 3-5 minutes | 2-4 GB |
| Load to database | 2-3 minutes | 1 GB |
| **Total Pipeline** | **6-10 minutes** | **4-6 GB peak** |

### After Phase 3 (Scalability)
| Operation | Improved Time | Improved Memory |
|-----------|--------------|----------------|
| Download 1 year data | 1-2 minutes | 100 MB |
| Reconstruct features | 2-4 minutes | 500 MB |
| Load to database | 1-2 minutes | 200 MB |
| Run backtest query | 0.1-0.5 seconds | 50 MB |
| **Total Pipeline** | **4-8 minutes** | **1 GB peak** |

---

## 7. Key Insights & Recommendations

### 7.1 Data Quality Considerations

**Current Limitations:**
1. **EOD Data Only**: No intraday entry/exit simulation
2. **IV Reconstruction Accuracy**: Uses settlement prices, degrades near expiry
3. **Next-Day Exit Model**: Assumes all trades exit at next EOD (no multi-day holds)
4. **Fixed Slippage**: 1.5% on entry (not market-adaptive)

**Recommendations:**
- Consider collecting tick-by-tick data for more accurate IV
- Implement intraday simulation if possible
- Add dynamic slippage based on liquidity (volume, bid-ask spread)

### 7.2 Statistical Rigor

**Current State:**
- Z-score calculation for n>=30 trades
- 95% confidence intervals
- Sharpe ratio calculation

**Recommendations:**
- Add walk-forward analysis
- Implement out-of-sample testing
- Add Monte Carlo simulation for robustness testing

### 7.3 Feature Engineering Opportunities

**Currently Not Captured:**
- Order flow imbalance
- Bid-ask spread dynamics
- Time-weighted average OI changes
- Correlation between different expiries
- Volatility term structure

---

## 8. Conclusion

The current backtest system is functionally complete but has significant performance bottlenecks:

1. **Data Download**: Sequential processing limits throughput
2. **IV Calculation**: Per-option loop-based approach is inefficient
3. **Database**: Missing indexes cause slow queries
4. **Memory**: Loading entire datasets limits scalability

By implementing the recommended improvements in phases, the system can achieve:
- **10-20x faster execution** (45 min → 4-8 min for full pipeline)
- **5x lower memory usage** (6 GB → 1 GB peak)
- **Ability to handle 10x more data** (10+ years historical)

The highest ROI improvements are:
1. Database indexes (30 min effort, 10-50x query speedup)
2. Parallel downloads (2-3 hours effort, 5-10x download speedup)
3. Vectorized IV calculation (4-6 hours effort, 10-20x calculation speedup)

These three changes alone would reduce the total pipeline time from 45-85 minutes to approximately 6-10 minutes.
