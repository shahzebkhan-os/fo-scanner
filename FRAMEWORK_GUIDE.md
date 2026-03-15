<div align="center">

# 🧭 How the F&O Scanner Works — A Simple Guide

**Written for everyone — no coding knowledge needed!**

</div>

---

## 📖 Table of Contents

- [What Is This App?](#-what-is-this-app)
- [How It Starts](#-how-it-starts)
- [Where Does the Data Come From?](#-where-does-the-data-come-from)
- [How the App Processes the Data](#-how-the-app-processes-the-data)
- [Tabs Explained — What You See on Screen](#-tabs-explained--what-you-see-on-screen)
  - [Scanner Tab](#1--scanner-tab--the-main-dashboard)
  - [Suggestions Tab](#2--suggestions-tab--trade-ideas)
  - [Paper Trading Tab](#3--paper-trading-tab--practice-trading)
  - [Option Chain Tab](#4--option-chain-tab--all-available-options)
  - [Greeks Tab](#5--greeks-tab--option-sensitivity-numbers)
  - [OI Heatmap Tab](#6--oi-heatmap-tab--where-the-money-is-sitting)
  - [Sectors Tab](#7--sectors-tab--industry-group-overview)
  - [UOA Tab](#8--uoa-tab--unusual-options-activity)
  - [Straddle Tab](#9--straddle-tab--two-way-bets)
  - [ML/NN Tab](#10--mlnn-tab--computer-predictions)
  - [Backtest Tab](#11--backtest-tab--testing-on-past-data)
  - [Settings Tab](#12--settings-tab--your-preferences)
- [What Runs Automatically in the Background](#-what-runs-automatically-in-the-background)
- [The Scoring System — How a Stock Gets Its Number](#-the-scoring-system--how-a-stock-gets-its-number)
- [Paper Trading — How Practice Trades Work](#-paper-trading--how-practice-trades-work)
- [The Full Picture — Start to Finish](#-the-full-picture--start-to-finish)

---

## 🏠 What Is This App?

Imagine you're at a busy vegetable market. There are hundreds of stalls (stocks), each selling different items (options), and the prices keep changing every second. It would be impossible for one person to watch all the stalls and figure out which ones are the best deals.

**This app does exactly that — but for the stock market.**

It watches **85+ stocks** on India's National Stock Exchange (NSE), looks at their options (financial contracts that let you bet on whether a stock will go up or down), and tells you:

- **Which stocks are showing the strongest signals** (bullish = likely going up, bearish = likely going down)
- **A score from 0 to 100** for each stock, so you can quickly compare them
- **Which specific options contracts look best** to consider
- **Alerts for unusual activity** that might signal big moves

Think of it as a **smart assistant** that watches the market for you and highlights what deserves your attention.

---

## 🚀 How It Starts

When you run the app (using the `./start.sh` command or Docker), two main parts start working:

### The Backend (The Brain) — Port 8000

This is the **invisible engine** running behind the scenes. It:
1. **Creates a database** (a filing cabinet) to store all the data it collects
2. **Starts background watchers** that automatically track the market
3. **Opens an API** (a communication channel) so the screen can ask it for data
4. **Begins a paper trade manager** that babysits any practice trades you've made

### The Frontend (The Screen) — Port 5175

This is **what you see** — the website with all the tabs, charts, and tables. It:
1. Opens in your web browser at `http://localhost:5175`
2. Talks to the backend every 1–2 minutes to get fresh data
3. Shows you everything in a nice, visual format

**Analogy:** Think of it like a restaurant. The **kitchen** (backend) prepares all the food, while the **dining area** (frontend) is where you sit, see the menu, and eat.

---

## 📡 Where Does the Data Come From?

The app pulls data from **three main sources**, all publicly available:

### 1. INDmoney Website (Live Options Data)

This is the **primary source** for live options chain data. For each of the 85+ stocks, the app visits the INDmoney options page and reads:
- All available strike prices and their premiums (prices)
- Open Interest (OI) — how many contracts are currently active
- Volume — how many contracts traded today
- Implied Volatility (IV) — the market's expectation of how much the stock will move

**Analogy:** It's like automatically checking the prices on 85 different shopping websites every few minutes.

### 2. Yahoo Finance (Global Market Data)

To understand the bigger picture, the app checks global markets:
- **S&P 500** and **NASDAQ** (US stock markets) — are they up or down?
- **Dollar Index (DXY)** — is the US dollar getting stronger or weaker?
- **Crude Oil** prices — affects energy stocks
- **USD/INR** exchange rate — affects Indian markets
- **CBOE VIX** — the global "fear gauge"

**Why?** If US markets crashed overnight, Indian markets are likely to open lower too. The app factors this in.

### 3. NSE (National Stock Exchange)

For specific data like:
- Bulk and block deals (when someone buys or sells a huge quantity)
- Latest stock prices
- Historical data for backtesting

---

## ⚙️ How the App Processes the Data

Once the raw data arrives, it goes through a **processing pipeline** — like an assembly line in a factory:

### Step 1: Calculate the Math (Analytics)

The raw option prices are fed into formulas that calculate:
- **Greeks** (Delta, Gamma, Theta, Vega) — these tell you how sensitive an option is to various changes
- **IV Rank** — where today's volatility sits compared to the last year (0% = very calm, 100% = very wild)
- **Put-Call Ratio (PCR)** — are more people betting on the stock going down (puts) or up (calls)?
- **Max Pain** — the price where most option writers would lose the least money

### Step 2: Generate Signals

The calculated numbers are checked for patterns:
- Is there **unusual activity** on certain strikes? (Someone might know something)
- Is the **OI building up** on the call side or put side? (Directional clue)
- What's the **market regime**? Is the stock trending, stuck in a range, or under pressure?
- What are **global markets** suggesting?

### Step 3: Score Each Stock (0–100)

All the signals are combined into a single **score** for each stock:
- **80–100**: Very strong signal — worth looking at closely
- **60–79**: Moderate signal — could be interesting
- **40–59**: Neutral — no clear direction
- **0–39**: Weak — probably best to stay away

The app also labels each stock as **BULLISH** (likely going up), **BEARISH** (likely going down), or **NEUTRAL** (unclear).

### Step 4: Pick the Best Options

For the top-scoring stocks, the app suggests the **best option contracts** to consider — looking for the best combination of:
- Being close to the current stock price (ATM = at the money)
- Having good trading volume (easy to buy and sell)
- Having favorable risk-reward

### Step 5: ML Prediction (Optional)

If the machine learning models are trained, they add a **computer prediction**:
- One model looks at the **current numbers** (LightGBM)
- Another model looks at **recent history patterns** (LSTM Neural Network)
- They combine (60% current + 40% historical) to predict the probability of the stock going up

---

## 🖥️ Tabs Explained — What You See on Screen

### 1. 📊 Scanner Tab — The Main Dashboard

**What it does:** This is the **home screen**. It scans all 85+ stocks and shows them ranked by score.

**What you see:**
- A **table** with every stock, showing its score (0–100), signal (BULLISH/BEARISH/NEUTRAL), and key numbers
- The **top picks** — the best option contracts the app recommends for each stock
- **Color coding** — green for bullish, red for bearish, grey for neutral
- A **score dial** that visually shows how strong each signal is

**How it works behind the scenes:**
1. Every 1–2 minutes, the frontend asks the backend: "Scan all stocks for me"
2. The backend fetches live data from INDmoney for each stock (in parallel, 8–10 at a time for speed)
3. It runs the full analytics pipeline (Greeks, signals, scoring)
4. Sends back a ranked list

**Auto-refresh:** During market hours (9:15 AM – 3:30 PM IST, Monday–Friday), it refreshes automatically. Outside market hours, it pauses.

---

### 2. 💡 Suggestions Tab — Trade Ideas

**What it does:** Goes one step further than the Scanner — it doesn't just tell you which stocks look good, it tells you **exactly what trade to consider**.

**What you see:**
- Trade **strategy recommendations** (e.g., "Buy Call Option", "Bull Call Spread", "Iron Condor")
- **Entry price** — what price to buy at
- **Target price** — where to take profits
- **Stop loss** — where to exit if the trade goes wrong
- **Risk-reward ratio** — how much you could gain vs. how much you could lose

**How it picks strategies:**
- If a stock is **strongly bullish + low volatility** → Buy a Call Option (simple directional bet)
- If a stock is **bullish + high volatility** → Use a Spread (limits your risk)
- If a stock is **neutral + high volatility** → Sell premium strategies like Iron Condor
- And more combinations based on the market conditions

**One-click trading:** You can click any suggestion to instantly open it as a paper (practice) trade.

---

### 3. 📝 Paper Trading Tab — Practice Trading

**What it does:** Lets you **practice trading with fake money** so you can test your skills without any financial risk.

**What you see:**
- All your **open trades** with live P&L (profit & loss) updating in real time
- **Closed trades** with their final results
- **Statistics** — win rate, average profit, total returns
- **Trade journal** — you can add notes to any trade ("entered because IV was low", etc.)
- **Export button** — download all your trade data as a CSV file

**How it works:**
- When you enter a trade, it records the entry price and time
- Every 60 seconds during market hours, the app checks the current price of your option
- It automatically calculates your profit or loss
- If your trade hits the stop loss or target, it closes automatically
- At 3:15 PM IST, all remaining open trades are closed (simulating end-of-day square-off)

---

### 4. 🔗 Option Chain Tab — All Available Options

**What it does:** Shows the complete list of available options for any stock — every strike price with both Call (CE) and Put (PE) options.

**What you see:**
- A **two-sided table**: Calls on the left, Puts on the right
- For each strike price: premium (price), open interest, volume, and implied volatility
- The **ATM** (at the money) strike is highlighted — that's the strike closest to the current stock price

**When to use it:** When you want to dig deeper into a specific stock and see all the options available, not just the top picks.

---

### 5. 📐 Greeks Tab — Option Sensitivity Numbers

**What it does:** Shows the **Greeks** for every option strike of a stock.

**What each Greek means (in plain English):**
- **Delta (Δ):** If the stock moves ₹1, how much does the option price change? (Higher = more responsive)
- **Gamma (Γ):** How fast does Delta change? (Higher = Delta is changing quickly)
- **Theta (θ):** How much value does the option lose each day just from time passing? (Options lose value every day)
- **Vega (V):** If volatility changes by 1%, how much does the option price change?

**When to use it:** Useful for advanced analysis — checking if an option is too expensive, or understanding how it will behave.

---

### 6. 🗺️ OI Heatmap Tab — Where the Money Is Sitting

**What it does:** Shows a visual map of **Open Interest (OI)** across different strike prices over time.

**What it tells you:**
- **Where big players are positioning** — large OI at a specific strike means lots of money is parked there
- **Support and resistance levels** — heavy Put OI = support (floor), heavy Call OI = resistance (ceiling)
- **How OI changed throughout the day** — the app takes snapshots every 15 minutes

**Analogy:** Imagine you can see where everyone in a stadium placed their bets. The strikes with the most bets are likely to act as barriers for the stock price.

---

### 7. 🏭 Sectors Tab — Industry Group Overview

**What it does:** Groups all 85+ stocks into **10 industries** (Banking, IT, Auto, Pharma, Energy, Metal, Finance, Consumer, Capital Goods, Cement) and shows the overall mood of each sector.

**What you see:**
- A **heatmap** showing which sectors are bullish (green), bearish (red), or neutral (grey)
- **Percentage of stocks** in each sector showing bullish signals
- **Top signals** per sector

**Why it's useful:** Sometimes an entire sector is moving together (e.g., all banking stocks going up). This tab helps you spot sector-wide trends at a glance.

---

### 8. 🔍 UOA Tab — Unusual Options Activity

**What it does:** Flags options where the **trading volume is unusually high** compared to the recent average.

**What counts as unusual?** If today's volume on a specific strike is 5× or more than the 5-day average volume, it gets flagged.

**Why it matters:** When someone suddenly buys a huge amount of options on a specific strike, they might have information or conviction about a price move. It could signal an upcoming event or a big bet by an institutional player.

**What you see:**
- Stock name, strike price, option type (Call/Put)
- **Volume ratio** — how many times the normal volume (e.g., 12× means 12 times the usual activity)
- Current price and whether it's in-the-money or out-of-the-money

---

### 9. ⚖️ Straddle Tab — Two-Way Bets

**What it does:** Finds stocks where **selling a straddle** (selling both a Call and a Put at the same strike) could be profitable.

**When this strategy works:** When you think the stock will NOT move much. You collect premium from both sides, and if the stock stays near the strike price, you keep the money.

**What you see:**
- Stocks sorted by how much premium you'd collect
- IV Rank — higher is better for sellers (more premium to collect)
- Maximum potential loss
- PCR ratio for context

---

### 10. 🧠 ML/NN Tab — Computer Predictions

**What it does:** Shows the **machine learning predictions** — the computer's opinion on whether each stock is likely to go up or down.

**How the computer decides:**
1. **LightGBM model** (60% weight) — looks at the current score, volatility, PCR, and market regime
2. **LSTM Neural Network** (40% weight) — looks at patterns over the last 10 time periods

**What you see:**
- Prediction probability (0% = very bearish, 100% = very bullish)
- Whether the models agree or disagree
- Model training status and accuracy metrics
- A button to **retrain** the models with the latest data

**Important:** The models need at least 500 historical data points to train properly. They get better with more data over time.

---

### 11. 🕰️ Backtest Tab — Testing on Past Data

**What it does:** Lets you test how a trading strategy would have **performed in the past**.

**What you enter:**
- Minimum score threshold (e.g., only trade stocks with score > 75)
- Take-profit percentage (e.g., exit when profit reaches 50%)
- Stop-loss percentage (e.g., exit when loss reaches 25%)

**What you get back:**
- Win rate — what percentage of trades would have been profitable
- Total profit/loss
- Maximum drawdown — the biggest dip from peak

**Why it's useful:** Before risking real money, you can see if your criteria would have worked historically.

---

### 12. ⚙️ Settings Tab — Your Preferences

**What it does:** Lets you customize the app to your needs.

**Settings you can change:**
- **Trading capital** — how much money you're working with (used for position sizing)
- **Watchlist** — your favorite stocks to always keep an eye on
- **Alert thresholds** — set custom score thresholds for each stock to get notified
- **Dark/Light mode** — switch the visual theme

---

## 🔄 What Runs Automatically in the Background

Even when you're not looking at the app, the backend is busy working:

| Task | When | What It Does |
|------|------|--------------|
| **OI Snapshots** | Every 15 minutes during market hours | Saves Open Interest data for all stocks (this powers the OI Heatmap) |
| **IV History** | Daily at 3:35 PM | Saves today's volatility number for each stock (this powers IV Rank, which needs historical data) |
| **Pre-Market Report** | Weekdays at 9:00 AM | Scans the top 5 setups and sends a summary to Telegram (if configured) |
| **Bulk Deals** | Weekdays at 4:00 PM | Fetches large institutional deals from NSE |
| **Paper Trade Updates** | Every 60 seconds during market hours | Updates all open practice trades with current prices, checks stop-loss/take-profit levels |
| **ML Retrain** | Daily at 3:45 PM | Retrains the prediction models with the latest market data |
| **Database Cleanup** | Every Sunday at midnight | Removes old data to keep the database small and fast |

---

## 📈 The Scoring System — How a Stock Gets Its Number

When the app scores a stock, it considers **multiple factors** (like a teacher grading an exam with several sections):

| Factor | What It Measures | Weight |
|--------|-----------------|--------|
| **OI Analysis** | Are big players positioning bullishly or bearishly? | High |
| **PCR Ratio** | Put-Call Ratio — more puts (bearish) or calls (bullish)? | High |
| **IV Rank** | Is volatility historically high or low? | Medium |
| **OI Velocity** | Is Open Interest changing fast? (Momentum indicator) | Medium |
| **Market Regime** | Is the stock trending, range-bound, or in squeeze? | Medium |
| **Global Cues** | Are US markets, crude oil, dollar supporting or opposing? | Low (±10 points max) |
| **Buildup Type** | Long buildup? Short covering? Short buildup? | Medium |

The final score (0–100) and direction (BULLISH/BEARISH/NEUTRAL) come from blending all these factors together.

**Example:** A stock might score 85 BULLISH if it has:
- Heavy Call OI building up (+15 points)
- Low PCR ratio (more calls than puts, +10 points)
- Low IV Rank (volatility is cheap, good for buying, +10 points)
- Positive OI velocity (momentum increasing, +10 points)
- Trending regime (+5 points)
- US markets are positive overnight (+8 points from global cues)
- Long buildup pattern (+12 points)
- Other factors contributing the rest

---

## 📄 Paper Trading — How Practice Trades Work

Here's the complete lifecycle of a practice trade:

### 1. Entry

You can enter a trade in three ways:
- **From the Scanner:** Click a top pick to open it as a trade
- **From Suggestions:** One-click to enter a suggested trade
- **Manual:** Type in the stock, strike price, and option type yourself

### 2. While the Trade Is Open

The app **automatically monitors** your trade every 60 seconds:
- Fetches the current price of your option from the live market
- Calculates your running profit or loss
- Checks if the price has hit your stop-loss or take-profit level

### 3. Automatic Exit Triggers

The app uses **smart stop-loss and take-profit levels** that adjust based on the option price:

- **Cheap options** (deep out-of-money): Wider stops — exit at -40% loss or +80% profit
- **Mid-range options**: Medium stops — exit at -25% loss or +50% profit
- **Expensive options** (at the money): Tighter stops — exit at -20% loss or +40% profit
- **Trailing stop**: Once profit reaches +25%, the minimum exit is locked at +10% profit (protects gains)

### 4. End of Day

At **3:15 PM IST**, any trade still open is automatically closed at the current market price, just like real intraday trading.

### 5. Record Keeping

Every trade — open and closed — is saved in the database with full details: entry time, exit time, prices, profit/loss, and the reason for exit (stop-loss hit, target hit, or end-of-day square-off).

---

## 🔄 The Full Picture — Start to Finish

Here's the complete journey from when you start the app to when you see data on screen:

```
1. YOU START THE APP (./start.sh)
   │
   ├─→ Backend starts on port 8000
   │   ├─ Creates database tables (if first time)
   │   ├─ Starts background watchers (OI snapshots, IV history, etc.)
   │   └─ Starts paper trade manager (monitors your practice trades)
   │
   └─→ Frontend starts on port 5175
       └─ Opens in your browser

2. YOU OPEN THE SCANNER TAB
   │
   └─→ Frontend asks backend: "Scan all stocks"
       │
       └─→ Backend fetches live data from INDmoney (8-10 stocks at a time)
           │
           ├─→ For each stock:
           │   ├─ Calculate Greeks (Delta, Gamma, Theta, Vega)
           │   ├─ Calculate IV Rank (needs historical data)
           │   ├─ Detect signals (OI buildup, UOA, regime)
           │   ├─ Score the stock (0-100)
           │   ├─ Pick the best option contracts
           │   └─ Run ML prediction (if models are trained)
           │
           └─→ Send results back to frontend
               │
               └─→ You see the ranked table with scores, signals, and top picks

3. IN THE BACKGROUND (while you browse other tabs)
   │
   ├─ Every 15 min: OI snapshots saved → powers the Heatmap tab
   ├─ Every 60 sec: Paper trades updated with live prices
   ├─ Daily 3:35 PM: IV saved → powers IV Rank over time
   ├─ Daily 3:45 PM: ML models retrained with new data
   └─ Daily 9:00 AM: Pre-market report sent to Telegram

4. YOU ENTER A PAPER TRADE
   │
   └─→ Trade saved in database
       │
       └─→ Paper trade manager monitors it every 60 seconds
           │
           ├─ If profit target hit → Auto-close with profit
           ├─ If stop-loss hit → Auto-close to limit loss
           └─ If 3:15 PM → Auto-close (end of day)
```

---

## 📝 Quick Glossary

| Term | Plain English Meaning |
|------|----------------------|
| **F&O** | Futures and Options — financial contracts based on stocks |
| **CE (Call)** | A bet that the stock price will go UP |
| **PE (Put)** | A bet that the stock price will go DOWN |
| **Strike Price** | The price level at which the option contract is set |
| **OI (Open Interest)** | The total number of active option contracts at a strike |
| **IV (Implied Volatility)** | How much the market expects the stock to move |
| **IV Rank** | Where today's IV sits compared to the past year (0–100%) |
| **PCR (Put-Call Ratio)** | Puts ÷ Calls — above 1 means more bearish bets, below 1 means more bullish |
| **ATM (At The Money)** | Strike price closest to the current stock price |
| **OTM (Out of The Money)** | Calls above or Puts below the current stock price — cheaper but riskier |
| **Greeks** | Numbers that describe how sensitive an option is to various changes |
| **UOA** | Unusual Options Activity — abnormally high trading volume on an option |
| **Straddle** | Buying or selling both a Call and Put at the same strike price |
| **Max Pain** | The stock price where option sellers (writers) lose the least money |
| **GEX** | Gamma Exposure — estimates how much market makers need to buy or sell |
| **Regime** | The current market behavior: Trending, Pinned (range-bound), Squeeze, or Expiry-day |
| **Paper Trade** | A practice trade with no real money at risk |
| **SL (Stop-Loss)** | An automatic exit to limit your losses |
| **TP (Take-Profit)** | An automatic exit to lock in your gains |
| **Backtest** | Testing a strategy on historical data to see how it would have performed |
| **ML/NN** | Machine Learning / Neural Network — computer models that learn patterns from data |

---

<div align="center">

**Questions? Open a [GitHub Issue](https://github.com/shahzebkhan-os/fo-scanner/issues) — we're happy to help!**

</div>
