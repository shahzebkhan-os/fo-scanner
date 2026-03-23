import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath("."))
import backend.main as b_main
from backend.fo_trades import run_pipeline
from backend.suggestions import generate_suggestions

async def run():
    print("Fetching scan_all...")
    # we don't start redis for test
    res = await b_main.scan_all(limit=5)
    print("Fetching suggestions...")
    sug = generate_suggestions(res)
    print("Running pipeline...")
    trades = run_pipeline(res, sug)
    print(f"Pipeline succeeded! {len(trades)} trades generated.")

if __name__ == "__main__":
    asyncio.run(run())
