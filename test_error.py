import sys
import os
import asyncio
import traceback

sys.path.insert(0, os.path.abspath("."))
from backend.main import scan_all

async def run():
    try:
        print("Running scan_all...")
        res = await scan_all()
        print("Success!")
    except Exception as e:
        print("EXCEPTION CAUGHT IN SCAN:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run())
