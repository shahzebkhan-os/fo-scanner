import sqlite3
import os
import logging
from datetime import datetime

log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "paper_trades.db")

def init_db():
    """Initializes the SQLite database with the required tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create trades table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        type TEXT NOT NULL,
        strike REAL NOT NULL,
        entry_time TEXT NOT NULL,
        entry_price REAL NOT NULL,
        status TEXT NOT NULL, -- 'OPEN' or 'CLOSED'
        exit_time TEXT,
        exit_price REAL,
        pnl REAL,
        pnl_pct REAL,
        highest_price REAL,
        lowest_price REAL,
        current_price REAL,
        reason TEXT,          -- Reason for exit (Take Profit, Stop Loss, EOD, etc.)
        trade_date TEXT NOT NULL -- YYYY-MM-DD
    );
    ''')
    
    # Ensure indices for fast lookup
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON trades(status);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON trades(trade_date);')
    
    conn.commit()
    conn.close()
    log.info(f"Database initialized at {DB_PATH}")

def execute_query(query: str, parameters: tuple = (), fetchall=False, fetchone=False):
    """Utility to execute SQLite queries securely."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # Return dict-like rows
    cursor = conn.cursor()
    try:
        cursor.execute(query, parameters)
        conn.commit()
        if fetchall:
            return [dict(row) for row in cursor.fetchall()]
        if fetchone:
            res = cursor.fetchone()
            return dict(res) if res else None
    except Exception as e:
        log.error(f"Database error: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()

# Operations

def add_trade(symbol: str, option_type: str, strike: float, entry_price: float, reason: str = None):
    now = datetime.now()
    trade_date = now.strftime("%Y-%m-%d")
    
    # Check if a trade for this symbol/type/strike already exists today to avoid spam
    existing = execute_query(
        "SELECT id FROM trades WHERE symbol=? AND type=? AND strike=? AND trade_date=?",
        (symbol, option_type, strike, trade_date),
        fetchone=True
    )
    
    if existing:
        log.info(f"Paper Trade {symbol} {strike} {option_type} already logged today.")
        return False
        
    query = '''
    INSERT INTO trades 
    (symbol, type, strike, entry_time, entry_price, status, highest_price, lowest_price, current_price, trade_date, reason)
    VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?)
    '''
    execute_query(query, (symbol, option_type, strike, now.isoformat(), entry_price, entry_price, entry_price, entry_price, trade_date, reason))
    log.info(f"🟢 LOGGED PAPER TRADE: {symbol} {strike} {option_type} @ ₹{entry_price}")
    return True

def get_open_trades():
    return execute_query("SELECT * FROM trades WHERE status='OPEN'", fetchall=True)

def get_all_trades():
    return execute_query("SELECT * FROM trades ORDER BY id DESC LIMIT 200", fetchall=True)

def update_trade(trade_id: int, current_price: float, exit_flag: bool = False, reason: str = None):
    trade = execute_query("SELECT * FROM trades WHERE id=?", (trade_id,), fetchone=True)
    if not trade or trade['status'] != 'OPEN': return
    
    high = max(trade['highest_price'] or current_price, current_price)
    low = min(trade['lowest_price'] or current_price, current_price)
    
    if exit_flag:
        pnl = current_price - trade['entry_price']
        pnl_pct = (pnl / trade['entry_price']) * 100
        execute_query('''
            UPDATE trades 
            SET status='CLOSED', exit_time=?, exit_price=?, pnl=?, pnl_pct=?, highest_price=?, lowest_price=?, reason=? 
            WHERE id=?
        ''', (datetime.now().isoformat(), current_price, pnl, pnl_pct, high, low, reason, trade_id))
        emoji = "🥇" if pnl > 0 else "🛑"
        log.info(f"{emoji} CLOSED PAPER TRADE: {trade['symbol']} {trade['strike']} {trade['type']} @ ₹{current_price} | PnL: ₹{pnl:.2f} ({pnl_pct:.2f}%) | Reason: {reason}")
    else:
        execute_query('''
            UPDATE trades 
            SET highest_price=?, lowest_price=?, current_price=?
            WHERE id=?
        ''', (high, low, current_price, trade_id))

def get_trade_stats():
    trades = execute_query("SELECT * FROM trades WHERE status='CLOSED'", fetchall=True)
    if not trades:
        return {"total_trades": 0, "win_rate": 0, "total_pnl": 0}
        
    wins = [t for t in trades if t['pnl'] > 0]
    total_pnl = sum([t['pnl'] for t in trades])
    win_rate = (len(wins) / len(trades)) * 100
    
    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(trades) - len(wins),
        "win_rate_pct": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2)
    }
