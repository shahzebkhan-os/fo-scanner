"""
db.py — Enhanced SQLite Database Layer v4
New tables vs v3:
  - oi_history        : 15-min OI snapshots per strike (powers heatmap, IVR, UOA)
  - iv_history        : daily IV per symbol (powers IV Rank / IVR)
  - notifications     : persisted alert dedup (survives restarts)
  - trade_notes       : journal notes per trade
  - bulk_deals        : NSE bulk/block deal cache
  - settings          : per-symbol config (alert threshold, watchlist, capital)
"""

import sqlite3, os, json
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "scanner.db")
IST = ZoneInfo("Asia/Kolkata")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with _conn() as c:
        # ── Existing tables (unchanged schema) ───────────────────────────────
        c.executescript("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT    NOT NULL,
            type         TEXT    NOT NULL,
            strike       REAL    NOT NULL,
            entry_price  REAL    NOT NULL,
            current_price REAL,
            exit_price   REAL,
            status       TEXT    DEFAULT 'OPEN',
            reason       TEXT,
            entry_time   TEXT    DEFAULT (datetime('now')),
            exit_time    TEXT,
            pnl          REAL,
            pnl_pct      REAL,
            lot_size     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tracked_picks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT    NOT NULL,
            type         TEXT    NOT NULL,
            strike       REAL    NOT NULL,
            entry_price  REAL    NOT NULL,
            current_price REAL,
            score        INTEGER DEFAULT 0,
            stock_price  REAL    DEFAULT 0,
            lot_size     INTEGER DEFAULT 0,
            status       TEXT    DEFAULT 'TRACKED',
            tracked_at   TEXT    DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tracked_picks_unique ON tracked_picks (symbol, type, strike, date(tracked_at));

        -- ── New: OI snapshots every 15 min ───────────────────────────────
        CREATE TABLE IF NOT EXISTS oi_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT    NOT NULL,
            expiry      TEXT    NOT NULL,
            strike      REAL    NOT NULL,
            opt_type    TEXT    NOT NULL,   -- CE or PE
            oi          REAL    DEFAULT 0,
            oi_chg      REAL    DEFAULT 0,
            volume      REAL    DEFAULT 0,
            iv          REAL    DEFAULT 0,
            ltp         REAL    DEFAULT 0,
            snap_time   TEXT    DEFAULT (datetime('now')),
            snap_date   TEXT    DEFAULT (date('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_oi_history_sym_date
            ON oi_history(symbol, snap_date, strike, opt_type);

        -- ── New: Daily IV per symbol for IVR calculation ─────────────────
        CREATE TABLE IF NOT EXISTS iv_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol      TEXT    NOT NULL,
            iv          REAL    NOT NULL,
            snap_date   TEXT    DEFAULT (date('now')),
            UNIQUE(symbol, snap_date)
        );
        CREATE INDEX IF NOT EXISTS idx_iv_history_sym
            ON iv_history(symbol, snap_date);

        -- ── New: Persisted alert dedup (survives server restarts) ─────────
        CREATE TABLE IF NOT EXISTS notifications (
            uid         TEXT    PRIMARY KEY,
            sent_at     TEXT    DEFAULT (datetime('now'))
        );

        -- ── New: Per-trade journal notes ──────────────────────────────────
        CREATE TABLE IF NOT EXISTS trade_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id    INTEGER NOT NULL REFERENCES paper_trades(id),
            note        TEXT    NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        -- ── New: NSE Bulk / Block deals cache ────────────────────────────
        CREATE TABLE IF NOT EXISTS bulk_deals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_date   TEXT    NOT NULL,
            symbol      TEXT    NOT NULL,
            client      TEXT,
            deal_type   TEXT,   -- BUY or SELL
            quantity    REAL    DEFAULT 0,
            price       REAL    DEFAULT 0,
            fetched_at  TEXT    DEFAULT (datetime('now')),
            UNIQUE(deal_date, symbol, client, deal_type)
        );

        -- ── New: Per-symbol settings & watchlist ─────────────────────────
        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT    PRIMARY KEY,
            value       TEXT    NOT NULL,
            updated_at  TEXT    DEFAULT (datetime('now'))
        );

        -- ── New: Partial exits for scale-out strategy ────────────────────
        CREATE TABLE IF NOT EXISTS partial_exits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id    INTEGER NOT NULL REFERENCES paper_trades(id),
            exit_price  REAL    NOT NULL,
            lots_exited INTEGER DEFAULT 1,
            pnl         REAL,
            reason      TEXT,
            exit_time   TEXT    DEFAULT (datetime('now'))
        );
        -- ── New: Accuracy Tracking Snapshots ────────────────────────────
        CREATE TABLE IF NOT EXISTS accuracy_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS accuracy_trades (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id  INTEGER NOT NULL REFERENCES accuracy_snapshots(id) ON DELETE CASCADE,
            symbol       TEXT    NOT NULL,
            type         TEXT    NOT NULL,
            strike       REAL    NOT NULL,
            entry_price  REAL    NOT NULL,
            current_price REAL,
            score        INTEGER DEFAULT 0,
            stock_price  REAL    DEFAULT 0,
            lot_size     INTEGER DEFAULT 0,
            ml_prob      REAL,
            signal       TEXT,
            iv_rank      REAL,
            regime       TEXT,
            max_pain     REAL,
            days_to_expiry INTEGER,
            pcr          REAL,
            iv           REAL,
            vol_spike    REAL,
            ml_score     INTEGER
        );

        CREATE TABLE IF NOT EXISTS csv_exports (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id  INTEGER REFERENCES accuracy_snapshots(id) ON DELETE SET NULL,
            filename     TEXT    NOT NULL,
            filepath     TEXT    NOT NULL,
            trade_count  INTEGER DEFAULT 0,
            avg_score    REAL    DEFAULT 0,
            avg_pnl_pct  REAL    DEFAULT 0,
            created_at   TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_accuracy_trades_snapshot ON accuracy_trades(snapshot_id);

        CREATE TABLE IF NOT EXISTS accuracy_trade_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id    INTEGER NOT NULL REFERENCES accuracy_trades(id) ON DELETE CASCADE,
            price       REAL    NOT NULL,
            timestamp   TEXT    DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_accuracy_history_trade ON accuracy_trade_history(trade_id);

        -- ══════════════════════════════════════════════════════════════════════════════
        -- Historical Backtesting Tables & Indexes
        -- ══════════════════════════════════════════════════════════════════════════════

        CREATE TABLE IF NOT EXISTS market_snapshots (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol                  TEXT NOT NULL,
            snapshot_time           TEXT NOT NULL,
            spot_price              REAL DEFAULT 0,
            spot_change_pct         REAL DEFAULT 0,
            total_ce_oi             REAL DEFAULT 0,
            total_pe_oi             REAL DEFAULT 0,
            pcr_oi                  REAL DEFAULT 0,
            total_ce_vol            REAL DEFAULT 0,
            total_pe_vol            REAL DEFAULT 0,
            pcr_vol                 REAL DEFAULT 0,
            atm_ce_iv               REAL DEFAULT 0,
            atm_pe_iv               REAL DEFAULT 0,
            iv_skew                 REAL DEFAULT 0,
            atm_ce_ltp              REAL DEFAULT 0,
            atm_pe_ltp              REAL DEFAULT 0,
            atm_strike              REAL DEFAULT 0,
            dte                     INTEGER DEFAULT 0,
            expiry_date             TEXT,
            signal                  TEXT,
            score                   INTEGER DEFAULT 0,
            confidence              REAL DEFAULT 0,
            regime                  TEXT,
            top_pick_type           TEXT,
            top_pick_strike         REAL DEFAULT 0,
            top_pick_ltp            REAL DEFAULT 0,
            net_gex                 REAL DEFAULT 0,
            zero_gamma_level        REAL DEFAULT 0,
            iv_rank                 REAL DEFAULT 0,
            max_pain_strike         REAL DEFAULT 0,
            oi_concentration_ratio  REAL DEFAULT 0,
            net_delta_flow          REAL DEFAULT 0,
            outcome_1h              REAL,
            outcome_eod             REAL,
            outcome_next            REAL,
            pick_ltp_1h             REAL,
            pick_ltp_eod            REAL,
            pick_pnl_pct_1h         REAL,
            pick_pnl_pct_eod        REAL,
            pick_pnl_pct_next       REAL,
            trade_result            TEXT,
            data_source             TEXT DEFAULT 'LIVE'
        );

        -- Critical Performance Indexes (10-50x query speedup)
        CREATE INDEX IF NOT EXISTS idx_snapshots_source_time
            ON market_snapshots(data_source, snapshot_time);
        CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_time
            ON market_snapshots(symbol, snapshot_time);
        CREATE INDEX IF NOT EXISTS idx_snapshots_score_confidence
            ON market_snapshots(score, confidence);
        CREATE INDEX IF NOT EXISTS idx_snapshots_signal_regime
            ON market_snapshots(signal, regime);
        CREATE INDEX IF NOT EXISTS idx_snapshots_trade_result
            ON market_snapshots(trade_result);
        CREATE INDEX IF NOT EXISTS idx_snapshots_composite
            ON market_snapshots(data_source, snapshot_time, score, confidence, signal);
        """)

    print("✅ DB initialised (v4)")
    # Migration: Add columns to accuracy_trades if they don't exist
    with _conn() as c:
        for col, dtype in [
            ("ml_prob", "REAL"), ("signal", "TEXT"), ("iv_rank", "REAL"),
            ("regime", "TEXT"), ("max_pain", "REAL"), ("days_to_expiry", "INTEGER"),
            ("pcr", "REAL"), ("iv", "REAL"), ("vol_spike", "REAL"), ("ml_score", "INTEGER")
        ]:
            try: c.execute(f"ALTER TABLE accuracy_trades ADD COLUMN {col} {dtype}")
            except: pass


# ══════════════════════════════════════════════════════════════════════════════
# Paper Trades
# ══════════════════════════════════════════════════════════════════════════════

def add_trade(symbol, opt_type, strike, entry_price, reason="", lot_size=0):
    with _conn() as c:
        c.execute("""
            INSERT INTO paper_trades (symbol, type, strike, entry_price, reason, lot_size)
            VALUES (?,?,?,?,?,?)
        """, (symbol, opt_type, float(strike), float(entry_price), reason, lot_size))
    return True

def get_open_trades():
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM paper_trades WHERE status='OPEN' ORDER BY entry_time DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def get_closed_trades():
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM paper_trades WHERE status='CLOSED' ORDER BY entry_time DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def get_all_trades():
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM paper_trades ORDER BY entry_time DESC LIMIT 500"
        ).fetchall()
    return [dict(r) for r in rows]

def update_trade(trade_id, current_price, exit_flag=False, reason=""):
    with _conn() as c:
        row = c.execute("SELECT * FROM paper_trades WHERE id=?", (trade_id,)).fetchone()
        if not row: return
        entry = row["entry_price"]
        pnl_pct = ((current_price - entry) / entry * 100) if entry > 0 else 0
        lot_size = row["lot_size"] if row["lot_size"] and row["lot_size"] > 0 else 1
        pnl_abs  = (current_price - entry) * lot_size

        if exit_flag:
            c.execute("""
                UPDATE paper_trades
                SET current_price=?, exit_price=?, status='CLOSED',
                    exit_time=datetime('now'), pnl=?, pnl_pct=?, reason=?
                WHERE id=?
            """, (current_price, current_price, round(pnl_abs,2), round(pnl_pct,2), reason, trade_id))
        else:
            c.execute("""
                UPDATE paper_trades SET current_price=?, pnl=?, pnl_pct=? WHERE id=?
            """, (current_price, round(pnl_abs,2), round(pnl_pct,2), trade_id))

def get_trade_stats(trade_type: str = "ALL"):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM paper_trades WHERE status='CLOSED'"
        ).fetchall()
    
    trades = []
    for r in rows:
        t = dict(r)
        reason = t.get("reason", "")
        # Filter logic based on reason prefix
        if trade_type == "AUTO" and not reason.startswith("Auto:"):
            continue
        if trade_type == "MANUAL" and reason.startswith("Auto:"):
            continue
        trades.append(t)
        
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "avg_pnl_pct": 0, "total_pnl": 0, "best": None, "worst": None,
                "by_symbol": {}, "equity_curve": []}

    wins   = [t for t in trades if (t["pnl"] or 0) > 0]
    losses = [t for t in trades if (t["pnl"] or 0) <= 0]

    # Equity curve: cumulative PnL sorted by exit_time
    sorted_trades = sorted(trades, key=lambda x: x.get("exit_time") or "")
    cumulative = 0
    equity_curve = []
    for t in sorted_trades:
        cumulative += (t["pnl"] or 0)
        equity_curve.append({
            "date":       t.get("exit_time", "")[:10],
            "cumulative": round(cumulative, 2),
            "trade_pnl":  round(t.get("pnl") or 0, 2),
            "symbol":     t["symbol"]
        })

    # Max drawdown
    peak = 0; max_dd = 0; running = 0
    for t in sorted_trades:
        running += (t["pnl"] or 0)
        if running > peak: peak = running
        dd = peak - running
        if dd > max_dd: max_dd = dd

    # By symbol breakdown
    by_symbol = {}
    for t in trades:
        sym = t["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "pnl": 0, "wins": 0}
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["pnl"]    += (t["pnl"] or 0)
        if (t["pnl"] or 0) > 0:
            by_symbol[sym]["wins"] += 1
    for sym in by_symbol:
        n = by_symbol[sym]["trades"]
        by_symbol[sym]["win_rate"] = round(by_symbol[sym]["wins"] / n * 100, 1) if n else 0
        by_symbol[sym]["pnl"]      = round(by_symbol[sym]["pnl"], 2)

    return {
        "total":       len(trades),
        "wins":        len(wins),
        "losses":      len(losses),
        "win_rate":    round(len(wins) / len(trades) * 100, 1),
        "avg_pnl_pct": round(sum(t.get("pnl_pct") or 0 for t in trades) / len(trades), 2),
        "total_pnl":   round(sum(t.get("pnl") or 0 for t in trades), 2),
        "max_drawdown": round(max_dd, 2),
        "best":        max(trades, key=lambda x: x.get("pnl") or 0) if trades else None,
        "worst":       min(trades, key=lambda x: x.get("pnl") or 0) if trades else None,
        "by_symbol":   by_symbol,
        "equity_curve": equity_curve,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tracked Picks
# ══════════════════════════════════════════════════════════════════════════════

def add_tracked_pick(symbol, opt_type, strike, entry_price, score, stock_price=0, lot_size=0):
    try:
        with _conn() as c:
            c.execute("""
                INSERT INTO tracked_picks
                    (symbol, type, strike, entry_price, score, stock_price, lot_size)
                VALUES (?,?,?,?,?,?,?)
            """, (symbol, opt_type, float(strike), float(entry_price), score, stock_price, lot_size))
        return True
    except sqlite3.IntegrityError:
        return False

def get_tracked_picks():
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM tracked_picks WHERE status='TRACKED' ORDER BY tracked_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def update_tracked_pick(pick_id, current_price, stock_price=0):
    with _conn() as c:
        c.execute("""
            UPDATE tracked_picks SET current_price=?, stock_price=? WHERE id=?
        """, (current_price, stock_price, pick_id))

def delete_tracked_pick(pick_id):
    with _conn() as c:
        c.execute("DELETE FROM tracked_picks WHERE id=?", (pick_id,))
    return True

def delete_all_tracked_picks():
    with _conn() as c:
        c.execute("DELETE FROM tracked_picks")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Accuracy Tracking
# ══════════════════════════════════════════════════════════════════════════════

def create_accuracy_snapshot():
    with _conn() as c:
        cursor = c.execute("INSERT INTO accuracy_snapshots (timestamp) VALUES (datetime('now'))")
        return cursor.lastrowid

def add_accuracy_trade(snapshot_id, symbol, opt_type, strike, entry_price, score, stock_price=0, lot_size=0, **kwargs):
    ml_prob = kwargs.get("ml_prob")
    signal = kwargs.get("signal")
    iv_rank = kwargs.get("iv_rank")
    regime = kwargs.get("regime")
    max_pain = kwargs.get("max_pain")
    dte = kwargs.get("days_to_expiry")
    pcr = kwargs.get("pcr")
    iv = kwargs.get("iv")
    vol_spike = kwargs.get("vol_spike")
    ml_score = kwargs.get("ml_score")

    with _conn() as c:
        cursor = c.execute("""
            INSERT INTO accuracy_trades (
                snapshot_id, symbol, type, strike, entry_price, current_price, score, stock_price, lot_size, 
                ml_prob, signal, iv_rank, regime, max_pain, days_to_expiry, pcr, iv, vol_spike, ml_score
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            snapshot_id, symbol, opt_type, float(strike), float(entry_price), float(entry_price), score, stock_price, lot_size,
            ml_prob, signal, iv_rank, regime, max_pain, dte, pcr, iv, vol_spike, ml_score
        ))
        return cursor.lastrowid

def get_accuracy_snapshots(limit=50):
    with _conn() as c:
        rows = c.execute("""
            SELECT s.*, (SELECT COUNT(*) FROM accuracy_trades WHERE snapshot_id = s.id) as trade_count
            FROM accuracy_snapshots s
            ORDER BY s.timestamp DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]

def delete_accuracy_snapshot(snapshot_id: int):
    with _conn() as c:
        c.execute("DELETE FROM accuracy_snapshots WHERE id=?", (snapshot_id,))
    return True

def get_latest_accuracy_snapshot():
    """Returns the most recent snapshot from today, or None if no snapshots exist today."""
    with _conn() as c:
        snapshot = c.execute("""
            SELECT s.*, (SELECT COUNT(*) FROM accuracy_trades WHERE snapshot_id = s.id) as trade_count
            FROM accuracy_snapshots s
            WHERE date(s.timestamp) = date('now')
            ORDER BY s.timestamp DESC
            LIMIT 1
        """).fetchone()
        if not snapshot:
            return None
        return dict(snapshot)

def get_all_today_accuracy_trades():
    """Returns all accuracy trades from all snapshots taken today, with latest prices."""
    with _conn() as c:
        rows = c.execute("""
            SELECT 
                t.*,
                s.timestamp as snapshot_time
            FROM accuracy_trades t
            JOIN accuracy_snapshots s ON t.snapshot_id = s.id
            WHERE date(s.timestamp) = date('now')
            ORDER BY t.symbol ASC, s.timestamp DESC
        """).fetchall()
    return [dict(r) for r in rows]

def get_accuracy_snapshot_details(snapshot_id):
    with _conn() as c:
        snapshot = c.execute("SELECT * FROM accuracy_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if not snapshot: return None
        trades = c.execute("SELECT * FROM accuracy_trades WHERE snapshot_id=?", (snapshot_id,)).fetchall()
        return {
            "snapshot": dict(snapshot),
            "trades": [dict(r) for r in trades]
        }

def update_accuracy_trade_price(trade_id, current_price):
    with _conn() as c:
        c.execute("UPDATE accuracy_trades SET current_price=? WHERE id=?", (current_price, trade_id))
        c.execute("INSERT INTO accuracy_trade_history (trade_id, price) VALUES (?,?)", (trade_id, float(current_price)))

def get_accuracy_trade_history(trade_id: int):
    with _conn() as c:
        rows = c.execute("""
            SELECT price, timestamp FROM accuracy_trade_history 
            WHERE trade_id=? ORDER BY timestamp ASC
        """, (trade_id,)).fetchall()
    return [dict(r) for r in rows]

def get_active_accuracy_trades():
    """Returns all accuracy trades from snapshots taken today that might need price updates."""
    with _conn() as c:
        rows = c.execute("""
            SELECT t.* FROM accuracy_trades t
            JOIN accuracy_snapshots s ON t.snapshot_id = s.id
            WHERE s.timestamp >= date('now')
        """).fetchall()
    return [dict(r) for r in rows]

def get_accuracy_backtest_report():
    """Aggregates historical accuracy data for the backtest report."""
    with _conn() as c:
        # Get all trades that have at least one history point
        trades = c.execute("""
            SELECT 
                t.id, t.symbol, t.type, t.strike, t.entry_price, t.score, t.lot_size,
                MAX(h.price) as max_price,
                MIN(h.price) as min_price
            FROM accuracy_trades t
            JOIN accuracy_trade_history h ON t.id = h.trade_id
            GROUP BY t.id
        """).fetchall()

    if not trades:
        return {"total_trades": 0, "win_rate": 0, "avg_max_pnl": 0, "best_trade": None, "score_brackets": {}}

    total = len(trades)
    winning_trades = 0
    total_max_pnl_pct = 0
    best_trade = None
    best_pnl_pct = -100

    score_brackets = {
        ">=90": {"total": 0, "wins": 0, "avg_pnl": 0},
        "80-89": {"total": 0, "wins": 0, "avg_pnl": 0},
        "<80": {"total": 0, "wins": 0, "avg_pnl": 0}
    }

    for r in trades:
        entry = r["entry_price"]
        if entry <= 0: continue
        
        # Win is defined as reaching at least +5% (or any positive threshold) at max
        # Here we'll define a "Win" as max_price > entry_price at all
        max_pnl_pct = ((r["max_price"] - entry) / entry) * 100
        
        if max_pnl_pct > 0:
            winning_trades += 1

        total_max_pnl_pct += max_pnl_pct

        if max_pnl_pct > best_pnl_pct:
            best_pnl_pct = max_pnl_pct
            best_trade = {
                "symbol": r["symbol"], "type": r["type"], "strike": r["strike"],
                "entry": entry, "max_price": r["max_price"], "pnl_pct": round(max_pnl_pct, 2),
                "score": r["score"]
            }

        # Bracket logic
        score = r["score"]
        if score >= 90: b = ">=90"
        elif score >= 80: b = "80-89"
        else: b = "<80"

        score_brackets[b]["total"] += 1
        if max_pnl_pct > 0: score_brackets[b]["wins"] += 1
        score_brackets[b]["avg_pnl"] += max_pnl_pct

    # Finalize brackets
    for b, data in score_brackets.items():
        if data["total"] > 0:
            data["win_rate"] = round((data["wins"] / data["total"]) * 100, 1)
            data["avg_pnl"] = round(data["avg_pnl"] / data["total"], 2)
        else:
            data["win_rate"] = 0
            data["avg_pnl"] = 0

    return {
        "total_trades": total,
        "win_rate": round((winning_trades / total) * 100, 1) if total > 0 else 0,
        "avg_max_pnl": round(total_max_pnl_pct / total, 2) if total > 0 else 0,
        "best_trade": best_trade,
        "score_brackets": score_brackets
    }


# ══════════════════════════════════════════════════════════════════════════════
# Trade Notes (Journal)
# ══════════════════════════════════════════════════════════════════════════════

def add_trade_note(trade_id: int, note: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO trade_notes (trade_id, note) VALUES (?,?)",
            (trade_id, note)
        )
    return True

def get_trade_notes(trade_id: int):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM trade_notes WHERE trade_id=? ORDER BY created_at DESC",
            (trade_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# OI History (15-min snapshots)
# ══════════════════════════════════════════════════════════════════════════════

def save_oi_snapshot(symbol: str, expiry: str, records: list):
    """Bulk-insert one full chain snapshot. Call every 15 minutes."""
    today = date.today().isoformat()
    now   = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    rows  = []
    for row in records:
        strike = row.get("strikePrice", 0)
        for side in ["CE", "PE"]:
            sd = row.get(side, {})
            if not sd: continue
            rows.append((
                symbol, expiry, strike, side,
                sd.get("openInterest", 0),
                sd.get("changeinOpenInterest", 0),
                sd.get("totalTradedVolume", 0),
                sd.get("impliedVolatility", 0),
                sd.get("lastPrice", 0),
                now, today
            ))
    if rows:
        with _conn() as c:
            c.executemany("""
                INSERT INTO oi_history
                    (symbol, expiry, strike, opt_type, oi, oi_chg, volume, iv, ltp, snap_time, snap_date)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, rows)

def get_oi_timeline(symbol: str, strike: float, opt_type: str, days: int = 5) -> list:
    """
    Return intraday OI timeline for a specific strike.
    Used for the OI heatmap and buildup charts.
    """
    with _conn() as c:
        rows = c.execute("""
            SELECT snap_time, oi, oi_chg, volume, iv, ltp
            FROM oi_history
            WHERE symbol=? AND strike=? AND opt_type=?
              AND snap_date >= date('now', ? || ' days')
            ORDER BY snap_time ASC
        """, (symbol, strike, opt_type, f"-{days}")).fetchall()
    return [dict(r) for r in rows]

def get_oi_heatmap(symbol: str, snap_date: str = None) -> list:
    """
    Returns all OI snapshots for a symbol on a given date
    (defaults to today). Used to build the OI buildup heatmap.
    """
    snap_date = snap_date or date.today().isoformat()
    with _conn() as c:
        rows = c.execute("""
            SELECT strike, opt_type, snap_time, oi, volume
            FROM oi_history
            WHERE symbol=? AND snap_date=?
            ORDER BY strike ASC, snap_time ASC
        """, (symbol, snap_date)).fetchall()
    return [dict(r) for r in rows]

def get_volume_baseline(symbol: str, strike: float, opt_type: str, days: int = 5) -> float:
    """
    Returns average daily volume for a strike over past N days.
    Used by UOA detector to flag unusual activity.
    """
    with _conn() as c:
        row = c.execute("""
            SELECT AVG(daily_vol) as avg_vol FROM (
                SELECT snap_date, MAX(volume) as daily_vol
                FROM oi_history
                WHERE symbol=? AND strike=? AND opt_type=?
                  AND snap_date < date('now')
                  AND snap_date >= date('now', ? || ' days')
                GROUP BY snap_date
            )
        """, (symbol, strike, opt_type, f"-{days}")).fetchone()
    return float(row["avg_vol"] or 0)


# ══════════════════════════════════════════════════════════════════════════════
# IV History (for IV Rank)
# ══════════════════════════════════════════════════════════════════════════════

def save_daily_iv(symbol: str, iv: float):
    """Upsert today's IV for a symbol."""
    if iv <= 0: return
    with _conn() as c:
        c.execute("""
            INSERT INTO iv_history (symbol, iv, snap_date)
            VALUES (?, ?, date('now'))
            ON CONFLICT(symbol, snap_date) DO UPDATE SET iv=excluded.iv
        """, (symbol, iv))

def get_iv_rank(symbol: str, lookback_days: int = 252) -> dict:
    """
    IVR = (current_iv - 52w_low) / (52w_high - 52w_low) × 100
    Returns: { current_iv, iv_rank, iv_52w_high, iv_52w_low, days_available }
    """
    with _conn() as c:
        rows = c.execute("""
            SELECT iv FROM iv_history
            WHERE symbol=? AND snap_date >= date('now', ? || ' days')
            ORDER BY snap_date DESC
        """, (symbol, f"-{lookback_days}")).fetchall()

    if not rows:
        return {"current_iv": 0, "iv_rank": 0, "iv_52w_high": 0, "iv_52w_low": 0, "days_available": 0}

    ivs         = [r["iv"] for r in rows]
    current_iv  = ivs[0]
    iv_high     = max(ivs)
    iv_low      = min(ivs)
    iv_range    = iv_high - iv_low
    iv_rank     = round((current_iv - iv_low) / iv_range * 100, 1) if iv_range > 0 else 50.0

    return {
        "current_iv":    round(current_iv, 1),
        "iv_rank":       iv_rank,
        "iv_52w_high":   round(iv_high, 1),
        "iv_52w_low":    round(iv_low, 1),
        "days_available": len(ivs),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Notifications (persisted dedup)
# ══════════════════════════════════════════════════════════════════════════════

def is_notified(uid: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM notifications WHERE uid=?", (uid,)
        ).fetchone()
    return row is not None

def mark_notified(uid: str):
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO notifications (uid) VALUES (?)", (uid,)
        )

def cleanup_old_notifications(days: int = 7):
    """Prune alerts older than N days to keep DB small."""
    with _conn() as c:
        c.execute(
            "DELETE FROM notifications WHERE sent_at < datetime('now', ? || ' days')",
            (f"-{days}",)
        )


# ══════════════════════════════════════════════════════════════════════════════
# Bulk Deals
# ══════════════════════════════════════════════════════════════════════════════

def save_bulk_deals(deals: list):
    with _conn() as c:
        c.executemany("""
            INSERT OR IGNORE INTO bulk_deals
                (deal_date, symbol, client, deal_type, quantity, price)
            VALUES (?,?,?,?,?,?)
        """, [(d["date"], d["symbol"], d.get("client",""), d["type"],
               d.get("quantity",0), d.get("price",0)) for d in deals])

def get_bulk_deals(symbol: str = None, days: int = 5) -> list:
    with _conn() as c:
        if symbol:
            rows = c.execute("""
                SELECT * FROM bulk_deals
                WHERE symbol=? AND deal_date >= date('now', ? || ' days')
                ORDER BY deal_date DESC
            """, (symbol, f"-{days}")).fetchall()
        else:
            rows = c.execute("""
                SELECT * FROM bulk_deals
                WHERE deal_date >= date('now', ? || ' days')
                ORDER BY deal_date DESC
            """, (f"-{days}",)).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# Settings
# ══════════════════════════════════════════════════════════════════════════════

def get_setting(key: str, default=None):
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]

def set_setting(key: str, value):
    with _conn() as c:
        c.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (key, json.dumps(value)))

def get_watchlist() -> list:
    return get_setting("watchlist", [])

def set_watchlist(symbols: list):
    set_setting("watchlist", symbols)

def get_capital() -> float:
    return float(get_setting("capital", 100000))

def set_capital(amount: float):
    set_setting("capital", amount)

def get_symbol_threshold(symbol: str) -> int:
    thresholds = get_setting("symbol_thresholds", {})
    return thresholds.get(symbol.upper(), 75)

def set_symbol_threshold(symbol: str, threshold: int):
    thresholds = get_setting("symbol_thresholds", {})
    thresholds[symbol.upper()] = threshold
    set_setting("symbol_thresholds", thresholds)


# ══════════════════════════════════════════════════════════════════════════════
# Partial Exits
# ══════════════════════════════════════════════════════════════════════════════

def add_partial_exit(trade_id: int, exit_price: float, lots: int, pnl: float, reason: str):
    with _conn() as c:
        c.execute("""
            INSERT INTO partial_exits (trade_id, exit_price, lots_exited, pnl, reason)
            VALUES (?,?,?,?,?)
        """, (trade_id, exit_price, lots, round(pnl, 2), reason))

def get_partial_exits(trade_id: int) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM partial_exits WHERE trade_id=? ORDER BY exit_time",
            (trade_id,)
        ).fetchall()
    return [dict(r) for r in rows]

# ── Missing Accuracy Tracking Helpers ───────────────────────────────────────────

def get_accuracy_trades_with_history(snapshot_id: int) -> list:
    """Fetches trades for a snapshot, including calculated max/min PnL from history spikes."""
    with _conn() as c:
        trades_rows = c.execute("SELECT * FROM accuracy_trades WHERE snapshot_id=?", (snapshot_id,)).fetchall()
        trades = [dict(r) for r in trades_rows]
        
        for t in trades:
            hist_rows = c.execute("""
                SELECT price, timestamp FROM accuracy_trade_history 
                WHERE trade_id=? ORDER BY timestamp ASC
            """, (t["id"],)).fetchall()
            t["price_history"] = [dict(r) for r in hist_rows]
            
            entry = t["entry_price"] or 0.1
            if t["price_history"]:
                prices = [h["price"] for h in t["price_history"]]
                t["max_price"] = max(prices)
                t["min_price"] = min(prices)
                t["pnl_pct"] = round(((t["current_price"] - entry) / entry * 100), 2)
                t["max_pnl_pct"] = round(((t["max_price"] - entry) / entry * 100, 2))
            else:
                t["max_price"] = t["current_price"]
                t["min_price"] = t["current_price"]
                t["pnl_pct"] = 0
                t["max_pnl_pct"] = 0
                
        return trades

def record_csv_export(snapshot_id, filename, filepath, trade_count, avg_score, avg_pnl):
    with _conn() as c:
        c.execute("""
            INSERT INTO csv_exports (snapshot_id, filename, filepath, trade_count, avg_score, avg_pnl_pct)
            VALUES (?,?,?,?,?,?)
        """, (snapshot_id, filename, filepath, trade_count, avg_score, avg_pnl))

def get_csv_exports():
    with _conn() as c:
        rows = c.execute("SELECT * FROM csv_exports ORDER BY created_at DESC LIMIT 100").fetchall()
    return [dict(r) for r in rows]

def get_csv_export_by_id(export_id: int):
    with _conn() as c:
        row = c.execute("SELECT * FROM csv_exports WHERE id=?", (export_id,)).fetchone()
    return dict(row) if row else None

def delete_csv_export(export_id: int):
    with _conn() as c:
        exp = c.execute("SELECT filepath FROM csv_exports WHERE id=?", (export_id,)).fetchone()
        if exp and os.path.exists(exp["filepath"]):
            try: os.remove(exp["filepath"])
            except: pass
        c.execute("DELETE FROM csv_exports WHERE id=?", (export_id,))
    return True