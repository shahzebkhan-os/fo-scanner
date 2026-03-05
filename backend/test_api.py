import asyncio, os, httpx, sys
sys.path.insert(0, os.path.dirname(__file__))
from main import INDSTOCKS_TOKEN

async def test_search():
    headers = {"Authorization": f"Bearer {INDSTOCKS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://api.indstocks.com/v1/market/instruments",
            params={"search": "SBIN", "exchange": "NFO"},
            headers=headers,
        )
        print("QUERY: 'SBIN'")
        data = r.json().get("data", [])
        for d in data[:10]:
            print(f"  - {d.get('name')} | {d.get('scripCode')} | type: {d.get('instrumentType')} | strike: {d.get('strikePrice')} | expiry: {d.get('expiry')}")

if __name__ == "__main__":
    asyncio.run(test_search())
