# How to Run Backtesting - Simple Step-by-Step Guide

This guide explains how to run backtesting on historical NSE F&O options data using the FO Scanner's backtesting system.

## Table of Contents
- [Quick Start](#quick-start)
- [Prerequisites](#prerequisites)
- [Step-by-Step Guide](#step-by-step-guide)
- [Understanding the Results](#understanding-the-results)
- [Common Use Cases](#common-use-cases)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Quick Start

If you just want to get started quickly:

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Initialize database
python -c "import db; db.init_db()"

# 3. Download sample historical data (last 3 months)
python historical_loader.py download --start 2024-10-01 --end 2024-12-31

# 4. Process and load the data into database
python historical_loader.py process --start 2024-10-01 --end 2024-12-31
python historical_loader.py load-db --start 2024-10-01 --end 2024-12-31

# 5. Run backtest
python backtest_runner.py --start 2024-10-01 --end 2024-12-31
```

That's it! You should now see backtest results with trade statistics.

---

## Prerequisites

Before running backtesting, make sure you have:

1. **Python 3.11+** installed
2. **Python dependencies** installed:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Additional backtesting dependencies** (if not in requirements.txt):
   ```bash
   pip install pandas tabulate tqdm scipy yfinance jugaad-data
   ```

4. **Database initialized**:
   ```bash
   python -c "import db; db.init_db()"
   ```

---

## Step-by-Step Guide

### Step 1: Check Current Data Status

First, check if you already have historical data loaded:

```bash
cd backend
python historical_loader.py status
```

**Expected Output:**
- If data exists: Shows number of records, date ranges, and data quality stats
- If no data: "No historical data to validate."

### Step 2: Download Historical Data

Download NSE F&O Bhavcopy files and spot prices:

```bash
# Download last 3 months (recommended for testing)
python historical_loader.py download --start 2024-10-01 --end 2024-12-31

# Or download full year for comprehensive testing
python historical_loader.py download --start 2024-01-01 --end 2024-12-31

# Or download specific date range
python historical_loader.py download --start 2024-06-01 --end 2024-09-30
```

**What happens:**
- Downloads ZIP files from NSE containing daily option chain data
- Downloads spot prices from Yahoo Finance
- Saves files to `./historical_data/` folder
- Uses rate limiting to avoid overwhelming servers (1.5s between requests)

**Time estimate:**
- 1 month of data: ~2-3 minutes
- 3 months of data: ~5-8 minutes
- 1 year of data: ~15-20 minutes

### Step 3: Process Historical Data

Process the downloaded files to reconstruct option chain features:

```bash
# Process the same date range you downloaded
python historical_loader.py process --start 2024-10-01 --end 2024-12-31
```

**What happens:**
- Reads downloaded ZIP files
- Standardizes NSE format changes
- Calculates Implied Volatility using Newton-Raphson method
- Computes Black-Scholes Greeks (Delta, Gamma, Theta, Vega)
- Calculates chain metrics: PCR, OI concentration, Max Pain, GEX
- Computes IV Skew and scores
- Labels next-day outcomes
- Creates processed CSV file

**Time estimate:**
- 1 month of data: ~1-2 minutes
- 3 months of data: ~3-5 minutes
- 1 year of data: ~10-15 minutes

### Step 4: Load Data into Database

Load the processed data into SQLite database:

```bash
python historical_loader.py load-db --start 2024-10-01 --end 2024-12-31
```

**What happens:**
- Reads processed CSV file
- Inserts data into `market_snapshots` table
- Uses `INSERT OR REPLACE` to avoid duplicates
- Safe to run multiple times on same data

**Time estimate:**
- 1 month of data: ~30 seconds
- 3 months of data: ~1-2 minutes
- 1 year of data: ~3-5 minutes

### Step 5: Run Backtests

Now you can run backtests on the loaded historical data:

#### Basic Backtest (Default Parameters)

```bash
python backtest_runner.py --start 2024-10-01 --end 2024-12-31
```

**Default parameters:**
- Score threshold: 75
- Confidence threshold: 0.5
- Take Profit: 40%
- Stop Loss: 25%
- Capital: ₹100,000
- Risk per trade: 2%

#### Custom Parameters

```bash
# More aggressive strategy (lower score threshold)
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --score 60 --tp 50 --sl 30

# Conservative strategy (higher score threshold)
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --score 85 --tp 30 --sl 20

# Test only bullish signals
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --signal BULLISH

# Test only bearish signals
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --signal BEARISH

# Test specific market regime
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --regime EXPIRY

# Test specific symbols only
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --symbols NIFTY,BANKNIFTY
```

#### All-in-One Command

You can run all steps in sequence with one command:

```bash
# Download, process, load, and run backtest in one go
python historical_loader.py full --start 2024-10-01 --end 2024-12-31
# Then run backtest
python backtest_runner.py --start 2024-10-01 --end 2024-12-31
```

---

## Understanding the Results

After running a backtest, you'll see output like this:

### Trade Table

```
symbol    type  strike  entry_date   entry_price  exit_date    exit_price  pnl_pct  exit_reason
--------  ----  ------  -----------  -----------  -----------  ----------  -------  ------------
NIFTY     CE    19500   2024-10-15   125.50       2024-10-16   175.70      +40.0%   TP_HIT
BANKNIFTY PE    44000   2024-10-18   200.00       2024-10-19   150.00      -25.0%   SL_HIT
```

### Summary Statistics

```
📊 BACKTEST RESULTS
═══════════════════

Total Trades:     25
Wins:            15 (60.0%)
Losses:          10 (40.0%)

Average Return:  +8.5% per trade
Total Return:    +212.5%

Best Trade:      +45.0%
Worst Trade:     -25.0%

Average Win:     +35.0%
Average Loss:    -18.5%

Profit Factor:   1.89
Sharpe Ratio:    1.45
Max Drawdown:    -12.5%
```

### Key Metrics Explained

- **Win Rate**: Percentage of profitable trades
- **Average Return**: Mean return per trade
- **Total Return**: Cumulative return on capital
- **Profit Factor**: Total profits / Total losses (>1 is profitable)
- **Sharpe Ratio**: Risk-adjusted return (>1 is good, >2 is excellent)
- **Max Drawdown**: Largest peak-to-trough decline in capital

### Detailed Breakdowns

The results also show:
- **By Signal Type**: Performance for BULLISH vs BEARISH signals
- **By Market Regime**: Performance in TRENDING, PINNED, EXPIRY, SQUEEZE conditions
- **By Days to Expiry**: Performance at different DTE ranges
- **Exit Reasons**: Distribution of TP_HIT, SL_HIT, EXPIRY exits

---

## Common Use Cases

### 1. Test Strategy on Recent Data (Quick Test)

```bash
# Last month only
python historical_loader.py full --start 2024-11-01 --end 2024-11-30
python backtest_runner.py --start 2024-11-01 --end 2024-11-30
```

### 2. Comprehensive Historical Test

```bash
# Full year
python historical_loader.py full --start 2024-01-01 --end 2024-12-31
python backtest_runner.py --start 2024-01-01 --end 2024-12-31
```

### 3. Optimize Parameters (Find Best Settings)

```bash
# Enable grid search mode
python backtest_runner.py --start 2024-01-01 --end 2024-12-31 --optimise
```

This will test multiple combinations of score, confidence, TP, and SL parameters to find the top 10 best performing combinations.

### 4. Test Specific Trading Style

```bash
# Day trading style (tight stops)
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --tp 15 --sl 10

# Swing trading style (wider stops)
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --tp 60 --sl 35

# High conviction only
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --score 90 --confidence 0.8
```

### 5. Test Around Specific Events

```bash
# Test during election period
python historical_loader.py full --start 2024-05-01 --end 2024-06-30
python backtest_runner.py --start 2024-05-01 --end 2024-06-30

# Test during budget
python historical_loader.py full --start 2024-07-01 --end 2024-08-31
python backtest_runner.py --start 2024-07-01 --end 2024-08-31
```

---

## Troubleshooting

### Problem: "No module named 'pandas'"

**Solution:**
```bash
pip install pandas tabulate tqdm scipy yfinance jugaad-data
```

### Problem: "no such table: market_snapshots"

**Solution:**
```bash
python -c "import db; db.init_db()"
```

### Problem: "No historical data to validate"

**Solution:**
You need to download and load data first:
```bash
python historical_loader.py full --start 2024-10-01 --end 2024-12-31
```

### Problem: "Rate limit exceeded" or "Download errors"

**Solution:**
The script includes automatic rate limiting and retries. If it fails:
1. Wait a few minutes
2. Run the same command again (it will skip already downloaded files)
3. Consider downloading smaller date ranges

### Problem: "No trades generated in backtest"

**Solution:**
Your filters might be too strict. Try:
```bash
# Lower the score threshold
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --score 50 --confidence 0

# Check if data exists for your date range
python historical_loader.py status
```

### Problem: "Processing is very slow"

**Solution:**
- Use smaller date ranges (process in chunks)
- Make sure you have sufficient RAM (processing is memory-intensive)
- Consider using a faster machine or cloud instance

---

## Advanced Usage

### Using Custom Database Path

```bash
# Specify custom database location
python backtest_runner.py --db /path/to/custom.db --start 2024-10-01 --end 2024-12-31
```

### Processing Only Specific Symbols

```bash
# Download and process only NIFTY and BANKNIFTY
python historical_loader.py full --start 2024-10-01 --end 2024-12-31 --symbols NIFTY,BANKNIFTY
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 --symbols NIFTY,BANKNIFTY
```

### Incremental Data Updates

```bash
# Download only new data (e.g., last week)
python historical_loader.py download --start 2024-12-25 --end 2024-12-31
python historical_loader.py process --start 2024-12-25 --end 2024-12-31
python historical_loader.py load-db --start 2024-12-25 --end 2024-12-31

# Run backtest including new data
python backtest_runner.py --start 2024-10-01 --end 2024-12-31
```

### Exporting Results

The backtest results are printed to console. To save them:

```bash
# Save to file
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 > results.txt

# Or use tee to see and save
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 | tee results.txt
```

---

## Data Storage Locations

Understanding where data is stored:

1. **Downloaded Raw Data**: `./historical_data/` folder
   - NSE ZIP files
   - Spot price CSVs

2. **Processed Data**: `./historical_data/processed_eod_features.csv`
   - Intermediate CSV with reconstructed features

3. **Database**: `backend/scanner.db`
   - SQLite database with `market_snapshots` table
   - This is what backtests query

4. **Logs**: Console output and any error logs

---

## Parameter Reference

### historical_loader.py Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--start` | Start date (YYYY-MM-DD) | `--start 2024-01-01` |
| `--end` | End date (YYYY-MM-DD) | `--end 2024-12-31` |
| `--symbols` | Comma-separated symbols | `--symbols NIFTY,BANKNIFTY` |
| `--db` | Custom database path | `--db /path/to/db` |
| `--file` | Kaggle file path | `--file data.csv` |

### backtest_runner.py Parameters

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `--start` | Start date (YYYY-MM-DD) | 2023-01-01 | `--start 2024-01-01` |
| `--end` | End date (YYYY-MM-DD) | 2024-12-31 | `--end 2024-12-31` |
| `--score` | Minimum score threshold | 75 | `--score 80` |
| `--confidence` | Minimum confidence | 0.5 | `--confidence 0.7` |
| `--tp` | Take profit percentage | 40.0 | `--tp 50` |
| `--sl` | Stop loss percentage | 25.0 | `--sl 30` |
| `--signal` | Filter by signal type | None | `--signal BULLISH` |
| `--regime` | Filter by market regime | None | `--regime EXPIRY` |
| `--symbols` | Comma-separated symbols | All | `--symbols NIFTY,BANKNIFTY` |
| `--optimise` | Enable grid search | False | `--optimise` |
| `--db` | Custom database path | scanner.db | `--db /path/to/db` |

---

## Tips and Best Practices

1. **Start Small**: Test with 1-2 months of data first to ensure everything works

2. **Validate Data Quality**: After loading data, run `historical_loader.py status` to check data quality

3. **Iterate on Parameters**: Start with default parameters, then adjust based on results

4. **Document Your Tests**: Keep notes on what parameters work best for different market conditions

5. **Consider Market Regimes**: Different parameters may work better in different regimes (TRENDING, PINNED, EXPIRY, SQUEEZE)

6. **Avoid Over-Optimization**: Don't optimize on the same data you'll test on (use train/test splits)

7. **Check Data Freshness**: NSE data availability may have delays, especially for recent dates

8. **Backup Your Database**: Before running extensive tests, backup `scanner.db`:
   ```bash
   cp backend/scanner.db backend/scanner.db.backup
   ```

---

## Next Steps

After running backtests:

1. **Analyze Results**: Look for patterns in winning vs losing trades
2. **Test Different Strategies**: Try various parameter combinations
3. **Validate on Different Periods**: Test on multiple time periods for robustness
4. **Compare Against Benchmarks**: How does your strategy compare to buy-and-hold?
5. **Paper Trade**: Use the paper trading feature to test in real-time
6. **Go Live**: Once confident, consider live trading (with caution!)

---

## Additional Resources

- **Technical Deep Dive**: See [README_BACKTESTING.md](README_BACKTESTING.md) for detailed technical documentation
- **Performance Analysis**: See [BACKTEST_ANALYSIS.md](BACKTEST_ANALYSIS.md) for optimization opportunities
- **Main Documentation**: See [README.md](README.md) for general project documentation
- **API Documentation**: http://localhost:8000/docs when server is running

---

## Quick Reference Card

```bash
# One-liner to get started (3 months of data)
cd backend && \
python -c "import db; db.init_db()" && \
python historical_loader.py full --start 2024-10-01 --end 2024-12-31 && \
python backtest_runner.py --start 2024-10-01 --end 2024-12-31

# Check data status
python historical_loader.py status

# Run with custom parameters
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 \
  --score 80 --tp 45 --sl 25 --signal BULLISH

# Optimize parameters
python backtest_runner.py --start 2024-01-01 --end 2024-12-31 --optimise

# Test specific symbols
python backtest_runner.py --start 2024-10-01 --end 2024-12-31 \
  --symbols NIFTY,BANKNIFTY
```

---

**Happy Backtesting!** 🚀📊

For issues or questions, please open an issue on GitHub: https://github.com/shahzebkhan-os/fo-scanner/issues
