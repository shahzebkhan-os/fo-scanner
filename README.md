<div align="center">

# NSE F&O Scanner v4

[![CI](https://github.com/shahzebkhan-os/fo-scanner/workflows/CI/badge.svg)](https://github.com/shahzebkhan-os/fo-scanner/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React 19](https://img.shields.io/badge/react-19-blue.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Full-featured NSE options chain scanner with live signals, Greeks calculation, OI heatmaps, sector analysis, unusual activity detection, and paper trading.**

[Features](#-features) • [Quick Start](#-quick-start) • [Documentation](#-documentation) • [API Reference](#-api-reference) • [Contributing](#-contributing)

</div>

---

## 📋 Table of Contents

- [Features](#-features)
- [What's New in v4](#-whats-new-in-v4)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Setup Guide](#-setup-guide)
- [API Reference](#-api-reference)
- [Keyboard Shortcuts](#-keyboard-shortcuts)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [Security](#-security)
- [License](#-license)

## ✨ Features

<table>
<tr>
<td width="50%">

### 📊 Real-Time Analysis
- Live NSE option chain data
- Black-Scholes Greeks (Δ, Γ, θ, V)
- IV Rank (52-week percentile)
- PCR intraday timeline
- OI heatmap with 15-min snapshots

</td>
<td width="50%">

### 🎯 Trading Tools
- Automated paper trading
- Position sizing calculator (2% rule)
- Stop-loss & take-profit automation
- Trade journal with notes
- P&L dashboard & equity curve

</td>
</tr>
<tr>
<td>

### 🔍 Advanced Scanning
- Unusual Options Activity (UOA)
- Straddle/Strangle screener
- Sector heatmap (10 sectors)
- NSE Bulk/Block deals
- FII/DII activity tracking

</td>
<td>

### 🚀 Modern Features
- PWA support (install on mobile)
- Dark/Light mode toggle
- Keyboard shortcuts
- Telegram alerts & reports
- Historical backtesting engine

</td>
</tr>
</table>

## 🆕 What's New in v4

| Feature | Description | File |
|---------|-------------|------|
| **Greeks Calculation** | Black-Scholes Δ, Γ, θ, V for all strikes | `analytics.py` |
| **IV Rank** | 52-week implied volatility percentile | `analytics.py` + `db.py` |
| **OI Heatmap** | 15-minute OI snapshots by strike | `scheduler.py` + `db.py` |
| **UOA Detection** | Unusual options activity scanner | `signals.py` |
| **Sector Analysis** | 10-sector aggregated signals | `signals.py` |
| **Telegram Reports** | Pre-market reports at 9 AM IST | `scheduler.py` |
| **Historical Backtester** | Test strategies on EOD data | `backtest_runner.py` |
| **Portfolio Dashboard** | P&L tracking with equity curve | Frontend |
| **PWA Support** | Install as mobile app | `manifest.json` |

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (optional)

### One-Command Setup

```bash
# Clone the repository
git clone https://github.com/shahzebkhan-os/fo-scanner.git
cd fo-scanner

# Copy environment variables
cp .env.example .env
# Edit .env with your credentials

# Run with startup script
./start.sh
```

**Access:**
- 🌐 Frontend: http://localhost:5175
- ⚡ Backend API: http://localhost:8000
- 📚 API Docs: http://localhost:8000/docs

### Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## 📁 Project Structure

```
fo-scanner/
├── backend/                 # Python FastAPI backend
│   ├── main.py             # Main FastAPI application
│   ├── analytics.py        # Greeks, IVR, scoring algorithms
│   ├── signals.py          # UOA, straddle, sector analysis
│   ├── scheduler.py        # Background tasks, OI snapshots
│   ├── db.py               # SQLite database operations
│   ├── backtest.py         # Backtesting core logic
│   ├── backtest_runner.py  # Backtest CLI interface
│   ├── historical_loader.py # Historical data ingestion
│   └── requirements.txt    # Python dependencies
├── frontend/               # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx        # Main React application
│   │   └── main.jsx       # Entry point
│   ├── public/            # Static assets
│   ├── package.json       # Node dependencies
│   └── vite.config.js     # Vite configuration
├── .github/               # GitHub Actions workflows
│   └── workflows/
│       └── ci.yml         # CI/CD pipeline
├── docker-compose.yml     # Docker orchestration
├── Dockerfile             # Multi-stage Docker build
├── pyproject.toml         # Python project config
├── .pre-commit-config.yaml # Pre-commit hooks
├── CONTRIBUTING.md        # Contribution guidelines
├── SECURITY.md            # Security policy
└── README.md              # This file
```

## 🔧 Setup Guide

### 1. Environment Variables

Create a `.env` file in the root directory:

```env
# INDmoney API Token (for live LTP updates)
INDSTOCKS_TOKEN="your_token_here"

# Telegram Configuration (optional)
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_chat_id"
```

**Getting Credentials:**
- **INDSTOCKS_TOKEN**: Sign up at [INDstocks API](https://api.indstocks.com/)
- **Telegram**: Message [@BotFather](https://t.me/BotFather) to create a bot
- **Chat ID**: Message [@userinfobot](https://t.me/userinfobot) to get your ID

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python -c "import db; db.init_db()"
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build

# Or run dev server
npm run dev
```

### 4. Running the Application

**Option A: Using startup script** (recommended)
```bash
./start.sh
```

**Option B: Manual start**
```bash
# Terminal 1 - Backend
cd backend
python main.py

# Terminal 2 - Frontend
cd frontend
npm run dev -- --port 5175
```

**Option C: Docker**
```bash
docker-compose up -d
```

## 📡 API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/greeks/{symbol}` | Black-Scholes Greeks for all strikes |
| `GET` | `/api/ivrank/{symbol}` | IV Rank (52-week percentile) |
| `GET` | `/api/oi-heatmap/{symbol}` | OI snapshots by strike (today) |
| `GET` | `/api/oi-timeline/{symbol}` | OI time series for one strike |
| `GET` | `/api/pcr-history/{symbol}` | Intraday PCR timeline |

### Signal Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/uoa` | Unusual options activity scan |
| `GET` | `/api/straddle-screen` | Straddle/strangle candidates |
| `GET` | `/api/sector-heatmap` | Sector-level aggregation |
| `GET` | `/api/bulk-deals` | NSE bulk/block deals |
| `GET` | `/api/fii-dii` | FII/DII activity data |

### Trading Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/portfolio` | P&L dashboard + equity curve |
| `GET` | `/api/position-size` | Position sizing calculator |
| `GET` | `/api/paper-trades/export` | CSV export of all trades |
| `POST` | `/api/paper-trades/{id}/note` | Add journal note |
| `GET` | `/api/paper-trades/{id}/notes` | Get trade notes |

### Settings Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET/POST` | `/api/settings/watchlist` | Manage watchlist |
| `GET/POST` | `/api/settings/capital` | Set trading capital |
| `GET/POST` | `/api/settings/threshold/{symbol}` | Alert thresholds |

**Interactive API Documentation:** http://localhost:8000/docs

## ⌨️ Keyboard Shortcuts

| Key | Action | Description |
|-----|--------|-------------|
| `R` | Scanner | Real-time options scanner |
| `C` | Chain | Full option chain view |
| `G` | Greeks | Greeks calculation table |
| `H` | Heatmap | OI heatmap visualization |
| `S` | Sectors | Sector analysis dashboard |
| `U` | UOA | Unusual options activity |
| `P` | Portfolio | P&L and trade history |
| `,` | Settings | Application settings |

## 📚 Documentation

- **[README2.md](README2.md)** - Trade scoring & selection logic deep-dive
- **[README_BACKTESTING.md](README_BACKTESTING.md)** - Historical backtesting guide
- **[PROJECT_IMPROVEMENTS.md](PROJECT_IMPROVEMENTS.md)** - Recommended improvements
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines
- **[SECURITY.md](SECURITY.md)** - Security policy & best practices

### Backtesting

Load historical data and test your strategies:

```bash
# Download and process historical data
python backend/historical_loader.py full --start 2024-01-01

# Run backtest with default parameters
python backend/backtest_runner.py

# Optimize parameters with grid search
python backend/backtest_runner.py --optimise

# Test specific strategy
python backend/backtest_runner.py --score 85 --signal BULLISH
```

See [README_BACKTESTING.md](README_BACKTESTING.md) for detailed documentation.

## 📝 Important Notes

- **IV Rank**: Requires 30+ days of history for accurate percentiles
- **UOA Detection**: Needs 5+ days of OI data for baseline establishment
- **OI Heatmap**: Data recorded only during market hours (9:15-15:30 IST)
- **Pre-market Reports**: Sent at 9:00 AM IST if Telegram is configured
- **Bulk Deals**: Fetched daily at 4:00 PM IST from NSE API

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

**Quick Start for Contributors:**

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Install development dependencies
pip install black isort pylint pytest
cd frontend && npm install --save-dev eslint prettier

# Run code quality checks
black backend/
isort backend/
pylint backend/*.py
cd frontend && npm run lint
```

### Areas We Need Help With

- 🧪 Writing tests (unit, integration, e2e)
- 📱 Mobile UI improvements
- 🔒 Security enhancements (authentication, rate limiting)
- 📊 Additional technical indicators
- 🌐 Internationalization (i18n)
- 📖 Documentation improvements

## 🔒 Security

Found a security vulnerability? Please see our [Security Policy](SECURITY.md) for responsible disclosure guidelines.

**Never commit:**
- Your `.env` file
- API tokens or credentials
- Database files (`*.db`)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- NSE for providing public market data
- [FastAPI](https://fastapi.tiangolo.com/) for the excellent web framework
- [React](https://react.dev/) and [Vite](https://vitejs.dev/) for the frontend
- [Recharts](https://recharts.org/) for beautiful visualizations

## 📞 Support

- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/shahzebkhan-os/fo-scanner/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/shahzebkhan-os/fo-scanner/discussions)
- 📧 **Security**: See [SECURITY.md](SECURITY.md)

---

<div align="center">

**Built with ❤️ for the trading community**

[⭐ Star this repo](https://github.com/shahzebkhan-os/fo-scanner) • [🐛 Report Bug](https://github.com/shahzebkhan-os/fo-scanner/issues) • [✨ Request Feature](https://github.com/shahzebkhan-os/fo-scanner/issues)

</div>
