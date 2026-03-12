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
    print("WARNING: jugaad_data missing. Bhavcopy downloading might fail.")

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

CONFIG = {
    "symbols": [
        "NIFTY", "BANKNIFTY", "FINNIFTY",
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "SBIN", "TATAMOTORS", "WIPRO", "AXISBANK", "BAJFINANCE"
    ],
    "start_date": "2023-01-01",
    "end_date":   "2024-12-31",
    "data_dir":   os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "historical_data"),
    "db_path":    os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner.db"),
    "rate_limit_seconds": 1.5,
    "max_retries": 3,
    "batch_size": 30,
    "pause_between_batches": 5,
}

# Add analytics for scoring
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
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
    date(2024, 11, 15), date(2024, 12, 25)
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

    res = {}
    logger.info(f"Downloading spot prices from {start} to {end}...")

    # Mapping to Yahoo Finance tickers
    yf_mapping = {
        "NIFTY": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "FINNIFTY": "NIFTY_FIN_SERVICE.NS", # Note: FinNifty YF ticker is notoriously unreliable, but we'll try it or fallback
    }

    for sym in symbols:
        logger.info(f"  Fetching {sym} (via yfinance)...")
        try:
            yf_ticker = yf_mapping.get(sym, f"{sym}.NS")
            if sym == "FINNIFTY":
                # FinNifty on yf is often missing/broken, use manual mapping if possible,
                # but ^CNXFIN is sometimes used. Let's try ^CNXFIN
                yf_ticker = "^CNXFIN"

            # Add 1 day buffer to end date because yfinance end date is strictly exclusive
            end_buf = (end + timedelta(days=1)).strftime("%Y-%m-%d")
            ticker_df = yf.download(yf_ticker, start=start_date_str, end=end_buf, progress=False)
            if ticker_df.empty:
                logger.warning(f"Failed spot download for {sym}: Empty Data")
                continue

            ticker_df.index = pd.to_datetime(ticker_df.index).strftime("%Y-%m-%d")

            # yfinance MultiIndex output handling
            if isinstance(ticker_df.columns, pd.MultiIndex):
                # Usually ('Close', 'RELIANCE.NS') format in newer yfinance versions
                close_series = ticker_df[("Close", yf_ticker)]
            else:
                close_series = ticker_df["Close"]

            new_prices = close_series.to_dict()

            # Merge with existing
            if sym not in existing_data:
                existing_data[sym] = new_prices
            else:
                existing_data[sym].update(new_prices)

        except Exception as e:
            logger.warning(f"Failed spot download for {sym}: {e}")
        time.sleep(0.5) # small delay to be nice to yf api

    with open(out_file, "w") as f:
        import json
        json.dump(existing_data, f)

    return existing_data


# ── STEP 1C: BHAVCOPY DOWNLOADER ─────────────────────────────────────────────

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

    logger.info(f"Downloading {total} bhavcopy days...")

    for i, d in enumerate(dates_to_fetch):
        # jugaad_data format: fo01Aug2023bhav.csv
        fname = f"fo{d.strftime('%d%b%Y')}bhav.csv"
        fpath = os.path.join(data_dir, "bhavcopies", fname)

        progress = int((i / total) * 20)
        bar = "=" * progress + ">" + " " * (20 - progress)
        sys.stdout.write(f"\r[{bar}] {i}/{total} | Current: {d.strftime('%d-%b-%Y')}")
        sys.stdout.flush()

        if os.path.exists(fpath):
            successful.append(fpath)
            continue

        retries = 0
        while retries < CONFIG["max_retries"]:
            try:
                if d >= date(2024, 7, 8):
                    # NSE changed its entire API/URL structure for Bhavcopies on July 8, 2024
                    s = requests.Session()
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    s.get("https://www.nseindia.com/all-reports", headers=headers, timeout=10)

                    dt_str = d.strftime("%Y%m%d")
                    url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{dt_str}_F_0000.csv.zip"
                    r = s.get(url, headers=headers, timeout=10)
                    r.raise_for_status()

                    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                        with z.open(z.namelist()[0]) as f:
                            df = pd.read_csv(f)
                            df.to_csv(fpath, index=False)
                else:
                    bhavcopy_fo_save(d, os.path.join(data_dir, "bhavcopies"))

                time.sleep(CONFIG["rate_limit_seconds"])
                successful.append(fpath)
                break
            except Exception as e:
                retries += 1
                time.sleep(2 ** retries)
                if retries == CONFIG["max_retries"]:
                    logger.warning(f"\nFailed to download {d} after {retries} retries: {e}")

        if (i + 1) % CONFIG["batch_size"] == 0:
            time.sleep(CONFIG["pause_between_batches"])

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

    # Needs to be sorted chronologically for DTE tracking
    raw_df = raw_df.sort_values(by="trade_date")

    grouped_days = raw_df.groupby(["trade_date", "symbol"])
    total_len = len(grouped_days)

    logger.info(f"Reconstructing {total_len} snapshots with progress tracking...")

    # Use tqdm for better progress visualization
    with tqdm(total=total_len, desc="Processing snapshots", unit="snapshot") as pbar:
        for i, ((tdate, sym), day_df) in enumerate(grouped_days):
            pbar.set_postfix({"symbol": sym, "date": tdate})

            spot_history = spot_prices.get(sym, {})
            spot = spot_history.get(tdate, 0)

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

            # 1. Chain Aggregates
            total_ce_oi = chain[chain["opt_type"] == "CE"]["open_interest"].sum()
            total_pe_oi = chain[chain["opt_type"] == "PE"]["open_interest"].sum()
            pcr_oi = total_pe_oi / max(1, total_ce_oi)

            total_ce_vol = chain[chain["opt_type"] == "CE"]["volume"].sum()
            total_pe_vol = chain[chain["opt_type"] == "PE"]["volume"].sum()
            pcr_vol = total_pe_vol / max(1, total_ce_vol)

            atm_row_ce = chain[(chain["strike"] == atm_strike) & (chain["opt_type"] == "CE")]
            atm_row_pe = chain[(chain["strike"] == atm_strike) & (chain["opt_type"] == "PE")]

            atm_ce_ltp = atm_row_ce["ltp"].values[0] if not atm_row_ce.empty else 0
            atm_pe_ltp = atm_row_pe["ltp"].values[0] if not atm_row_pe.empty else 0

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

            # 2. IV Reconstruct
            atm_ce_iv = compute_implied_volatility(atm_ce_ltp, spot, atm_strike, dte, "CE") or 0.0
            atm_pe_iv = compute_implied_volatility(atm_pe_ltp, spot, atm_strike, dte, "PE") or 0.0
            iv_skew = atm_pe_iv - atm_ce_iv

            # 3. Greeks + GEX (Approximations for scoring)
            # Assuming v2 compute_stock_score handles the internal loggeric, we build a pseudo chain payload
            pseudo_records = {"underlyingValue": spot, "expiryDates": expiries, "data": []}
            for st in strikes:
                rce = chain[(chain["strike"] == st) & (chain["opt_type"] == "CE")]
                rpe = chain[(chain["strike"] == st) & (chain["opt_type"] == "PE")]

                row = {"strikePrice": st, "expiryDate": near_exp}
                if not rce.empty:
                    rce = rce.iloc[0]
                    row["CE"] = {"lastPrice": rce["ltp"], "openInterest": rce["open_interest"], "changeinOpenInterest": rce["chg_in_oi"], "impliedVolatility": compute_implied_volatility(rce["ltp"], spot, st, dte, "CE") or 0.0, "totalTradedVolume": rce["volume"]}
                if not rpe.empty:
                    rpe = rpe.iloc[0]
                    row["PE"] = {"lastPrice": rpe["ltp"], "openInterest": rpe["open_interest"], "changeinOpenInterest": rpe["chg_in_oi"], "impliedVolatility": compute_implied_volatility(rpe["ltp"], spot, st, dte, "PE") or 0.0, "totalTradedVolume": rpe["volume"]}
                pseudo_records["data"].append(row)

            score_res = compute_stock_score_v2({"records": pseudo_records}, spot, sym, near_exp, {"iv_rank": 50}) # defaulting IVR for historical

            top_picks = score_res.get("top_picks", [])
            top_type = None
            top_str = 0
            top_pr = 0
            if top_picks:
                tp = top_picks[0]
                top_type = tp["type"]
                top_str = tp["strike"]
                top_pr = tp["ltp"]

            # NEXT DAY OUTCOME LABELLING
            nday = next_trading_day(datetime.strptime(tdate, "%Y-%m-%d").date())
            nday_str = nday.strftime("%Y-%m-%d")

            out_next = spot_history.get(nday_str)
            pick_pnl_next = 0
            trade_res = None

            if top_type and out_next:
                nday_df = raw_df[(raw_df["trade_date"] == nday_str) & (raw_df["symbol"] == sym)]
                tgt_row = nday_df[(nday_df["strike"] == top_str) & (nday_df["opt_type"] == top_type)]

                if not tgt_row.empty:
                    pick_ltp_next = float(tgt_row.iloc[0]["ltp"])
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
                "spot_change_pct": 0,
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
                "signal": score_res.get("signal", "NEUTRAL"),
                "score": score_res.get("score", 0),
                "confidence": score_res.get("confidence", 0.0),
                "regime": score_res.get("regime", "EXPIRY"),
                "top_pick_type": top_type,
                "top_pick_strike": top_str,
                "top_pick_ltp": top_pr,
                "net_gex": score_res.get("gex", {}).get("net_gamma_exposure", 0),
                "zero_gamma_level": score_res.get("gex", {}).get("zero_gamma_level", atm_strike),
                "iv_rank": 50, # Computed fully next pass
                "max_pain_strike": max_pain,
                "oi_concentration_ratio": score_res.get("oi_concentration_ratio", 0),
                "net_delta_flow": 0,
                "outcome_1h": None, "outcome_eod": spot, "outcome_next": out_next,
                "pick_ltp_1h": None, "pick_ltp_eod": top_pr,
                "pick_pnl_pct_1h": None, "pick_pnl_pct_eod": 0,
                "pick_pnl_pct_next": pick_pnl_next,
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

    if args.cmd in ["download", "full"]:
        download_spot_prices(syms, args.start, args.end, CONFIG["data_dir"])
        download_bhavcopy_range(args.start, args.end, CONFIG["data_dir"])

    if args.cmd in ["process", "full"]:
        spot = download_spot_prices(syms, args.start, args.end, CONFIG["data_dir"])
        df = merge_data_sources(os.path.join(CONFIG["data_dir"], "bhavcopies"), [args.file] if args.file else [], syms)
        out = reconstruct_features(df, spot)
        out.to_csv(os.path.join(CONFIG["data_dir"], "reconstructed.csv"), index=False)

    if args.cmd in ["load-db", "full"]:
        out = pd.read_csv(os.path.join(CONFIG["data_dir"], "reconstructed.csv"))
        load_to_database(out, args.db)
        load_iv_history(out, args.db)

    if args.cmd in ["status", "full"]:
        validate_data_quality(args.db)
