# NSE F&O Scanner v4 — Project Information

This document serves as the primary technical guide for AI agents and developers to understand the architecture, logic, and workflows of the NSE F&O Scanner.

## 📌 Project Overview
The NSE F&O Scanner is a quantitative market analysis tool designed for the Indian Derivatives market (NSE). It provides real-time option chain scanning, Black-Scholes Greeks, OI heatmaps, sector analysis, and a historical backtesting engine.

**Core Goal**: Identify high-probability trading setups using quantitative confluence rather than purely technical patterns.

---

## 🛠 Technology Stack

### Backend (Python 3.11+)
- **Framework**: FastAPI (Asynchronous API hub)
- **Data Fetching**: `curl_cffi` + `BeautifulSoup` (Scraping), `httpx` (API calls)
- **Math & Logic**: `NumPy` (Vectorized calculations), `math` (Black-Scholes)
- **Persistence**: SQLite (`scanner.db`, `trades.db`)
- **Scheduling**: `asyncio` based task manager for snapshots and Telegram reports.

### Frontend (React 19 + Vite)
- **UI Architecture**: Single Page Application (SPA) with tabbed navigation.
- **Charts**: `Recharts` for OI Heatmaps and Equity Curves.
- **Styling**: Vanilla CSS (Tailwind not used by default).
- **Integration**: Vite Proxy for `/api` calls.

---

## 🗺 Codebase Map

### Core Logic & Hubs
- [main.py](file:///Users/aayan/Desktop/fo-scanner/backend/main.py): Service orchestration, API routing, and paper trade lifecycle.
- [analytics.py](file:///Users/aayan/Desktop/fo-scanner/backend/analytics.py): The "Math Brain". Contains `compute_stock_score_v2`, Black-Scholes Greeks, Max Pain, and Regime Detection.
- [signals.py](file:///Users/aayan/Desktop/fo-scanner/backend/signals.py): High-level detectors for UOA (Unusual Options Activity), Straddles, and Sector Heatmaps.
- [db.py](file:///Users/aayan/Desktop/fo-scanner/backend/db.py): Database contract. Handles all SQLite operations and performance indexes.
- [scheduler.py](file:///Users/aayan/Desktop/fo-scanner/backend/scheduler.py): Managed background tasks (market-hours snapshots, EOD cleanup, Telegram).

### Frontend Components
- [App.jsx](file:///Users/aayan/Desktop/fo-scanner/frontend/src/App.jsx): Main shell and layout controller.
- [ScannerTab.jsx](file:///Users/aayan/Desktop/fo-scanner/frontend/src/components/ScannerTab.jsx): The flagship real-time dashboard.
- [HeatmapTab.jsx](file:///Users/aayan/Desktop/fo-scanner/frontend/src/components/HeatmapTab.jsx): 15-minute OI snapshot visualization.

---

## 🔄 Data Flow & Lifecycle

### 1. The Scan Loop (Real-time)
1. `backend/main.py` triggers `/api/scan`.
2. `fetch_nse_chain()` scrapes INDmoney or NSE for live chain data.
3. `compute_stock_score_v2()` processes the chain (Greeks → IV Skew → GEX → Overall Score).
4. Results are cached/returned and optionally saved to `db.add_trade()` if auto-trigger is on.

### 2. Historical Backtesting
1. [historical_loader.py](file:///Users/aayan/Desktop/fo-scanner/backend/historical_loader.py): Fetches EOD data and reconstructs features (Greeks/Scores) into `market_snapshots`.
2. [backtest_runner.py](file:///Users/aayan/Desktop/fo-scanner/backend/backtest_runner.py): Executes strategy replay on the `market_snapshots` table.

---

## 🧮 Key Algorithms

### Quantitative Scoring v2
The system detects the current **Market Regime** (PINNED, TRENDING, EXPIRY, SQUEEZE) and applies dynamic weights to:
- **GEX (Gamma Exposure)**: Directional bias from market maker hedging.
- **IV Skew**: Put IV vs Call IV spread.
- **DWOI/Vol PCR**: Greeks-weighted Put-Call Ratios.
- **Buildup**: Long/Short buildup detection (LTP vs OI Change).

### Performance Optimizations (Backtest)
- **Database Indexes**: Strategic indexes on `market_snapshots` for 10-50x faster queries.
- **Vectorization**: NumPy-based Max Pain and Option Greeks.
- **Smart IV Guess**: Moneyness-based initial guess for Newton-Raphson to speed up convergence.

---

## 🚀 Future Suggestions & Roadmap

> [!TIP]
> **Parallelization**: The `historical_loader.py` currently reconstructs features sequentially. Moving to `multiprocessing` could reduce a 60-minute process to under 10 minutes.

> [!IMPORTANT]
> **Testing**: The project lacks a formal test suite. Implementing `pytest` for `analytics.py` and `signals.py` is highly recommended for stability.

> [!WARNING]
> **Data Dependency**: The system relies heavily on scraping; any change in INDmoney/NSE HTML structure will break the `fetch_nse_chain()` function. Consider adding robust error handling or official API fallbacks.

**AI Suggestions for Improvement:**
1. **Caching Layer**: Implement Redis or disk-based caching for frequent API requests to avoid scraping throttles.
2. **Strategy Builder**: A frontend UI for [backtest_runner.py](file:///Users/aayan/Desktop/fo-scanner/backend/backtest_runner.py) parameters.
3. **ML Refinement**: While currently quantitative, a LightGBM model could be trained on `market_snapshots` to refine the `weighted_score` weights.
