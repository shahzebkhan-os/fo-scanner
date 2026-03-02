import asyncio
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
import json

FO_STOCKS = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","ADANIENT","WIPRO",
    "AXISBANK","BAJFINANCE","HCLTECH","LT","KOTAKBANK","TATAMOTORS","MARUTI",
    "SUNPHARMA","ITC","ONGC","POWERGRID","NTPC","BPCL","GRASIM","TITAN",
    "INDUSINDBK","ULTRACEMCO","HEROMOTOCO","ASIANPAINT","MM","DRREDDY",
    "DIVISLAB","CIPLA","TECHM","TATASTEEL","BAJAJFINSV","NESTLEIND",
    "HINDALCO","COALINDIA","VEDL","JSWSTEEL","SAIL","APOLLOHOSP",
    "PIDILITIND","SIEMENS","HAVELLS","VOLTAS",
]
INDEX_SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "referer": "https://www.google.com/"
}

async def fetch_slug(client, symbol):
    if symbol == "NIFTY": return "nifty-50-share-price"
    if symbol == "BANKNIFTY": return "nifty-bank-share-price"
    if symbol == "FINNIFTY": return "nifty-fin-service-share-price"
    
    url = f"https://www.indmoney.com/search?q={symbol}"
    try:
        r = await client.get(url, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/stocks/" in href and "-share-price" in href:
                    slug = href.split("/stocks/")[-1].split("?")[0].strip("/")
                    return slug
    except Exception as e:
        print(f"Error {symbol}: {e}")
    return ""

async def main():
    slug_map = {}
    async with AsyncSession(impersonate="chrome120", headers=HEADERS) as client:
        # Test just one
        print("Testing HDFCBANK...")
        s = await fetch_slug(client, "HDFCBANK")
        print("HDFCBANK ->", s)
        
        if not s:
            print("Failed to find via search HTML.")
            return

        for symbol in FO_STOCKS:
            slug = await fetch_slug(client, symbol)
            if slug:
                slug_map[symbol] = slug
            print(f"{symbol} -> {slug}")
            await asyncio.sleep(0.5)
            
    # Add indices
    slug_map["NIFTY"] = "nifty-50-share-price"
    slug_map["BANKNIFTY"] = "nifty-bank-share-price"
    slug_map["FINNIFTY"] = "nifty-fin-service-share-price"
    
    with open("slugs.json", "w") as f:
        json.dump(slug_map, f, indent=2)

asyncio.run(main())
