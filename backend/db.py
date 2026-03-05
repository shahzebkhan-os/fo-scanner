"""
db.py — SQLite Paper Trade Database
=====================================
Handles all persistence for the paper trading system.
Tables:
  trades      — all paper trades (open + closed)
  scan_log    — historical scan results for backtesting

Usage:
  import db
  db.init_db()
  db.add_trade("NIFTY", "CE", 22500, 120.5, "Auto: score=85")
  db.get_open_trades()
  db.get_trade_stats()
"""

import sqlite3
import os
from datetime import datetime
from zoneinfo import ZoneInfo

IST      = ZoneInfo("Asia/Kolkata")
DB_PATH  = os.path.join(os.path.dirname(__file__), "trades.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT    NOT NULL,
                type            TEXT    NOT NULL,        -- CE or PE
                strike          REAL    NOT NULL,
                entry_price     REAL    NOT NULL,
                current_price   REAL,
                exit_price      REAL,
                entry_time      TEXT    NOT NULL,
                exit_time       TEXT,
                exit_reason     TEXT,
                reason          TEXT,                    -- why trade was logged
                status          TEXT    DEFAULT 'OPEN',  -- OPEN / CLOSED
                expiry          TEXT,
                pnl_pct         REAL    DEFAULT 0.0,
                pnl_abs         REAL    DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT    NOT NULL,
                scan_time   TEXT    NOT NULL,
                spot        REAL,
                score       INTEGER,
                signal      TEXT,
                pcr         REAL,
                iv          REAL,
                oi_change   REAL,
                vol_spike   REAL
            );

            CREATE TABLE IF NOT EXISTS notified_signals (
                uid         TEXT PRIMARY KEY,
                notified_at TEXT NOT NULL
            );
        """)
    print(f"✅ DB initialised at {DB_PATH}")


# ── Trade CRUD ────────────────────────────────────────────────────────────────

def add_trade(symbol: str, opt_type: str, strike: float,
              entry_price: float, reason: str = "", expiry: str = "") -> int:
    """Log a new paper trade. Returns the new trade id."""
    now = datetime.now(IST).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades
              (symbol, type, strike, entry_price, current_price,
               entry_time, status, reason, expiry)
            VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (symbol, opt_type, strike, entry_price, entry_price, now, reason, expiry),
        )
        return cur.lastrowid


def update_trade(trade_id: int, current_price: float,
                 exit_flag: bool = False, reason: str = ""):
    """Update current price, and optionally close the trade."""
    with get_conn() as conn:
        # Fetch entry price for P&L calc
        row = conn.execute(
            "SELECT entry_price FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if not row:
            return

        entry_price = row["entry_price"]
        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price else 0
        pnl_abs = current_price - entry_price

        if exit_flag:
            now = datetime.now(IST).isoformat()
            conn.execute(
                """
                UPDATE trades
                SET current_price = ?,
                    exit_price    = ?,
                    exit_time     = ?,
                    exit_reason   = ?,
                    status        = 'CLOSED',
                    pnl_pct       = ?,
                    pnl_abs       = ?
                WHERE id = ?
                """,
                (current_price, current_price, now, reason, pnl_pct, pnl_abs, trade_id),
            )
        else:
            conn.execute(
                """
                UPDATE trades
                SET current_price = ?,
                    pnl_pct       = ?,
                    pnl_abs       = ?
                WHERE id = ?
                """,
                (current_price, pnl_pct, pnl_abs, trade_id),
            )


def get_open_trades() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY entry_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_trades() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY entry_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_closed_trades() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_trades_by_symbol(symbol: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE symbol = ? ORDER BY entry_time DESC",
            (symbol.upper(),),
        ).fetchall()
        return [dict(r) for r in rows]


def add_tracked_pick(symbol: str, type_: str, strike: float, entry_price: float, score: int, stock_price: float = 0.0, lot_size: int = 0) -> bool:
    """Adds a new manually tracked pick."""
    with get_conn() as conn:
        now = datetime.now(IST).date().isoformat()
        exists = conn.execute(
            "SELECT id FROM trades WHERE symbol=? AND type=? AND strike=? AND status='TRACKED' AND date(entry_time)=?",
            (symbol, type_, strike, now)
        ).fetchone()
        if exists:
            return False
            
        conn.execute(
            """
            INSERT INTO trades
              (symbol, type, strike, entry_price, entry_time, status, reason, stock_price, lot_size, score)
            VALUES (?, ?, ?, ?, ?, 'TRACKED', 'Manual Track', ?, ?, ?)
            """,
            (symbol, type_, strike, entry_price, datetime.now(IST).isoformat(), stock_price, lot_size, score),
        )
        return True


def get_tracked_picks() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status = 'TRACKED' ORDER BY entry_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]

def update_tracked_pick(trade_id: int, current_price: float, stock_price: float = None):
    with get_conn() as conn:
        row = conn.execute("SELECT entry_price FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row: return
        entry_price = row[0]
        pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price else 0
        pnl_abs = current_price - entry_price
        
        if stock_price is not None:
            conn.execute(
                """
                UPDATE trades
                SET current_price = ?,
                    pnl_pct       = ?,
                    pnl_abs       = ?,
                    stock_price   = ?
                WHERE id = ?
                """,
                (current_price, pnl_pct, pnl_abs, stock_price, trade_id),
            )
        else:
            conn.execute(
                """
                UPDATE trades
                SET current_price = ?,
                    pnl_pct       = ?,
                    pnl_abs       = ?
                WHERE id = ?
                """,
                (current_price, pnl_pct, pnl_abs, trade_id),
            )

def delete_tracked_pick(trade_id: int) -> bool:
    """Removes a tracked pick from the database."""
    with get_conn() as conn:
        cursor = conn.execute("DELETE FROM trades WHERE id = ? AND status = 'TRACKED'", (trade_id,))
        return cursor.rowcount > 0

def delete_all_tracked_picks() -> bool:
    """Removes all tracked picks from the database."""
    with get_conn() as conn:
        conn.execute("DELETE FROM trades WHERE status = 'TRACKED'")
        return True

def get_trade_stats() -> dict:
    """Compute win/loss statistics across all closed trades."""
    closed = get_closed_trades()
    open_  = get_open_trades()

    if not closed:
        return {
            "total_closed":  0,
            "total_open":    len(open_),
            "winners":       0,
            "losers":        0,
            "win_rate_pct":  0.0,
            "avg_pnl_pct":   0.0,
            "avg_win_pct":   0.0,
            "avg_loss_pct":  0.0,
            "total_pnl_pct": 0.0,
            "best_trade":    None,
            "worst_trade":   None,
            "by_reason":     {},
        }

    winners = [t for t in closed if t["pnl_pct"] > 0]
    losers  = [t for t in closed if t["pnl_pct"] <= 0]

    avg_pnl  = sum(t["pnl_pct"] for t in closed) / len(closed)
    avg_win  = sum(t["pnl_pct"] for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t["pnl_pct"] for t in losers)  / len(losers)  if losers  else 0
    win_rate = len(winners) / len(closed) * 100

    best  = max(closed, key=lambda x: x["pnl_pct"])
    worst = min(closed, key=lambda x: x["pnl_pct"])

    # Breakdown by exit reason
    by_reason: dict = {}
    for t in closed:
        r = t.get("exit_reason") or "Unknown"
        # Normalise
        if "Stop" in r:   key = "Stop Loss"
        elif "Target" in r: key = "Target Hit"
        elif "EOD" in r:  key = "EOD Square Off"
        else:             key = r
        if key not in by_reason:
            by_reason[key] = {"count": 0, "avg_pnl": 0.0, "pnls": []}
        by_reason[key]["count"] += 1
        by_reason[key]["pnls"].append(t["pnl_pct"])

    for key in by_reason:
        pnls = by_reason[key]["pnls"]
        by_reason[key]["avg_pnl"] = round(sum(pnls) / len(pnls), 2)
        del by_reason[key]["pnls"]

    # Per-symbol stats
    by_symbol: dict = {}
    for t in closed:
        s = t["symbol"]
        if s not in by_symbol:
            by_symbol[s] = {"trades": 0, "wins": 0, "pnl_sum": 0.0}
        by_symbol[s]["trades"]  += 1
        by_symbol[s]["pnl_sum"] += t["pnl_pct"]
        if t["pnl_pct"] > 0:
            by_symbol[s]["wins"] += 1
    for s in by_symbol:
        st = by_symbol[s]
        st["win_rate_pct"] = round(st["wins"] / st["trades"] * 100, 1)
        st["avg_pnl_pct"]  = round(st["pnl_sum"] / st["trades"], 2)
        del st["pnl_sum"]

    return {
        "total_closed":  len(closed),
        "total_open":    len(open_),
        "winners":       len(winners),
        "losers":        len(losers),
        "win_rate_pct":  round(win_rate, 2),
        "avg_pnl_pct":   round(avg_pnl, 2),
        "avg_win_pct":   round(avg_win, 2),
        "avg_loss_pct":  round(avg_loss, 2),
        "total_pnl_pct": round(sum(t["pnl_pct"] for t in closed), 2),
        "best_trade":    best,
        "worst_trade":   worst,
        "by_reason":     by_reason,
        "by_symbol":     by_symbol,
    }


# ── Scan Log ──────────────────────────────────────────────────────────────────

def log_scan(symbol: str, spot: float, score: int, signal: str,
             pcr: float, iv: float, oi_change: float, vol_spike: float):
    """Save a scan result for historical analysis / backtesting."""
    now = datetime.now(IST).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO scan_log
              (symbol, scan_time, spot, score, signal, pcr, iv, oi_change, vol_spike)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (symbol, now, spot, score, signal, pcr, iv, oi_change, vol_spike),
        )


def get_scan_history(symbol: str = None, days: int = 30) -> list[dict]:
    """Fetch scan log for a symbol over the last N days."""
    with get_conn() as conn:
        if symbol:
            rows = conn.execute(
                """
                SELECT * FROM scan_log
                WHERE symbol = ?
                  AND scan_time >= datetime('now', ?)
                ORDER BY scan_time DESC
                """,
                (symbol.upper(), f"-{days} days"),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM scan_log
                WHERE scan_time >= datetime('now', ?)
                ORDER BY scan_time DESC
                """,
                (f"-{days} days",),
            ).fetchall()
        return [dict(r) for r in rows]


# ── Notifications ─────────────────────────────────────────────────────────────

def is_signal_notified(uid: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM notified_signals WHERE uid = ?", (uid,)).fetchone()
        return bool(row)

def mark_signal_notified(uid: str):
    now = datetime.now(IST).isoformat()
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO notified_signals (uid, notified_at) VALUES (?, ?)", (uid, now))


# ── CLI — quick inspection ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    init_db()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"

    if cmd == "stats":
        stats = get_trade_stats()
        print(f"\n📊 Trade Statistics")
        print(f"   Closed trades : {stats['total_closed']}")
        print(f"   Open trades   : {stats['total_open']}")
        print(f"   Win rate      : {stats['win_rate_pct']}%")
        print(f"   Avg P&L       : {stats['avg_pnl_pct']:+.1f}%")
        print(f"   Avg Win       : {stats['avg_win_pct']:+.1f}%")
        print(f"   Avg Loss      : {stats['avg_loss_pct']:+.1f}%")
        print(f"   Total P&L     : {stats['total_pnl_pct']:+.1f}%")
        if stats["best_trade"]:
            b = stats["best_trade"]
            print(f"   Best trade    : {b['symbol']} {b['type']} {b['strike']} → {b['pnl_pct']:+.1f}%")
        print(f"\n   By exit reason:")
        for reason, data in stats.get("by_reason", {}).items():
            print(f"     {reason:<20}: {data['count']} trades  avg {data['avg_pnl']:+.1f}%")
        print(f"\n   By symbol:")
        for sym, data in sorted(stats.get("by_symbol", {}).items(),
                                key=lambda x: x[1]["avg_pnl_pct"], reverse=True):
            print(f"     {sym:<14}: {data['trades']} trades  WR {data['win_rate_pct']}%  avg {data['avg_pnl_pct']:+.1f}%")

    elif cmd == "open":
        trades = get_open_trades()
        print(f"\n📋 Open Trades ({len(trades)})")
        for t in trades:
            pnl = t.get("pnl_pct", 0)
            print(f"  {'✅' if pnl >= 0 else '🔴'} {t['symbol']:<10} {t['type']} "
                  f"Strike={t['strike']}  Entry=₹{t['entry_price']}  "
                  f"Current=₹{t.get('current_price',0)}  P&L={pnl:+.1f}%")

    elif cmd == "history":
        trades = get_all_trades()
        print(f"\n📋 All Trades ({len(trades)})")
        for t in trades:
            status = "🟢" if t["status"] == "OPEN" else ("✅" if t["pnl_pct"] > 0 else "❌")
            print(f"  {status} [{t['id']:>3}] {t['symbol']:<10} {t['type']} "
                  f"Strike={t['strike']}  Entry=₹{t['entry_price']}  "
                  f"P&L={t['pnl_pct']:+.1f}%  {t['status']}  {t.get('exit_reason','')}")

    elif cmd == "clear":
        confirm = input("⚠️  This will DELETE all trades. Type YES to confirm: ")
        if confirm == "YES":
            with get_conn() as conn:
                conn.execute("DELETE FROM trades")
                conn.execute("DELETE FROM scan_log")
            print("✅ All trades cleared.")
        else:
            print("Cancelled.")

    else:
        print(f"Usage: python db.py [stats|open|history|clear]")