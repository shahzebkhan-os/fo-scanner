# 📈 NSE F&O Option Chain Algorithmic Scanner

A powerful, full-stack algorithmic trading dashboard for the National Stock Exchange (NSE). It continuously scans the options chain of all 180+ F&O stocks and indices in real time, applies a proprietary scoring model to identify high-probability breakout trades, executes active paper-trades using a background engine, provides native historical backtesting capabilities, and routes high-confidence signals directly to a Telegram bot and browser alerts.

> ⚠️ **For educational purposes only. Not financial advice. Paper trading is simulated.**

---

## 🚀 Key Features

*   **Real-Time Algorithmic Scanner:** Fetches live chain data directly from the NSE API to rank the strength of every single Strike Price based on Put-Call Ratio (PCR), Open Interest (OI) changes, Volume spikes, and ATM Implied Volatility (IV).
*   **Active DB Algo Trades (Paper Trading):** Background Python loops automatically "buy" and "sell" Top Picks matching specific algorithmic thresholds, enforcing strict Take Profit (TP) and Stop Loss (SL) risk management, storing the results in SQLite.
*   **Live Tracked Picks:** A manual watchlist table where users can actively track manual picks. Updates real-time prices for PnL tracking and formats monetary returns correctly against NSE lot sizes.
*   **Historical Backtester:** Replays the algorithmic score history to simulate trading sessions across varying TP/SL/Score conditions, reporting exact Win Rates, Net PnL, Profit Factors, and charting the exit reasons.
*   **Audio & Visual Alerts:** Emits immediate visual HTML5 Toasts and a high-pitched ring when the scanner locates a `Score >= 70`.
*   **Telegram Integration:** Directly dispatches push notifications containing actionable breakdown setups to your phone seamlessly in the background.

---

## 🏗️ System Architecture: What Each File Does

The software operates via a decoupled architecture featuring a FastAPI Python Backend and a React JS Frontend.

### Backend Application
*   **`backend/main.py`**: The core heartbeat of the application. It runs the FastAPI server to serve static assets and APIs. It manages background asynchronous loops to fetch NSE data, calculates the Option Scores using statistical analysis (combining PCR, Volume, OI, and IV), runs the automated Paper Trade auto-exiting loop, and manages the Telegram HTTP hooks.
*   **`backend/db.py`**: The SQLite database driver. Manages the `trades.db` files. Contains logical functions to `add_trade`, update Live Tracked options, compute abstract PnL, and transition trades from `OPEN` to `CLOSED`.
*   **`backend/Backtest.py`**: The mathematical simulation engine. Reads historical data to test various user-input strategies (like strict `%` Stop-Loss). Computes and aggregates the total system PnL, Win Rates, and Loss Rates into a digestible JSON array for the React visualizer.

### Utility Scripts
*   **`fetch_lot_sizes.py`**: Connects to the AngelOne OpenAPIScripMaster to download the authoritative absolute truth array of all current NSE Lot Sizes (since the Exchange often crashes or expands lot boundaries), writing them directly into the Python matrices.
*   **`backfill_db.py`**: A database operation script to correct historical log flaws or recalculate old PnL histories if lot-sizes/scores change retrospectively.
*   **`start.sh`**: The orchestrator script. Safely kills old hung processes, boots the Python Uvicorn engine, and simultaneously starts the Vite React frontend so the application binds seamlessly for the user.

### Frontend Application
*   **`frontend/src/App.jsx`**: A React application built with Vite containing sophisticated tables, data visualizations, routing elements, sorting functions, Audio alerts, and floating HTML DOM notifications dynamically updating as the backend scans.

---

## 🧠 Algorithmic Scoring Logic

Every F&O asset gets an intrinsic **Score (0–100)** calculated during every iteration. 

### Step 1: The Global Signal (Stock Level)
Before targeting specific strikes, the system grades the *entire* stock option chain:
1.  **Volume Spike:** Is the total chain volume massively spiking compared to existing Open Interest? High volume relative to OI means institutional movement.
2.  **PCR (Put-Call Ratio):** A contrarian indicator. If the crowd is massively loading puts (PCR > 1.3), it often indicates a potential Short Squeeze upwards (Bullish). If heavily loaded into Calls (PCR < 0.8), it acts as gravity downwards (Bearish).
3.  **ATM IV Levels:** IV operates as the 'premium cost'. 15-25% indicates cheap, healthy pricing. Extremely high IVs (>50%) severely penalize the score because premiums become aggressively prone to crushing.
4.  **Overall OI Change:** Averaging Open Interest additions flags new money committing to directional bets.

### Step 2: Individual Strike Scoring (Contract Level)
If the Stock scores over 50, the algorithm ranks every single CE/PE strike price inside that chain up to 100 points:
*   **Strike OI Change (Max 30pts):** Massive explosion of OI at *one exact strike* defines breakout positioning.
*   **Proximity to Money (Max 30pts):** The closer a strike is to At-The-Money (ATM), the safer and more delta-responsive it is. Deep OTM contracts are harshly docked.
*   **Contract Volume (Max 20pts):** Discards illiquid chains with wide bid-ask spreads.
*   **Strike IV (Max 20pts):** Rewards contracts priced fairly relative to implied decay.

The system snags the highest sorted options and forwards them to the Telegram hook and Paper Database as **"Top Picks"**.

---

## 💻 Installation & Quick Start

```bash
# 1. Clone & Enter the folder
cd fo-scanner

# 2. Add your environment variables to a `.env` in the root backend
## (See Environment Variables below)
cp .env.example .env

# 3. Boot the full application Stack (React + Python + DB)
./start.sh
```

**Market Hours:** Monday–Friday, 9:15 AM – 3:30 PM IST  
Once active, navigate your browser to `http://localhost:5175`.

---

## ⚙️ Environment Variables (`.env`)

For the application to function perfectly, configure these keys inside a `.env` file within your folder.

| Variable | Description |
|---|---|
| `INDSTOCKS_TOKEN` | (Optional but recommended) Your IndStocks JWT for real-time underlying Spot LTP fetching fallback. |
| `TELEGRAM_BOT_TOKEN` | Generated natively via `@BotFather` on Telegram. The bot token authorizing the notification pipeline. |
| `TELEGRAM_CHAT_ID` | Your personal or group chat destination ID where the Python engine formats the >70 Score setups. |

---

## 🔒 Limitations & Security
*   **SQLite DB Persistence:** The entire database sits as a simple local `trades.db` file. No cloud required. Keep backups if using it heavily over months.
*   **Akamai Anti-Bot Handling:** The NSE applies extreme throttling on scraping its Option Chains. `main.py` utilizes `curl_cffi` to mimic Chrome TLS fingerprints to circumvent basic scraping bans, rotating headers constantly. Overuse (e.g. infinite loops under 1 second apart) can lead to temporary IP blocks.