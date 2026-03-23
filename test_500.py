import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath("."))
import backend.main as b_main
from backend.cache import cache

async def run():
    print("Testing _do_full_scan with RBLBANK...")
    await cache.connect()
    b_main.all_symbols = ["RBLBANK"]
    res = await b_main._do_full_scan(1)
    print("Test complete.")

if __name__ == "__main__":
    asyncio.run(run())
