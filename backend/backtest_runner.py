"""
NSE Scorer Backtest Engine
Simulates historical trades using pre-processed EOD option datasets and market_snapshots parameters.
"""

import sys
import sqlite3
import argparse
import math
import pandas as pd
import os
from datetime import datetime
from tabulate import tabulate

def compute_sharpe(capital_curve, risk_free=0.065):
    if len(capital_curve) < 2:
        return None
    daily_returns = [
        (capital_curve[i] - capital_curve[i-1]) / capital_curve[i-1]
        for i in range(1, len(capital_curve))
    ]
    n = len(daily_returns)
    mean_r = sum(daily_returns) / n
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / n
    std_r = math.sqrt(variance) if variance > 0 else 0
    daily_rf = risk_free / 252
    if std_r == 0:
        return None
    return round((mean_r - daily_rf) / std_r * math.sqrt(252), 2)


class EODBacktester:
    def __init__(self, db_path: str, capital: float = 100000, risk_pct: float = 2.0, slippage_pct: float = 1.5):
        self.db_path = db_path
        self.capital = capital
        self.risk_pct = risk_pct
        self.slippage = slippage_pct
        
        # Performance Tracking
        self.capital_curve = [capital]
        self.trades = []
        self.peak_capital = capital

    def run(self, start_date: str, end_date: str, score_threshold: int = 75,
            confidence_threshold: float = 0.5, tp_pct: float = 40.0, sl_pct: float = 25.0,
            signal_filter: str = None, regime_filter: str = None, symbols: list = None):
        
        conn = sqlite3.connect(self.db_path)
        base_q = "SELECT * FROM market_snapshots WHERE data_source='EOD_HISTORICAL' AND trade_result IS NOT NULL"
        base_q += f" AND snapshot_time >= '{start_date} 00:00:00' AND snapshot_time <= '{end_date} 23:59:59'"
        if signal_filter: base_q += f" AND signal = '{signal_filter}'"
        if regime_filter: base_q += f" AND regime = '{regime_filter}'"
        
        df = pd.read_sql(base_q, conn)
        conn.close()
        
        if symbols:
            df = df[df["symbol"].isin(symbols)]

        # Apply Thresholds
        df = df[(df["score"] >= score_threshold) & (df["confidence"] >= confidence_threshold)]
        df = df[df["signal"] != "NEUTRAL"]
        
        # Sort by trade entry
        df = df.sort_values(by="snapshot_time")
        
        current_cap = self.capital
        MAX_SIMULTANEOUS = 3
        open_by_date = {}
        
        for _, r in df.iterrows():
            if current_cap <= 0: break
            
            trade_date = r["snapshot_time"].split()[0]
            if open_by_date.get(trade_date, 0) >= MAX_SIMULTANEOUS:
                continue
            
            e_pr = r["top_pick_ltp"]
            if e_pr <= 0: continue
            
            entry = e_pr * (1 + self.slippage / 100)
            
            # Dynamic SL / TP
            cur_sl, cur_tp = sl_pct, tp_pct
            if entry < 20: cur_sl, cur_tp = 40.0, 80.0
            elif entry < 50: cur_sl, cur_tp = 25.0, 50.0

            # Assuming NEXT DAY EOD EXIT
            nd_pnl = r.get("pick_pnl_pct_next")
            if nd_pnl is None or pd.isna(nd_pnl):
                continue
            nd_pnl = float(nd_pnl)
            
            actual_pnl_pct = nd_pnl
            if nd_pnl <= -cur_sl: actual_pnl_pct = -cur_sl
            if nd_pnl >= cur_tp: actual_pnl_pct = cur_tp
            
            # Sizing
            LOT_SIZES = {
                "NIFTY": 75, "BANKNIFTY": 30, "FINNIFTY": 65,
                "RELIANCE": 500, "TCS": 175, "INFY": 400,
                "HDFCBANK": 550, "ICICIBANK": 700, "SBIN": 750,
                "TATAMOTORS": 1425, "WIPRO": 3000, "AXISBANK": 625,
                "BAJFINANCE": 750,
            }
            lot_size = LOT_SIZES.get(r["symbol"], 100)
            risk_amt = current_cap * (self.risk_pct / 100)
            max_loss_pts = entry * (cur_sl / 100)
            lots = max(1, int(risk_amt / (max_loss_pts * lot_size)))

            trade_pnl_abs = (actual_pnl_pct / 100) * entry * lots * lot_size
            
            # NOTE: This model assumes same-row entry and exit (EOD in, next EOD out).
            # Capital is updated atomically. Multi-day hold logic would require
            # tracking allocated capital separately.
            current_cap += trade_pnl_abs

            self.capital_curve.append(current_cap)
            self.peak_capital = max(self.peak_capital, current_cap)
            open_by_date[trade_date] = open_by_date.get(trade_date, 0) + 1
            
            self.trades.append({
                "date": trade_date,
                "symbol": r["symbol"],
                "regime": r["regime"],
                "signal": r["signal"],
                "dte": r["dte"],
                "ivr": r["iv_rank"],
                "entry": entry,
                "pnl_pct": actual_pnl_pct,
                "pnl_abs": trade_pnl_abs,
                "win": actual_pnl_pct >= cur_tp
            })
            
        return BacktestResult(self)


class BacktestResult:
    def __init__(self, bt: EODBacktester):
        self.trades = pd.DataFrame(bt.trades)
        self.start_cap = bt.capital
        self.end_cap = bt.capital_curve[-1] if self.trades is not None and len(self.trades) > 0 else bt.capital
        self.cap_curve = bt.capital_curve
        if not self.trades.empty:
            self.trades["date"] = pd.to_datetime(self.trades["date"])

    def print_report(self):
        print("\n" + "═" * 50)
        print(" BACKTEST RESULTS")
        print("═" * 50)
        
        if self.trades.empty:
            print("No trades found matching criteria.")
            return

        total = len(self.trades)
        wins = len(self.trades[self.trades["win"] == True])
        losses = total - wins
        wr = (wins / total) * 100
        
        avg_w = self.trades[self.trades["win"] == True]["pnl_pct"].mean() if wins > 0 else 0
        avg_l = self.trades[self.trades["win"] == False]["pnl_pct"].mean() if losses > 0 else 0
        
        expct = (wr/100 * avg_w) + ((losses/total) * avg_l)
        pf = abs(self.trades[self.trades["win"] == True]["pnl_abs"].sum() / min(-0.01, self.trades[self.trades["win"] == False]["pnl_abs"].sum()))

        peak = self.start_cap
        max_dd = 0
        for cap in self.cap_curve:
            if cap > peak:
                peak = cap
            dd = peak - cap
            if dd > max_dd:
                max_dd = dd
        max_dd_pct = max_dd / self.start_cap * 100
        
        sharpe = compute_sharpe(self.cap_curve)
        sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"

        print(" PERFORMANCE SUMMARY")
        print(" ─────────────────────────────────────────────")
        print(f" Total Trades:    {total}")
        print(f" Wins:            {wins} ({wr:.1f}%)")
        print(f" Losses:          {losses} ({100-wr:.1f}%)")
        print(f" Avg Win:        +{avg_w:.1f}%")
        print(f" Avg Loss:       {avg_l:.1f}%")
        print(f" Expectancy:      +{expct:.2f}% per trade")
        print(f" Profit Factor:   {pf:.2f}")
        print(f" Max Drawdown:    ₹{max_dd:,.0f} ({max_dd_pct:.1f}%)")
        print(f" Sharpe Ratio:    {sharpe_str}")
        
        if total >= 30:
            p0 = 0.5
            z = (wr/100 - p0) / math.sqrt(p0 * (1-p0) / total)
            significant = "✅ Significant" if abs(z) > 1.96 else "⚠️  NOT significant (could be luck)"
            margin = 1.96 * math.sqrt((wr/100) * (1 - wr/100) / total) * 100
            print(f"\n STATISTICAL SIGNIFICANCE")
            print(f" ─────────────────────────────────────────────")
            print(f" Sample size: {total} trades")
            print(f" 95% CI: [{wr-margin:.1f}%, {wr+margin:.1f}%]")
            print(f" Result: {significant}")
        else:
            print(f"\n ⚠️  Only {total} trades — results not statistically meaningful")
            print(f"    Need 30+ trades for basic significance")
            
        print("\n BY SIGNAL")
        print(" ─────────────────────────────────────────────")
        for sig in ["BULLISH", "BEARISH"]:
            sub = self.trades[self.trades["signal"] == sig]
            if not sub.empty: print(f" {sig}: {len(sub)} trades | {len(sub[sub['win']==True])/len(sub)*100:.1f}% WR")
            
        print("\n BY REGIME")
        print(" ─────────────────────────────────────────────")
        for reg in ["TRENDING", "PINNED", "EXPIRY", "SQUEEZE"]:
            sub = self.trades[self.trades["regime"] == reg]
            if not sub.empty: print(f" {reg}: {len(sub)} trades | {len(sub[sub['win']==True])/len(sub)*100:.1f}% WR")

        print("\n BY DTE")
        print(" ─────────────────────────────────────────────")
        dtes = [(0,2), (3,5), (6,15), (15,999)]
        for low, high in dtes:
            sub = self.trades[(self.trades["dte"] >= low) & (self.trades["dte"] <= high)]
            if not sub.empty: print(f" {low}-{high if high < 999 else '+'} days: {len(sub)} trades | {len(sub[sub['win']==True])/len(sub)*100:.1f}% WR")
        
        print("\n TOP 5 SYMBOLS BY P&L")
        print(" ─────────────────────────────────────────────")
        symbol_grps = self.trades.groupby("symbol")["pnl_abs"].sum().sort_values(ascending=False).head(5)
        for sym, pnl in symbol_grps.items():
            sym_df = self.trades[self.trades["symbol"] == sym]
            print(f" {sym}: ₹{pnl:.0f} | {len(sym_df)} trades | {len(sym_df[sym_df['win']==True])/len(sym_df)*100:.1f}% WR")

    def to_dict(self):
        if self.trades.empty:
            return {"error": "No trades found matching criteria."}

        total = len(self.trades)
        wins = len(self.trades[self.trades["win"] == True])
        losses = total - wins
        wr = (wins / total) * 100
        
        avg_w = self.trades[self.trades["win"] == True]["pnl_pct"].mean() if wins > 0 else 0
        avg_l = self.trades[self.trades["win"] == False]["pnl_pct"].mean() if losses > 0 else 0
        
        expct = (wr/100 * avg_w) + ((losses/total) * avg_l)
        pf = abs(self.trades[self.trades["win"] == True]["pnl_abs"].sum() / min(-0.01, self.trades[self.trades["win"] == False]["pnl_abs"].sum()))

        peak = self.start_cap
        max_dd = 0
        for cap in self.cap_curve:
            if cap > peak:
                peak = cap
            dd = peak - cap
            if dd > max_dd:
                max_dd = dd
        max_dd_pct = max_dd / self.start_cap * 100
        
        sharpe = compute_sharpe(self.cap_curve)

        significant = False
        if total >= 30:
            p0 = 0.5
            z = (wr/100 - p0) / math.sqrt(p0 * (1-p0) / total)
            significant = (abs(z) > 1.96)
            
        by_signal = {}
        for sig in ["BULLISH", "BEARISH"]:
            sub = self.trades[self.trades["signal"] == sig]
            if not sub.empty: by_signal[sig] = {"trades": len(sub), "wr": len(sub[sub['win']==True])/len(sub)*100}
            
        by_regime = {}
        for reg in ["TRENDING", "PINNED", "EXPIRY", "SQUEEZE"]:
            sub = self.trades[self.trades["regime"] == reg]
            if not sub.empty: by_regime[reg] = {"trades": len(sub), "wr": len(sub[sub['win']==True])/len(sub)*100}

        by_dte = {}
        dtes = [(0,2, "0-2"), (3,5, "3-5"), (6,15, "6-15"), (15,999, "15+")]
        for low, high, label in dtes:
            sub = self.trades[(self.trades["dte"] >= low) & (self.trades["dte"] <= high)]
            if not sub.empty: by_dte[label] = {"trades": len(sub), "wr": len(sub[sub['win']==True])/len(sub)*100}

        top_symbols = []
        symbol_grps = self.trades.groupby("symbol")["pnl_abs"].sum().sort_values(ascending=False).head(5)
        for sym, pnl in symbol_grps.items():
            sym_df = self.trades[self.trades["symbol"] == sym]
            top_symbols.append({
                "symbol": sym, "pnl": pnl, "trades": len(sym_df),
                "wr": len(sym_df[sym_df['win']==True])/len(sym_df)*100
            })

        return {
            "summary": {
                "total": total,
                "wins": wins,
                "losses": losses,
                "win_rate": wr,
                "avg_win": avg_w,
                "avg_loss": avg_l,
                "expectancy": expct,
                "profit_factor": pf,
                "max_drawdown": max_dd,
                "max_drawdown_pct": max_dd_pct,
                "sharpe": sharpe,
                "significant": significant
            },
            "by_signal": by_signal,
            "by_regime": by_regime,
            "by_dte": by_dte,
            "top_symbols": top_symbols,
            "equity_curve": self.cap_curve
        }


def run_optimiser(db_path: str, start: str, end: str):
    grid = {
        "score_threshold":     [40, 45, 50, 55, 60, 65, 70],
        "confidence_threshold":[0.3, 0.4, 0.5, 0.6],
        "tp_pct":              [30, 40, 50, 60],
        "sl_pct":              [15, 20, 25, 30],
    }
    
    print("Running optimization grid... (this may take a moment)")
    res = []
    
    # Simple Permutation loop
    for sc in grid["score_threshold"]:
        for cn in grid["confidence_threshold"]:
            for tp in grid["tp_pct"]:
                for sl in grid["sl_pct"]:
                    bt = EODBacktester(db_path)
                    bz = bt.run(start, end, score_threshold=sc, confidence_threshold=cn, tp_pct=tp, sl_pct=sl)
                    tr = bz.trades
                    if len(tr) < 30: continue
                    
                    wins = len(tr[tr["win"] == True])
                    wr = wins / len(tr)
                    aw = tr[tr["win"] == True]["pnl_pct"].mean() if wins else 0
                    al = tr[tr["win"] == False]["pnl_pct"].mean() if (len(tr)-wins) else 0
                    
                    expectancy = (wr * aw) + ((1 - wr) * al)
                    res.append({"Score": sc, "Conf": cn, "TP": tp, "SL": sl, "Trades": len(tr), "WR": wr*100, "Expectancy": expectancy})

    if not res:
        print("\nNo parametre combinations produced enough trades to be statistically valid (>30 trades).")
        return

    res_df = pd.DataFrame(res).sort_values(by="Expectancy", ascending=False).head(10)
    print("\nTOP 10 PARAMETER COMBINATIONS")
    print(tabulate(res_df, headers="keys", tablefmt="psql", showindex=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--score", type=int, default=75)
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--tp", type=float, default=40.0)
    parser.add_argument("--sl", type=float, default=25.0)
    parser.add_argument("--signal", type=str)
    parser.add_argument("--regime", type=str, choices=["TRENDING","PINNED","EXPIRY","SQUEEZE"], help="Filter to specific market regime")
    parser.add_argument("--symbols", type=str)
    parser.add_argument("--optimise", action="store_true")
    parser.add_argument("--db", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner.db"))
    
    args = parser.parse_args()
    syms = args.symbols.split(",") if args.symbols else None
    
    if args.optimise:
        run_optimiser(args.db, args.start, args.end)
    else:
        bt = EODBacktester(args.db)
        res = bt.run(args.start, args.end, score_threshold=args.score, confidence_threshold=args.confidence, 
                     tp_pct=args.tp, sl_pct=args.sl, signal_filter=args.signal, regime_filter=args.regime, symbols=syms)
        res.print_report()
