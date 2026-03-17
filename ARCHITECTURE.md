# NSE F&O Scanner — Architecture & Component Guide

> **Version 4.0** · Full-stack options trading scanner with real-time signals, paper
> trading, ML-assisted scoring, and historical backtesting.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Project Structure](#project-structure)
3. [Backend Components](#backend-components)
   - [main.py — API Server](#mainpy--api-server)
   - [analytics.py — Scoring Engine](#analyticspy--scoring-engine)
   - [data_source.py — Market Data](#data_sourcepy--market-data)
   - [db.py — Database Layer](#dbpy--database-layer)
   - [constants.py — Configuration](#constantspy--configuration)
   - [scheduler.py — Background Tasks](#schedulerpy--background-tasks)
   - [cache.py — Caching Layer](#cachepy--caching-layer)
   - [ml_model.py — Machine Learning](#ml_modelpy--machine-learning)
   - [nn_model.py — LSTM Neural Network](#nn_modelpy--lstm-neural-network)
4. [Signal System (12 Signals)](#signal-system-12-signals)
   - [base.py — Signal Framework](#basepy--signal-framework)
   - [engine.py — Master Signal Engine](#enginepy--master-signal-engine)
   - [oi_analysis.py — Open Interest](#oi_analysispy--open-interest)
   - [iv_analysis.py — Implied Volatility](#iv_analysispy--implied-volatility)
   - [max_pain.py — Max Pain & GEX](#max_painpy--max-pain--gex)
   - [oi_velocity.py — OI Change Rate & UOA](#oi_velocitypy--oi-change-rate--uoa)
   - [price_action.py — Price Action](#price_actionpy--price-action)
   - [technicals.py — Technical Indicators](#technicalspy--technical-indicators)
   - [global_cues.py — Global Markets](#global_cuespy--global-markets)
   - [fii_dii.py — Institutional Flows](#fii_diipy--institutional-flows)
   - [straddle_pricing.py — Straddle Analysis](#straddle_pricingpy--straddle-analysis)
   - [news_scanner.py — Event Risk](#news_scannerpy--event-risk)
   - [greeks_signal.py — Greeks Aggregation](#greeks_signalpy--greeks-aggregation)
5. [Market & Execution Modules](#market--execution-modules)
   - [market/regime.py — Regime Classifier](#marketregimepy--regime-classifier)
   - [execution/executor.py — Trade Execution](#executionexecutorpy--trade-execution)
   - [execution/sizer.py — Position Sizing](#executionsizerpy--position-sizing)
   - [watcher/state.py — Trade State](#watcherstatepy--trade-state)
6. [Backtesting System](#backtesting-system)
7. [Frontend Architecture](#frontend-architecture)
   - [App.jsx — Shell & Routing](#appjsx--shell--routing)
   - [ScannerTab — Real-time Scanner](#scannertab--real-time-scanner)
   - [ChainTab — Option Chain Viewer](#chaintab--option-chain-viewer)
   - [GreeksTab — Greeks Calculator](#greekstab--greeks-calculator)
   - [HeatmapTab — OI Heatmap](#heatmaptab--oi-heatmap)
   - [SectorTab — Sector Analysis](#sectortab--sector-analysis)
   - [UOATab — Unusual Options Activity](#uoatab--unusual-options-activity)
   - [StraddleTab — Straddle Screener](#straddletab--straddle-screener)
   - [Portfolio & Trade Tabs](#portfolio--trade-tabs)
   - [BacktestTab — Historical Simulation](#backtesttab--historical-simulation)
   - [StrategyBuilder — Custom Strategies](#strategybuilder--custom-strategies)
   - [SettingsTab — Configuration](#settingstab--configuration)
8. [Data Flow Diagrams](#data-flow-diagrams)
9. [API Endpoint Reference](#api-endpoint-reference)
10. [Database Schema](#database-schema)

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React 19 + Vite)                  │
│  ScannerTab · ChainTab · GreeksTab · HeatmapTab · SectorTab    │
│  UOATab · StraddleTab · PortfolioTab · TradeTab · TrackerTab    │
│  BacktestTab · StrategyBuilder · SettingsTab                    │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP /api/* (Vite proxy → :8000)
┌────────────────────────────▼────────────────────────────────────┐
│                 BACKEND (FastAPI + Python 3.11+)                │
│                                                                 │
│  ┌─────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │ main.py │──│ analytics.py │──│ signals/ (12 modules)     │  │
│  │ 47 APIs │  │ scoring v2   │  │ OI · IV · MaxPain · Tech  │  │
│  └────┬────┘  └──────────────┘  │ Velocity · Global · FII   │  │
│       │                         │ Straddle · News · Greeks   │  │
│  ┌────▼────┐  ┌──────────────┐  │ PriceAction · engine.py   │  │
│  │ db.py   │  │ scheduler.py │  └───────────────────────────┘  │
│  │ SQLite  │  │ cron tasks   │                                  │
│  └─────────┘  └──────────────┘  ┌───────────────────────────┐  │
│                                 │ ml_model.py (LightGBM+NN) │  │
│  ┌──────────────┐               └───────────────────────────┘  │
│  │ data_source.py│  ┌────────────────────────────────────────┐  │
│  │ NSE fetching  │  │ market/ · execution/ · watcher/        │  │
│  └──────────────┘  │ regime · executor · sizer · state       │  │
│                     └────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        │                    │
   INDmoney.com         NSE APIs
   (option chains)      (LTP, FII/DII)
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19, Vite 7, Recharts, CSS custom properties |
| **Backend** | Python 3.11+, FastAPI 0.135, uvicorn |
| **Database** | SQLite (paper_trades.db) |
| **ML** | LightGBM + LSTM neural network, isotonic calibration |
| **Caching** | Redis (production) / in-memory dict (dev) |
| **Scheduling** | APScheduler (background tasks) |
| **Data Sources** | INDmoney (chains), NSE (LTP/FII), IndStocks (fallback) |
| **Alerts** | Telegram Bot API |

---

## Project Structure

```
fo-scanner/
├── backend/
│   ├── main.py                 # FastAPI server, 47 API endpoints
│   ├── analytics.py            # Scoring engine (compute_stock_score_v2)
│   ├── data_source.py          # NSE/INDmoney data fetching
│   ├── db.py                   # SQLite ORM, 13 tables
│   ├── constants.py            # Symbols, lot sizes, API config
│   ├── scheduler.py            # Background tasks (OI snapshots, reports)
│   ├── cache.py                # Redis/in-memory cache with TTL
│   ├── ml_model.py             # LightGBM + NN ensemble training & prediction
│   ├── nn_model.py             # LSTM neural network for historical sequences
│   ├── signals_legacy.py       # UOA, straddle, sector helpers
│   ├── backtest.py             # Live-signal backtesting
│   ├── backtest_runner.py      # Historical EOD backtesting
│   ├── historical_loader.py    # Data pipeline for backtest DB
│   ├── signals/                # 12-signal engine
│   │   ├── base.py             # SignalResult + BaseSignal ABC
│   │   ├── engine.py           # MasterSignalEngine aggregator
│   │   ├── oi_analysis.py      # PCR, buildup, OI walls
│   │   ├── iv_analysis.py      # IVR, IVP, skew, term structure
│   │   ├── max_pain.py         # Max pain + GEX
│   │   ├── oi_velocity.py      # OI change rate, UOA detection
│   │   ├── price_action.py     # VWAP, ORB, gaps, key levels
│   │   ├── technicals.py       # RSI, Supertrend, BBands, EMA
│   │   ├── global_cues.py      # GIFT Nifty, DXY, crude, USD/INR
│   │   ├── fii_dii.py          # FII/DII futures & options flow
│   │   ├── straddle_pricing.py # Implied vs realized vol
│   │   ├── news_scanner.py     # Event risk & blackout
│   │   └── greeks_signal.py    # Aggregate delta, charm, vanna
│   ├── market/
│   │   └── regime.py           # Regime classifier (4 types)
│   ├── execution/
│   │   ├── executor.py         # Strategy execution engine
│   │   └── sizer.py            # Position sizing (% risk)
│   ├── watcher/
│   │   └── state.py            # Trade state tracking
│   ├── models/                 # Saved ML artifacts
│   └── tests/                  # 8 test files, 91+ tests
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Main shell, 13 tabs
│   │   ├── main.jsx            # React entry point
│   │   └── components/
│   │       ├── ScannerTab.jsx  # Real-time scanner
│   │       ├── ChainTab.jsx    # Option chain viewer
│   │       ├── GreeksTab.jsx   # Greeks calculator
│   │       ├── HeatmapTab.jsx  # OI heatmap + PCR history
│   │       ├── SectorTab.jsx   # Sector aggregation
│   │       ├── UOATab.jsx      # Unusual options activity
│   │       ├── StraddleTab.jsx # Straddle/strangle screener
│   │       ├── BacktestTab.jsx # Historical backtesting UI
│   │       ├── StrategyBuilder.jsx # Custom strategy builder
│   │       └── SettingsTab.jsx # User configuration
│   ├── vite.config.js          # Vite config + API proxy
│   └── package.json
├── scripts/
│   └── refresh_slugs.py        # Update symbol→slug mapping
├── start.sh                    # One-command launcher
├── pyproject.toml              # Python project config
└── .github/workflows/ci.yml   # CI/CD pipeline
```

---

## Backend Components

### main.py — API Server

**Purpose**: FastAPI application server with 47 REST endpoints, scan orchestration,
paper trade lifecycle, and background task coordination.

#### Lifespan Events

On startup the server:
1. Initializes the SQLite database (`db.init_db()`)
2. Connects to the cache layer (Redis or in-memory fallback)
3. Starts the APScheduler with all background jobs
4. Launches the `paper_trade_manager()` background loop

#### Scan Flow (`GET /api/scan`)

This is the core endpoint that powers the Scanner tab:

```
1. Fetch data in parallel (semaphore=3 concurrent)
   ├── fetch_nse_chain(symbol) for each symbol   → option chain
   └── fetch_indstocks_ltp()                     → live prices

2. For each symbol with valid chain data:
   ├── compute_stock_score_v2()   → score, signal, top_picks
   ├── MasterSignalEngine         → engine_score, strategies
   └── ML predict (if trained)    → bullish probability

3. Score refinement (ML gates):
   ├── If score≥80 + high ML confidence → +5 point boost
   └── If ML direction ≠ signal → downgrade to NEUTRAL

4. Auto-trade entry (score≥85):
   ├── Directional guard: BULLISH→CE only, BEARISH→PE only
   ├── Dedup via _traded_today set (max 1 per symbol/day)
   ├── Sector cap: max 3 trades per sector
   └── Insert to paper_trades table

5. Telegram alerts (score≥70):
   └── Batch CSV dispatch to configured chat

6. Cache result for 60 seconds → return JSON
```

#### Paper Trade Manager

Runs as a background task during market hours (09:15–15:30 IST):

```
Every 60 seconds:
├── Fetch current prices for all open trades
├── Apply adaptive SL/TP:
│   ├── Entry < ₹20:  SL=-40%, TP=+80% (cheap OTM, wider)
│   ├── Entry ₹20–50: SL=-25%, TP=+50%
│   └── Entry > ₹50:  SL=-20%, TP=+40%
├── Trailing stop: once +25% hit, floor SL at +10%
└── EOD square-off at 15:15 IST
```

#### Key API Groups

| Group | Endpoints | Purpose |
|-------|-----------|---------|
| **Scan** | `/api/scan` | Real-time scanner with scores |
| **Chain** | `/api/chain/{symbol}` | Full option chain + Greeks |
| **Greeks** | `/api/greeks/{symbol}` | Black-Scholes for all strikes |
| **OI** | `/api/oi-heatmap/{symbol}`, `/api/oi-timeline/{symbol}` | OI snapshots |
| **PCR** | `/api/pcr-history/{symbol}` | Intraday PCR timeline |
| **UOA** | `/api/uoa` | Unusual options activity |
| **Straddle** | `/api/straddle-screen` | Straddle/strangle screener |
| **Sectors** | `/api/sector-heatmap` | Sector-level aggregation |
| **Portfolio** | `/api/portfolio`, `/api/position-size` | P&L + sizing |
| **Trades** | `/api/paper-trades` (CRUD) | Paper trading lifecycle |
| **Tracking** | `/api/tracked-picks`, `/api/trade-tracker/*` | Pick tracking |
| **Backtest** | `/api/backtest`, `/api/historical-backtest`, `/api/backtest/run` | Backtesting |
| **ML** | `/api/ml/train`, `/api/ml/status` | Model training |
| **Settings** | `/api/settings/watchlist`, `/api/settings/capital` | User config |
| **FII/DII** | `/api/fii-dii`, `/api/bulk-deals` | Institutional data |
| **Debug** | `/api/debug-slugs`, `/api/debug/{symbol}` | Diagnostics |

---

### analytics.py — Scoring Engine

**Purpose**: Quantitative scoring of stocks and options using 6 weighted factors,
Black-Scholes Greeks, regime detection, and max pain calculation.

#### Black-Scholes Greeks

Calculates option Greeks using the standard Black-Scholes model:

| Greek | Formula | Interpretation |
|-------|---------|---------------|
| **Delta (Δ)** | N(d₁) for calls, N(d₁)−1 for puts | Price sensitivity (0 to ±1) |
| **Gamma (Γ)** | φ(d₁) / (S·σ·√T) | Delta's rate of change |
| **Theta (Θ)** | Time decay per day | Always negative for longs |
| **Vega (ν)** | S·φ(d₁)·√T | Impact of 1% IV change |
| **Rho (ρ)** | K·T·e^(−rT)·N(d₂)/100 | Interest rate sensitivity |

Also computes: intrinsic value, time value, moneyness label (ITM/ATM/OTM).

#### Max Pain Calculation

Iterates all strikes to find the one where option writers lose least:

```
For each candidate strike:
  pain = Σ(call_OI × max(0, strike − candidate))
       + Σ(put_OI × max(0, candidate − strike))

Max pain = strike with minimum total pain
```

This is the price the market gravitates toward at expiry.

#### Regime Detection

Classifies market conditions into one of four regimes:

| Regime | Detection Logic | Typical Strategy |
|--------|----------------|-----------------|
| **EXPIRY** | DTE ≤ 2 | Gamma scalping, tight stops |
| **SQUEEZE** | IVR < 25 and DTE > 5 | Buy premium (vol expansion) |
| **PINNED** | Top-3 strike OI > 60% of total | Sell premium (range-bound) |
| **TRENDING** | Default fallback | Directional trades |

#### compute_stock_score_v2() — Core Scoring

The main scoring function uses 6 weighted factors that change by regime:

```
┌─────────────────────────────────────────────────────────┐
│  REGIME_WEIGHTS (factors sum to 1.0 per regime)         │
├──────────┬────────┬──────────┬─────────┬────────────────┤
│ Factor   │ PINNED │ TRENDING │ SQUEEZE │ EXPIRY         │
├──────────┼────────┼──────────┼─────────┼────────────────┤
│ GEX      │  0.30  │   0.15   │  0.40   │  0.10          │
│ Vol PCR  │  0.10  │   0.25   │  0.30   │  0.40          │
│ DWOI PCR │  0.40  │   0.15   │  0.10   │  0.10          │
│ IV Skew  │  0.10  │   0.20   │  0.10   │  0.10          │
│ Buildup  │  0.02  │   0.13   │  0.02   │  0.18          │
│ Velocity │  0.08  │   0.12   │  0.08   │  0.12          │
└──────────┴────────┴──────────┴─────────┴────────────────┘
```

**Sub-score computation**:

1. **GEX** (Gamma Exposure): 100 if spot > zero-gamma-level and net GEX > 0
   (stabilizing), 0 if bearish, 50 if mixed.
2. **Vol PCR**: `min(100, PE_volume / CE_volume × 50)`. Higher PE volume
   relative to CE → more bullish (contrarian).
3. **DWOI PCR** (Delta-Weighted OI): `min(100, (PE_OI×|δ|) / (CE_OI×|δ|) × 50)`.
   Like PCR but weighted by how "in-play" each strike is.
4. **IV Skew**: `100 − skew_percentile`. Low skew (puts cheap) → bullish.
5. **Buildup**: 100 if long buildup detected, 0 if short buildup, 50 if mixed.
6. **OI Velocity**: `50 + (velocity_score × 40)`. Velocity from the
   OiVelocitySignal module, measuring speed of OI accumulation.

**Signal determination**: Count bullish vs bearish factors; need ≥2 aligned →
BULLISH or BEARISH; else NEUTRAL.

**UOA override**: When Unusual Options Activity is detected with confidence > 0.6,
apply ±8 point score boost.

**Per-option scoring** (`score_option_v2`): Each individual option contract gets
scored 0–100 based on delta proximity (25 pts), liquidity/OI (50 pts), and IV
rank (25 pts). Top 2 picks per direction are selected.

---

### data_source.py — Market Data

**Purpose**: Fetches and normalizes option chain data from INDmoney and live
prices from NSE/IndStocks.

#### Option Chain Fetching

```
fetch_nse_chain(symbol)
├── Look up URL slug (e.g., "NIFTY" → "nifty-50-share-price")
├── HTTP GET to https://www.indmoney.com/options/{slug}
│   └── Uses curl_cffi with browser impersonation (bypasses Akamai)
├── Parse HTML → extract __NEXT_DATA__ script tag
├── Recursive search for "option_chain_data" key
├── For each row in chains:
│   ├── Extract call_data → {OI, volume, IV, LTP}
│   ├── Extract put_data → {OI, volume, IV, LTP}
│   └── Compute OI change = OI × oi_change_pct / 100
└── Return {records, spot, expiries} in NSE-compatible format
```

#### Live Price Fetching

Two-tier fallback for spot prices:

```
fetch_indstocks_ltp()
├── Primary: NSE Market Watch API
│   ├── /api/equity-stockIndices?index=SECURITIES IN F&O  (stocks)
│   └── /api/equity-stockIndices?index=NIFTY 50           (indices)
└── Fallback: IndStocks API (token-based)
    └── /market/quotes/full?scrip-codes=NSE_SYM1,NSE_SYM2,...
```

---

### db.py — Database Layer

**Purpose**: SQLite persistence for trades, OI history, settings, accuracy
tracking, and backtest data.

#### Tables (13 total)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `paper_trades` | Paper/auto trades | symbol, type, strike, entry/exit price, pnl, status |
| `tracked_picks` | Watchlist options | symbol, strike, entry_price, score |
| `oi_history` | 15-min OI snapshots | symbol, strike, opt_type, oi, volume, iv |
| `iv_history` | Daily IV per symbol | symbol, iv, snap_date (unique) |
| `notifications` | Alert dedup | uid (alert ID), sent_at |
| `trade_notes` | Journal per trade | trade_id, note text |
| `bulk_deals` | NSE bulk/block deals | symbol, client, quantity, price |
| `settings` | Key-value config | key, value, updated_at |
| `partial_exits` | Scale-out tracking | trade_id, exit_price, lots_exited |
| `accuracy_snapshots` | Time-series snapshots | timestamp |
| `accuracy_trades` | Live trade tracking | snapshot_id, symbol, score, ml_prob, signal |
| `accuracy_trade_history` | Price history | trade_id, price, timestamp |
| `market_snapshots` | Historical backtest data | symbol, spot, pcr, iv, signal, outcome |

#### Key Operations

- **`init_db()`**: Creates all tables + indexes; runs ALTER TABLE migrations for
  new columns (safe with try/except).
- **`add_trade()` / `update_trade()`**: Paper trade CRUD with P&L calculation.
- **`save_oi_snapshot()`**: Bulk-inserts full chain every 15 min.
- **`get_iv_rank()`**: Computes `(current − 52w_low) / (52w_high − 52w_low) × 100`.
- **`get_trade_stats()`**: Win/loss counts, equity curve, max drawdown.

---

### constants.py — Configuration

Centralizes all static configuration:

| Constant | Description |
|----------|-------------|
| `FO_STOCKS` | 44 NSE F&O-eligible stock symbols |
| `INDEX_SYMBOLS` | `["NIFTY", "BANKNIFTY", "FINNIFTY"]` |
| `LOT_SIZES` | Contract multipliers (NIFTY=75, BANKNIFTY=30, etc.) |
| `NSE_HEADERS` | Browser-like headers for NSE API scraping |
| `SLUG_MAP` | Symbol → INDmoney URL slug mapping |
| `INDSTOCKS_BASE` | IndStocks API base URL |
| `NSE_BASE` | NSE website base URL |
| `MAX_DAILY_AUTO_TRADES` | Unlimited (no daily cap) |
| `MAX_SECTOR_TRADES` | Unlimited (no sector cap) |

---

### scheduler.py — Background Tasks

**Purpose**: Runs timed tasks during and after market hours.

| Task | Schedule | Logic |
|------|----------|-------|
| **OI Snapshot** | Every 15 min (market hours) | Fetches full chain for all symbols → `oi_history` table |
| **IV History** | Daily at 15:35 IST | Saves ATM IV at close → powers IV Rank |
| **Pre-Market Report** | 09:00 weekdays | Top 5 picks + sector heatmap → Telegram |
| **Bulk Deals** | 16:00 IST | Fetches NSE bulk/block deals after close |
| **DB Cleanup** | Sunday midnight | Purges snapshots > 30 days old |
| **Accuracy Sampler** | Every 10 min | Snapshots predictions for backtesting |
| **Price Updater** | Every 5 min | Updates current prices in accuracy trades |
| **ML Retrain** | On-demand / daily | Retrains LightGBM + LSTM neural network |

---

### cache.py — Caching Layer

**Purpose**: Redis primary with in-memory dict fallback.

```
Cache()
├── Redis (production) — async operations with TTL
└── In-memory dict (development) — TTL tracked with expiration timestamps
```

| Key Prefix | TTL | Used For |
|------------|-----|----------|
| `option_chain` | 5 sec | Chain data refresh |
| `indices` | 3 sec | Index prices |
| `scan_result` | 60 sec | Scan endpoint cache |
| `fii_dii` | 6 hours | Institutional data |
| `iv_history` | 1 hour | IV history |
| `ban_list` | 24 hours | NSE ban list |

---

### ml_model.py — Machine Learning

**Purpose**: Ensemble of LightGBM classifier + LSTM neural network predicting next-bar direction (bullish/bearish).

#### Training Pipeline — LightGBM

```
1. Load market_snapshots (requires 500+ rows)
2. Extract 13 features:
   weighted_score, gex, iv_skew, pcr, regime_encoded,
   vix_norm, dte, hour_sin, hour_cos, day_of_week,
   price_momentum_5, volume_ratio, max_pain_distance
3. Create labels: 1 if next_close > current_close, else 0
4. Time-series cross-validation (no future leakage)
5. Train LightGBM (200 estimators, early stopping)
6. Calibrate with isotonic regression
7. Save only if CV loss < 0.693 (better than random)
```

#### Training Pipeline — LSTM Neural Network (nn_model.py)

```
1. Load market_snapshots ordered by symbol + time
2. Normalize features with StandardScaler
3. Create sliding-window sequences (10 bars per sample) per symbol
4. Time-series cross-validation (no future leakage)
5. Train 2-layer LSTM (hidden=64) + MLP head with early stopping
6. Save only if CV loss < 0.693 (better than random)
```

The neural network captures temporal patterns in the historical data
that the point-in-time LightGBM classifier may miss (trends, momentum,
regime transitions).

#### Score Blending

Final score combines three sources:

```
Ensemble = QUANT (50%) + ML (up to 30%) + Engine (up to 20%)
```

ML probability is itself an ensemble when both models are trained:

```
ML = LightGBM (60%) + Neural Network LSTM (40%)
```

- **QUANT**: `compute_stock_score_v2()` output (0–100)
- **ML (LightGBM)**: Calibrated probability from isotonic regression
- **ML (Neural Net)**: LSTM probability from last 10 historical bars
- **Engine**: `MasterSignalEngine.compute_all_signals()` composite

Time-of-day adjustments apply discounts: morning (−15%), expiry afternoon
(−10%), EOD (−20%).

---

### nn_model.py — LSTM Neural Network

**Purpose**: PyTorch LSTM that processes sliding windows of historical
market data to capture temporal patterns (trends, momentum, regime shifts).

#### Architecture

```
Input (batch, 10, 5)          ← 10 historical bars × 5 features
  → LSTM(hidden=64, layers=2, dropout=0.3)
  → last time-step hidden state
  → Dropout(0.3)
  → Linear(64 → 32) + ReLU
  → Linear(32 → 1) + Sigmoid
Output: P(bullish) ∈ [0, 1]
```

#### Prediction Flow

```
1. Query last 10 market_snapshots for the symbol
2. Append current live features as the newest bar
3. Normalize with the saved StandardScaler
4. Feed through the trained LSTM
5. Return P(bullish)
```

Falls back gracefully to `None` if torch is not installed or the model
is not yet trained.

---

## Signal System (12 Signals)

### base.py — Signal Framework

All signals implement a common interface:

```python
@dataclass
class SignalResult:
    score: float       # -1.0 (bearish) to +1.0 (bullish)
    confidence: float  # 0.0 to 1.0
    reason: str        # Human-readable explanation
    metadata: dict     # Signal-specific data

class BaseSignal(ABC):
    @abstractmethod
    def compute(self, **kwargs) -> SignalResult: ...
```

Values are auto-clamped to valid ranges in `__post_init__`.

---

### engine.py — Master Signal Engine

**Purpose**: Aggregates all 12 signals into a single trading decision.

```
Input: option chain + spot + historical data + external feeds
  ↓
12 signals computed independently
  ↓
RegimeClassifier determines market state
  ↓
Regime-specific weights applied:
  ├── RANGE_BOUND:     OI + IV + MaxPain + Straddle (mean reversion)
  ├── TRENDING_UP/DOWN: Price + Technicals + Global (momentum)
  └── HIGH_VOLATILITY:  VIX + News + IV + Straddle (event-driven)
  ↓
Composite score + confidence + trade decision
  ↓
Output: AggregatedSignal {
  composite_score,  # -1.0 to +1.0
  confidence,       # weighted average
  regime,           # market state
  trade,            # boolean (score≥0.45 AND confidence≥0.60)
  blackout,         # True if news event blocks trading
  recommended_strategy  # e.g., "iron_condor"
}
```

---

### oi_analysis.py — Open Interest

Three sub-signals weighted 35% + 40% + 25%:

1. **PCR Signal**: Contrarian — high PCR (fear) → bullish; low PCR (greed) → bearish
2. **OI Buildup**: CE OI rising + price falling → resistance; PE OI rising +
   price rising → support
3. **Wall Distance**: Asymmetry between highest CE and PE OI walls

---

### iv_analysis.py — Implied Volatility

Four sub-metrics weighted 30% + 25% + 15% + 30%:

1. **IV Rank**: Percentile of current IV in 52-week range. IVR > 70 → sell
   premium; IVR < 30 → buy premium
2. **IV Percentile**: % of days IV was below current (robust alternative to IVR)
3. **IV Skew**: ATM put IV minus call IV. High skew → fear, low skew → complacency
4. **Term Structure**: Near-month vs far-month IV (backwardation vs contango)

Also includes **VIX analysis**: VIX > 20 → fear/sell premium; VIX < 12 →
complacency/buy vega.

---

### max_pain.py — Max Pain & GEX

Two components weighted by DTE:

1. **Max Pain**: Strike minimizing option writer losses. Near expiry (DTE ≤ 2)
   acts as strong magnet; far expiry is weak reference.
2. **Gamma Exposure (GEX)**: `Σ(CE_γ × CE_OI − PE_γ × PE_OI) × S² × lot`.
   Positive GEX → market makers stabilize (long gamma); negative →
   destabilize (short gamma). GEX flip detection flags volatility expansion.

---

### oi_velocity.py — OI Change Rate & UOA

**Purpose**: Measures speed of OI change, not just level. Detects institutional
block trades (Unusual Options Activity).

```
OI velocity = (current_OI − prev_OI) / elapsed_minutes

UOA = velocity > 2× rolling 20-period average
```

- Maintains per-symbol rolling window of 20 snapshots
- Only measures ATM strikes (±1.5% of spot)
- Score: positive = call velocity dominant (bullish), negative = put dominant
- UOA flag triggers ±8 point score boost in analytics.py

---

### price_action.py — Price Action

Four sub-signals averaged:

1. **VWAP**: >30 min above → bullish; >30 min below → bearish
2. **Opening Range Breakout** (9:15–9:30 candle): breakout/breakdown detection
3. **Gap Analysis**: gap fill >50% → counter-trend; gap holding → trend-follow
4. **Key Levels**: previous close/high/low, OI walls as support/resistance

---

### technicals.py — Technical Indicators

Five indicators weighted 25% + 20% + 15% + 20% + 10%:

1. **Supertrend** (10, 3): Dynamic ATR-based support/resistance
2. **RSI(14)**: >70 overbought, <30 oversold
3. **Bollinger Bands** (20, 2σ): Squeeze detection + band touches
4. **EMA Crossover** (9 vs 21): Bullish/bearish crossover signals
5. **Volume Analysis**: Spike >2× average → conviction signal

---

### global_cues.py — Global Markets

Five external market sources with time-decaying weights:

| Source | Weight | Logic |
|--------|--------|-------|
| **GIFT Nifty** | 25% | Gap > ±1% → strong signal |
| **US Markets** (SPX, NASDAQ) | 25% | Overnight sentiment (60/40 split) |
| **DXY** (Dollar Index) | 15% | >106 = FII outflows (inverse) |
| **Crude Oil** | 15% | >$90 = bearish India (importer) |
| **USD/INR** | 20% | >84 = INR weak, FII selling (inverse) |

**Time multiplier**: Full weight at open (1.0), fades to 0.3 by afternoon
as domestic factors dominate.

---

### fii_dii.py — Institutional Flows

Four components weighted 35% + 25% + 25% + 15%:

1. **FII Futures Flow**: >₹5000cr = strong bullish; <−₹2000cr = bearish
2. **FII Options Activity**: PE selling = bullish; CE selling = bearish
3. **Cumulative 3-Day Flow**: >₹15000cr = bullish regime
4. **DII Counterbalance**: Strong DII buying offsets FII selling

Confidence capped at 0.85 due to 1-day data lag.

---

### straddle_pricing.py — Straddle Analysis

Three components weighted 40% + 30% + 30%:

1. **Implied vs Realized Volatility**: Straddle cost vs historical move.
   Ratio > 1.3 → overpriced (sell); ratio < 0.8 → underpriced (buy)
2. **Breakeven Levels**: Upper/lower breakevens as support/resistance
3. **Decay Rate**: Faster decay than expected → IV crush (exit longs)

---

### news_scanner.py — Event Risk

**Most critical output: the BLACKOUT flag.**

- Pre-event (HIGH impact within 24h): `blackout=True`, blocks premium selling
- Post-event: IV crush detection (IV drop >20%), large move detection
- HIGH impact events: RBI MPC, US Fed, earnings, CPI, GDP, budget, elections

---

### greeks_signal.py — Greeks Aggregation

Four metrics weighted 30% + 20% + 20% + 30%:

1. **Aggregate Delta**: Net delta across all strikes → market directional bias
2. **Charm Analysis** (DTE ≤ 2): Delta collapse risk on OTM options
3. **Vanna Analysis**: Delta sensitivity to IV changes
4. **Portfolio Greeks Balance**: Net vega, theta, delta-neutral checks

---

## Market & Execution Modules

### market/regime.py — Regime Classifier

Classifies market conditions to adapt strategy and position sizing:

| Regime | Detection | Size Multiplier | Best Strategies |
|--------|-----------|-----------------|-----------------|
| **TRENDING_UP** | Price > 20-EMA, Supertrend bullish | 0.7× | Bull call spreads |
| **TRENDING_DOWN** | Price < 20-EMA, Supertrend bearish | 0.7× | Bear put spreads |
| **RANGE_BOUND** | Within ±0.3% of VWAP, positive GEX | 1.0× | Iron condor, straddle |
| **HIGH_VOLATILITY** | VIX > 18 or VIX spike >10% | 0.4× | Long straddle only |

---

### execution/executor.py — Trade Execution

Executes multi-leg options strategies:

```
Signal → Strategy Definition → Resolve Strikes → Validate Liquidity
→ Calculate Position Size → Risk Gate Check → Execute All Legs
→ Register with TradeWatcher
```

**Predefined strategies**: bull_call_spread, bear_put_spread, iron_condor,
short_straddle, long_straddle, etc.

**Validation**: Min OI 500 lots, max spread 2% of mid, all legs must be available.

---

### execution/sizer.py — Position Sizing

Uses the 2% risk rule:

```
risk_amount = capital × risk_pct        # e.g., ₹100k × 2% = ₹2,000
max_loss    = entry × sl_pct × lot_size # e.g., ₹150 × 20% × 75 = ₹2,250
lots        = risk_amount / max_loss    # e.g., ₹2,000 / ₹2,250 = 0.89 → 1 lot
```

Defined-risk strategies (spreads): max loss = width − net credit.
Undefined-risk strategies (naked): max loss = 2× straddle price.

---

### watcher/state.py — Trade State

Tracks all active and closed multi-leg trades:

```python
OptionsTradeState:
  legs[]             # Individual option contracts
  current_pnl        # Sum of all legs' P&L
  max_profit/loss    # Strategy-defined limits
  target_pnl         # Take profit level
  stop_loss_pnl      # Stop loss level
  regime_at_entry    # Market conditions when entered

TradeWatcher:
  register(trade)            # Add new trade
  update_all_prices(prices)  # Update LTP for all legs
  check_exits()              # Find trades hitting TP/SL
  get_portfolio_greeks()     # Sum Greeks across trades
```

---

## Backtesting System

Two backtesting modes:

### Mode 1: backtest.py — Live Signal Replay

- Fetches current live signals via `/api/scan`
- For each top pick, fetches historical candles from IndStocks
- Simulates entry → exit on TP/SL/hold-to-end
- Outputs: win rate, profit factor, Sharpe ratio, drawdown

### Mode 2: backtest_runner.py — Historical EOD Simulation

- Loads pre-computed `market_snapshots` from SQLite
- Filters by score threshold, confidence, signal direction
- Applies configurable SL/TP with adaptive logic
- Tracks equity curve, regime breakdown, per-symbol stats

### historical_loader.py — Data Pipeline

Reconstructs historical option chain snapshots for the backtest DB:

```
yfinance (spot prices) + NSE Bhavcopy (option EOD data)
→ Reconstruct ATM chain per day per symbol
→ Calculate PCR, IV, max pain, pseudo-GEX, Greeks
→ Label next-day outcome (WIN/LOSS/NEUTRAL)
→ Insert into market_snapshots table
```

---

## Frontend Architecture

### App.jsx — Shell & Routing

The main application shell provides:

- **13 tabs** with keyboard shortcuts (R=Scanner, C=Chain, G=Greeks, etc.)
- **Dark/light theme** persisted to localStorage
- **Health check** every 30 seconds (monitors backend + market status)
- **Lot sizes** loaded from `/api/lot-sizes` for position sizing

### ScannerTab — Real-time Scanner

The primary tab showing all symbols scored and ranked:

- **Auto-refresh** every 60 seconds with countdown timer
- **ML model status**: Shows trained/untrained; offers "Train Model" button
- **Score dials**: Two circular gauges (Quant Score + ML Score)
- **Signal cards**: Color-coded (green=BULLISH, red=BEARISH, gray=NEUTRAL)
- **Top picks**: Best option contracts per direction
- **UOA banner**: Shown when institutional activity detected
- **Filtering**: By signal direction or keyword search
- **Watchlist**: Star button toggles symbols to personal list

Calls: `GET /api/scan`, `GET /api/ml/status`, `GET /api/settings/watchlist`

### ChainTab — Option Chain Viewer

Full strike-by-strike option chain display for a selected symbol:
- All strikes with CE/PE OI, volume, IV, LTP, Greeks
- Color-coded by moneyness (ITM/ATM/OTM)
- Integrated Greeks per strike

Calls: `GET /api/chain/{symbol}`

### GreeksTab — Greeks Calculator

Dedicated Greeks analysis:
- Tabular display of delta, gamma, theta, vega, rho for all strikes
- Moneyness classification

Calls: `GET /api/greeks/{symbol}`

### HeatmapTab — OI Heatmap

Visual representation of OI across strikes and time:
- **OI Heatmap**: Color-coded OI intensity by strike
- **PCR History**: Intraday PCR timeline chart

Calls: `GET /api/oi-heatmap/{symbol}`, `GET /api/pcr-history/{symbol}`

### SectorTab — Sector Analysis

Aggregates scanner results by sector (Banking, IT, Pharma, etc.):
- Sector-level signal (BULLISH/BEARISH/NEUTRAL)
- Average score across sector symbols
- Bullish/bearish/neutral count breakdown

Calls: `GET /api/sector-heatmap`

### UOATab — Unusual Options Activity

Identifies strikes with abnormally high volume relative to history:
- Volume > 5× the 5-day average → flagged as UOA
- Shows: symbol, strike, type, volume ratio, OI, distance from spot

Calls: `GET /api/uoa`

### StraddleTab — Straddle Screener

Screens for straddle/strangle setups:
- ATM straddle price, breakeven levels
- Implied move vs historical realized move
- Cost and % move needed

Calls: `GET /api/straddle-screen`

### Portfolio & Trade Tabs

- **PortfolioTab (P&L)**: Equity curve, open positions with SL/TP bars,
  closed trade history, win/loss stats
- **ManualTradeTab (Trade)**: Pre-filled form from scanner picks, adjustable
  strike/entry/size
- **TradeTrackerTab (Tracker)**: Auto-tracked 15-min snapshots showing
  prediction accuracy over time

Calls: `GET /api/portfolio`, `GET /api/paper-trades/*`, `GET /api/trade-tracker/*`

### BacktestTab — Historical Simulation

UI for running backtests with configurable parameters:
- Date range, score threshold, SL/TP percentages
- Results: equity curve, win rate, Sharpe, profit factor
- Breakdown by regime, DTE, symbol

Calls: `POST /api/backtest/run`, `POST /api/historical-backtest`

### StrategyBuilder — Custom Strategies

Interface for building custom multi-leg option strategies.

### SettingsTab — Configuration

User preferences:
- Trading capital (₹), watchlist symbols
- Auto-refresh interval, score thresholds
- FII/DII activity display
- Keyboard shortcut reference

Calls: `GET/POST /api/settings/*`, `GET /api/fii-dii`

---

## Data Flow Diagrams

### Live Scan Cycle (every 60 seconds)

```
NSE/INDmoney APIs
       │
       ▼
┌─────────────────┐     ┌──────────────────┐
│ data_source.py  │────▶│ Option chains    │
│ fetch_nse_chain │     │ + Live prices    │
└─────────────────┘     └────────┬─────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   analytics.py          │
                    │   compute_stock_score   │
                    │                         │
                    │   6 factors:            │
                    │   GEX · Vol PCR · DWOI  │
                    │   Skew · Buildup · OI   │
                    │   Velocity              │
                    │                         │
                    │   → Regime detection    │
                    │   → Weighted scoring    │
                    │   → Top pick selection  │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
     ┌────────────────┐  ┌─────────────┐  ┌────────────────┐
     │ MasterSignal   │  │ ML Model    │  │ Auto-Trade     │
     │ Engine (12 sig)│  │ (LightGBM)  │  │ Entry Guard    │
     └───────┬────────┘  └──────┬──────┘  └───────┬────────┘
             │                  │                  │
             └──────────────────┼──────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Score Blending:      │
                    │  QUANT 50% + ML 30%   │
                    │  + Engine 20%         │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Cache (60s) → API    │
                    │  → Telegram alerts    │
                    │  → Frontend display   │
                    └───────────────────────┘
```

### Paper Trade Lifecycle

```
Entry (manual or auto)
       │
       ▼
┌─────────────────┐
│ paper_trades    │ ← db.add_trade()
│ table insert    │
└────────┬────────┘
         │
         ▼ (every 60s during market hours)
┌─────────────────────────────────────────┐
│ paper_trade_manager()                   │
│                                         │
│  Fetch current price                    │
│  ├── Apply adaptive SL/TP:             │
│  │   ├── < ₹20:  SL=-40%, TP=+80%     │
│  │   ├── ₹20-50: SL=-25%, TP=+50%     │
│  │   └── > ₹50:  SL=-20%, TP=+40%     │
│  ├── Trailing: +25% hit → floor at +10%│
│  └── EOD: square off at 15:15 IST      │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Exit: pnl calc  │
│ status='CLOSED' │
└─────────────────┘
```

---

## API Endpoint Reference

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/scan` | Real-time scanner with scores for all symbols |
| GET | `/api/chain/{symbol}` | Full option chain with Greeks |
| GET | `/api/greeks/{symbol}` | Black-Scholes Greeks all strikes |
| GET | `/api/ivrank/{symbol}` | 52-week IV rank |
| GET | `/api/oi-heatmap/{symbol}` | OI snapshots by strike |
| GET | `/api/oi-timeline/{symbol}` | 5-day intraday OI for one strike |
| GET | `/api/pcr-history/{symbol}` | Intraday PCR timeline |
| GET | `/api/uoa` | Unusual options activity |
| GET | `/api/straddle-screen` | Straddle/strangle candidates |
| GET | `/api/sector-heatmap` | Sector-level signal aggregation |
| GET | `/api/portfolio` | P&L dashboard |
| GET | `/api/position-size` | Position sizing calculation |
| GET | `/api/lot-sizes` | Contract multipliers |
| GET | `/api/fii-dii` | Institutional flows |
| GET | `/api/bulk-deals` | NSE bulk/block deals |
| POST | `/api/bulk-deals/refresh` | Refresh bulk deal data |
| POST | `/api/paper-trades` | Create new paper trade |
| GET | `/api/paper-trades/active` | List open positions |
| GET | `/api/paper-trades/history` | List closed trades |
| GET | `/api/paper-trades/stats` | Trade statistics + equity curve |
| GET | `/api/paper-trades/export` | Export trades as CSV |
| POST | `/api/paper-trades/{id}/exit` | Close a position |
| POST | `/api/paper-trades/{id}/note` | Add journal note |
| GET | `/api/paper-trades/{id}/notes` | Get notes for trade |
| POST | `/api/track-pick` | Add option to watchlist |
| GET | `/api/tracked-picks` | List watched options |
| DELETE | `/api/track-pick/{id}` | Remove from watchlist |
| DELETE | `/api/tracked-picks` | Clear all tracked picks |
| GET | `/api/trade-tracker/latest` | Latest accuracy snapshot |
| GET | `/api/trade-tracker/today` | Today's tracked trades |
| POST | `/api/backtest` | Run live-signal backtest |
| POST | `/api/historical-backtest` | Run historical EOD backtest |
| POST | `/api/backtest/run` | Run backtest (backtest_runner) |
| GET | `/api/backfill/progress` | Historical data load progress |
| POST | `/api/backfill/start` | Start historical data load |
| POST | `/api/ml/train` | Train LightGBM + Neural Network models |
| GET | `/api/ml/status` | Check if model is trained |
| GET | `/api/settings/watchlist` | Get user watchlist |
| POST | `/api/settings/watchlist` | Update user watchlist |
| GET | `/api/settings/capital` | Get trading capital |
| POST | `/api/settings/capital` | Update trading capital |
| GET | `/api/settings/threshold/{sym}` | Get per-symbol threshold |
| POST | `/api/settings/threshold/{sym}` | Set per-symbol threshold |
| GET | `/api/debug-slugs` | Debug slug mapping |
| GET | `/api/debug/{symbol}` | Debug chain fetch for symbol |
| GET | `/api/debug-indstocks` | Debug IndStocks LTP |
| GET | `/health` | Health check + market status |

---

## Database Schema

### paper_trades
```sql
id INTEGER PRIMARY KEY,
symbol TEXT, type TEXT, strike REAL,
entry_price REAL, current_price REAL, exit_price REAL,
status TEXT DEFAULT 'OPEN',
pnl REAL DEFAULT 0, pnl_pct REAL DEFAULT 0,
lot_size INTEGER, reason TEXT,
created_at TIMESTAMP, updated_at TIMESTAMP
```

### oi_history
```sql
id INTEGER PRIMARY KEY,
symbol TEXT, strike REAL, opt_type TEXT,
oi INTEGER, oi_chg INTEGER,
volume INTEGER, iv REAL, ltp REAL,
snap_date TIMESTAMP
```

### iv_history
```sql
id INTEGER PRIMARY KEY,
symbol TEXT, iv REAL,
snap_date DATE UNIQUE(symbol, snap_date)
```

### market_snapshots
```sql
id INTEGER PRIMARY KEY,
symbol TEXT, snapshot_time DATETIME,
spot_price REAL, pcr_oi REAL,
atm_ce_iv REAL, atm_pe_iv REAL,
max_pain REAL, dte INTEGER,
score REAL, confidence REAL,
signal TEXT, regime TEXT,
top_pick_type TEXT, top_pick_strike REAL,
top_pick_ltp REAL,
pick_pnl_pct_next REAL,
trade_result TEXT,        -- WIN|LOSS|NEUTRAL
data_source TEXT,         -- EOD_HISTORICAL|LIVE
oi_velocity_score REAL,
uoa_detected INTEGER,
global_score REAL
```

### accuracy_trades
```sql
id INTEGER PRIMARY KEY,
snapshot_id INTEGER REFERENCES accuracy_snapshots(id),
symbol TEXT, type TEXT, strike REAL,
entry_price REAL, current_price REAL,
score REAL, ml_prob REAL,
signal TEXT, regime TEXT,
pcr REAL, iv REAL, iv_rank REAL
```
