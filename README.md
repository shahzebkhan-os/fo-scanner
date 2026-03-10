# NSE F&O Scanner v4

Full-featured NSE options chain scanner with live signals, Greeks, OI heatmaps, 
sector analysis, unusual activity detection, and paper trading.

---

## What's New in v4

| Feature | File |
|---|---|
| Black-Scholes Greeks (Δ Γ θ V) | `analytics.py` |
| IV Rank (IVR) — 52-week percentile | `analytics.py` + `db.py` |
| OI Heatmap (15-min snapshots) | `scheduler.py` + `db.py` |
| PCR intraday timeline | `signals.py` |
| Unusual Options Activity (UOA) | `signals.py` |
| Straddle / Strangle screener | `signals.py` |
| Sector heatmap (10 sectors) | `signals.py` |
| Pre-market Telegram report (9 AM) | `scheduler.py` |
| NSE Bulk/Block deals | `signals.py` |
| FII/DII data | `new_endpoints.py` |
| Portfolio P&L dashboard + equity curve | `new_endpoints.py` |
| Per-symbol position sizing (2% rule) | `analytics.py` |
| Trade journal notes | `db.py` |
| Settings: capital, watchlist, thresholds | `db.py` |
| CSV export of all trades | `new_endpoints.py` |
| Dark/Light mode toggle | `App.jsx` |
| Keyboard shortcuts | `App.jsx` |
| PWA — install on mobile home screen | `manifest.json` |

---

## Project Structure

```
fo-scanner/
├── backend/
│   ├── main.py          # FastAPI app (existing, updated)
│   ├── analytics.py     # NEW: Greeks, IVR, scoring
│   ├── signals.py       # NEW: UOA, straddle, sector heatmap
│   ├── scheduler.py     # NEW: OI snapshots, pre-market report
│   ├── db.py            # UPDATED: all new tables
│   ├── backtest.py      # (existing)
│   ├── slugs.json       # (existing)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   └── App.jsx      # UPDATED: all 9 tabs
│   ├── public/
│   │   └── manifest.json  # NEW: PWA manifest
│   ├── index.html
│   └── package.json
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

---

## Setup

### 1. Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
INDSTOCKS_TOKEN=your_token_here
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 2. Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

New dependencies needed:
```
httpx
fastapi
uvicorn
curl_cffi
beautifulsoup4
python-dotenv
```

### 3. Install Frontend Dependencies

```bash
cd frontend
npm install
npm run build
```

### 4. Run

```bash
# Development
cd backend && python main.py

# Production
docker-compose up -d
```

### 5. Integrate New Files into main.py

Follow the instructions at the top of `new_endpoints.py`:

1. Add imports at the top of `main.py`
2. Replace `@app.on_event("startup")` with the lifespan context manager
3. Add the `_internal_scan()` helper function
4. Paste all routes from `new_endpoints.py` into `main.py`

### 6. Enable PWA on Mobile

Add to your `frontend/index.html` `<head>`:
```html
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#6366f1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
```

---

## API Reference

All new endpoints:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/greeks/{symbol}` | Full Greeks table for all strikes |
| GET | `/api/ivrank/{symbol}` | IV Rank (52-week percentile) |
| GET | `/api/oi-heatmap/{symbol}` | OI snapshots by strike (today) |
| GET | `/api/oi-timeline/{symbol}` | OI over time for one strike |
| GET | `/api/pcr-history/{symbol}` | Intraday PCR timeline |
| GET | `/api/uoa` | Unusual options activity scan |
| GET | `/api/straddle-screen` | Straddle/strangle candidates |
| GET | `/api/sector-heatmap` | Sector-level signal aggregation |
| GET | `/api/portfolio` | P&L dashboard + equity curve |
| GET | `/api/position-size` | Position sizing calculator |
| GET | `/api/bulk-deals` | NSE bulk/block deals |
| POST | `/api/bulk-deals/refresh` | Force refresh deals |
| GET | `/api/fii-dii` | FII/DII activity from NSE |
| GET | `/api/paper-trades/export` | CSV export |
| POST | `/api/paper-trades/{id}/note` | Add journal note |
| GET | `/api/paper-trades/{id}/notes` | Get journal notes |
| GET | `/api/settings/watchlist` | Get watchlist |
| POST | `/api/settings/watchlist` | Update watchlist |
| GET | `/api/settings/capital` | Get capital setting |
| POST | `/api/settings/capital` | Set capital |
| GET | `/api/settings/threshold/{symbol}` | Get alert threshold |
| POST | `/api/settings/threshold/{symbol}` | Set alert threshold |

---

## Notes

- **IVR** requires at least 30 days of history to be meaningful. Keep the scanner running daily.
- **UOA** requires at least 5 days of OI history to establish baselines.
- **OI Heatmap** data is only recorded during market hours (9:15–15:30 IST).
- **Pre-market report** fires at 9:00 AM IST on weekdays if `TELEGRAM_BOT_TOKEN` is set.
- **Bulk deals** are fetched daily at 4:00 PM IST from NSE's public API.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `R` | Scanner |
| `C` | Chain |
| `G` | Greeks |
| `H` | OI Heatmap |
| `S` | Sectors |
| `U` | UOA |
| `P` | Portfolio |
| `,` | Settings |