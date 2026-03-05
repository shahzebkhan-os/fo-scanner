import sqlite3
import re
from backend.main import LOT_SIZES

def backfill():
    conn = sqlite3.connect('backend/trades.db')
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, symbol, reason, lot_size, score FROM trades WHERE status='TRACKED'").fetchall()
    
    for r in rows:
        t_id = r['id']
        sym = r['symbol']
        reason = r['reason'] or ''
        
        # Parse score from reason
        score_val = r['score']
        if score_val == 0 and sum(1 for _ in re.finditer(r'Score:\s*(\d+)', reason)) > 0:
            match = re.search(r'Score:\s*(\d+)', reason)
            if match:
                score_val = int(match.group(1))
                
        # Parse lot size
        lot = r['lot_size']
        if lot == 0:
            lot = LOT_SIZES.get(sym, 0)
            
        conn.execute("UPDATE trades SET lot_size=?, score=? WHERE id=?", (lot, score_val, t_id))
    
    conn.commit()
    conn.close()
    print("Backfill completed.")

if __name__ == "__main__":
    backfill()
