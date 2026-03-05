"""
NSE F&O Strategy Backtester
============================
Uses IndStocks historical API to replay your scanner strategy on past data.

Two modes:
  --from-db   : Replay actual paper trades saved by the scanner in trades.db
  (default)   : Scan live signals now and test them on recent historical data

Usage:
  python backtest.py                          # scan top 10 stocks
  python backtest.py --symbol NIFTY           # single symbol
  python backtest.py --score 75 --tp 50 --sl 25
  python backtest.py --from-db               # replay saved paper trades
"""

import os, sys, asyncio, argparse, csv, sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from collections import Counter
import httpx
from dotenv import load_dotenv

load_dotenv()

INDSTOCKS_TOKEN = os.getenv("INDSTOCKS_TOKEN", "")
INDSTOCKS_BASE  = "https://api.indstocks.com/v1"
IST             = ZoneInfo("Asia/Kolkata")
DB_PATH         = os.path.join(os.path.dirname(__file__), "paper_trades.db")

GREEN  = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
CYAN   = "\033[96m"; BOLD = "\033[1m"; RESET  = "\033[0m"

def clr(val: float, fmt: str = ".2f") -> str:
    s = f"{val:{fmt}}"
    return f"{GREEN}{s}{RESET}" if val > 0 else f"{RED}{s}{RESET}" if val < 0 else s


# ── IndStocks API helpers ─────────────────────────────────────────────────────

async def get_instruments(query: str) -> list:
    """Search NFO instrument master for a symbol."""
    if not INDSTOCKS_TOKEN:
        return []
    headers = {"Authorization": f"Bearer {INDSTOCKS_TOKEN}"}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(
                f"{INDSTOCKS_BASE}/market/instruments",
                params={"search": query, "exchange": "NFO"},
                headers=headers,
            )
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception as e:
            print(f"{RED}  Instruments search error: {e}{RESET}")
            return []


async def get_candles(scrip_code: str, start_dt: datetime, end_dt: datetime, interval: str = "1day") -> list:
    """Fetch OHLCV candles. Returns [[ts, open, high, low, close, volume], ...]"""
    if not INDSTOCKS_TOKEN:
        return []
    headers = {"Authorization": f"Bearer {INDSTOCKS_TOKEN}"}
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(
                f"{INDSTOCKS_BASE}/market/historical/{interval}",
                params={
                    "scrip-codes": scrip_code,
                    "start_time":  int(start_dt.timestamp() * 1000),
                    "end_time":    int(end_dt.timestamp() * 1000),
                },
                headers=headers,
            )
            r.raise_for_status()
            return r.json().get("data", {}).get("candles", [])
        except Exception as e:
            print(f"{RED}  Candles error for {scrip_code}: {e}{RESET}")
            return []


async def find_option_scrip(symbol: str, opt_type: str, strike: float) -> Optional[str]:
    """Find NFO scrip code for a specific option strike."""
    query    = f"{symbol} {int(strike)} {opt_type}"
    results  = await get_instruments(query)
    if not results:
        return None
    # Filter: must contain symbol, strike, type
    matches = [
        i for i in results
        if str(int(strike)) in i.get("name", "")
        and opt_type in i.get("name", "").upper()
        and symbol in i.get("name", "").upper()
    ]
    if not matches:
        matches = results
    # Sort by nearest expiry
    matches.sort(key=lambda x: x.get("expiry", ""))
    return matches[0].get("scripCode") if matches else None


# ── Single Trade Simulation ───────────────────────────────────────────────────

async def simulate_trade(
    symbol: str,
    opt_type: str,
    strike: float,
    entry_date: str,       # "YYYY-MM-DD"
    signal_score: int,
    take_profit_pct: float = 40.0,
    stop_loss_pct: float   = -20.0,
    hold_days: int         = 5,
) -> Optional[dict]:
    """
    Simulate one options trade using IndStocks historical daily candles.
    Entry  = open price of first candle on/after entry_date
    Exit   = first of: TP hit (high), SL hit (low), or close of last candle
    """
    scrip_code = await find_option_scrip(symbol, opt_type, strike)
    if not scrip_code:
        print(f"    {YELLOW}⚠️  No scrip found: {symbol} {int(strike)} {opt_type}{RESET}")
        return None

    entry_dt = datetime.strptime(entry_date, "%Y-%m-%d").replace(tzinfo=IST)
    end_dt   = entry_dt + timedelta(days=hold_days + 7)
    candles  = await get_candles(scrip_code, entry_dt, end_dt, "1day")

    if not candles:
        print(f"    {YELLOW}⚠️  No candles for {scrip_code}{RESET}")
        return None

    entry_price = candles[0][1]   # open of first candle
    entry_ts    = datetime.fromtimestamp(candles[0][0]/1000, tz=IST).strftime("%Y-%m-%d")

    if entry_price <= 0:
        return None

    tp_price = entry_price * (1 + take_profit_pct / 100)
    sl_price = entry_price * (1 + stop_loss_pct / 100)

    exit_price  = candles[-1][4]   # default: close of last candle
    exit_date   = datetime.fromtimestamp(candles[-1][0]/1000, tz=IST).strftime("%Y-%m-%d")
    exit_reason = "Hold End"

    for candle in candles[1:]:
        ts    = datetime.fromtimestamp(candle[0]/1000, tz=IST)
        high  = candle[2]
        low   = candle[3]
        close = candle[4]

        if low <= sl_price:
            exit_price  = sl_price
            exit_date   = ts.strftime("%Y-%m-%d")
            exit_reason = f"Stop Loss ({stop_loss_pct:.0f}%)"
            break

        if high >= tp_price:
            exit_price  = tp_price
            exit_date   = ts.strftime("%Y-%m-%d")
            exit_reason = f"Take Profit (+{take_profit_pct:.0f}%)"
            break

        exit_price = close
        exit_date  = ts.strftime("%Y-%m-%d")

    pnl_pct = (exit_price - entry_price) / entry_price * 100
    icon    = "✅" if pnl_pct > 0 else "❌"
    print(f"    {icon} {symbol} {opt_type} {int(strike)} | ₹{entry_price:.2f}→₹{exit_price:.2f} "
          f"| {clr(pnl_pct, '.1f')}% | {exit_reason} | scrip={scrip_code}")

    return {
        "symbol":      symbol,
        "type":        opt_type,
        "strike":      strike,
        "scrip_code":  scrip_code,
        "entry_date":  entry_ts,
        "entry_price": round(entry_price, 2),
        "exit_date":   exit_date,
        "exit_price":  round(exit_price, 2),
        "exit_reason": exit_reason,
        "pnl":         round(exit_price - entry_price, 2),
        "pnl_pct":     round(pnl_pct, 2),
        "score":       signal_score,
    }


# ── Backtest Modes ────────────────────────────────────────────────────────────

async def backtest_from_db(tp: float, sl: float) -> list:
    """Replay all closed trades from the paper trading database."""
    if not os.path.exists(DB_PATH):
        print(f"{RED}❌ trades.db not found. Run the scanner first to build history.{RESET}")
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM trades WHERE status='CLOSED' ORDER BY entry_time DESC LIMIT 200"
    ).fetchall()
    conn.close()

    if not rows:
        print(f"{YELLOW}No closed trades in database yet.{RESET}")
        print("The scanner auto-logs paper trades when score >= 80 during market hours.")
        return []

    print(f"\n{BOLD}Replaying {len(rows)} closed paper trades from trades.db...{RESET}\n")
    trades = []
    for _row in rows:
        row = dict(_row)
        # Instead of calculating simulated PnL from an API, grab actual tracked performance 
        entry = row["entry_price"]
        exit = row["exit_price"]
        pnl_val = row["pnl"]
        pct = row["pnl_pct"]
        is_tp = False
        is_sl = False

        # Assign reasons contextually since they evaluate against user inputted backtest bounds
        reason = row.get("reason", "EOD Square Off")
        if pct >= tp:
            pct = tp
            exit = entry * (1 + (tp/100))
            reason = f"Take Profit (+{tp:.0f}%)"
            is_tp = True
        elif pct <= -abs(sl):
            pct = -abs(sl)
            exit = entry * (1 - (abs(sl)/100))
            reason = f"Stop Loss ({sl:.0f}%)"
            is_sl = True

        trades.append({
            "symbol":      row["symbol"],
            "type":        row["type"],
            "strike":      row["strike"],
            "scrip_code":  f"{row['symbol']}_{row['strike']}_{row['type']}",
            "entry_date":  row["entry_time"][:10],
            "entry_price": round(entry, 2),
            "exit_date":   row["exit_time"][:10] if row["exit_time"] else "N/A",
            "exit_price":  round(exit, 2),
            "exit_reason": reason,
            "pnl":         round(exit - entry, 2),
            "pnl_pct":     round(pct, 2),
            "score":       80,  # Legacy SQLite logic requires 80 score for logging implicitly
        })
    return trades


async def backtest_live_signals(symbols: list, score_threshold: int, tp: float, sl: float) -> list:
    """
    Scan live signals now, then test each top pick on recent historical candles.
    Best used during or right after market hours.
    """
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from main import fetch_nse_chain, compute_stock_score
    except ImportError as e:
        print(f"{RED}❌ Cannot import main.py: {e}{RESET}")
        return []

    print(f"\n{BOLD}Scanning {len(symbols)} symbols...{RESET}\n")
    trades = []
    today  = datetime.now(IST).strftime("%Y-%m-%d")

    for symbol in symbols:
        try:
            chain = await fetch_nse_chain(symbol)
            spot  = chain.get("records", {}).get("underlyingValue", 0)
            if not spot:
                print(f"  {YELLOW}{symbol}: no live data (market may be closed){RESET}")
                continue

            stats = compute_stock_score(chain, spot)
            score = stats.get("score", 0)

            if score < score_threshold:
                print(f"  {symbol}: score {score} < {score_threshold} threshold — skip")
                continue

            print(f"\n  {CYAN}{BOLD}{symbol}{RESET} ₹{spot} | score={score} | {stats['signal']} | PCR={stats['pcr']}")

            for pick in stats.get("top_picks", [])[:2]:
                t = await simulate_trade(
                    symbol=symbol, opt_type=pick["type"], strike=pick["strike"],
                    entry_date=today, signal_score=score,
                    take_profit_pct=float(tp), stop_loss_pct=float(-abs(sl)),
                )
                if t:
                    trades.append(t)
        except Exception as e:
            print(f"  {RED}Error {symbol}: {e}{RESET}")

    return trades


# ── Report ────────────────────────────────────────────────────────────────────

def generate_report(trades: list, tp: float, sl: float) -> dict:
    if not trades:
        return {"trades": [], "stats": {}}

    wins   = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_pct"] for t in trades)
    win_gross  = sum(t["pnl_pct"] for t in wins)
    loss_gross = abs(sum(t["pnl_pct"] for t in losses))

    print(f"\n{'═'*68}")
    print(f"{BOLD}{CYAN}  BACKTEST REPORT   TP=+{tp:.0f}%  SL=-{sl:.0f}%{RESET}")
    print(f"{'═'*68}")
    print(f"\n  {'Symbol':<12} {'T':<3} {'Strike':<8} {'Entry':>8} {'Exit':>8} {'P&L%':>7}  Reason")
    print(f"  {'-'*63}")

    for t in sorted(trades, key=lambda x: x["pnl_pct"], reverse=True):
        icon = "✅" if t["pnl_pct"] > 0 else "❌"
        print(
            f"  {icon} {t['symbol']:<10} {t['type']:<3} {int(t['strike']):<8} "
            f"₹{t['entry_price']:>7.2f} ₹{t['exit_price']:>7.2f} "
            f"{clr(t['pnl_pct'], '>6.1f')}%  {t['exit_reason']}"
        )

    print(f"\n  {'─'*63}")
    print(f"  Total Trades   : {BOLD}{len(trades)}{RESET}")
    print(f"  Win Rate       : {BOLD}{clr(len(wins)/len(trades)*100, '.1f')}%{RESET}  ({len(wins)}W / {len(losses)}L)")
    print(f"  Avg Return     : {BOLD}{clr(total_pnl/len(trades), '.2f')}%{RESET}")
    print(f"  Total Return   : {BOLD}{clr(total_pnl, '.2f')}%{RESET}")
    print(f"  Best Trade     : {GREEN}+{max(t['pnl_pct'] for t in trades):.2f}%{RESET}")
    print(f"  Worst Trade    : {RED}{min(t['pnl_pct'] for t in trades):.2f}%{RESET}")
    print(f"  Avg Win        : {GREEN}+{sum(t['pnl_pct'] for t in wins)/max(1,len(wins)):.2f}%{RESET}")
    print(f"  Avg Loss       : {RED}{sum(t['pnl_pct'] for t in losses)/max(1,len(losses)):.2f}%{RESET}")
    print(f"  Profit Factor  : {BOLD}{win_gross/max(0.01,loss_gross):.2f}{RESET}")

    exit_counts = Counter(t["exit_reason"] for t in trades)
    print(f"\n  Exit Breakdown:")
    for reason, count in exit_counts.most_common():
        print(f"    {reason:<28} {count:>3}  ({count/len(trades)*100:.0f}%)")

    # Save CSV
    csv_path = os.path.join(os.path.dirname(__file__), "backtest_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=trades[0].keys())
        writer.writeheader()
        writer.writerows(trades)
    print(f"\n  {CYAN}Results saved → {csv_path}{RESET}")
    print(f"{'═'*68}\n")
    
    # Return serializable data for the FastAPI endpoint
    return {
        "trades": sorted(trades, key=lambda x: x["pnl_pct"], reverse=True),
        "stats": {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(trades) * 100, 1),
            "avg_return_pct": round(float(total_pnl / len(trades)), 2),
            "total_return_pct": round(float(total_pnl), 2),
            "best_trade_pct": round(float(max(t["pnl_pct"] for t in trades)), 2),
            "worst_trade_pct": round(float(min(t["pnl_pct"] for t in trades)), 2),
            "avg_win_pct": round(float(sum(t["pnl_pct"] for t in wins) / max(1, len(wins))), 2),
            "avg_loss_pct": round(float(sum(t["pnl_pct"] for t in losses) / max(1, len(losses))), 2),
            "profit_factor": round(float(win_gross / max(0.01, loss_gross)), 2),
            "exit_breakdown": [{"reason": str(r), "count": int(c), "pct": round(float(c/len(trades)*100), 1)} for r, c in exit_counts.most_common()]
        }
    }


# ── CLI Entry Point ───────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="NSE F&O Strategy Backtester")
    parser.add_argument("--from-db", action="store_true",
                        help="Replay closed paper trades from trades.db")
    parser.add_argument("--symbol",  type=str,   default="",
                        help="Single symbol (e.g. NIFTY). Omit for top 10 stocks.")
    parser.add_argument("--score",   type=int,   default=70,
                        help="Min scanner score to trigger a trade (default 70)")
    parser.add_argument("--tp",      type=float, default=40.0,
                        help="Take profit %% (default 40)")
    parser.add_argument("--sl",      type=float, default=20.0,
                        help="Stop loss %% (default 20)")
    args = parser.parse_args()

    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════╗
║       NSE F&O STRATEGY BACKTESTER                ║
║  Take Profit: +{args.tp:.0f}%   Stop Loss: -{args.sl:.0f}%             ║
║  Min Score:   {args.score}                                 ║
╚══════════════════════════════════════════════════╝{RESET}
""")

    if not INDSTOCKS_TOKEN:
        print(f"{RED}❌ INDSTOCKS_TOKEN not set. Add it to your .env file.{RESET}")
        return

    if args.from_db:
        trades = await backtest_from_db(tp=args.tp, sl=args.sl)
    else:
        symbols = (
            [args.symbol.upper()] if args.symbol
            else ["NIFTY","BANKNIFTY","RELIANCE","TCS","ICICIBANK",
                  "SBIN","HDFCBANK","INFY","AXISBANK","TATAMOTORS"]
        )
        trades = await backtest_live_signals(
            symbols=symbols, score_threshold=args.score,
            tp=args.tp, sl=args.sl,
        )

    generate_report(trades, tp=args.tp, sl=args.sl)


if __name__ == "__main__":
    asyncio.run(main())
