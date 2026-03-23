import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath("."))
from backend.data_source import fetch_nse_chain
from backend.constants import INDEX_SYMBOLS, FO_STOCKS

async def process(symbol):
    res = await fetch_nse_chain(symbol)
    data = res.get("records", {}).get("data", [])
    if isinstance(data, list):
        for idx, row in enumerate(data):
            if isinstance(row, str):
                print(f"FOUND STRING IN {symbol} AT INDEX {idx}: {row}")
    elif isinstance(data, dict):
        print(f"FOUND DICT DATA IN {symbol}: {list(data.keys())}")

async def run():
    print("Checking all symbols for string data...")
    all_symbols = INDEX_SYMBOLS + FO_STOCKS
    await asyncio.gather(*[process(s) for s in all_symbols])
    print("Done checking.")

if __name__ == "__main__":
    asyncio.run(run())
