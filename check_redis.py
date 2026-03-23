import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.abspath("."))
from backend.cache import cache

async def run():
    await cache.connect()
    if cache._redis is None:
        print("Redis not available.")
        return

    key = "fo_scanner:fetch_nse_chain:FINNIFTY"
    val = await cache._redis.get(key)
    if val:
        try:
            cj = json.loads(val)
            data = cj.get("records", {}).get("data", [])
            print(f"Type of data from Redis: {type(data)}")
            if isinstance(data, dict):
                print(f"It's a dict! Keys: {list(data.keys())[:5]}")
            elif isinstance(data, list):
                print(f"It's a list! First item type: {type(data[0]) if data else 'empty'}")
                if data and isinstance(data[0], str):
                    print(f"First string item: {data[0]}")
        except Exception as e:
            print(f"Failed to parse Redis: {e}")
    else:
        print("No cache entry found in Redis for FINNIFTY.")

if __name__ == "__main__":
    asyncio.run(run())
