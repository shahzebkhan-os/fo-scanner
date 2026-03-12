import os, asyncio, logging
from typing import Optional, List
from datetime import datetime, time as dtime
import json
import httpx, uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from pydantic import BaseModel
import csv, io

from . import db
from . import analytics as Analytics
from . import signals as Signals
from . import scheduler as Scheduler
from .analytics import compute_stock_score_v2 as compute_stock_score, score_option_v2 as score_option, black_scholes_greeks, days_to_expiry
from .signals import build_sector_heatmap, detect_uoa, screen_straddle, get_pcr_history

from .constants import (
    FO_STOCKS, INDEX_SYMBOLS, LOT_SIZES, NSE_HEADERS, SLUG_MAP,
    INDSTOCKS_BASE, NSE_BASE, MAX_DAILY_AUTO_TRADES, MAX_SECTOR_TRADES
)
from .data_source import (
    fetch_nse_chain, fetch_indstocks_ltp
)
from .backtest_runner import EODBacktester

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# Secure token logic
INDSTOCKS_TOKEN = os.getenv("INDSTOCKS_TOKEN", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Deduplication sets ────────
_traded_today: set  = set()
notified_signals: set = set()
_daily_trade_count: int = 0
_sector_trade_count: dict = {}

def _reset_daily_sets():
    global _traded_today, notified_signals, _daily_trade_count, _sector_trade_count
    _traded_today.clear()
    notified_signals.clear()
    _daily_trade_count = 0
    _sector_trade_count = {}

_last_reset_date = None

def _maybe_reset_daily():
    global _last_reset_date
    today = datetime.now(IST).date()
    if _last_reset_date != today:
        _last_reset_date = today
        _reset_daily_sets()

# ── Market Hours ──────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    """NSE is open Mon–Fri, 9:15 AM – 3:30 PM IST."""
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)

def is_optimal_trade_time() -> bool:
    """Avoid suboptimal entry times."""
    now = datetime.now(IST).time()
    if now < dtime(9, 30):       # Opening volatility
        return False
    if dtime(12, 0) <= now < dtime(13, 0):  # Lunch lull
        return False
    if now >= dtime(15, 0):      # Last 30 mins
        return False
    return True

def market_status() -> dict:
    now = datetime.now(IST)
    open_ = is_market_open()
    return {
        "open":     open_,
        "ist_time": now.strftime("%H:%M:%S"),
        "ist_date": now.strftime("%Y-%m-%d"),
        "weekday":  now.strftime("%A"),
        "message":  "Market OPEN" if open_ else "Market CLOSED (opens Mon–Fri 9:15 AM IST)",
    }

# ── Telegram Alerts ───────────────────────────────────────────────────────────

async def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload, timeout=8)
        except Exception as e:
            log.error(f"Telegram alert error: {e}")

async def send_telegram_document(filename: str, content: str, caption: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    files = {"document": (filename, content)}
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, data=data, files=files, timeout=12)
        except Exception as e:
            log.error(f"Telegram document error: {e}")

# ── Background Tasks ───────────────────────────────────────────────────────────

async def paper_trade_manager():
    """Background task to manage open paper trades with adaptive SL/TP."""
    log.info("Started Paper Trade Manager background loop.")
    while True:
        try:
            _maybe_reset_daily()
            if not is_market_open():
                await asyncio.sleep(300)
                continue

            open_trades   = db.get_open_trades()
            tracked_picks = db.get_tracked_picks()
            all_to_check  = open_trades + tracked_picks

            if all_to_check:
                symbols = list(set([t["symbol"] for t in all_to_check]))
                sem = asyncio.Semaphore(5)
                async def fetch_and_update(sym):
                    async with sem:
                        try:
                            return sym, await fetch_nse_chain(sym)
                        except Exception:
                            return sym, None

                results   = await asyncio.gather(*[fetch_and_update(s) for s in symbols])
                chain_map = {sym: data for sym, data in results if data}

                for trade in all_to_check:
                    sym   = trade["symbol"]
                    chain = chain_map.get(sym)
                    if not chain: continue

                    records = chain.get("records", {}).get("data", [])
                    spot    = chain.get("records", {}).get("underlyingValue")
                    if not records or not spot: continue

                    current_price = None
                    for row in records:
                        if row.get("strikePrice") == trade["strike"]:
                            opt_data = row.get(trade["type"])
                            if opt_data:
                                current_price = opt_data.get("lastPrice")
                            break

                    if not current_price: continue

                    if trade.get("status") == "TRACKED":
                        db.update_tracked_pick(trade["id"], current_price, stock_price=spot)
                        continue

                    # Adaptive SL/TP
                    entry = trade["entry_price"]
                    if entry <= 0: continue
                    pnl_pct = ((current_price - entry) / entry) * 100
                    db.update_trade(trade["id"], current_price)

                    now = datetime.now(IST)
                    if now.time() >= dtime(15, 15):
                        db.update_trade(trade["id"], current_price, exit_flag=True, reason="EOD Square Off")
                        continue

                    sl_pct, tp_pct = (-25.0, 50.0)
                    if entry < 20: sl_pct, tp_pct = (-40.0, 80.0)
                    elif entry >= 50: sl_pct, tp_pct = (-20.0, 40.0)

                    if pnl_pct >= 25: sl_pct = max(sl_pct, 10.0)

                    if pnl_pct <= sl_pct:
                        db.update_trade(trade["id"], current_price, exit_flag=True, reason=f"SL Hit ({sl_pct}%)")
                    elif pnl_pct >= tp_pct:
                        db.update_trade(trade["id"], current_price, exit_flag=True, reason=f"TP Hit ({tp_pct}%)")

            await asyncio.sleep(60)
        except Exception as e:
            log.error(f"Manager error: {e}")
            await asyncio.sleep(60)

async def _internal_scan() -> list:
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    ltp_map = await fetch_indstocks_ltp(all_symbols)
    sem = asyncio.Semaphore(5)

    async def process(symbol):
        async with sem:
            try:
                cj    = await fetch_nse_chain(symbol)
                recs  = cj.get("records", {})
                spot  = recs.get("underlyingValue") or ltp_map.get(symbol, {}).get("ltp") or 0
                try:
                    spot = float(spot)
                except (ValueError, TypeError):
                    spot = 0
                if spot == 0: return None
                ivr   = db.get_iv_rank(symbol)
                exp   = recs.get("expiryDates", [""])[0]
                stats = compute_stock_score(cj, spot, symbol, exp, ivr, prev_chain_data=None, fii_net=0.0)
                return {"symbol": symbol, "ltp": spot, **stats}
            except:
                return None

    raw = await asyncio.gather(*[process(s) for s in all_symbols])
    return [r for r in raw if r]

# ── API Initialization ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    Scheduler.init_scheduler(
        fetch_chain_fn    = fetch_nse_chain,
        send_telegram_fn  = send_telegram_alert,
        is_market_open_fn = is_market_open,
        scan_fn           = _internal_scan,
        all_symbols       = INDEX_SYMBOLS + FO_STOCKS,
    )
    asyncio.create_task(paper_trade_manager())
    await Scheduler.start_all()
    yield

app = FastAPI(title="NSE F&O Scanner API", version="4.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "4.0", "time": datetime.now().isoformat()}

@app.get("/api/scan")
async def scan_all(limit: int = Query(48, ge=1, le=100)):
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    log.info(f"=== SCAN: {len(all_symbols)} symbols ===")
    _maybe_reset_daily()

    ltp_map = await fetch_indstocks_ltp(all_symbols, token=INDSTOCKS_TOKEN)
    sem = asyncio.Semaphore(5)
    batch_alerts = []

    async def process(symbol: str):
        global _daily_trade_count, _sector_trade_count
        async with sem:
            try:
                cj = await fetch_nse_chain(symbol)
                recs = cj.get("records", {})
                spot = recs.get("underlyingValue") or ltp_map.get(symbol, {}).get("ltp") or 0
                try:
                    spot = float(spot)
                except (ValueError, TypeError):
                    spot = 0
                if not spot: return None

                ivr = db.get_iv_rank(symbol)
                exp = recs.get("expiryDates", [""])[0]
                stats = compute_stock_score(cj, float(spot), symbol, exp, ivr, prev_chain_data=None, fii_net=0.0)

                stock_score = stats.get("score", 0)
                signal = stats.get("signal", "NEUTRAL")
                top_picks = stats.get("top_picks", [])

                # Auto trade logic
                if (stock_score >= 85 and signal != "NEUTRAL" and is_market_open() and is_optimal_trade_time()
                    and _daily_trade_count < MAX_DAILY_AUTO_TRADES):
                    from .signals import get_sector
                    sector = get_sector(symbol)
                    if _sector_trade_count.get(sector, 0) < MAX_SECTOR_TRADES:
                        for pick in top_picks[:1]:
                            if (signal == "BULLISH" and pick["type"] == "CE") or (signal == "BEARISH" and pick["type"] == "PE"):
                                uid = f"{symbol}-{pick['type']}-{pick['strike']}-{datetime.now(IST).date()}"
                                if uid not in _traded_today:
                                    _traded_today.add(uid)
                                    db.add_trade(symbol, pick["type"], pick["strike"], pick["ltp"], f"Auto: {signal} Score {stock_score}", LOT_SIZES.get(symbol, 1))
                                    _daily_trade_count += 1
                                    _sector_trade_count[sector] = _sector_trade_count.get(sector, 0) + 1

                # Alerts
                if stock_score >= 70 and signal != "NEUTRAL":
                    for pick in top_picks:
                        if (signal == "BULLISH" and pick["type"] == "CE") or (signal == "BEARISH" and pick["type"] == "PE"):
                            uid = f"{symbol}-{pick['type']}-{pick['strike']}-{datetime.now(IST).date()}"
                            if uid not in notified_signals:
                                notified_signals.add(uid)
                                reasons = " | ".join(stats.get("signal_reasons", []))
                                batch_alerts.append(f"{symbol},{signal},{stock_score},{pick['strike']} {pick['type']},{pick['ltp']},{reasons}")

                return {"symbol": symbol, "ltp": round(spot, 2), **stats}
            except Exception as e:
                log.error(f"Process {symbol}: {e}")
                return None

    results = await asyncio.gather(*[process(s) for s in all_symbols[:limit]])
    res = [r for r in results if r]
    res.sort(key=lambda x: x["score"], reverse=True)

    if batch_alerts:
        content = "Symbol,Signal,Score,Contract,LTP,Reasons\n" + "\n".join(batch_alerts)
        asyncio.create_task(send_telegram_document("alerts.csv", content, f"🚀 {len(batch_alerts)} High Confidence Signals"))

    return {"timestamp": datetime.now().isoformat(), "market_status": market_status(), "count": len(res), "data": res}

# ── Tracker & Portfolio Endpoints ──────────────────────────────────────────────


# ── CSV Auto-Export Sessions ──────────────────────────────────────────────────

@app.get("/api/tracker/csv-exports")
async def list_csv_exports(limit: int = Query(100, ge=1, le=500)):
    """List all auto-saved CSV exports with metadata."""
    return {"exports": db.get_csv_exports(limit)}

@app.get("/api/tracker/csv-exports/{export_id}")
async def get_csv_export_detail(export_id: int):
    """Get metadata for a specific CSV export."""
    export = db.get_csv_export(export_id)
    if not export:
        raise HTTPException(404, "CSV export not found")
    return export

@app.get("/api/tracker/csv-exports/{export_id}/download")
async def download_csv_export(export_id: int):
    """Download a specific auto-saved CSV file."""
    export = db.get_csv_export(export_id)
    if not export:
        raise HTTPException(404, "CSV export not found")
    filepath = export.get("filepath", "")
    if not os.path.exists(filepath):
        raise HTTPException(404, "CSV file not found on disk")
    return FileResponse(filepath, media_type="text/csv", filename=export.get("filename", "accuracy.csv"))

@app.delete("/api/tracker/csv-exports/{export_id}")
async def delete_csv_export_endpoint(export_id: int):
    """Delete a specific CSV export record and file."""
    filepath = db.delete_csv_export(export_id)
    if filepath is None:
        raise HTTPException(404, "CSV export not found")
    # Delete file from disk too
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        log.warning(f"Could not delete CSV file {filepath}: {e}")
    return {"status": "ok"}

@app.get("/api/tracker/snapshot/{snapshot_id}/trades-with-history")
async def get_snapshot_trades_with_history(snapshot_id: int):
    """Get trades for a snapshot with full 5-min price history."""
    trades = db.get_accuracy_trades_with_history(snapshot_id)
    if not trades:
        raise HTTPException(404, "No trades found for this snapshot")
    return {"snapshot_id": snapshot_id, "trades": trades}

@app.get("/api/portfolio")
async def get_portfolio():
    stats = db.get_trade_stats()
    open_trades = db.get_open_trades()
    unrealised = sum(((t["current_price"] or t["entry_price"]) - t["entry_price"]) * (t["lot_size"] or 1) for t in open_trades if t["entry_price"])
    return {"closed_trades": stats, "open_positions": len(open_trades), "unrealised_pnl": round(unrealised, 2), "capital": db.get_capital()}

# ── Chains & Greeks ───────────────────────────────────────────────────────────

@app.get("/api/chain/{symbol}")
async def get_chain(symbol: str, expiry: str = None):
    symbol = symbol.upper()
    data = await fetch_nse_chain(symbol)
    recs = data.get("records", {})
    spot, rows, exps = recs.get("underlyingValue", 0), recs.get("data", []), recs.get("expiryDates", [])
    if not rows: raise HTTPException(404, "No data for " + symbol)
    if expiry: rows = [r for r in rows if r["expiryDate"] == expiry]

    stats = compute_stock_score(data, spot, symbol, expiry or (exps[0] if exps else ""), db.get_iv_rank(symbol), None, 0)
    picks = {f"{p['strike']}-{p['type']}": p["score"] for p in stats.get("top_picks", [])}

    strikes = []
    for r in rows:
        strike, ce, pe = r["strikePrice"], r.get("CE", {}), r.get("PE", {})
        strikes.append({
            "strike": strike, "isATM": abs(strike-spot) <= spot*0.012, "expiryDate": r["expiryDate"],
            "CE": {**ce, "score": picks.get(f"{strike}-CE", 0)}, "PE": {**pe, "score": picks.get(f"{strike}-PE", 0)}
        })
    return {"symbol": symbol, "spot": round(spot, 2), "expiry": expiry or (exps[0] if exps else ""), "expiries": exps[:6], "strikes": strikes, "top_picks": stats.get("top_picks", [])[:4]}

@app.get("/api/greeks/{symbol}")
async def get_greeks(symbol: str, expiry: str = None):
    symbol = symbol.upper()
    data = await fetch_nse_chain(symbol)
    recs = data.get("records", {})
    spot, rows, exps = recs.get("underlyingValue", 0), recs.get("data", []), recs.get("expiryDates", [])
    if not rows: raise HTTPException(404)
    sel_exp = expiry or (exps[0] if exps else "")
    dte = days_to_expiry(sel_exp)
    res = []
    for r in rows:
        strike, ce, pe = r["strikePrice"], r.get("CE", {}) or {}, r.get("PE", {}) or {}
        iv = ce.get("impliedVolatility", 0) or pe.get("impliedVolatility", 0) or 20
        res.append({"strike": strike, "CE": {**ce, "greeks": black_scholes_greeks(spot, strike, iv, dte, "CE")},
                    "PE": {**pe, "greeks": black_scholes_greeks(spot, strike, iv, dte, "PE")}})
    return {"symbol": symbol, "spot": spot, "expiry": sel_exp, "dte": dte, "strikes": res}

# ── Analytics & History ───────────────────────────────────────────────────────

@app.get("/api/ivrank/{symbol}")
async def get_ivr(symbol: str): return db.get_iv_rank(symbol.upper())

@app.get("/api/oi-heatmap/{symbol}")
async def get_heatmap(symbol: str, date: str = None): return {"symbol": symbol.upper(), "data": db.get_oi_heatmap(symbol.upper(), date)}

@app.get("/api/oi-timeline/{symbol}")
async def get_timeline(symbol: str, strike: float = None, type: str = "CE"):
    symbol = symbol.upper()
    if not strike:
        cj = await fetch_nse_chain(symbol)
        strike = Analytics.nearest_atm(cj.get("records", {}).get("underlyingValue", 0), symbol)
    return {"symbol": symbol, "strike": strike, "type": type, "timeline": db.get_oi_timeline(symbol, strike, type.upper())}

@app.get("/api/pcr-history/{symbol}")
async def get_pcr(symbol: str): return {"symbol": symbol.upper(), "timeline": get_pcr_history(symbol.upper())}

@app.get("/api/uoa")
async def get_uoa(threshold: float = 5.0):
    all_syms, res, sem = INDEX_SYMBOLS + FO_STOCKS, [], asyncio.Semaphore(5)
    async def chk(s):
        async with sem:
            try:
                cj = await fetch_nse_chain(s)
                return detect_uoa(cj.get("records", {}).get("data", []), s, cj["records"]["underlyingValue"], threshold)
            except: return []
    raw = await asyncio.gather(*[chk(s) for s in all_syms])
    for r in raw: res.extend(r)
    res.sort(key=lambda x: x.get("ratio", 0), reverse=True)
    return {"data": res[:50]}

@app.get("/api/straddle-screen")
async def get_straddle():
    all_syms, res, sem = INDEX_SYMBOLS + FO_STOCKS, [], asyncio.Semaphore(5)
    async def chk(s):
        async with sem:
            try:
                cj = await fetch_nse_chain(s)
                recs, spot, exps = cj["records"]["data"], cj["records"]["underlyingValue"], cj["records"]["expiryDates"]
                ivr = db.get_iv_rank(s)
                stats = compute_stock_score(cj, spot, s, exps[0], ivr, None, 0)
                sr = screen_straddle(recs, s, spot, exps[0], stats["pcr"], stats["iv"])
                if sr: sr["score"], sr["iv_rank"] = stats["score"], ivr["iv_rank"]
                return sr
            except: return None
    raw = await asyncio.gather(*[chk(s) for s in all_syms])
    res = [r for r in raw if r]
    res.sort(key=lambda x: x["iv"], reverse=True)
    return {"candidates": res}

@app.get("/api/sector-heatmap")
async def get_sector_hm():
    res = await _internal_scan()
    hm = build_sector_heatmap(res)
    deals = Signals.get_deals_for_scan(res)
    for s in hm.values():
        for sy in s["symbols"]:
            if sy["symbol"] in deals: sy["bulk_deals"] = len(deals[sy["symbol"]])
    return {"sectors": hm}

# ── Utility & Settings ────────────────────────────────────────────────────────

@app.get("/api/lot-sizes")
async def get_lots(): return LOT_SIZES

@app.get("/api/settings")
async def get_all_settings():
    return {
        "watchlist": db.get_watchlist(),
        "capital": db.get_capital(),
        "refresh_interval": db.get_setting("refresh_interval", 60),
        "min_score": db.get_setting("min_score", 85),
        "max_positions": db.get_setting("max_positions", 5),
        "stop_loss": db.get_setting("stop_loss", 25)
    }

@app.post("/api/settings")
async def save_all_settings(req: dict):
    if "watchlist" in req: db.set_watchlist(req["watchlist"])
    if "capital" in req: db.set_capital(float(req["capital"]))
    if "refresh_interval" in req: db.set_setting("refresh_interval", int(req["refresh_interval"]))
    if "min_score" in req: db.set_setting("min_score", int(req["min_score"]))
    if "max_positions" in req: db.set_setting("max_positions", int(req["max_positions"]))
    if "stop_loss" in req: db.set_setting("stop_loss", float(req["stop_loss"]))
    return {"status": "ok"}

@app.get("/api/settings/watchlist")
async def get_wl(): return {"watchlist": db.get_watchlist()}

@app.post("/api/settings/watchlist")
async def set_wl(symbols: List[str]): db.set_watchlist(symbols); return {"status": "ok"}

@app.get("/api/bulk-deals")
async def get_deals(symbol: str = None): return {"data": db.get_bulk_deals(symbol.upper() if symbol else None)}

@app.get("/api/fii-dii")
async def get_fii():
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as c:
            await c.get("https://www.nseindia.com")
            r = await c.get("https://www.nseindia.com/api/fiidiiTradeReact")
            return {"data": [row for row in r.json() if row.get("category") in ("FII/FPI", "DII")]}
    except: return {"data": []}

# ── Historical Backtest ───────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    start: str = "2023-01-01"
    end: str = "2024-12-31"
    score: int = 20
    confidence: float = 0
    tp: float = 40
    sl: float = 25
    signal: str = "ALL"
    regime: str = "ALL"
    symbols: str = ""

@app.post("/api/historical-backtest")
async def run_historical_backtest(req: BacktestRequest):
    db_path = os.path.join(os.path.dirname(__file__), "scanner.db")
    if not os.path.exists(db_path):
        raise HTTPException(400, "scanner.db not found – load historical data first")
    try:
        bt = EODBacktester(db_path)
        signal_filter = req.signal if req.signal not in ("ALL", "") else None
        regime_filter = req.regime if req.regime not in ("ALL", "") else None
        symbols = [s.strip() for s in req.symbols.split(",") if s.strip()] or None
        result = bt.run(
            start_date=req.start,
            end_date=req.end,
            score_threshold=req.score,
            confidence_threshold=req.confidence,
            tp_pct=req.tp,
            sl_pct=req.sl,
            signal_filter=signal_filter,
            regime_filter=regime_filter,
            symbols=symbols,
        )
        data = result.to_dict()
        if "error" in data:
            return data
        s = data["summary"]
        # Flatten top-level fields the frontend expects, plus full detail
        return {
            "win_rate": round(s["win_rate"], 1),
            "total_trades": s["total"],
            "avg_pnl": round(s["expectancy"], 2),
            "wins": s["wins"],
            "losses": s["losses"],
            "avg_win": round(s["avg_win"], 2),
            "avg_loss": round(s["avg_loss"], 2),
            "profit_factor": round(s["profit_factor"], 2),
            "max_drawdown_pct": round(s["max_drawdown_pct"], 1),
            "sharpe": s["sharpe"],
            "significant": s["significant"],
            "by_signal": data.get("by_signal", {}),
            "by_regime": data.get("by_regime", {}),
            "by_dte": data.get("by_dte", {}),
            "top_symbols": data.get("top_symbols", []),
            "equity_curve": data.get("equity_curve", []),
        }
    except Exception as e:
        log.exception("Backtest failed")
        raise HTTPException(500, str(e))

@app.get("/api/paper-trades/active")
async def pt_active(): return db.get_open_trades()

@app.get("/api/paper-trades/history")
async def pt_history(): return db.get_closed_trades()

@app.post("/api/paper-trades")
async def pt_add(req: dict):
    db.add_trade(req["symbol"], req["type"], req["strike"], req["entry_price"], req.get("reason", "Manual"), req.get("lots", 0))
    return {"status": "ok"}

@app.post("/api/paper-trades/{trade_id}/exit")
async def pt_exit(trade_id: int, exit_price: Optional[float] = None):
    # If exit_price not provided, we should ideally fetch current ltp,
    # but for manual exit button, let's assume it's passed or use current_price from DB
    if exit_price is None:
        open_trades = db.get_open_trades()
        for t in open_trades:
            if t["id"] == trade_id:
                exit_price = t.get("current_price") or t["entry_price"]
                break
    db.update_trade(trade_id, exit_price or 0, exit_flag=True, reason="Manual Exit")
    return {"status": "ok"}

@app.post("/api/paper-trades/{trade_id}/note")
async def pt_note(trade_id: int, note: str):
    db.add_trade_note(trade_id, note)
    return {"status": "ok"}

@app.get("/api/paper-trades/export")
async def pt_export():
    trades = db.get_all_trades()
    out = io.StringIO()
    if trades:
        dw = csv.DictWriter(out, fieldnames=trades[0].keys())
        dw.writeheader(); dw.writerows(trades)
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=trades.csv"})

# ── Frontend ──────────────────────────────────────────────────────────────────

dist_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/"): raise HTTPException(404)
    idx = os.path.join(dist_path, "index.html")
    if os.path.exists(idx): return FileResponse(idx)
    return {"error": "Frontend not found"}

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)
