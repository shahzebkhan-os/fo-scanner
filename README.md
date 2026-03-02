# 📈 NSE F&O Option Chain Scanner

A local Python backend that scans all NSE F&O stocks in real time, scores every option strike, and surfaces the best CE/PE opportunities ranked by a multi-factor signal model.

> ⚠️ **For educational purposes only. Not financial advice.**

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install fastapi uvicorn httpx

# 2. Set your IndStocks token
export INDSTOCKS_TOKEN=your_token_here

# 3. Start the backend
python main.py

# 4. Test it (during market hours)
curl http://localhost:8000/api/debug/NIFTY
```

**Market Hours:** Monday–Friday, 9:15 AM – 3:30 PM IST  
All endpoints return a `market_status` field so you always know if the data is live.

---

## 📡 API Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Backend status + market hours |
| `GET /api/market-status` | Current IST time and market open/close |
| `GET /api/scan` | Scan all F&O stocks, ranked by score |
| `GET /api/chain/{SYMBOL}` | Full option chain for a stock |
| `GET /api/chain/{SYMBOL}?expiry=06-Mar-2025` | Chain filtered by expiry |
| `GET /api/top-picks` | Best single option pick across all stocks |
| `GET /api/debug/{SYMBOL}` | Diagnose NSE connection for one symbol |
| `GET /docs` | Interactive API explorer |

---

## 🧠 How Stocks Are Scored

Every F&O stock gets a **Stock Score (0–100)** computed from its full option chain. Here is exactly how it works.

### Step 1 — Fetch the Full Chain from NSE

For each stock, the scanner fetches the complete option chain from NSE's API. This gives us all strikes across all expiries with OI, volume, IV, and change data for both CE and PE sides.

### Step 2 — Compute Four Factors

---

#### Factor 1: PCR (Put-Call Ratio) — max 20 pts

```
PCR = Total PE Open Interest / Total CE Open Interest
```

PCR is used as a **contrarian indicator**:

| PCR Value | Crowd Sentiment | Signal | Points |
|---|---|---|---|
| > 1.5 | Too many puts — crowd overly bearish | 🟢 BULLISH | 20 pts |
| 0.7 – 1.5 | Balanced — no clear edge | 🟡 NEUTRAL | 5 pts |
| < 0.7 | Too many calls — crowd overly bullish | 🔴 BEARISH | 15 pts |

> **Why contrarian?** When too many traders are positioned one way, the market tends to move against them. High PCR = bears are crowded = fuel for a squeeze upward.

---

#### Factor 2: OI Change % — max 25 pts

```
OI Change % = (Change in OI / Open Interest) × 100
Averaged across all strikes and both CE + PE sides
```

Rising open interest means new money is entering the market — this confirms the strength of the current trend.

```
Score = min(25, |avg OI Change %| × 2)
```

| OI Change | Meaning | Score |
|---|---|---|
| High positive change | New positions being built | Up to 25 pts |
| Flat | No new conviction | ~5 pts |
| Falling OI | Positions being closed — weak signal | Near 0 pts |

---

#### Factor 3: Volume/OI Ratio (Vol Spike) — max 20 pts

```
Vol Spike = (Total CE Volume + Total PE Volume) / (Total CE OI + Total PE OI)
Capped at 10×
```

This ratio measures how actively the chain is being traded relative to existing positions. A spike means institutional players are making large moves today.

```
Score = min(20, Vol Spike × 20)
```

| Ratio | Meaning | Score |
|---|---|---|
| > 1.0 | Volume exceeds open interest — very active | High |
| 0.3 – 1.0 | Normal activity | Medium |
| < 0.1 | Quiet — low conviction | Low |

---

#### Factor 4: ATM Implied Volatility — max 15 pts

The IV of the ATM strike is used as a measure of option cheapness.

| ATM IV | Meaning | Score |
|---|---|---|
| 15% – 25% | Cheap options — ideal entry | 15 pts |
| 25% – 50% | Moderate — acceptable | 10 pts |
| > 50% | Expensive — high risk | 5 pts |
| < 15% | Suspiciously low — possibly stale data | 10 pts |

---

#### Final Stock Score Formula

```
Stock Score = PCR Score + OI Change Score + Vol Score + IV Score
              (Capped at 100)
```

Stocks with **Score ≥ 70** are considered strong signals worth deeper analysis.

---

## 🎯 How Top Picks Are Selected

Once stocks are ranked, the scanner selects the best individual option strike to trade using a separate **Strike Score (0–100)**.

### Strike Scoring — 4 Components

---

#### Component 1: OI Change % at This Strike — max 30 pts

```
Strike OI Change % = (Change in OI at this strike / OI at this strike) × 100
Score = min(30, OI Change % × 2)
```

Rising OI at a specific strike is the strongest signal — it means smart money is actively building positions there right now.

---

#### Component 2: Volume at This Strike — max 20 pts

```
Score = min(20, Volume / 100,000 × 20)
```

100,000 contracts or more = full score. This filters out illiquid strikes where the bid-ask spread is too wide to trade efficiently.

---

#### Component 3: IV Level at This Strike — max 20 pts

| IV Range | Score | Reasoning |
|---|---|---|
| 15% – 25% | 20 pts | Sweet spot — cheap but real volatility |
| 25% – 40% | 12 pts | Moderate premium |
| 40% – 60% | 6 pts | Expensive |
| > 60% | 2 pts | Very expensive — event risk |
| < 15% | 10 pts | May be stale or illiquid |

---

#### Component 4: ATM Proximity — max 30 pts

```
Strikes Away = |Spot Price − Strike Price| / Strike Interval
Score = max(0, 30 − Strikes Away × 5)
```

The closer the strike to the current spot price, the higher the score. ATM options offer the best combination of delta (directional exposure) and gamma (how fast delta changes).

Strike intervals are dynamically calculated per instrument — not hardcoded:

| Spot Price Range | Interval Used |
|---|---|
| > 40,000 (BANKNIFTY range) | 100 |
| 20,000 – 40,000 (NIFTY range) | 50 |
| 5,000 – 20,000 | 50 |
| 2,000 – 5,000 | 20 |
| 1,000 – 2,000 | 10 |
| < 1,000 | 5 |

---

#### Final Strike Score Formula

```
Strike Score = OI Change Score + Volume Score + IV Score + ATM Proximity Score
               (Capped at 100)
```

---

### The Full Top Picks Pipeline

```
1.  Scan all F&O stocks  →  compute Stock Score for each
2.  Keep stocks with Stock Score ≥ 50
3.  For each qualifying stock, fetch the full option chain
4.  Score every CE and PE strike using the Strike Score formula
5.  Take the top 2 CE and top 2 PE strikes per stock
6.  Sort all picks globally by Strike Score descending
7.  Return the top N picks
```

The result is a ranked list of the most actionable options across the entire F&O universe, updated every time you call the API.

---

## 📊 Reading the Results

### Scanner Response (`/api/scan`)

```json
{
  "symbol":     "RELIANCE",
  "ltp":        1432.50,
  "signal":     "BULLISH",
  "pcr":        1.82,
  "iv":         18.4,
  "oi_change":  6.3,
  "vol_spike":  0.74,
  "score":      78
}
```

| Field | What it means |
|---|---|
| `signal` | BULLISH / BEARISH / NEUTRAL — derived from PCR (contrarian) |
| `pcr` | Put-Call Ratio — above 1.5 triggers BULLISH signal |
| `iv` | ATM implied volatility % |
| `oi_change` | Average OI change % across all strikes |
| `vol_spike` | Volume-to-OI ratio — higher means more institutional activity |
| `score` | Overall stock signal strength 0–100 |

---

### Chain Response — Top Pick (`/api/chain/{SYMBOL}`)

```json
{
  "type":        "CE",
  "strike":      1440,
  "ltp":         28.50,
  "iv":          19.2,
  "oi_chg_pct":  12.4,
  "volume":      185000,
  "score":       84
}
```

| Field | What it means |
|---|---|
| `type` | CE (Call Option) or PE (Put Option) |
| `strike` | The strike price |
| `ltp` | Last traded price of this option |
| `iv` | Implied volatility at this specific strike |
| `oi_chg_pct` | OI change % at this strike — the key signal |
| `volume` | Contracts traded today at this strike |
| `score` | Strike signal strength 0–100 |

---

## 🔒 Security

- Never commit your `.env` file or token to git
- Add `.env`, `venv/`, `node_modules/` to `.gitignore`
- Regenerate your IndStocks token at [indstocks.com/app/api-trading](https://indstocks.com/app/api-trading) if it is ever exposed

---

## ⚙️ Environment Variables

| Variable | Description |
|---|---|
| `INDSTOCKS_TOKEN` | Your IndStocks JWT token for live LTP data |

---

## 🐛 Troubleshooting

**`strike_count: 0` on debug endpoint**  
NSE returns empty data outside market hours (9:15 AM – 3:30 PM IST, Mon–Fri). This is expected.

**`403` errors in logs**  
NSE's Akamai bot protection blocked the session. The scanner auto-refreshes cookies on 403. If it persists, restart the backend.

**IndStocks `401 Unauthorized`**  
Your token has expired. Regenerate it at indstocks.com.

**`ltp: 0` for all stocks**  
IndStocks token is not set or invalid. LTP automatically falls back to the NSE spot price from the chain data.
