# README2 — Trade Scoring & Selection Logic (v5)

This document explains how the F&O Scanner identifies, scores, and
auto-selects trades. Three files are involved:

| File | Role |
|------|------|
| `analytics.py` | Scores individual options + computes stock-level signal |
| `main.py` | Applies entry filters and triggers auto paper-trades |
| `scheduler.py` | Monitors open trades for TP/SL exit |

---

## 1. Option Scoring (`score_option` — 0 to 100)

Each CE/PE contract is scored independently. Six components, max 100:

```
25 pts  OI Momentum     Fresh money flowing in
20 pts  V/OI Activity   Real trading vs dead positions
20 pts  ATM Proximity   Near-the-money preferred
15 pts  IV Quality      15-40% sweet spot, IVR adjusted
10 pts  OI Strength     Absolute OI size (institutional)
10 pts  Bid Quality     Not deep OTM / penny option
```

### Scoring Details

**OI Momentum (25 pts)**
- Requires at least 500 OI (filters out illiquid options)
- OI change must be > 5% (no credit for flat positions)
- Formula: `min(25, (oi_pct - 5) * 2)`
- Why: Rising OI = new money entering → stronger conviction

**V/OI Activity (20 pts)**
- Volume-to-OI ratio must exceed 0.3
- Formula: `min(20, (voi - 0.3) * 15)`
- Why: High V/OI = active intraday interest, not stale positions

**ATM Proximity (20 pts)**
- Measured in "intervals away" (e.g., NIFTY = 50pt intervals)
- Full points at ATM, zero at 5+ intervals away
- Formula: `max(0, 1.0 - bands_away / 5.0) * 20`
- Why: ATM options have highest gamma and best risk/reward

**IV Quality (15 pts)**
- Sweet spot: 15-40% IV → full 15 pts
- Below 15% or above 40% → reduced (options too cheap/expensive)
- IVR adjustment: low IVR (<30) = 1.2x bonus, high IVR (>80) = 0.7x penalty
- Why: Cheap IV = better long option entry; expensive = worse

**OI Strength (10 pts)**
- > 100K OI → 10 pts | > 50K → 7 pts | > 10K → 4 pts
- Why: High absolute OI = institutional participation = more reliable levels

**Bid Quality (10 pts)**
- Distance from spot < 5% → 10 pts | < 10% → 5 pts | > 10% → 0
- Requires LTP > 0 (no dead contracts)
- Why: Filters out deep OTM penny options that inflate scores

---

## 2. Stock-Level Signal Direction (Voting System)

After scoring all individual options, the system determines the overall
direction for the stock using a **multi-factor voting system**:

```
Factor                 Max Votes   Direction Rule
─────────────────────  ─────────   ──────────────────────
PCR Extremes           ±3 votes    > 1.5 = strong bullish, < 0.6 = strong bearish
OI Direction Change    ±2 votes    CE building + PE unwinding = bearish
Volume Dominance       ±1 vote     > 65% on one side
Max Pain Bias          ±1 vote     Spot far from Max Pain
```

### PCR (Put-Call Ratio) — Contrarian Indicator
```
PCR > 1.5   → +3 BULLISH  (extreme put writing = support)
PCR > 1.3   → +2 BULLISH  (heavy put writing)
PCR > 1.15  → +1 BULLISH  (mild)
PCR < 0.6   → +3 BEARISH  (extreme call writing = resistance)
PCR < 0.7   → +2 BEARISH  (heavy call writing)
PCR < 0.85  → +1 BEARISH  (mild)
0.85 – 1.15 → NEUTRAL     (dead zone, no vote)
```

### OI Direction — Most Reliable Indicator (+2 weight)
```
CE OI ↑ + PE OI ↓  →  +2 BEARISH  (writers selling calls, covering puts)
PE OI ↑ + CE OI ↓  →  +2 BULLISH  (writers selling puts, covering calls)
Both ↑              →  No vote     (hedging / event play)
```

### Signal Decision
```
If |bullish_votes - bearish_votes| >= 2  →  BULLISH or BEARISH
If margin < 2                           →  NEUTRAL (insufficient conviction)
```

---

## 3. Composite Stock Score (0-100)

Once signal direction is determined, a composite stock-level score is built:

```
25 pts  Activity Score     Volume/OI spike (market interest)
15 pts  OI Momentum Score  Average OI % change across strikes
15 pts  IV Score           ATM IV quality (same 15-40 sweet spot)
30 pts  Signal Score       max(bull_votes, bear_votes) * 10
10 pts  Conviction Bonus   vote_margin * 3 (clear direction)
 5 pts  Max Pain Score     How close spot is to max pain
 5 pts  Expiry Bonus       Nearer expiry = more gamma
```

---

## 4. Auto-Trade Entry Gate (`main.py`)

A trade is only entered automatically when ALL of these pass:

```
✅  Stock score >= 85          (high conviction only)
✅  Signal ≠ NEUTRAL           (clear direction)
✅  Vol spike > 0.5            (active market for symbol)
✅  |PCR - 1| > 0.2            (PCR showing bias, not neutral)
✅  Market is open             (9:15 AM – 3:30 PM IST, Mon-Fri)
✅  Optimal trade time         (see below)
✅  Daily trades < 10          (prevent over-trading)
✅  Sector trades < 3          (prevent concentration risk)
✅  Not already traded today   (dedup by strike+type+date)
✅  Direction match            (BULLISH → CE only, BEARISH → PE only)
```

### Time-of-Day Filter
```
❌  9:15 – 9:30    Opening volatility (fake moves)
✅  9:30 – 12:00   Morning session (best liquidity)
❌  12:00 – 13:00  Lunch lull (low volume, wide spreads)
✅  13:00 – 15:00  Afternoon session
❌  15:00 – 15:30  EOD risk (square-off pressure)
```

---

## 5. Auto Exit Logic (`scheduler.py`)

Runs every 5 minutes. Three exit conditions:

```
✅  P&L >= +25%   →  Take Profit (lock in gains)
❌  P&L <= -15%   →  Stop Loss (cut losses)
🔲  Time >= 15:15 →  EOD Square-off (no overnight risk)
```

LTP is fetched from the live option chain, matching by strike + type.

---

## 6. Trade Lifecycle (End to End)

```
                    ┌─────────────────┐
                    │  NSE Chain Data  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  score_option() │  Score each CE/PE 0-100
                    │  (per contract) │
                    └────────┬────────┘
                             │
                  ┌──────────▼──────────┐
                  │ compute_stock_score()│  PCR/OI/volume voting
                  │  (per symbol)       │  → signal + composite score
                  └──────────┬──────────┘
                             │
              ┌──────────────▼──────────────┐
              │     Auto-Trade Entry Gate    │
              │  score ≥ 85, direction ≠ N,  │
              │  vol spike, PCR bias, time,  │
              │  daily cap, sector cap       │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼────────┐
                    │  Paper Trade DB │
                    │  (OPEN status)  │
                    └────────┬────────┘
                             │
              ┌──────────────▼──────────────┐
              │   Auto TP/SL Monitor Loop   │
              │  Every 5 min:               │
              │  +25% → exit | -15% → exit  │
              │  15:15 → EOD square-off     │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼────────┐
                    │  CLOSED trade   │
                    │  with P&L + reason │
                    └─────────────────┘
```

---

## Key Design Principles

1. **Accuracy > Volume** — Strict 85+ threshold means fewer but better trades
2. **Multi-factor confirmation** — No single indicator triggers entry
3. **Contrarian PCR** — Extreme put writing = bullish floor, not bearish
4. **Minimum conviction** — 2-vote margin required, 1-vote → NEUTRAL
5. **Time awareness** — Avoid opening noise, lunch lulls, EOD dumps
6. **Risk management** — Daily cap (10), sector cap (3), auto TP/SL
7. **Direction alignment** — BULLISH only buys CE, BEARISH only buys PE
