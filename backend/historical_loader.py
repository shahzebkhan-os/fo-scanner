"""
NSE F&O Historical Loader
Downloads historical bhavcopies, reconstructs features, and loads into SQLite.
"""

import os
import sys
import time
import argparse
import logging
import sqlite3
import pandas as pd
import numpy as np
from collections import deque
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from pathlib import Path
from math import log, sqrt, exp
import requests
import zipfile
import io

try:
    from jugaad_data.nse import bhavcopy_fo_save
except ImportError:
    print("WARNING: jugaad_data missing. Falling back to direct NSE archive downloads for pre-Jul-2024 dates.")
    bhavcopy_fo_save = None

try:
    import yfinance as yf
except ImportError:
    print("WARNING: yfinance missing. Missing Spot limits will occur.")
    yf = None

try:
    from tqdm import tqdm
except ImportError:
    # Fallback if tqdm is not available
    class tqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total
            self.desc = desc
            self.n = 0

        def __iter__(self):
            return iter(self.iterable) if self.iterable else self

        def __next__(self):
            raise StopIteration

        def update(self, n=1):
            self.n += n

        def set_postfix(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

# ── CONFIGURATION ────────────────────────────────────────────────────────────

try:
    from .constants import FO_STOCKS, INDEX_SYMBOLS
except ImportError:
    from constants import FO_STOCKS, INDEX_SYMBOLS

CONFIG = {
    "symbols": FO_STOCKS + INDEX_SYMBOLS,
    "start_date": "2023-01-01",
    "end_date":   "2024-12-31",
    "data_dir":   os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "historical_data"),
    "db_path":    os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner.db"),
    "rate_limit_seconds": 1.5,
    "max_retries": 3,
    "batch_size": 30,
    "pause_between_batches": 5,
}

try:
    from .analytics import compute_stock_score_v2, black_scholes_greeks, nearest_atm
except ImportError:
    from analytics import compute_stock_score_v2, black_scholes_greeks, nearest_atm

# Known NSE Holidays for 2023 & 2024
NSE_HOLIDAYS = {
    # 2023
    date(2023, 1, 26), date(2023, 3, 7), date(2023, 3, 30), date(2023, 4, 4),
    date(2023, 4, 7), date(2023, 4, 14), date(2023, 5, 1), date(2023, 6, 28),
    date(2023, 8, 15), date(2023, 9, 19), date(2023, 10, 2), date(2023, 10, 24),
    date(2023, 11, 14), date(2023, 11, 27), date(2023, 12, 25),
    # 2024
    date(2024, 1, 26), date(2024, 3, 8), date(2024, 3, 25), date(2024, 3, 29),
    date(2024, 4, 11), date(2024, 4, 17), date(2024, 5, 1), date(2024, 6, 17),
    date(2024, 7, 17), date(2024, 8, 15), date(2024, 10, 2), date(2024, 11, 1),
    date(2024, 11, 15), date(2024, 12, 25),
    # 2025
    date(2025, 1, 26), date(2025, 2, 26), date(2025, 3, 14), date(2025, 3, 31),
    date(2025, 4, 6), date(2025, 4, 10), date(2025, 4, 14), date(2025, 4, 18),
    date(2025, 5, 1), date(2025, 6, 7), date(2025, 7, 6), date(2025, 8, 15),
    date(2025, 8, 27), date(2025, 10, 2), date(2025, 10, 21), date(2025, 10, 22),
    date(2025, 11, 5), date(2025, 12, 25)
}

# ── LOGGING ──────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

os.makedirs(CONFIG["data_dir"], exist_ok=True)


# ── HELPER: NEXT TRADING DAY ─────────────────────────────────────────────────

def next_trading_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5 or nxt in NSE_HOLIDAYS:
        nxt += timedelta(days=1)
    return nxt

def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NSE_HOLIDAYS


# ── STEP 1B: SPOT PRICE DOWNLOADER ───────────────────────────────────────────

def download_spot_prices(symbols: list, start_date_str: str, end_date_str: str, data_dir: str) -> dict:
    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    out_file = os.path.join(data_dir, "spot_prices.json")

    existing_data = {}
    if os.path.exists(out_file):
        import json
        with open(out_file, "r") as f:
            existing_data = json.load(f)

    if yf is None:
        logger.info(f"Loaded existing spot prices from {out_file} (yfinance missing)")
        return existing_data

    logger.info(f"Fetching spot prices from {start_date_str} to {end_date_str}...")
    logger.info(f"Downloading spot prices from {start} to {end}...")

    # Mapping to Yahoo Finance tickers — ordered fallback lists per symbol.
    # yfinance is flaky; the first ticker that returns data wins.
    yf_fallbacks = {
        "NIFTY":      ["^NSEI"],
        "BANKNIFTY":  ["^NSEBANK"],
        "FINNIFTY":   ["NIFTY_FIN_SERVICE.NS", "^CNXFIN"],
        "TATAMOTORS": ["TMPV.NS", "TATAMOTORS.NS", "TATAMTRDVR.NS", "TATAMOTORS.BO", "TTM"],
        "MM":         ["M&M.NS", "M&M.BO", "MM.NS"],
    }

    end_buf = (end + timedelta(days=1)).strftime("%Y-%m-%d")

    for sym in symbols:
        # Already have enough data for this symbol? Skip the download.
        if sym in existing_data and len(existing_data[sym]) > 200:
            logger.info(f"  {sym}: using {len(existing_data[sym])} cached prices (skip download)")
            continue

        candidates = yf_fallbacks.get(sym, [f"{sym}.NS"])
        downloaded = False

        for yf_ticker in candidates:
            logger.info(f"  Fetching {sym} → {yf_ticker} ...")
            try:
                ticker_df = yf.download(yf_ticker, start=start_date_str, end=end_buf, progress=False)
                if ticker_df.empty:
                    logger.warning(f"    {yf_ticker}: empty data, trying next fallback")
                    continue

                ticker_df.index = pd.to_datetime(ticker_df.index).strftime("%Y-%m-%d")

                # yfinance MultiIndex output handling (newer versions)
                if isinstance(ticker_df.columns, pd.MultiIndex):
                    close_series = ticker_df[("Close", yf_ticker)]
                else:
                    close_series = ticker_df["Close"]

                new_prices = close_series.to_dict()

                if sym not in existing_data:
                    existing_data[sym] = new_prices
                else:
                    existing_data[sym].update(new_prices)

                logger.info(f"    ✅ {sym}: got {len(new_prices)} prices via {yf_ticker}")
                downloaded = True
                break  # success — stop trying fallbacks

            except Exception as e:
                logger.warning(f"    {yf_ticker} failed: {e}")

            time.sleep(0.5)

        if not downloaded:
            if sym in existing_data and existing_data[sym]:
                logger.warning(f"  ⚠️  {sym}: all tickers failed, using {len(existing_data[sym])} cached prices")
            else:
                logger.error(f"  ❌ {sym}: no spot data available (all tickers failed, no cache)")

        time.sleep(0.5)

    with open(out_file, "w") as f:
        import json
        json.dump(existing_data, f)

    loaded = {s: len(v) for s, v in existing_data.items() if v}
    logger.info(f"Spot prices ready: {loaded}")
    return existing_data


# ── STEP 1C: BHAVCOPY DOWNLOADER ─────────────────────────────────────────────

def _http_download_bhavcopy(url: str, fpath: str):
    """Download a bhavcopy ZIP from the given NSE archive URL and save as CSV."""
    s = requests.Session()
    headers = {'User-Agent': 'Mozilla/5.0'}
    s.get("https://www.nseindia.com/all-reports", headers=headers, timeout=10)
    r = s.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csv_name = next((n for n in z.namelist() if n.endswith(".csv")), z.namelist()[0])
        with z.open(csv_name) as f:
            df = pd.read_csv(f)
            df.to_csv(fpath, index=False)


def _download_single_bhavcopy(d: date, data_dir: str):
    # jugaad_data format: fo01Aug2023bhav.csv
    fname = f"fo{d.strftime('%d%b%Y')}bhav.csv"
    fpath = os.path.join(data_dir, "bhavcopies", fname)
    if os.path.exists(fpath):
        return fpath

    retries = 0
    while retries < CONFIG["max_retries"]:
        try:
            if d >= date(2024, 7, 8):
                # NSE changed its entire API/URL structure for Bhavcopies on July 8, 2024
                dt_str = d.strftime("%Y%m%d")
                url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{dt_str}_F_0000.csv.zip"
                _http_download_bhavcopy(url, fpath)
            elif bhavcopy_fo_save is not None:
                bhavcopy_fo_save(d, os.path.join(data_dir, "bhavcopies"))
            else:
                # jugaad_data not installed — fall back to direct NSE archive download
                mon = d.strftime("%b").upper()
                yr = d.strftime("%Y")
                day = d.strftime("%d")
                zip_fname = f"fo{day}{mon}{yr}bhav.csv.zip"
                url = f"https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{yr}/{mon}/{zip_fname}"
                _http_download_bhavcopy(url, fpath)

            time.sleep(float(CONFIG["rate_limit_seconds"]) / 3)
            return fpath
        except Exception as e:
            retries += 1
            time.sleep(2 ** retries)
            if retries == CONFIG["max_retries"]:
                logger.warning(f"\nFailed to download {d} after {retries} retries: {e}")
                return None
    return None

def download_bhavcopy_range(start_date_str: str, end_date_str: str, data_dir: str) -> list:
    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    curr = start
    dates_to_fetch = []
    while curr <= end:
        if is_trading_day(curr):
            dates_to_fetch.append(curr)
        curr += timedelta(days=1)

    successful = []
    total = len(dates_to_fetch)
    os.makedirs(os.path.join(data_dir, "bhavcopies"), exist_ok=True)

    logger.info(f"Downloading {total} bhavcopy days concurrently...")

    import concurrent.futures
    max_workers = 5
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_download_single_bhavcopy, d, data_dir): d for d in dates_to_fetch}
        
        for i, future in enumerate(concurrent.futures.as_completed(futures)):
            d = futures[future]
            try:
                res = future.result()
                if res:
                    successful.append(res)
            except Exception as e:
                logger.warning(f"\nError downloading {d}: {e}")
            
            progress = int(((i + 1) / total) * 20)
            bar = "=" * progress + ">" + " " * (20 - progress)
            sys.stdout.write(f"\r[{bar}] {i + 1}/{total}")
            sys.stdout.flush()

    sys.stdout.write(f"\n✅ Downloaded {len(successful)}/{total} dates.\n")
    return successful


# ── STEP 1D: KAGGLE DATA LOADER ──────────────────────────────────────────────

def load_kaggle_csv(file_path: str) -> pd.DataFrame:
    df = pd.read_csv(file_path, low_memory=False)
    df.columns = df.columns.str.strip()

    # Translate modern NSE July 2024+ formatting back to legacy
    if "TckrSymb" in df.columns:
        df.rename(columns={
            "FinInstrmTp": "INSTRUMENT",
            "TckrSymb": "SYMBOL",
            "XpryDt": "EXPIRY_DT",
            "StrkPric": "STRIKE_PR",
            "OptnTp": "OPTION_TYP",
            "OpnPric": "OPEN",
            "HghPric": "HIGH",
            "LwPric": "LOW",
            "ClsPric": "CLOSE",
            "PrvsClsgPric": "SETTLE_PR",
            "TtlTradgVol": "CONTRACTS",
            "OpnIntrst": "OPEN_INT",
            "ChngInOpnIntrst": "CHG_IN_OI",
            "TradDt": "TIMESTAMP"
        }, inplace=True)
        # Map IDs
        inst_map = {"IDO": "OPTIDX", "STO": "OPTSTK", "IDF": "FUTIDX", "STF": "FUTSTK"}
        df["INSTRUMENT"] = df["INSTRUMENT"].map(inst_map)

    df = df[df["INSTRUMENT"].isin(["OPTIDX", "OPTSTK"])]
    df = df[df["OPTION_TYP"].isin(["CE", "PE"])]
    df = df[(df["OPEN_INT"] > 0) | (df["CLOSE"] > 0)]
    df = df[df["STRIKE_PR"] > 0]

    df["EXPIRY_DT"] = pd.to_datetime(df["EXPIRY_DT"], format="mixed", dayfirst=True).dt.strftime("%Y-%m-%d")
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], format="mixed", dayfirst=True).dt.strftime("%Y-%m-%d")
    df["CHG_IN_OI"] = df["CHG_IN_OI"].fillna(0)

    # Clean strike
    df["STRIKE_PR"] = pd.to_numeric(df["STRIKE_PR"]).astype(float)

    cols = {
        "TIMESTAMP": "trade_date", "SYMBOL": "symbol", "EXPIRY_DT": "expiry_date",
        "STRIKE_PR": "strike", "OPTION_TYP": "opt_type", "OPEN": "open",
        "HIGH": "high", "LOW": "low", "CLOSE": "close", "SETTLE_PR": "settle_price",
        "CONTRACTS": "volume", "OPEN_INT": "open_interest", "CHG_IN_OI": "chg_in_oi"
    }

    df = df.rename(columns=cols)
    df["ltp"] = df["close"].where(df["close"] > 0, df["settle_price"])
    return df

def merge_data_sources(bhavcopy_dir: str, kaggle_files: list, symbols: list) -> pd.DataFrame:
    dfs = []
    # Kaggle
    for kf in kaggle_files:
        if os.path.exists(kf):
            dfs.append(load_kaggle_csv(kf))

    # Bhavcopies
    for root, _, files in os.walk(bhavcopy_dir):
        for f in files:
            if f.endswith(".csv"):
                df = load_kaggle_csv(os.path.join(root, f))
                dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    combo = pd.concat(dfs, ignore_index=True)
    combo = combo[combo["symbol"].isin(symbols)]
    combo = combo.drop_duplicates(subset=["trade_date", "symbol", "expiry_date", "strike", "opt_type"])
    
    logger.info(f"Merged {len(dfs)} data sources. Total rows after filtering: {len(combo)}")
    return combo


# ── STEP 2A: IV & GREEKS RECONSTRUCTION ──────────────────────────────────────

def _bs_price(S, K, T, r, sigma, opt_type):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, S - K) if opt_type == 'CE' else max(0.0, K - S)
    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)

    from scipy.stats import norm
    if opt_type == "CE": return S * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
    else: return K * exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def _bs_vega(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    from scipy.stats import norm
    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    return S * norm.pdf(d1) * sqrt(T)

def _smart_iv_initial_guess(spot, strike, opt_type):
    """
    Improved initial IV guess based on moneyness.
    Reduces Newton-Raphson iterations by 20-30%.
    """
    moneyness = spot / strike

    if opt_type == "CE":
        # Call options
        if moneyness > 1.05:  # ITM (In The Money)
            return 0.25
        elif moneyness < 0.95:  # OTM (Out of The Money)
            return 0.40
        else:  # ATM (At The Money)
            return 0.30
    else:  # PE
        # Put options
        if moneyness < 0.95:  # ITM
            return 0.25
        elif moneyness > 1.05:  # OTM
            return 0.40
        else:  # ATM
            return 0.30

def compute_implied_volatility(market_price, spot, strike, dte, opt_type, r=0.065, max_iter=100, tol=1e-6):
    if market_price <= 0 or spot <= 0 or strike <= 0: return None
    T = max(dte, 0.5) / 365.0

    # Smart initial guess based on moneyness (20-30% faster convergence)
    iv = _smart_iv_initial_guess(spot, strike, opt_type)

    for _ in range(max_iter):
        price = _bs_price(spot, strike, T, r, iv, opt_type)
        vega = _bs_vega(spot, strike, T, r, iv)
        if abs(vega) < 1e-12: break

        diff = price - market_price
        if abs(diff) < tol: return max(0.01, min(iv * 100, 500.0))

        step = diff / vega
        # Dampen large steps to prevent overflow
        if abs(step) > 1.0:
            step = 1.0 if step > 0 else -1.0
        iv -= step

        # Clamp iv to a sane range
        if iv <= 0.001: iv = 0.001
        if iv > 5.0: iv = 5.0

    result = iv * 100
    if result != result:  # NaN check
        return None
    return max(0.01, min(result, 500.0))

# ── FEATURE PIPELINE ─────────────────────────────────────────────────────────

def reconstruct_features(raw_df: pd.DataFrame, spot_prices: dict) -> pd.DataFrame:
    """
    LIMITATION 1: EOD data only
        This snapshot represents EOD conditions only.
        Intraday OI buildup, IV crush during the day,
        and actual entry timing are not captured.

    LIMITATION 2: IV reconstruction accuracy
        Reconstructed IV uses EOD settlement prices.
        Accuracy suffers near expiry without exact tick data.
    """
    snapshots = []
    prev_spot_map = {}  # Track previous spot for spot_change_pct

    # Needs to be sorted chronologically for DTE tracking
    raw_df = raw_df.sort_values(by="trade_date")

    # PRE-CALCULATE LOOKUP TABLE (Massive performance boost for next-day labeling)
    # This prevents filtering raw_df in every loop iteration (O(N^2) -> O(N))
    logger.info("Building price lookup table...")
    price_lookup = {}
    for row in raw_df[["trade_date", "symbol", "strike", "opt_type", "ltp"]].itertuples(index=False):
        price_lookup[(row.trade_date, row.symbol, row.strike, row.opt_type)] = row.ltp

    # Group by symbol first, then trade_date to maintain prev_spot_map context across dates
    grouped_syms = raw_df.groupby(["symbol", "trade_date"])
    total_len = len(grouped_syms)

    logger.info(f"Reconstructing {total_len} snapshots with progress tracking...")

    # Per-symbol rolling IV history for iv_rank computation (252-bar lookback ≈ 1 year)
    iv_history_per_symbol: dict = {}

    # Use tqdm for better progress visualization
    with tqdm(total=total_len, desc="Processing snapshots", unit="snapshot") as pbar:
        for i, ((sym, tdate), day_df) in enumerate(grouped_syms):
            pbar.set_postfix(symbol=sym, date=tdate)

            spot_history = spot_prices.get(sym, {})
            spot = spot_history.get(tdate, 0)

            # HEURISTIC: Fix yfinance adjusted prices (e.g. BAJFINANCE 650 -> 6500)
            # If the spot is ~10x smaller than the strike range, scale it up.
            if spot > 0 and not day_df.empty:
                avg_strike = day_df["strike"].median()
                if avg_strike > 1000 and spot < avg_strike / 5:
                    spot *= 10.0
                elif avg_strike > 5000 and spot < avg_strike / 5:
                    # Some might need even more scaling if multiple splits/dividends
                    # but usually it's a factor of 10 or similar.
                    # Best approach: find the strike that minimizes distance to spot*10
                    pass

            # We need a spot price. Without it we cannot calculate metrics.
            if spot == 0:
                pbar.update(1)
                continue

            expiries = sorted(day_df["expiry_date"].unique())
            if not expiries:
                pbar.update(1)
                continue

            near_exp = expiries[0]
            chain = day_df[day_df["expiry_date"] == near_exp]

            dte = (datetime.strptime(near_exp, "%Y-%m-%d") - datetime.strptime(tdate, "%Y-%m-%d")).days

            atm_strike = nearest_atm(spot, sym)

            # Look for LTP with a small search window if exact ATM is untraded
            def get_traded_ltp(center_strike, opt_type, chain_df):
                f_row = chain_df[(chain_df["strike"] == center_strike) & (chain_df["opt_type"] == opt_type)]
                if not f_row.empty and f_row["ltp"].values[0] > 0:
                    return f_row["ltp"].values[0]
                # Search nearby strikes
                nearby = chain_df[chain_df["opt_type"] == opt_type].copy()
                nearby["dist"] = (nearby["strike"] - center_strike).abs()
                nearby = nearby[nearby["ltp"] > 0].sort_values("dist")
                return nearby["ltp"].values[0] if not nearby.empty else 0

            atm_ce_ltp = get_traded_ltp(atm_strike, "CE", chain)
            atm_pe_ltp = get_traded_ltp(atm_strike, "PE", chain)

            # Spot change pct
            prev_spot = prev_spot_map.get(sym, spot)
            spot_change_pct = ((spot - prev_spot) / prev_spot * 100) if prev_spot > 0 else 0
            prev_spot_map[sym] = spot

            # 1. Chain Aggregates
            total_ce_oi = chain[chain["opt_type"] == "CE"]["open_interest"].sum()
            total_pe_oi = chain[chain["opt_type"] == "PE"]["open_interest"].sum()
            pcr_oi = total_pe_oi / max(1, total_ce_oi)

            total_ce_vol = chain[chain["opt_type"] == "CE"]["volume"].sum()
            total_pe_vol = chain[chain["opt_type"] == "PE"]["volume"].sum()
            pcr_vol = total_pe_vol / max(1, total_ce_vol)

            # Max pain - Optimized vectorized calculation (5-10x faster)
            strikes = sorted(chain["strike"].unique())
            pain_vals = []

            # Pre-filter CE and PE data for faster lookups
            ce_data = chain[chain["opt_type"] == "CE"][["strike", "open_interest"]].values
            pe_data = chain[chain["opt_type"] == "PE"][["strike", "open_interest"]].values

            for strike in strikes:
                # Vectorized calculation: CE losses for strikes above current
                ce_loss = ((ce_data[:, 0] > strike) * (ce_data[:, 0] - strike) * ce_data[:, 1]).sum()

                # Vectorized calculation: PE losses for strikes below current
                pe_loss = ((pe_data[:, 0] < strike) * (strike - pe_data[:, 0]) * pe_data[:, 1]).sum()

                pain_vals.append((ce_loss + pe_loss, strike))

            max_pain = min(pain_vals)[1] if pain_vals else atm_strike

            # 2. IV Reconstruct - ATM only (not per-strike, for speed)
            atm_ce_iv = compute_implied_volatility(atm_ce_ltp, spot, atm_strike, dte, "CE") or 0.0
            atm_pe_iv = compute_implied_volatility(atm_pe_ltp, spot, atm_strike, dte, "PE") or 0.0
            iv_skew = atm_pe_iv - atm_ce_iv
            avg_iv = (atm_ce_iv + atm_pe_iv) / 2.0

            # 2.5 OI Velocity & UOA (EOD Heuristic)
            atm_band_strikes = chain[(chain["strike"] >= spot * 0.985) & (chain["strike"] <= spot * 1.015)]
            
            top_ce_chg, top_pe_chg = 0, 0
            top_ce_strike, top_pe_strike = atm_strike, atm_strike
            avg_vol = 1
            
            if not atm_band_strikes.empty:
                ce_band = atm_band_strikes[atm_band_strikes["opt_type"] == "CE"]
                pe_band = atm_band_strikes[atm_band_strikes["opt_type"] == "PE"]
                
                if not ce_band.empty:
                    max_idx = ce_band["chg_in_oi"].abs().idxmax()
                    top_ce_chg = ce_band.loc[max_idx, "chg_in_oi"]
                    top_ce_strike = ce_band.loc[max_idx, "strike"]
                    
                if not pe_band.empty:
                    max_idx = pe_band["chg_in_oi"].abs().idxmax()
                    top_pe_chg = pe_band.loc[max_idx, "chg_in_oi"]
                    top_pe_strike = pe_band.loc[max_idx, "strike"]
                
                avg_vol = max(1, atm_band_strikes["volume"].mean())

            net_chg = top_ce_chg - top_pe_chg
            scale = max(abs(top_ce_chg), abs(top_pe_chg), 1)
            raw_vel_score = float(np.tanh(net_chg / scale)) if scale else 0.0
            
            ce_spike = abs(top_ce_chg) / avg_vol
            pe_spike = abs(top_pe_chg) / avg_vol
            
            is_uoa = max(ce_spike, pe_spike) >= 2.0
            
            uoa_side = None
            uoa_strike = None
            if is_uoa:
                uoa_side = "CE" if ce_spike > pe_spike else "PE"
                uoa_strike = top_ce_strike if uoa_side == "CE" else top_pe_strike

            vel_conf = min(0.95, (max(ce_spike, pe_spike) - 1.0) / 4.0) if max(ce_spike, pe_spike) > 1.0 else 0.1

            # 3. FAST GEX + Regime - vectorized, no IV per-strike needed
            # GEX = gamma * OI * spot^2 * 0.01
            # Use approximate gamma = N(d1)/spot/sigma/sqrt(T) with avg_iv for ATM band
            T = max(dte, 0.5) / 365.0
            sigma = max(avg_iv / 100.0, 0.05)  # convert % to decimal
            import math as _math
            
            net_gex = 0.0
            zero_gamma_level = atm_strike
            try:
                cum_gex = []
                for _, grp in chain.groupby("opt_type"):
                    is_ce = grp["opt_type"].iloc[0] == "CE"
                    for _, srow in grp.iterrows():
                        K = srow["strike"]
                        oi = srow["open_interest"]
                        if K <= 0 or oi <= 0: continue
                        d1 = (_math.log(spot / K) + (0.065 + 0.5 * sigma**2) * T) / (sigma * _math.sqrt(T))
                        gamma = _math.exp(-0.5 * d1**2) / (_math.sqrt(2 * _math.pi) * spot * sigma * _math.sqrt(T))
                        g = gamma * oi * spot**2 * 0.01
                        net_gex += g if is_ce else -g
                        cum_gex.append((K, g if is_ce else -g))
                # Approximate zero-gamma as weighted avg strike where gex sign flips
                if cum_gex:
                    cum_gex.sort(key=lambda x: x[0])
                    running = 0.0
                    zgl = atm_strike
                    for k, g in cum_gex:
                        prev = running
                        running += g
                        if prev * running < 0:  # sign flip
                            zgl = k
                    zero_gamma_level = zgl
            except Exception:
                pass

            # ── Rolling IV rank (252-bar percentile, per symbol) ─────────────
            iv_hist = iv_history_per_symbol.setdefault(sym, deque(maxlen=252))
            if iv_hist:
                iv_rank = float(np.mean(np.array(iv_hist) <= avg_iv) * 100)
            else:
                iv_rank = 50.0  # insufficient history; neutral default
            iv_hist.append(avg_iv)

            # Fast regime: derive from dte + OI concentration
            ce_oi_series = chain[chain["opt_type"] == "CE"]["open_interest"]
            pe_oi_series = chain[chain["opt_type"] == "PE"]["open_interest"]
            top_ce_conc = ce_oi_series.nlargest(3).sum() / max(ce_oi_series.sum(), 1)
            top_pe_conc = pe_oi_series.nlargest(3).sum() / max(pe_oi_series.sum(), 1)
            oi_conc = (top_ce_conc + top_pe_conc) / 2.0
            oi_concentration_ratio = oi_conc

            straddle_iv = avg_iv / 100.0

            if dte <= 2:
                regime = "EXPIRY"
            elif oi_conc > 0.70:
                regime = "PINNED"
            elif straddle_iv < 0.12:
                regime = "SQUEEZE"
            elif abs(pcr_oi - 1.0) > 0.4:
                regime = "TRENDING"
            else:
                regime = "NEUTRAL"

            # Align with analytics.py: negative skew (PE < CE IV) is BULLISH, positive skew is BEARISH
            if pcr_oi > 1.3 and iv_skew < -1.0:
                signal = "BULLISH"
            elif pcr_oi < 0.7 and iv_skew > 1.0:
                signal = "BEARISH"
            elif is_uoa and vel_conf > 0.4:
                # Institutional UOA detected - let it drive the signal
                signal = "BULLISH" if uoa_side == "CE" else "BEARISH"
            else:
                signal = "NEUTRAL"
            
            # Score logic: aligned with analytics.py compute_stock_score_v2 refinement
            score = 50
            if signal == "BULLISH":
                score = min(95, int(50 + (pcr_oi - 1.0) * 20 + (100 - iv_rank)/5 + (vel_conf * 20)))
            elif signal == "BEARISH":
                score = min(95, int(50 + (1.0 - pcr_oi) * 20 + (iv_rank/5) + (vel_conf * 20)))
            
            confidence = min(0.95, oi_conc if dte > 2 else 0.5)

            # Top pick: use UOA strike if available, otherwise ATM
            top_type = "CE" if signal == "BULLISH" else ("PE" if signal == "BEARISH" else None)
            top_str = uoa_strike if (is_uoa and uoa_side == top_type) else atm_strike
            
            if top_type:
                # Find LTP for the selected top_str
                top_pr = get_traded_ltp(top_str, top_type, chain)
            else:
                top_pr = 0
            oi_concentration_ratio = (top_ce_conc + top_pe_conc) / 2.0

            # NEXT DAY OUTCOME LABELLING
            nday = next_trading_day(datetime.strptime(tdate, "%Y-%m-%d").date())
            nday_str = nday.strftime("%Y-%m-%d")

            out_next = spot_history.get(nday_str)
            pick_pnl_next = 0
            trade_res = None

            if top_type and out_next:
                pick_ltp_next = price_lookup.get((nday_str, sym, top_str, top_type))
                
                if pick_ltp_next is not None:
                    if top_pr > 0:
                        pick_pnl_next = ((pick_ltp_next - top_pr) / top_pr) * 100

                    if pick_pnl_next >= 20: trade_res = "WIN"
                    elif pick_pnl_next <= -20: trade_res = "LOSS"
                    else: trade_res = "NEUTRAL"
                else:
                    trade_res = None # Data gap

            # Fill Snapshot Result
            snap = {
                "symbol": sym,
                "snapshot_time": f"{tdate} 15:30:00",
                "spot_price": spot,
                "spot_change_pct": round(spot_change_pct, 4),
                "total_ce_oi": total_ce_oi,
                "total_pe_oi": total_pe_oi,
                "pcr_oi": pcr_oi,
                "total_ce_vol": total_ce_vol,
                "total_pe_vol": total_pe_vol,
                "pcr_vol": pcr_vol,
                "atm_ce_iv": atm_ce_iv,
                "atm_pe_iv": atm_pe_iv,
                "iv_skew": iv_skew,
                "atm_ce_ltp": atm_ce_ltp,
                "atm_pe_ltp": atm_pe_ltp,
                "atm_strike": atm_strike,
                "dte": dte,
                "expiry_date": near_exp,
                "signal": signal,
                "score": score,
                "confidence": confidence,
                "ml_bullish_probability": 0.5, # Neutral default for historical EOD
                "regime": regime,
                "top_pick_type": top_type,
                "top_pick_strike": top_str,
                "top_pick_ltp": top_pr,
                "net_gex": round(net_gex, 2),
                "zero_gamma_level": round(zero_gamma_level, 2),
                "iv_rank": round(iv_rank, 1),
                "max_pain_strike": max_pain,
                "oi_concentration_ratio": round(oi_concentration_ratio, 4),
                "net_delta_flow": round((0.5 * total_ce_vol - 0.5 * total_pe_vol), 2),
                "oi_velocity_score": round(raw_vel_score, 4),
                "oi_velocity_conf": round(vel_conf, 4),
                "uoa_detected": int(is_uoa),
                "uoa_strike": uoa_strike,
                "uoa_side": uoa_side,
                "outcome_1h": None, "outcome_eod": spot, "outcome_next": out_next,
                "pick_ltp_1h": None, "pick_ltp_eod": top_pr,
                "pick_pnl_pct_1h": None, "pick_pnl_pct_eod": 0,
                "pick_pnl_pct_next": round(pick_pnl_next, 2),
                "trade_result": trade_res,
                "data_source": "EOD_HISTORICAL"
            }

            snapshots.append(snap)
            pbar.update(1)  # Update progress bar

    return pd.DataFrame(snapshots)

# ── DATA VALIDATION ──────────────────────────────────────────────────────────

def validate_snapshot(snapshot: dict) -> tuple[bool, list]:
    """
    Validate reconstructed snapshot data for quality and accuracy.
    Returns: (is_valid, list_of_errors)
    """
    errors = []

    # Critical field validation
    if snapshot.get('spot_price', 0) <= 0:
        errors.append("Invalid spot_price: must be > 0")

    # PCR validation (Put-Call Ratio should be reasonable)
    pcr_oi = snapshot.get('pcr_oi', 0)
    if not (0 <= pcr_oi <= 10):
        errors.append(f"Invalid pcr_oi: {pcr_oi} (should be 0-10)")

    # IV validation (Implied Volatility in percentage)
    atm_ce_iv = snapshot.get('atm_ce_iv', 0)
    atm_pe_iv = snapshot.get('atm_pe_iv', 0)
    if not (0 <= atm_ce_iv <= 500):
        errors.append(f"Invalid atm_ce_iv: {atm_ce_iv} (should be 0-500)")
    if not (0 <= atm_pe_iv <= 500):
        errors.append(f"Invalid atm_pe_iv: {atm_pe_iv} (should be 0-500)")

    # Score validation
    score = snapshot.get('score', 0)
    if not (0 <= score <= 100):
        errors.append(f"Invalid score: {score} (should be 0-100)")

    # Confidence validation
    confidence = snapshot.get('confidence', 0)
    if not (0 <= confidence <= 1):
        errors.append(f"Invalid confidence: {confidence} (should be 0-1)")

    # DTE validation (Days to Expiry)
    dte = snapshot.get('dte', 0)
    if not (0 <= dte <= 90):
        errors.append(f"Unusual dte: {dte} (typically 0-90 days)")

    # Top pick validation
    top_pick_ltp = snapshot.get('top_pick_ltp', 0)
    if top_pick_ltp < 0:
        errors.append(f"Invalid top_pick_ltp: {top_pick_ltp} (must be >= 0)")

    return (len(errors) == 0, errors)

def validate_data_batch(snapshots: pd.DataFrame) -> dict:
    """
    Validate a batch of snapshots and return quality report.
    """
    total = len(snapshots)
    if total == 0:
        return {"total": 0, "valid": 0, "invalid": 0, "error_summary": {}}

    valid_count = 0
    invalid_count = 0
    error_summary = {}

    for _, snap in snapshots.iterrows():
        is_valid, errors = validate_snapshot(snap.to_dict())
        if is_valid:
            valid_count += 1
        else:
            invalid_count += 1
            for error in errors:
                error_summary[error] = error_summary.get(error, 0) + 1

    return {
        "total": total,
        "valid": valid_count,
        "invalid": invalid_count,
        "validity_rate": round(valid_count / total * 100, 2) if total > 0 else 0,
        "error_summary": error_summary
    }

# ── LOAD DATABASE ────────────────────────────────────────────────────────────

def load_to_database(df: pd.DataFrame, db_path: str, replace=False):
    # Validate data quality before loading
    validation_report = validate_data_batch(df)
    logger.info(f"Data Validation: {validation_report['valid']}/{validation_report['total']} valid "
                f"({validation_report['validity_rate']}%)")

    if validation_report['invalid'] > 0:
        logger.warning(f"Found {validation_report['invalid']} invalid snapshots:")
        for error, count in list(validation_report['error_summary'].items())[:5]:  # Show top 5 errors
            logger.warning(f"  - {error}: {count} occurrences")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    if replace:
        cur.execute("DELETE FROM market_snapshots WHERE data_source='EOD_HISTORICAL'")

    df.to_sql("market_snapshots", conn, if_exists="append", index=False)

    wins = len(df[df["trade_result"] == "WIN"])
    losses = len(df[df["trade_result"] == "LOSS"])
    neutrals = len(df[df["trade_result"] == "NEUTRAL"])

    logger.info(f"Loaded {len(df)} rows into DB")
    logger.info(f"Wins: {wins} | Losses: {losses} | Neutrals: {neutrals}")
    conn.commit()
    conn.close()

def load_iv_history(df: pd.DataFrame, db_path: str):
    conn = sqlite3.connect(db_path)

    ivs = []
    for _, r in df.iterrows():
        dt = r["snapshot_time"].split()[0]
        aiv = (r["atm_ce_iv"] + r["atm_pe_iv"]) / 2
        ivs.append({"symbol": r["symbol"], "snap_date": dt, "iv": aiv})

    piv = pd.DataFrame(ivs)
    if piv.empty:
        conn.close()
        return

    piv = piv.drop_duplicates(subset=["symbol", "snap_date"])

    # Save to temp table and gracefully UPSERT
    piv.to_sql("iv_history_temp", conn, if_exists="replace", index=False)

    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO iv_history (symbol, snap_date, iv)
        SELECT symbol, snap_date, iv FROM iv_history_temp
    """)
    cur.execute("DROP TABLE iv_history_temp")

    conn.commit()
    conn.close()


def validate_data_quality(db_path: str):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM market_snapshots WHERE data_source='EOD_HISTORICAL'", conn)

    if df.empty:
        logger.info("No historical data to validate.")
        return

    logger.info(f"Data Quality Report: {len(df)} rows")
    avg_score = df["score"].mean()
    logger.info(f"Avg Score: {avg_score:.2f}")


# ── PARALLEL RECONSTRUCTION ──────────────────────────────────────────────────

import multiprocessing as mp
from functools import partial
from typing import List
import asyncio


def _reconstruct_day_features(snapshot_row: dict, analytics_module) -> dict:
    """
    Worker function — runs in separate process.
    Takes a raw EOD snapshot row, returns computed features.
    Must be top-level function (picklable for multiprocessing).
    """
    try:
        # Call existing compute_stock_score_v2 logic on this row
        score_data = analytics_module.compute_stock_score_v2(
            chain_data=snapshot_row["raw_chain"],
            spot=snapshot_row["spot_price"],
            regime=snapshot_row.get("regime", "TRENDING"),
        )
        return {
            "snapshot_id": snapshot_row["id"],
            "date": snapshot_row["date"],
            "weighted_score": score_data.get("score", 0),
            "gex": score_data.get("gex", {}),
            "iv_skew": score_data.get("iv_skew", 0),
            "pcr": score_data.get("pcr", 1),
            "regime": score_data.get("regime", "TRENDING"),
        }
    except Exception as e:
        return {"snapshot_id": snapshot_row.get("id", 0), "error": str(e)}


async def reconstruct_features_parallel(
    snapshot_rows: List[dict],
    workers: int = None,
    progress_callback=None
) -> List[dict]:
    """
    Replace the existing sequential for-loop with this.
    workers=None → uses CPU count automatically.
    Reduces 60min → ~8min on a 4-core machine.
    """
    if workers is None:
        workers = min(mp.cpu_count(), 8)
    
    if not snapshot_rows:
        return []
    
    # Import analytics module for workers
    import analytics
    
    worker_fn = partial(_reconstruct_day_features, analytics_module=analytics)
    
    loop = asyncio.get_event_loop()
    with mp.Pool(processes=workers) as pool:
        results = await loop.run_in_executor(
            None,
            lambda: pool.map(worker_fn, snapshot_rows)
        )
    
    errors = [r for r in results if "error" in r]
    if errors:
        logger.warning(f"[historical_loader] {len(errors)} rows failed reconstruction")
        for err in errors[:5]:  # Show first 5 errors
            logger.warning(f"  - Snapshot {err.get('snapshot_id', '?')}: {err.get('error', 'unknown')}")
    
    successful = [r for r in results if "error" not in r]
    
    if progress_callback:
        progress_callback(len(successful), len(snapshot_rows))
    
    return successful


# Backfill progress tracking for API
_backfill_progress = {"status": "idle", "processed": 0, "total": 0, "pct": 0, "errors": []}


def get_backfill_progress() -> dict:
    """Get current backfill progress."""
    return _backfill_progress.copy()


def reset_backfill_progress():
    """Reset backfill progress to idle state."""
    global _backfill_progress
    _backfill_progress = {"status": "idle", "processed": 0, "total": 0, "pct": 0, "errors": []}


async def run_backfill_with_progress(days: int = 252, db_path: str = None):
    """
    Run historical backfill with progress tracking.
    Called from the /api/backfill/start endpoint.
    """
    global _backfill_progress
    
    if db_path is None:
        db_path = CONFIG["db_path"]
    
    _backfill_progress = {"status": "running", "processed": 0, "total": days, "pct": 0, "errors": []}
    
    try:
        # Download spot prices
        _backfill_progress["status"] = "downloading_spots"
        spot_prices = download_spot_prices(
            CONFIG["symbols"], 
            CONFIG["start_date"], 
            CONFIG["end_date"], 
            CONFIG["data_dir"]
        )
        
        # Download bhavcopies
        _backfill_progress["status"] = "downloading_bhavcopies"
        download_bhavcopy_range(
            CONFIG["start_date"], 
            CONFIG["end_date"], 
            CONFIG["data_dir"]
        )
        
        # Process data
        _backfill_progress["status"] = "processing"
        df = merge_data_sources(
            os.path.join(CONFIG["data_dir"], "bhavcopies"),
            [],
            CONFIG["symbols"]
        )
        
        # Reconstruct features
        _backfill_progress["status"] = "reconstructing"
        out = reconstruct_features(df, spot_prices)
        
        _backfill_progress["processed"] = len(out)
        _backfill_progress["pct"] = 100
        
        # Load to database
        _backfill_progress["status"] = "loading_db"
        load_to_database(out, db_path)
        load_iv_history(out, db_path)
        
        _backfill_progress["status"] = "completed"
        logger.info(f"Backfill completed: {len(out)} snapshots processed")
        
    except Exception as e:
        _backfill_progress["status"] = "error"
        _backfill_progress["errors"].append(str(e))
        logger.error(f"Backfill failed: {e}")


# ── CLI ENTRY POINT ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["download", "load-kaggle", "process", "load-db", "full", "status"])
    parser.add_argument("--start", default=CONFIG["start_date"])
    parser.add_argument("--end", default=CONFIG["end_date"])
    parser.add_argument("--symbols", default=",".join(CONFIG["symbols"]))
    parser.add_argument("--file", help="Kaggle file path")
    parser.add_argument("--db", default=CONFIG["db_path"])

    args = parser.parse_args()
    syms = args.symbols.split(",")

    logger.info("NSE F&O HISTORICAL LOADER")

    # Ensure data directory exists
    os.makedirs(CONFIG["data_dir"], exist_ok=True)
    os.makedirs(os.path.join(CONFIG["data_dir"], "bhavcopies"), exist_ok=True)

    if args.cmd in ["download", "full"]:
        download_spot_prices(syms, args.start, args.end, CONFIG["data_dir"])
        download_bhavcopy_range(args.start, args.end, CONFIG["data_dir"])

    if args.cmd in ["process", "full"]:
        spot = download_spot_prices(syms, args.start, args.end, CONFIG["data_dir"])
        df = merge_data_sources(os.path.join(CONFIG["data_dir"], "bhavcopies"), [args.file] if args.file else [], syms)
        out = reconstruct_features(df, spot)
        out.to_csv(os.path.join(CONFIG["data_dir"], "reconstructed.csv"), index=False)

    if args.cmd in ["load-db", "full"]:
        recon_path = os.path.join(CONFIG["data_dir"], "reconstructed.csv")
        if not os.path.exists(recon_path):
            logger.error(f"❌ '{recon_path}' not found.")
            logger.error("Please run the 'process' command first to generate reconstructed features.")
            sys.exit(1)
            
        out = pd.read_csv(recon_path)
        load_to_database(out, args.db)
        load_iv_history(out, args.db)

    if args.cmd in ["status", "full"]:
        validate_data_quality(args.db)
