"""
Tests for paper trading auto-accuracy: verifies that closing a trade
preserves the original reason prefix so get_trade_stats(trade_type="AUTO")
correctly identifies auto-created trades after they are closed.
"""

import os
import sqlite3
import pytest

# Use a temp DB so tests don't touch the real scanner.db
TEST_DB = os.path.join(os.path.dirname(__file__), "_test_paper.db")


@pytest.fixture(autouse=True)
def use_test_db(monkeypatch):
    """Redirect db module to a fresh temporary database for each test."""
    from backend import db

    # Override DB_PATH
    monkeypatch.setattr(db, "DB_PATH", TEST_DB)

    # Re-init the database
    db.init_db()
    yield

    # Cleanup
    try:
        os.remove(TEST_DB)
    except FileNotFoundError:
        pass
    for suffix in ("-wal", "-shm"):
        try:
            os.remove(TEST_DB + suffix)
        except FileNotFoundError:
            pass


class TestUpdateTradePreservesReason:
    """Ensure update_trade with exit_flag=True keeps the original reason prefix."""

    def test_auto_trade_reason_preserved_on_close(self):
        from backend import db

        # Create an auto-trade
        db.add_trade("NIFTY", "CE", 24000, 185.0, "Auto: BULLISH | Score 85 | PCR 1.2", lot_size=75)

        open_trades = db.get_open_trades()
        assert len(open_trades) == 1
        trade = open_trades[0]
        assert trade["reason"].startswith("Auto:")

        # Close the trade (simulating SL hit)
        db.update_trade(trade["id"], 150.0, exit_flag=True, reason="Stop Loss (-20%)")

        closed = db.get_closed_trades()
        assert len(closed) == 1
        closed_trade = closed[0]

        # The original "Auto:" prefix must still be present
        assert closed_trade["reason"].startswith("Auto:")
        assert "Stop Loss" in closed_trade["reason"]
        assert "Exit:" in closed_trade["reason"]

    def test_auto_trade_stats_count_after_close(self):
        from backend import db

        # Create and close an auto-trade
        db.add_trade("RELIANCE", "PE", 2500, 50.0, "Auto: BEARISH | Score 90 | PCR 0.6", lot_size=250)
        trades = db.get_open_trades()
        db.update_trade(trades[0]["id"], 75.0, exit_flag=True, reason="Take Profit (+50%)")

        # Auto stats should count this trade
        auto_stats = db.get_trade_stats(trade_type="AUTO")
        assert auto_stats["total"] == 1
        assert auto_stats["wins"] == 1

    def test_manual_trade_not_counted_as_auto(self):
        from backend import db

        # Create a manual trade
        db.add_trade("TCS", "CE", 3500, 100.0, "Suggestion trade: TCS CE 3500", lot_size=150)
        trades = db.get_open_trades()
        db.update_trade(trades[0]["id"], 120.0, exit_flag=True, reason="Manual close")

        auto_stats = db.get_trade_stats(trade_type="AUTO")
        assert auto_stats["total"] == 0

        manual_stats = db.get_trade_stats(trade_type="MANUAL")
        assert manual_stats["total"] == 1

    def test_eod_square_off_preserves_reason(self):
        from backend import db

        db.add_trade("BANKNIFTY", "CE", 52000, 300.0, "Auto: BULLISH | Score 92 | PCR 1.5", lot_size=30)
        trades = db.get_open_trades()
        db.update_trade(trades[0]["id"], 280.0, exit_flag=True, reason="EOD Square Off")

        closed = db.get_closed_trades()
        assert closed[0]["reason"].startswith("Auto:")
        assert "EOD Square Off" in closed[0]["reason"]

        auto_stats = db.get_trade_stats(trade_type="AUTO")
        assert auto_stats["total"] == 1

    def test_equity_curve_generated_for_auto_trades(self):
        from backend import db

        # Create two auto-trades, close them
        db.add_trade("NIFTY", "CE", 24000, 200.0, "Auto: BULLISH | Score 85", lot_size=75)
        db.add_trade("NIFTY", "PE", 23800, 100.0, "Auto: BEARISH | Score 82", lot_size=75)

        trades = db.get_open_trades()
        db.update_trade(trades[0]["id"], 250.0, exit_flag=True, reason="TP hit")
        db.update_trade(trades[1]["id"], 80.0, exit_flag=True, reason="SL hit")

        auto_stats = db.get_trade_stats(trade_type="AUTO")
        assert auto_stats["total"] == 2
        assert len(auto_stats["equity_curve"]) == 2
        assert "cumulative" in auto_stats["equity_curve"][0]
