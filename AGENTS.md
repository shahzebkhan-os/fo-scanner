# AGENTS.md

## Project map (what matters first)
- `backend/main.py` is the runtime hub: FastAPI app, scan orchestration, paper trade lifecycle, scheduler wiring, and SPA serving fallback.
- `backend/data_source.py` normalizes market data into an NSE-like `records` shape used by analytics/signals.
- `backend/analytics.py` holds scoring math (`compute_stock_score_v2`, option scoring, Greeks, regimes).
- `backend/signals.py` adds higher-level detectors (UOA, straddle, sector heatmap, PCR timeline, bulk/block deal fetch).
- `backend/db.py` is the persistence contract; most behavior depends on `scanner.db` tables initialized in `init_db()`.
- `frontend/src/App.jsx` is a tabbed shell; each tab calls backend APIs directly via `fetch` with `API=""` (Vite proxy expected).

## End-to-end data flow
- Scan loop: `/api/scan` in `backend/main.py` -> `fetch_nse_chain()` + `fetch_indstocks_ltp()` -> `compute_stock_score_v2()` -> optional auto-trade writes via `db.add_trade()`.
- Background tasks are started in FastAPI lifespan (`Scheduler.start_all()` + `paper_trade_manager()`), not by an external worker.
- OI/IV history is built asynchronously in `backend/scheduler.py` and later consumed by IV Rank, UOA baseline, heatmap, and PCR endpoints.
- Frontend scanner (`frontend/src/components/ScannerTab.jsx`) refreshes every 60s and drives chain/greeks navigation from top picks.

## Developer workflows (actual repo behavior)
- Quick local start script: `./start.sh` (kills ports 8000/5173-5175, then starts backend + Vite on 5175).
- Backend deps are pinned in `backend/requirements.txt`; frontend scripts live in `frontend/package.json` (`dev`, `build`, `lint`, `format`).
- Formatting/lint conventions come from `pyproject.toml`: Black line length 120, isort profile black, relaxed pylint rules.
- No test suite is present in-tree; verify changes by exercising API endpoints and affected UI tabs manually.

## Project-specific conventions to follow
- Keep symbol universe centralized in `backend/constants.py` (`FO_STOCKS`, `INDEX_SYMBOLS`, `LOT_SIZES`, `SLUG_MAP`).
- Preserve IST-based timing logic (`ZoneInfo("Asia/Kolkata")`) for market windows and scheduler gates.
- Maintain current API payload shapes; frontend components are tightly coupled to fields like `score`, `signal`, `top_picks`, `iv_rank`.
- Continue async throttling pattern (`asyncio.Semaphore`) when calling external market APIs.
- DB writes generally happen through thin helpers in `db.py`; avoid ad-hoc SQL in route handlers unless extending `db.py` first.

## Integration boundaries and external dependencies
- Options chain source is INDmoney page scraping (`curl_cffi` + `BeautifulSoup`) in `fetch_nse_chain()`; LTP uses NSE market-watch first, then optional INDstocks token fallback.
- Telegram is optional but wired deeply (`send_telegram_alert`, `send_telegram_document`, pre-market reports in scheduler).
- Frontend-backend integration assumes Vite proxy for `/api` (`frontend/vite.config.js`), but one watchlist save call hardcodes `http://localhost:8000` in `ScannerTab.jsx`.

## Known codebase mismatches to keep in mind
- `README.md` documents endpoints/files that are not currently in `backend/main.py` (for example `/api/historical-backtest`, `/api/position-size`, settings subroutes).
- `frontend/src/components/BacktestTab.jsx` calls `/api/historical-backtest`, which is not implemented in `backend/main.py`.
- `ScannerTab.jsx` posts to `/api/tracker/snapshot/manual`, but only snapshot read/report/export routes are defined in backend.
- There are two separate backtest paths (`backend/backtest.py` API-driven replay and `backend/backtest_runner.py` EOD SQLite engine); pick one before extending.

## High-value files to read before edits
- `backend/main.py`, `backend/scheduler.py`, `backend/db.py`
- `backend/analytics.py`, `backend/signals.py`, `backend/data_source.py`
- `frontend/src/App.jsx`, `frontend/src/components/ScannerTab.jsx`, `frontend/src/components/SettingsTab.jsx`
- `start.sh`, `pyproject.toml`, `backend/requirements.txt`, `frontend/vite.config.js`

